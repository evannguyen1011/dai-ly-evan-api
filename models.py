"""Pydantic models cho request/response."""
from typing import Optional

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    product_id: str
    product_name: str
    qty_units: int


class RecentOrder(BaseModel):
    order_id: str
    order_date: str
    items: list[OrderItem]
    total_vnd: float


class Customer(BaseModel):
    customer_id: str
    business_name: str
    contact_name: str
    address: str
    customer_type: str
    tier: str
    tier_discount_pct: float
    credit_limit_vnd: float
    current_debt_vnd: float
    credit_available_vnd: float
    payment_terms_days: int
    payment_behavior: str
    order_count_last_6mo: int
    avg_order_value_vnd: float
    last_order_date: Optional[str] = None
    recent_orders: list[RecentOrder] = Field(default_factory=list)


class InventoryItem(BaseModel):
    product_id: str
    product_name: str
    qty_on_hand_units: int
    qty_reserved_units: int
    qty_available_units: int
    stock_status: str
    restock_eta_date: Optional[str] = None
    warehouse: str


class QuoteItemRequest(BaseModel):
    product_id: str
    qty_units: int = Field(..., gt=0)


class QuoteCreateRequest(BaseModel):
    customer_id: Optional[str] = None
    items: list[QuoteItemRequest] = Field(..., min_length=1)
    delivery_note: Optional[str] = None
    notes: Optional[str] = None


class QuoteLineItem(BaseModel):
    product_id: str
    product_name: str
    qty_units: int
    list_price_vnd: float
    subtotal_vnd: float


class Quote(BaseModel):
    quote_id: str
    customer_id: Optional[str] = None
    items: list[QuoteLineItem]
    delivery_note: Optional[str] = None
    notes: Optional[str] = None
    total_vnd: float
    created_at: str
