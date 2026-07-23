# Đại lý Evan - Customer / Inventory / Quote API

Server FastAPI phục vụ 1 AI agent bên ngoài (chạy trên PAL/MindPal) đọc dữ
liệu khách hàng, tồn kho và lưu báo giá. Có **2 mặt cùng chạy trên 1 server**:

- **MCP server (Streamable HTTP)** ở `/mcp` — dùng cho PAL, vì PAL kết nối
  theo chuẩn MCP (Model Context Protocol), không nhận REST thường. Có 4
  tool: `get_customer`, `check_inventory`, `create_quote`, `get_quote`.
- **REST API** ở root (`/health`, `/customers/{id}`, `/inventory`,
  `/quotes`, ...) — giữ lại để test nhanh bằng curl/Postman.

Cả 2 dùng chung logic (`storage.py`, `quotes_service.py`):
- `khach_hang.json`, `ton_kho.json`, `quotes.json` đóng vai trò database
  tạm thời — đọc/ghi trực tiếp, mỗi file có lock riêng trong process để
  tránh ghi đè khi nhiều request tới cùng lúc. `quotes.json` tự được tạo
  nếu chưa tồn tại.
- `bang_gia_san_pham.csv` được load 1 lần lúc start server, cache trong
  RAM, dùng để tra `product_name` / `list_price_vnd` theo `product_id`
  khi tạo báo giá.

Mỗi request (cả REST lẫn MCP) đều được log ra terminal: method/path,
body request, body response, status, thời gian xử lý — để dễ theo dõi
agent đang gọi gì và nhận lại gì.

## 1. Cài đặt

```bash
pip install -r requirements.txt
```

Tạo `.env` từ mẫu (đổi `API_KEY` sang giá trị thật trước khi expose ra
ngoài):

```bash
cp .env.example .env
```

## 2. Chạy local

```bash
uvicorn main:app --reload --port 8000
```

Server log ra console: số sản phẩm đã load từ `bang_gia_san_pham.csv`, và
sau đó từng request (method, path, status code, thời gian xử lý).

## 3. Expose ra ngoài qua ngrok (để PAL/MindPal gọi vào)

```bash
ngrok http 8000
```

Trong PAL, khi thêm **"Add New Remote MCP Server"**:
- **Authentication Method**: `Headers / API Key`
- **Server Name**: tuỳ ý, vd `Customer / Inventory / Quote`
- **Server URL**: `https://xxxx.ngrok-free.app/mcp` — **nhớ thêm `/mcp` ở
  cuối**, nếu chỉ điền URL gốc sẽ lỗi 404 khi bấm "Validate MCP Server".
- **Headers**: thêm 1 header `X-API-Key` = giá trị `API_KEY` trong `.env`

> Vì đây là URL public tạm thời, hãy đổi `API_KEY` sang giá trị khó đoán
> trước khi expose, và tắt ngrok khi không dùng nữa.

## 4. Test bằng curl

Thay `changeme` bằng giá trị `API_KEY` thật, và `http://localhost:8000`
bằng URL ngrok nếu test qua internet.

### GET /health

```bash
curl http://localhost:8000/health
```

### GET /customers/{customer_id} — thành công

```bash
curl http://localhost:8000/customers/KH001 \
  -H "X-API-Key: changeme"
```

### GET /customers/{customer_id} — lỗi: sai/thiếu API key (401)

```bash
curl http://localhost:8000/customers/KH001 \
  -H "X-API-Key: sai-key"
# {"error":"unauthorized"}
```

### GET /customers/{customer_id} — lỗi: khách không tồn tại (404)

```bash
curl http://localhost:8000/customers/KH999 \
  -H "X-API-Key: changeme"
# {"error":"customer_not_found","customer_id":"KH999"}
```

### GET /inventory — hỏi nhiều mã cùng lúc (có mã không tồn tại)

