# mcp-deepseek-search

[English](README.md) | **ภาษาไทย**

[MCP](https://modelcontextprotocol.io) server ที่ให้เอเจนต์และผู้ช่วย AI มีเครื่องมือ 2 อย่าง คือ **ค้นหาเว็บ** และ **อ่านหน้าเว็บ**
โดยใช้ [DeepSeek Search & Fetch API](https://api-docs.deepseek.com/guides/search/)

ใช้ได้กับ MCP client ทุกตัวที่รองรับ streamable HTTP เช่น Claude Code, Claude Desktop, VS Code, Cursor หรือเอเจนต์ที่คุณเขียนเอง
API key ของ DeepSeek เก็บอยู่ที่ server นี้เท่านั้น และทุกการเรียกจะถูกบันทึกเวลากับค่าใช้จ่ายไว้ จึงรู้เสมอว่าเอเจนต์ใช้เงินไปเท่าไร

- [ได้อะไรบ้าง](#ได้อะไรบ้าง)
- [เครื่องมือ](#เครื่องมือ)
- [การทำงาน](#การทำงาน)
- [เริ่มใช้งานด้วย Docker](#เริ่มใช้งานด้วย-docker)
- [รันโดยไม่ใช้ Docker](#รันโดยไม่ใช้-docker)
- [เชื่อมกับ MCP client](#เชื่อมกับ-mcp-client)
- [เปิด/ปิดเครื่องมือทีละตัว](#เปิดปิดเครื่องมือทีละตัว)
- [ข้อมูลการใช้งานและค่าใช้จ่าย](#ข้อมูลการใช้งานและค่าใช้จ่าย)
- [การตั้งค่าทั้งหมด](#การตั้งค่าทั้งหมด)
- [ความปลอดภัย](#ความปลอดภัย)
- [แก้ปัญหา](#แก้ปัญหา)

## ได้อะไรบ้าง

- **ผลค้นหาที่เอเจนต์ประเมินได้** ทุกรายการมีวันที่เผยแพร่ คะแนนความน่าเชื่อถือของแหล่ง (0–4) และคะแนนความเกี่ยวข้อง (0–3)
  เอเจนต์จึงเลือกแหล่งที่ใหม่และน่าเชื่อถือ และข้ามผลที่ไม่ตรงได้
- **ตัวกรองการค้นหาเป็นพารามิเตอร์** เลือกเว็บไซต์ที่ต้องการหรือไม่ต้องการ ภาษา ความใหม่ หรือช่วงวันที่ได้ server แปลงเป็น operator ของ DeepSeek ให้
- **อ่านหน้ายาวทีละช่วง** หน้าที่ยาวจะส่งกลับเป็นช่วง พร้อมบอกตำแหน่งของช่วงถัดไป context ของเอเจนต์จึงไม่เต็มเพราะหน้าเดียว
- **ไม่มี AI สรุปคำตอบให้** server ส่งแหล่งข้อมูล ไม่ใช่คำตอบที่โมเดลอื่นเขียน เอเจนต์ของคุณอ่านแล้วเขียนคำตอบและอ้างอิงเอง
- **ประหยัด token** ตัด Markdown escape และหัวข้อสรุปที่ซ้ำกับชื่อเรื่องออกก่อนส่งให้เอเจนต์
- **บันทึกเวลาและค่าใช้จ่าย** หนึ่งบรรทัด JSON ต่อการเรียก อ่านได้ที่ `GET /usage` มีแต่ตัวเลข ไม่มีคำค้นหรือเนื้อหาหน้าเว็บ
- **เปิด/ปิดเครื่องมือทีละตัว** ปิดใน `.env` แล้วเครื่องมือนั้นจะหายไปจากรายการเครื่องมือของ client

## เครื่องมือ

| เครื่องมือ | ทำอะไร | สวิตช์ใน .env |
|---|---|---|
| `deepseek_search` | ค้นหาเว็บ แต่ละรายการมีชื่อ URL ชื่อเว็บไซต์ วันที่เผยแพร่ ความน่าเชื่อถือ ความเกี่ยวข้อง และสรุปเนื้อหา | `ENABLE_DEEPSEEK_SEARCH` |
| `deepseek_fetch` | อ่านหน้าเว็บหนึ่งหน้าเป็น Markdown หน้าที่ยาวจะส่งกลับทีละช่วง | `ENABLE_DEEPSEEK_FETCH` |

### `deepseek_search`

| พารามิเตอร์ | ชนิด | ค่าเริ่มต้น | ความหมาย |
|---|---|---|---|
| `query` | ข้อความ | (จำเป็น) | คำค้น ใส่ operator ได้ เช่น `"วลีตรงตัว"` หรือ `-คำที่ไม่ต้องการ` |
| `count` | 1–50 | `DEFAULT_COUNT` (10) | จำนวนผลลัพธ์ ราคาเท่าเดิมไม่ว่าจะขอกี่รายการ แต่ยิ่งมากยิ่งใช้ token ของเอเจนต์ |
| `sites` | รายการ | `[]` | ค้นเฉพาะเว็บไซต์เหล่านี้ เช่น `["who.int", "moph.go.th"]` (กลายเป็น `site:who.int OR site:moph.go.th`) |
| `exclude_sites` | รายการ | `[]` | ตัดเว็บไซต์เหล่านี้ออก (กลายเป็น `-site:example.com`) |
| `language` | ข้อความ | `""` (ทุกภาษา) | จำกัดภาษาของผลลัพธ์ เช่น `th` หรือ `th,en` ไม่ส่งหรือเว้นว่าง = ไม่จำกัดภาษา |
| `recency` | `day` `week` `month` `year` | `""` (ทุกช่วงเวลา) | เฉพาะหน้าที่เผยแพร่ภายในช่วงนั้น (แปลงเป็น `after:`) |
| `after` / `before` | `YYYY` หรือ `YYYY-MM-DD` | `""` | ช่วงวันที่เผยแพร่ ถ้าระบุทั้ง `after` และ `recency` จะใช้ `after` |
| `min_score` | 0–3 | `0` | ตัดผลที่คะแนนความเกี่ยวข้องต่ำกว่านี้ ตั้งแต่ 1.5 ขึ้นไปถือว่าตรงดี |
| `with_content` | true / false | `false` | แนบเนื้อหาของแต่ละหน้า (ตัดตาม `CONTENT_CHARS`) ใช้ token มากขึ้นมาก |
| `question` | ข้อความ | `""` | คำถามเดิมของผู้ใช้ ช่วยให้ DeepSeek จัดอันดับผลได้ตรงขึ้น |

คำค้นรวมตัวกรองทั้งหมดต้องยาวไม่เกิน **128 ตัวอักษร** (ข้อจำกัดของ API) หากเกิน server จะไม่เรียก DeepSeek (จึงไม่เสียเงิน)
และบอกเอเจนต์ให้ย่อคำค้นหรือลดจำนวนเว็บไซต์

ตัวอย่างข้อความที่เอเจนต์ได้รับ:

```
Found 2 search results for: นโยบายพลังงานทดแทน site:energy.go.th after:2026-01-01

[1] แผนพลังงานชาติ 2026
URL: https://www.energy.go.th/...
กระทรวงพลังงาน · published 2026-03-14 · authority 4/4 · relevance 2.41/3
คณะรัฐมนตรีเห็นชอบแผนพลังงานชาติ ...

[2] ...
```

### `deepseek_fetch`

| พารามิเตอร์ | ชนิด | ค่าเริ่มต้น | ความหมาย |
|---|---|---|---|
| `url` | ข้อความ | (จำเป็น) | ที่อยู่ที่ขึ้นต้นด้วย `http://` หรือ `https://` |
| `max_chars` | 1,000–100,000 | `FETCH_MAX_CHARS` (20,000) | จำนวนตัวอักษรสูงสุดที่ส่งกลับในครั้งนี้ |
| `start` | ตัวเลข | `0` | อ่านต่อจากตัวอักษรที่เท่าไร |

เมื่อหน้ายาวกว่า `max_chars` คำตอบจะขึ้นต้นด้วย
`Showing characters 0-20000 of 54210 - call again with start=20000 for the rest` เอเจนต์เรียกอีกครั้งด้วย `start` นั้นเพื่ออ่านต่อ
การเรียกแต่ละครั้งคือการดึงหน้าใหม่และคิดเงินใหม่

บางเว็บไซต์ไม่อนุญาตให้อ่านอัตโนมัติ เอเจนต์จะได้คำอธิบายสั้น ๆ (HTTP 403 หรือ 404) แทนข้อผิดพลาด

## การทำงาน

```
MCP client / เอเจนต์ ──MCP (HTTP)──▶ mcp-deepseek-search ──HTTPS──▶ api.deepseek.com/v1/tools/search
                                           │                         api.deepseek.com/v1/tools/fetch
                                           └── usage/*.jsonl ──GET /usage──▶ ตารางคำนวณ แดชบอร์ด หรืองานวิจัย
```

1. client เรียกเครื่องมือผ่าน MCP
2. server ตรวจข้อมูลที่ส่งมาและสร้างคำขอไปที่ DeepSeek ตัวกรองถูกแปลงเป็น search operator
3. HTTP 408, 429, 5xx และเครือข่ายขัดข้องจะลองใหม่โดยเว้นช่วงสั้น ๆ (`RETRIES` ค่าเริ่มต้น 2) ข้อผิดพลาดอื่นส่งกลับให้เอเจนต์เป็นคำอธิบายสั้น ๆ
   เช่น *"HTTP 402 - the DeepSeek account has no balance left"* การเรียกของ client จะไม่ล้มเพราะ server
4. ทำความสะอาดคำตอบ (ตัด Markdown escape และตัดสรุปที่ยาวเกิน) แล้วส่งกลับเป็นข้อความ
5. เขียนบันทึกการใช้งานหนึ่งระเบียนต่อการเรียก DeepSeek และอีกหนึ่งระเบียนต่อการเรียกเครื่องมือ

**ราคา** (DeepSeek เป็นผู้กำหนด): 0.00075 USD ต่อคำขอที่ *สำเร็จ* หรือ 0.75 USD ต่อการค้นหาหรือดึงหน้า 1,000 ครั้ง
ค้นแล้วไม่พบผลหรือดึงหน้าไม่สำเร็จไม่คิดเงิน ตรวจราคาล่าสุดที่เว็บไซต์ DeepSeek และแก้ `PRICE_PER_REQUEST_USD` เมื่อราคาเปลี่ยน
ค่านี้ใช้คำนวณตัวเลขค่าใช้จ่ายในบันทึกการใช้งานเท่านั้น

## เริ่มใช้งานด้วย Docker

ต้องมี [Docker](https://docs.docker.com/get-docker/) พร้อม Docker Compose และ API key ของ DeepSeek จาก
[platform.deepseek.com](https://platform.deepseek.com) โดยบัญชีต้องมียอดเงิน

**1. ดาวน์โหลดโค้ด**

```bash
git clone https://github.com/chacharin/mcp-deepseek-search.git
```

```bash
cd mcp-deepseek-search
```

**2. สร้าง docker network** (ครั้งเดียวต่อเครื่อง) container ที่อยู่ใน network นี้ เช่น เอเจนต์ที่รันใน Docker จะเรียก server ด้วยชื่อได้
ถ้ามี network นี้อยู่แล้วข้ามขั้นนี้ได้

```bash
docker network create agent_network
```

**3. สร้าง `.env` แล้วใส่ key**

```bash
cp .env.example .env
```

เปิด `.env` แล้วแทนค่าตัวอย่างของ `DEEPSEEK_API_KEY` ด้วย key ของคุณ ค่าอื่นยังไม่ต้องแก้

**4. เริ่ม server**

```bash
docker compose up -d --build
```

**5. ตรวจสอบ**

```bash
curl http://localhost:8807/health
```

ควรเห็น `"ok": true` ถ้าไม่ใช่ ช่อง `problems` จะบอกว่าต้องแก้อะไร การตรวจนี้ไม่เรียก DeepSeek จึงไม่เสียเงิน

ตอนนี้ MCP endpoint คือ `http://localhost:8807/mcp` บนเครื่องนี้ และ `http://mcp-deepseek-search:8000/mcp` จาก container อื่นใน `agent_network`

หยุด server ด้วย `docker compose down` บันทึกการใช้งานยังเก็บอยู่ใน volume `usage`

## รันโดยไม่ใช้ Docker

ต้องมี Python 3.12 ขึ้นไป และ [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

เพิ่มบรรทัดเหล่านี้ใน `.env` เพื่อให้ server ฟังที่พอร์ต 8807 และเก็บบันทึกไว้ในโฟลเดอร์โปรเจกต์

```
MCP_PORT=8807
USAGE_DIR=./usage
```

```bash
uv run --env-file .env python -m app.server
```

## เชื่อมกับ MCP client

server ใช้ **streamable HTTP** ให้ใช้ URL ที่ client เข้าถึงได้

| client อยู่ที่ไหน | URL |
|---|---|
| เครื่องเดียวกัน | `http://localhost:8807/mcp` |
| container อื่นใน `agent_network` | `http://mcp-deepseek-search:8000/mcp` |
| เครื่องอื่นในเครือข่าย | `http://<ip-ของ-server>:8807/mcp` (ควรตั้ง `MCP_AUTH_TOKEN` ดู[ความปลอดภัย](#ความปลอดภัย)) |

ถ้าตั้ง `MCP_AUTH_TOKEN` ไว้ client ต้องส่ง header `Authorization: Bearer <token>`

**Claude Code**

```bash
claude mcp add --transport http deepseek-search http://localhost:8807/mcp
```

ถ้ามี token ให้เพิ่ม `--header "Authorization: Bearer <token>"`

**Claude Desktop** (`claude_desktop_config.json` ผ่านตัวเชื่อม [mcp-remote](https://www.npmjs.com/package/mcp-remote) ต้องมี Node.js)

```json
{
  "mcpServers": {
    "deepseek-search": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8807/mcp"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "deepseek-search": { "type": "http", "url": "http://localhost:8807/mcp" }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "deepseek-search": { "url": "http://localhost:8807/mcp" }
  }
}
```

**Hermes Agent** (`config.yaml`)

```yaml
mcp_servers:
  deepseek_search:
    url: http://mcp-deepseek-search:8000/mcp
    timeout: 120
    # headers: {Authorization: "Bearer <token>"}
```

**client อื่น ๆ** ใช้ URL ข้างบนกับ transport แบบ streamable HTTP ตั้ง timeout ของเครื่องมืออย่างน้อย 60 วินาที เพราะบางเว็บไซต์ดึงช้า

**ทดลองโดยไม่ต้องมีเอเจนต์** ใช้ [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (ต้องมี Node.js)

```bash
npx @modelcontextprotocol/inspector
```

ในหน้าที่เปิดขึ้น เลือก Transport = *Streamable HTTP*, URL = `http://localhost:8807/mcp` กด *Connect* แล้วเปิดแท็บ *Tools*
และสั่ง `deepseek_search`

**คำแนะนำสำหรับคำสั่งของเอเจนต์** เอเจนต์จะได้ผลดีขึ้นเมื่อบอกวิธีใช้คะแนน เช่น
*"ค้นด้วย deepseek_search เลือกผลที่ authority 3–4 และ relevance ตั้งแต่ 1.5 ก่อนยกข้อเท็จจริงใดให้อ่านหน้านั้นด้วย deepseek_fetch
และอ้างอิง URL ทุกแหล่งที่ใช้"*

## เปิด/ปิดเครื่องมือทีละตัว

ตั้งสวิตช์ใน `.env` เป็น `true` หรือ `false` (รับ `1/0`, `yes/no` และ `on/off` ด้วย)

```
ENABLE_DEEPSEEK_SEARCH=true
ENABLE_DEEPSEEK_FETCH=false
```

เครื่องมือที่ปิดจะไม่อยู่ในรายการเครื่องมือเลย จึงไม่เสีย token ค่าคำอธิบายและเรียกไม่ได้ ค่าอื่นจะถือว่าเปิดและแจ้งไว้ใน `/health`

เมื่อเปลี่ยนแล้วสั่ง `docker compose up -d` จากนั้นเชื่อมต่อ client ใหม่หรือรีสตาร์ต client เพราะ client อ่านรายการเครื่องมือตอนเชื่อมต่อ

## ข้อมูลการใช้งานและค่าใช้จ่าย

```bash
curl http://localhost:8807/usage
```

บันทึกเป็น JSON Lines ใน volume `usage` วันละไฟล์ ตาม schema `harness-usage/1` มี **แต่ตัวเลข** ไม่มีคำค้น URL หรือเนื้อหาหน้าเว็บ

| `kind` | หนึ่งระเบียนต่อ | ข้อมูลหลัก |
|---|---|---|
| `search_call` / `fetch_call` | การเรียก DeepSeek API หนึ่งครั้ง | `duration_s`, `cost_usd`, `status`, `detail.http_status`, `detail.attempts`, `detail.billable`, `detail.results`, `detail.kept`, `detail.content_chars` |
| `mcp_tool` | การเรียกเครื่องมือหนึ่งครั้ง | เวลารวม ค่าใช้จ่ายรวม ตัวกรองที่ใช้ (เป็นจำนวนและค่าเปิด/ปิด ไม่ใช่ค่าที่กรอก) |

ระเบียนของการเรียกเครื่องมือครั้งเดียวกันใช้ `request_id` ร่วมกัน พารามิเตอร์ที่ใช้ได้:

| พารามิเตอร์ | ความหมาย |
|---|---|
| `since`, `until` | ช่วงเวลาเป็นวินาทีแบบ Unix |
| `limit` | จำนวนระเบียนสูงสุด ค่าเริ่มต้น 50,000 (เก็บรายการล่าสุดไว้ และเรียงจากเก่าไปใหม่) |

ตัวอย่าง: ค่าใช้จ่ายรวมของวันนี้ (ต้องมี Python)

```bash
curl -s "http://localhost:8807/usage?since=$(date -d today +%s)" | python -c "import json,sys; r=json.load(sys.stdin)['records']; print(sum(x['cost_usd'] for x in r if x['kind']!='mcp_tool'))"
```

ปิดการบันทึกได้ด้วย `USAGE_LOG=false`

## การตั้งค่าทั้งหมด

ค่าทั้งหมดอยู่ใน `.env` และมีคำอธิบายใน [.env.example](.env.example) ด้วย เมื่อแก้แล้วสั่ง `docker compose up -d`

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `DEEPSEEK_API_KEY` | (จำเป็น) | API key ของ DeepSeek |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | เปลี่ยนเมื่อต้องเรียกผ่าน proxy ขององค์กร |
| `SEARCH_TIMEOUT_SECONDS` | `30` | เวลารอสูงสุดของการค้นหา |
| `FETCH_TIMEOUT_SECONDS` | `60` | เวลารอสูงสุดของการดึงหน้า |
| `RETRIES` | `2` | จำนวนครั้งที่ลองใหม่เมื่อได้ HTTP 408, 429, 5xx หรือเครือข่ายขัดข้อง |
| `PRICE_PER_REQUEST_USD` | `0.00075` | ราคาที่ใช้คำนวณค่าใช้จ่าย |
| `ENABLE_DEEPSEEK_SEARCH` | `true` | เปิดให้ใช้ `deepseek_search` |
| `ENABLE_DEEPSEEK_FETCH` | `true` | เปิดให้ใช้ `deepseek_fetch` |
| `DEFAULT_COUNT` | `10` | จำนวนผลค้นหาเมื่อเอเจนต์ไม่ได้ระบุ `count` |
| `SUMMARY_CHARS` | `800` | ความยาวสูงสุดของสรุปแต่ละรายการ |
| `CONTENT_CHARS` | `3000` | ความยาวสูงสุดของเนื้อหาแต่ละรายการเมื่อใช้ `with_content` |
| `FETCH_MAX_CHARS` | `20000` | จำนวนตัวอักษรต่อการเรียก `deepseek_fetch` เมื่อเอเจนต์ไม่ได้ระบุ `max_chars` |
| `LOCALIZATION_IP` | (ว่าง) | IP address ในพื้นที่ที่ต้องการให้ผลค้นหาเหมาะสม ว่าง = ไม่ระบุพื้นที่ |
| `MCP_AUTH_TOKEN` | (ว่าง) | เมื่อกำหนด `/mcp` และ `/usage` ต้องมี `Authorization: Bearer <token>` |
| `USAGE_LOG` | `true` | เก็บบันทึกการใช้งาน |
| `USAGE_DIR` | `/app/usage` | โฟลเดอร์ของบันทึกการใช้งาน |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | address และพอร์ตภายใน container (หรือบนเครื่องเมื่อไม่ใช้ Docker) |
| `DOCKER_NETWORK` | `agent_network` | docker network ที่ใช้ร่วมกับเอเจนต์ |
| `PUBLISH_ADDR` | `0.0.0.0` | `0.0.0.0` = เครื่องอื่นเชื่อมต่อได้, `127.0.0.1` = เฉพาะเครื่องนี้ |
| `PUBLISH_PORT` | `8807` | พอร์ตบนเครื่อง |

## ความปลอดภัย

- **อย่า commit `.env`** ไฟล์นี้อยู่ใน `.gitignore` แล้ว
- **ใครที่เข้าถึง server ได้ก็ใช้ยอดเงิน DeepSeek ของคุณได้** ถ้าเครื่องอื่นเข้าถึงพอร์ตได้ (`PUBLISH_ADDR=0.0.0.0` ซึ่งเป็นค่าเริ่มต้น)
  ให้ตั้ง `MCP_AUTH_TOKEN` เป็นค่าสุ่มยาว ๆ หรือใช้ `PUBLISH_ADDR=127.0.0.1`
- key ไม่ออกจาก server `/health` บอกเพียงว่าตั้ง key แล้วหรือยัง และเปิดเสมอเพื่อให้ระบบเฝ้าระวังใช้ได้
- บันทึกการใช้งานไม่มีคำค้น URL หรือเนื้อหาหน้าเว็บ
- container รันด้วยผู้ใช้ที่ไม่ใช่ root
- ผลค้นหาและหน้าเว็บมาจากอินเทอร์เน็ตทั่วไป ควรบอกเอเจนต์ให้ถือเป็นข้อมูล ไม่ใช่คำสั่ง

## แก้ปัญหา

| สิ่งที่เห็น | สาเหตุและวิธีแก้ |
|---|---|
| `network agent_network declared as external, but could not be found` | สั่ง `docker network create agent_network` หรือตั้ง `DOCKER_NETWORK` เป็น network ที่มีอยู่ |
| `port is already allocated` | โปรแกรมอื่นใช้พอร์ต 8807 อยู่ ตั้ง `PUBLISH_PORT` เป็นพอร์ตที่ว่าง |
| `/health` บอกว่า key ว่างหรือยังเป็นค่าตัวอย่าง | ใส่ key จริงใน `.env` แล้วสั่ง `docker compose up -d` |
| `HTTP 401` | key ผิดหรือถูกยกเลิก สร้าง key ใหม่ที่ platform.deepseek.com |
| `HTTP 402` | บัญชี DeepSeek ไม่มียอดเงิน ให้เติมเงิน |
| `HTTP 429` | ส่งคำขอถี่เกินไป server ลองใหม่ให้แล้ว ให้เอเจนต์เรียกช้าลง |
| `HTTP 403` หรือ `404` ตอนดึงหน้า | เว็บไซต์ไม่อนุญาตให้อ่านอัตโนมัติ หรือหน้าไม่มีเนื้อหาที่อ่านได้ ให้ใช้แหล่งอื่น |
| `the query with its filters is … characters` | ย่อคำค้นหรือลดจำนวน `sites` (จำกัด 128 ตัวอักษร) |
| client ได้ `401 unauthorized` | มีการตั้ง `MCP_AUTH_TOKEN` ให้ส่ง `Authorization: Bearer <token>` |
| client ไม่เห็นเครื่องมือบางตัว | ตรวจสวิตช์ `ENABLE_…` และ `/health` แล้วเชื่อมต่อ client ใหม่ |
| ตัวเลขค่าใช้จ่ายดูไม่ถูก | แก้ `PRICE_PER_REQUEST_USD` ให้ตรงกับราคาปัจจุบันของ DeepSeek |

ดู log ของ server ได้ด้วย `docker compose logs -f`

## License

MIT · DeepSeek เป็นเครื่องหมายการค้าของเจ้าของ โครงการนี้ไม่ได้เกี่ยวข้องกับ DeepSeek
