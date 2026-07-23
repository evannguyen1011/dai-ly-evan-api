"""Đọc/ghi các file JSON dùng làm database tạm, và cache bảng giá CSV.

Server chạy 1 process/1 worker (uvicorn --reload), nên mỗi file dùng 1
threading.Lock riêng là đủ để tránh 2 request ghi đè lẫn nhau. Ghi file
theo kiểu atomic (ghi ra file tạm rồi os.replace) để tránh file bị hỏng
nếu server crash giữa chừng khi đang ghi.
"""
import csv
import json
import os
import threading
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOMERS_PATH = os.path.join(BASE_DIR, "khach_hang.json")
INVENTORY_PATH = os.path.join(BASE_DIR, "ton_kho.json")
QUOTES_PATH = os.path.join(BASE_DIR, "quotes.json")
PRICE_LIST_PATH = os.path.join(BASE_DIR, "bang_gia_san_pham.csv")

_customers_lock = threading.Lock()
_inventory_lock = threading.Lock()
_quotes_lock = threading.Lock()

# product_id -> {"product_name": ..., "list_price_vnd": ...}
PRICE_LIST: dict[str, dict] = {}


def load_price_list() -> None:
    PRICE_LIST.clear()
    with open(PRICE_LIST_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            PRICE_LIST[row["product_id"]] = {
                "product_name": row["product_name"],
                "list_price_vnd": float(row["list_price_vnd"]),
            }


def _read_json(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, data: list[dict]) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def get_customer(customer_id: str) -> Optional[dict]:
    with _customers_lock:
        customers = _read_json(CUSTOMERS_PATH)
    for customer in customers:
        if customer.get("customer_id") == customer_id:
            return customer
    return None


def get_all_inventory() -> list[dict]:
    with _inventory_lock:
        return _read_json(INVENTORY_PATH)


def get_inventory_by_id(product_id: str) -> Optional[dict]:
    with _inventory_lock:
        items = _read_json(INVENTORY_PATH)
    for item in items:
        if item.get("product_id") == product_id:
            return item
    return None


def get_inventory_for_ids(product_ids: Optional[list[str]]) -> list[dict]:
    """Không truyền product_ids (None/rỗng) -> trả toàn bộ tồn kho.
    Mã không tồn tại trả kèm {"product_id":..., "error":"not_found"}."""
    if not product_ids:
        return get_all_inventory()
    result = []
    for product_id in product_ids:
        item = get_inventory_by_id(product_id)
        result.append(item if item is not None else {"product_id": product_id, "error": "not_found"})
    return result


def save_quote(quote: dict) -> dict:
    with _quotes_lock:
        quotes = _read_json(QUOTES_PATH)
        quotes.append(quote)
        _write_json_atomic(QUOTES_PATH, quotes)
    return quote


def get_quote(quote_id: str) -> Optional[dict]:
    with _quotes_lock:
        quotes = _read_json(QUOTES_PATH)
    for quote in quotes:
        if quote.get("quote_id") == quote_id:
            return quote
    return None
