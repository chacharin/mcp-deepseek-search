# mcp-deepseek-search

[English](README.md) | **ภาษาไทย**

MCP server ที่ให้เอเจนต์ AI ค้นหาเว็บและอ่านหน้าเว็บผ่าน [DeepSeek Search & Fetch API](https://api-docs.deepseek.com/guides/search/)
ทำงานแบบ streamable HTTP (`http://<host>:8807/mcp`) และบันทึกค่าใช้จ่ายกับเวลาของทุกการเรียกไว้ให้ส่งออกไปวิจัยต่อได้

## เครื่องมือ

| เครื่องมือ | ทำอะไร | สวิตช์ใน .env |
|---|---|---|
| `deepseek_search` | ค้นหาเว็บ ได้รายการผลลัพธ์ แต่ละรายการมีชื่อ URL วันที่เผยแพร่ ความน่าเชื่อถือของแหล่ง (authority 0–4) คะแนนความเกี่ยวข้อง (relevance 0–3) และสรุปเนื้อหา | `ENABLE_DEEPSEEK_SEARCH` |
| `deepseek_fetch` | อ่านหน้าเว็บเป็น Markdown หน้าที่ยาวจะแสดงทีละช่วงและบอกค่า `start` สำหรับอ่านช่วงถัดไป | `ENABLE_DEEPSEEK_FETCH` |

ไม่มี AI สรุปคำตอบให้ เอเจนต์เป็นผู้อ่านผลแล้วสรุปเอง จึงควบคุมการอ้างอิงแหล่งได้เต็มที่

### พารามิเตอร์ของ `deepseek_search`

| พารามิเตอร์ | ความหมาย |
|---|---|
| `query` (จำเป็น) | คำค้น ใส่ operator ได้ เช่น `"วลีตรงตัว"` หรือ `-คำที่ไม่ต้องการ` |
| `count` | จำนวนผลลัพธ์ 1–50 (ค่าเริ่มต้น `DEFAULT_COUNT`) |
| `sites` / `exclude_sites` | ค้นเฉพาะ หรือตัดเว็บไซต์ที่ระบุ (กลายเป็น `site:a OR site:b` และ `-site:c`) |
| `language` | จำกัดภาษา เช่น `th` หรือ `th,en` ไม่ส่งหรือเว้นว่าง (`""`) = ไม่จำกัดภาษา ซึ่งเป็นค่าเริ่มต้น |
| `recency` | `day` `week` `month` `year` (แปลงเป็น `after:` อัตโนมัติ) |
| `after` / `before` | ช่วงวันที่เผยแพร่ (`YYYY` หรือ `YYYY-MM-DD`) |
| `min_score` | ตัดผลที่คะแนนความเกี่ยวข้องต่ำกว่านี้ (0–3) |
| `with_content` | แนบเนื้อหาของแต่ละหน้า (ใช้ token มากขึ้น) |
| `question` | คำถามเดิมของผู้ใช้ ช่วยให้ DeepSeek จัดอันดับได้ตรงขึ้น |

คำค้นรวมตัวกรองทั้งหมดต้องยาวไม่เกิน 128 ตัวอักษร (ข้อจำกัดของ API) หากเกิน server จะบอกเอเจนต์ให้ย่อโดยไม่ส่งไปที่ DeepSeek

### พารามิเตอร์ของ `deepseek_fetch`

`url` (จำเป็น), `max_chars` (1,000–100,000 ค่าเริ่มต้น `FETCH_MAX_CHARS`), `start` (อ่านต่อจากตัวอักษรที่เท่าไร)

## การทำงาน

```
เอเจนต์ (Hermes ฯลฯ) ──MCP──▶ mcp-deepseek-search ──HTTPS──▶ api.deepseek.com/v1/tools/{search,fetch}
                                  │
                                  └── usage/*.jsonl ──GET /usage──▶ collector / งานวิจัย
```

- API key อยู่ใน server นี้เท่านั้น เอเจนต์ไม่เห็น key
- HTTP 408, 429, 5xx และเครือข่ายขัดข้อง จะลองใหม่ตาม `RETRIES` ข้อผิดพลาดอื่นส่งกลับเป็นคำอธิบายสั้น ๆ เช่น 402 = ยอดเงินหมด
- ตัด Markdown escape (`\|`, `\-` ฯลฯ) และหัวข้อที่ซ้ำกับชื่อเรื่องออก เพื่อประหยัด token ของเอเจนต์
- คิดเงินต่อครั้งที่สำเร็จ 0.00075 USD (ค้นแล้วไม่พบผล หรือดึงหน้าไม่สำเร็จ ไม่คิดเงิน)

## ติดตั้ง

ต้องมี Docker และ docker network ที่ใช้ร่วมกับเอเจนต์

```bash
docker network create agent_network
```

```bash
cp .env.example .env
```

แก้ `DEEPSEEK_API_KEY` ใน `.env` เป็น key จาก https://platform.deepseek.com (บัญชีต้องมียอดเงิน) แล้วสั่ง

```bash
docker compose up -d --build
```

```bash
curl http://localhost:8807/health
```

`"ok": true` หมายถึงตั้ง key แล้วและอ่านสวิตช์ได้ครบ (health ไม่เรียก DeepSeek จึงไม่เสียเงิน)

## เชื่อมกับเอเจนต์

Hermes (`config.yaml` ของ profile)

```yaml
mcp_servers:
  deepseek_search:
    url: http://mcp-deepseek-search:8000/mcp      # จากภายใน agent_network
    timeout: 120
    # headers: {Authorization: "Bearer <MCP_AUTH_TOKEN>"}   # เมื่อตั้ง MCP_AUTH_TOKEN
```

client อื่นที่อยู่นอก docker ใช้ `http://localhost:8807/mcp` ทดสอบด้วย MCP Inspector ได้

```bash
npx @modelcontextprotocol/inspector
```

เลือก Transport = Streamable HTTP, URL = `http://localhost:8807/mcp`

## เปิด/ปิดเครื่องมือทีละตัว

ตั้ง `ENABLE_DEEPSEEK_SEARCH` และ `ENABLE_DEEPSEEK_FETCH` ใน `.env` เป็น `true` หรือ `false`
(รับ `1/0`, `yes/no`, `on/off` ด้วย ค่าอื่นจะถือว่าเปิดและแจ้งใน `/health`)
เครื่องมือที่ปิดจะไม่อยู่ในรายการเครื่องมือเลย จึงไม่เสีย token ค่าคำอธิบาย เปลี่ยนแล้วสั่ง `docker compose up -d` และรีสตาร์ตเอเจนต์ (หรือ `/reload-mcp`)

## ข้อมูลการใช้งาน (`GET /usage`)

ทุกการเรียกบันทึกเป็น JSONL ใน volume `usage` ตาม schema `harness-usage/1` (ไม่มีคำค้นหรือเนื้อหา มีแต่ตัวเลข)

| kind | หนึ่งระเบียนต่อ | ข้อมูลหลัก |
|---|---|---|
| `search_call` / `fetch_call` | การเรียก DeepSeek หนึ่งครั้ง | `duration_s`, `cost_usd`, `detail.http_status`, `attempts`, `billable`, `results`, `kept`, `content_chars` |
| `mcp_tool` | การเรียกเครื่องมือหนึ่งครั้ง | เวลารวม ค่าใช้จ่ายรวม ตัวกรองที่ใช้ (จำนวน ไม่ใช่ค่า) |

ระเบียนของการเรียกเดียวกันใช้ `request_id` ร่วมกัน กรองช่วงเวลาได้ด้วย `?since=<epoch>&until=<epoch>&limit=<n>`
ปิดการบันทึกได้ด้วย `USAGE_LOG=false`

## ปรับแต่ง

ค่าทั้งหมดอธิบายไว้ใน [.env.example](.env.example) เช่น `DEFAULT_COUNT`, `SUMMARY_CHARS`, `CONTENT_CHARS`, `FETCH_MAX_CHARS`,
`LOCALIZATION_IP` (ให้ผลเหมาะกับพื้นที่), `SEARCH_TIMEOUT_SECONDS`, `FETCH_TIMEOUT_SECONDS`, `RETRIES`, `PRICE_PER_REQUEST_USD`
และพอร์ต `PUBLISH_PORT` (ค่าเริ่มต้น 8807)

## ความปลอดภัย

- อย่า commit `.env` (อยู่ใน `.gitignore` แล้ว)
- เมื่อเปิดพอร์ตให้เครื่องอื่นเข้าถึง (`PUBLISH_ADDR=0.0.0.0`) ทุกคนในเครือข่ายใช้ยอดเงิน DeepSeek ของคุณได้
  ให้ตั้ง `MCP_AUTH_TOKEN` หรือใช้ `PUBLISH_ADDR=127.0.0.1`
- `/health` เปิดเสมอและไม่เปิดเผย key

## พัฒนาต่อ

```bash
uv sync
```

```bash
uv run pytest -q
```

เทสต์ใช้ DeepSeek API จำลอง จึงไม่เสียเงิน โครงสร้างโค้ด: `app/config.py` (ตั้งค่า), `app/deepseek.py` (เรียก API และจัดรูปข้อความ),
`app/server.py` (เครื่องมือ MCP, `/health`, `/usage`), `app/usage.py` (บันทึกการใช้งาน)

ใช้ร่วมกับ [osint-harness-profile](https://github.com/chacharin/osint-harness-profile) ได้

## License

MIT
