"""Ánh Dương Apparel - Customer / Inventory / Quote API.

REST API để 1 AI agent (chạy trên PAL/MindPal) đọc dữ liệu khách hàng,
tồn kho và lưu báo giá.
"""
import json
import logging
import os
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager

# Ép stdout/stderr dùng UTF-8 — mặc định trên Windows, console/redirect có
# thể dùng codepage khác (vd cp1252), làm log tiếng Việt bị lỗi (?, \uXXXX).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import storage
from mcp_server import mcp
from models import Customer, Quote, QuoteCreateRequest
from quotes_service import CustomerNotFoundError, ProductNotFoundError, create_quote_record

load_dotenv()

API_KEY = os.getenv("API_KEY")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("quote-inventory-api")

MAX_LOG_BODY_CHARS = 2000

# Mô tả action theo (method, path prefix) — để log ghi rõ agent đang "dùng
# tool" nào thay vì chỉ hiện path kỹ thuật.
_ACTION_DESCRIPTIONS = [
    ("GET", "/health", "Health check"),
    ("GET", "/customers/", "Tra cứu thông tin khách hàng"),
    ("GET", "/inventory", "Tra cứu tồn kho"),
    ("POST", "/quotes", "Tạo báo giá mới"),
    ("GET", "/quotes/", "Tra cứu báo giá đã lưu"),
    ("POST", "/mcp", "MCP call — xem body vào để biết tool nào"),
    ("GET", "/mcp", "MCP call (GET)"),
]


def _describe_action(method: str, path: str) -> str:
    for m, prefix, desc in _ACTION_DESCRIPTIONS:
        if method == m and path.startswith(prefix):
            return desc
    return "?"


def _body_preview(raw: bytes) -> str:
    if not raw:
        return "(rỗng)"
    try:
        parsed = json.loads(raw)
        text = json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        text = repr(raw)
    if len(text) > MAX_LOG_BODY_CHARS:
        text = text[:MAX_LOG_BODY_CHARS] + f"...(rút gọn, tổng {len(text)} ký tự)"
    return text


# Phải gọi streamable_http_app() trước để tạo mcp.session_manager, rồi mới
# đưa vào lifespan bên dưới — nếu không sẽ lỗi lúc startup.
mcp_asgi_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning(
            "API_KEY chưa được set trong .env — mọi request sẽ bị từ chối với 401."
        )
    storage.load_price_list()
    logger.info("Loaded %d products from bang_gia_san_pham.csv", len(storage.PRICE_LIST))
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield


app = FastAPI(title="Ánh Dương Apparel - Customer / Inventory / Quote API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_and_log(request: Request, call_next):
    start = time.perf_counter()
    method = request.method
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    action = _describe_action(method, path)

    request_body = await request.body()

    logger.info("")
    logger.info("--> [%s] %s %s%s", action, method, path, query)
    if request_body:
        logger.info("    body vào : %s", _body_preview(request_body))

    if path != "/health":
        provided_key = request.headers.get("x-api-key")
        if not API_KEY or provided_key != API_KEY:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("<-- 401 unauthorized (%.1fms)", duration_ms)
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

    response = await call_next(request)

    response_body = b""
    async for chunk in response.body_iterator:
        response_body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("<-- %d (%.1fms)", response.status_code, duration_ms)
    if response_body:
        logger.info("    body ra  : %s", _body_preview(response_body))

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(detail)})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: str):
    customer = storage.get_customer(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "customer_not_found", "customer_id": customer_id},
        )
    return customer


@app.get("/inventory")
def get_inventory(product_ids: str | None = Query(default=None)):
    ids = [p.strip() for p in product_ids.split(",") if p.strip()] if product_ids else None
    return storage.get_inventory_for_ids(ids)


@app.post("/quotes", response_model=Quote)
def create_quote(body: QuoteCreateRequest):
    try:
        return create_quote_record(
            customer_id=body.customer_id,
            items=[{"product_id": i.product_id, "qty_units": i.qty_units} for i in body.items],
            delivery_note=body.delivery_note,
            notes=body.notes,
        )
    except CustomerNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "customer_not_found", "customer_id": e.customer_id},
        )
    except ProductNotFoundError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "product_not_found", "product_id": e.product_id},
        )


@app.get("/quotes/{quote_id}", response_model=Quote)
def get_quote(quote_id: str):
    quote = storage.get_quote(quote_id)
    if quote is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "quote_not_found", "quote_id": quote_id},
        )
    return quote


# MCP endpoint thực tế cho PAL: <Server URL>/mcp
# Mount ở "/" (không phải "/mcp") vì mcp_server.py đã tự có route "/mcp" —
# mount ở "/mcp" + route con "/" sẽ gây Starlette redirect 307 "/mcp" -> "/mcp/".
app.mount("/", mcp_asgi_app)