```bash
curl "http://localhost:8000/inventory?product_ids=SP001,SP002,SP999" \
  -H "X-API-Key: changeme"
```

Response: các mã tìm thấy trả object tồn kho đầy đủ, mã không tồn tại trả
`{"product_id":"SP999","error":"not_found"}` thay vì bị bỏ qua.

### GET /inventory — không truyền product_ids (toàn bộ tồn kho)

```bash
curl http://localhost:8000/inventory \
  -H "X-API-Key: changeme"
```

### POST /quotes — tạo báo giá thành công

Không cần gửi `product_name` / `list_price_vnd` — server tự tra theo
`product_id` trong `bang_gia_san_pham.csv` và tính `subtotal_vnd`.

```bash
curl -X POST http://localhost:8000/quotes \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "KH001",
    "items": [
      {"product_id": "SP001", "qty_units": 30},
      {"product_id": "SP003", "qty_units": 50}
    ],
    "delivery_note": "Giao Hải Dương thứ 5",
    "notes": "Khách hỏi giá gấp"
  }'
```

Response trả về báo giá vừa lưu, gồm `quote_id` tự sinh (dạng `BG` +
timestamp), từng dòng có `product_name`/`list_price_vnd`/`subtotal_vnd`,
và `total_vnd` là tổng các dòng.

### POST /quotes — customer_id gửi lên nhưng không tồn tại (404)

```bash
curl -X POST http://localhost:8000/quotes \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "KH999", "items": [{"product_id": "SP001", "qty_units": 10}]}'
# {"error":"customer_not_found","customer_id":"KH999"}
```

### POST /quotes — customer_id null (khách vãng lai, hợp lệ)

```bash
curl -X POST http://localhost:8000/quotes \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": null, "items": [{"product_id": "SP001", "qty_units": 10}]}'
```

### POST /quotes — product_id không tồn tại trong bảng giá (422)

```bash
curl -X POST http://localhost:8000/quotes \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"product_id": "SP999", "qty_units": 10}]}'
# {"error":"product_not_found","product_id":"SP999"}
```

### POST /quotes — thiếu field bắt buộc (422)

```bash
curl -X POST http://localhost:8000/quotes \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{}'
# 422 kèm chi tiết field nào thiếu (items là bắt buộc)
```

### GET /quotes/{quote_id} — tra lại báo giá đã lưu

```bash
curl http://localhost:8000/quotes/BG... \
  -H "X-API-Key: changeme"
```

### GET /quotes/{quote_id} — báo giá không tồn tại (404)

```bash
curl http://localhost:8000/quotes/BG_KHONG_TON_TAI \
  -H "X-API-Key: changeme"
# {"error":"quote_not_found","quote_id":"BG_KHONG_TON_TAI"}
```

## Test MCP endpoint trực tiếp (không qua PAL)

`/mcp` nói MCP protocol (JSON-RPC), không test bằng curl thường được. Cách
nhanh nhất là dùng chính MCP Python client:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = "http://localhost:8000/mcp"
    headers = {"X-API-Key": "changeme"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])
            result = await session.call_tool("get_customer", {"customer_id": "KH001"})
            print(result.content[0].text)

asyncio.run(main())
```

## Cấu trúc dự án

```
main.py                  # FastAPI app: REST routes + mount MCP server ở /mcp
mcp_server.py             # MCP server (Streamable HTTP) — 4 tool cho PAL gọi
quotes_service.py         # logic tạo báo giá dùng chung giữa REST và MCP
models.py                 # Pydantic models cho REST request/response
storage.py                # đọc/ghi JSON an toàn (lock trong process) + cache CSV
requirements.txt
.env.example
README.md
khach_hang.json           # database khách hàng
ton_kho.json               # database tồn kho
bang_gia_san_pham.csv      # bảng giá — tra cứu khi tạo báo giá
quotes.json                 # database báo giá đã lưu (tự tạo nếu chưa có)
```
