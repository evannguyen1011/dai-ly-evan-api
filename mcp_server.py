"""MCP server (Streamable HTTP) cho PAL — cùng data với REST API trong main.py."""
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import storage
from models import QuoteItemRequest
from quotes_service import CustomerNotFoundError, ProductNotFoundError, create_quote_record

# streamable_http_path="/mcp" và mount ở "/" trong main.py (không phải mount
# ở "/mcp" với path "/") — tránh Starlette redirect 307 "/mcp" -> "/mcp/" mà
# nhiều HTTP client (vd PAL) không tự follow cho request POST.
# stateless_http + json_response để tương thích tốt với client HTTP đơn giản.
#
# enable_dns_rebinding_protection=False: mặc định SDK chỉ chấp nhận Host
# header là localhost/127.0.0.1, sẽ chặn luôn cả request đi qua ngrok (Host
# header là domain ngrok, đổi mỗi lần restart). Tắt vì server đã có lớp
# X-API-Key chặn ở main.py, và đây là môi trường demo expose tạm qua ngrok.
mcp = FastMCP(
    "Ánh Dương Apparel - Customer / Inventory / Quote",
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def get_customer(customer_id: str) -> dict:
    """Lấy thông tin khách hàng: công nợ, hạn mức tín dụng, tier, đơn hàng gần đây... theo customer_id."""
    customer = storage.get_customer(customer_id)
    if customer is None:
        raise ValueError(f"customer_not_found: {customer_id}")
    return customer


@mcp.tool()
def check_inventory(product_ids: Optional[list[str]] = None) -> list[dict]:
    """Tra tồn kho theo danh sách product_id. Không truyền product_ids để lấy toàn bộ tồn kho.
    Mã không tồn tại trả kèm {"product_id":..., "error":"not_found"}."""
    return storage.get_inventory_for_ids(product_ids)


@mcp.tool()
def create_quote(
    items: list[QuoteItemRequest],
    customer_id: Optional[str] = None,
    delivery_note: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Tạo báo giá mới. Tự tra product_name/list_price_vnd theo product_id, tính subtotal
    từng dòng và total_vnd, lưu lại và trả về báo giá vừa tạo (kèm quote_id)."""
    try:
        return create_quote_record(
            customer_id=customer_id,
            items=[{"product_id": i.product_id, "qty_units": i.qty_units} for i in items],
            delivery_note=delivery_note,
            notes=notes,
        )
    except CustomerNotFoundError as e:
        raise ValueError(f"customer_not_found: {e.customer_id}")
    except ProductNotFoundError as e:
        raise ValueError(f"product_not_found: {e.product_id}")


@mcp.tool()
def get_quote(quote_id: str) -> dict:
    """Tra lại 1 báo giá đã lưu theo quote_id."""
    quote = storage.get_quote(quote_id)
    if quote is None:
        raise ValueError(f"quote_not_found: {quote_id}")
    return quote
