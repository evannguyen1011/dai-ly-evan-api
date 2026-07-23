"""Logic tạo báo giá — dùng chung cho REST endpoint và MCP tool."""
from datetime import datetime, timezone

import storage


class CustomerNotFoundError(Exception):
    def __init__(self, customer_id: str):
        self.customer_id = customer_id


class ProductNotFoundError(Exception):
    def __init__(self, product_id: str):
        self.product_id = product_id


def _generate_quote_id() -> str:
    return f"BG{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def create_quote_record(
    *,
    customer_id: str | None,
    items: list[dict],
    delivery_note: str | None = None,
    notes: str | None = None,
) -> dict:
    """items: list các {"product_id": str, "qty_units": int}."""
    if customer_id is not None:
        customer = storage.get_customer(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)

    line_items = []
    total_vnd = 0.0
    for requested in items:
        product = storage.PRICE_LIST.get(requested["product_id"])
        if product is None:
            raise ProductNotFoundError(requested["product_id"])
        subtotal_vnd = product["list_price_vnd"] * requested["qty_units"]
        total_vnd += subtotal_vnd
        line_items.append(
            {
                "product_id": requested["product_id"],
                "product_name": product["product_name"],
                "qty_units": requested["qty_units"],
                "list_price_vnd": product["list_price_vnd"],
                "subtotal_vnd": subtotal_vnd,
            }
        )

    quote = {
        "quote_id": _generate_quote_id(),
        "customer_id": customer_id,
        "items": line_items,
        "delivery_note": delivery_note,
        "notes": notes,
        "total_vnd": total_vnd,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return storage.save_quote(quote)
