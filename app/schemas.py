"""Shapes of API requests and responses (Pydantic).

FastAPI checks every incoming request against these classes. Bad input (a negative price, a missing
field, an unknown payment method) is rejected with HTTP 422 before our code even runs.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.constants import MovementReason, PaymentMethod, Role, SalePaymentMethod, SaleStatus, SerialStatus


class In(BaseModel):
    """Base for request bodies: trims spaces and rejects unknown fields (catches typos in client code)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Out(BaseModel):
    """Base for responses: can be built straight from SQLAlchemy objects."""
    model_config = ConfigDict(from_attributes=True)


# ---------- Users & auth ----------

class UserOut(Out):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(In):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)   # bcrypt only uses the first 72 bytes
    role: Role = "vendeur"


class UserUpdate(In):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


class PasswordChange(In):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


# ---------- Categories ----------

class CategoryIn(In):
    name: str = Field(min_length=2, max_length=80)


class CategoryOut(Out):
    id: int
    name: str
    position: int


# ---------- Products & stock ----------

class ProductCreate(In):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=80)
    category_id: int
    price_centimes: int = Field(ge=0)
    wholesale_price_centimes: int | None = Field(default=None, ge=0)
    cost_centimes: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=3, ge=0)
    tracks_serial: bool = False
    # No "quantity" here on purpose: stock only enters through /restock, which records a movement.


class ProductUpdate(In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=80)
    category_id: int | None = None
    price_centimes: int | None = Field(default=None, ge=0)
    wholesale_price_centimes: int | None = Field(default=None, ge=0)   # send null to remove it
    cost_centimes: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(Out):
    id: int
    sku: str
    name: str
    brand: str | None
    category: CategoryOut
    price_centimes: int
    wholesale_price_centimes: int | None
    cost_centimes: int | None = None   # hidden (None) for sellers; only admins see purchase prices
    quantity: int
    low_stock_threshold: int
    is_low_stock: bool
    tracks_serial: bool
    is_active: bool
    image_url: str | None


class Restock(In):
    quantity: int = Field(gt=0, le=10_000)
    serials: list[str] = Field(default_factory=list)   # required for phones/computers: one IMEI per unit
    cost_centimes: int | None = Field(default=None, ge=0)  # optional: new purchase price
    note: str | None = Field(default=None, max_length=255)


class StockAdjust(In):
    change: int = Field(ne=0, ge=-10_000, le=10_000)   # e.g. -1 for a broken item found in inventory
    note: str = Field(min_length=3, max_length=255)    # a reason is mandatory for manual corrections


class MovementOut(Out):
    id: int
    product_id: int
    change: int
    reason: MovementReason
    sale_id: int | None
    note: str | None
    created_at: datetime
    user_name: str | None = None


class SerialOut(Out):
    serial: str
    status: SerialStatus
    product_id: int
    created_at: datetime


class SerialLookup(BaseModel):
    serial: str
    status: SerialStatus
    product_id: int
    product_name: str
    received_at: datetime
    sale_id: int | None = None
    sold_at: datetime | None = None
    customer_name: str | None = None
    customer_phone: str | None = None


# ---------- Sales ----------

class SaleItemIn(In):
    product_id: int
    quantity: int = Field(gt=0, le=1_000)
    serials: list[str] = Field(default_factory=list)


class SaleCreate(In):
    items: list[SaleItemIn] = Field(min_length=1, max_length=100)
    payment_method: SalePaymentMethod = "especes"
    # Sale to another shop: reseller prices, goes on their account. They may pay part of it right away.
    reseller_id: int | None = None
    paid_now_centimes: int = Field(default=0, ge=0)
    paid_now_method: PaymentMethod = "especes"
    discount_centimes: int = Field(default=0, ge=0)
    customer_name: str | None = Field(default=None, max_length=120)
    customer_phone: str | None = Field(default=None, max_length=30)


class SaleCancel(In):
    reason: str = Field(min_length=3, max_length=255)


class SaleItemOut(Out):
    product_id: int
    product_name: str
    quantity: int
    unit_price_centimes: int
    line_total_centimes: int
    serial_numbers: list[str]


class SaleOut(Out):
    id: int
    created_at: datetime
    seller_name: str
    reseller_id: int | None
    reseller_name: str | None
    paid_now_centimes: int = 0       # reseller sales: paid at the till, the rest went on their account
    customer_name: str | None
    customer_phone: str | None
    payment_method: SalePaymentMethod
    subtotal_centimes: int
    discount_centimes: int
    total_centimes: int
    status: SaleStatus
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: list[SaleItemOut]


# ---------- Reports ----------

class PaymentBreakdown(BaseModel):
    payment_method: SalePaymentMethod
    sale_count: int
    total_centimes: int


class DailyReport(BaseModel):
    date: date
    sale_count: int
    cancelled_count: int
    items_sold: int
    revenue_centimes: int
    discount_centimes: int
    cost_centimes: int
    margin_centimes: int
    by_payment: list[PaymentBreakdown]
    reseller_payments_centimes: int      # money received from resellers that day (old or new debts)


class TopProduct(BaseModel):
    product_id: int
    name: str
    quantity_sold: int
    revenue_centimes: int


class DayTotal(BaseModel):
    date: date
    sale_count: int
    revenue_centimes: int


# ---------- Resellers ----------

class ResellerIn(In):
    name: str = Field(min_length=2, max_length=120)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


class ResellerUpdate(In):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ResellerOut(BaseModel):
    id: int
    name: str
    contact_name: str | None
    phone: str | None
    city: str | None
    notes: str | None
    is_active: bool
    purchases_centimes: int    # everything they bought (cancelled sales excluded)
    paid_centimes: int         # everything they paid
    balance_centimes: int      # what they still owe (negative = they paid in advance)
    last_activity: datetime | None


class ResellerPaymentIn(In):
    amount_centimes: int = Field(gt=0)
    payment_method: PaymentMethod = "especes"
    note: str | None = Field(default=None, max_length=255)


class StatementEntry(BaseModel):
    date: datetime
    kind: str                  # "achat", "achat_annule" or "paiement"
    label: str
    sale_id: int | None = None
    debit_centimes: int = 0    # increases what they owe
    credit_centimes: int = 0   # decreases what they owe
    balance_centimes: int      # running balance after this line
    by: str | None = None


class OpenPurchaseItem(BaseModel):
    product_name: str
    quantity: int
    unit_price_centimes: int
    serial_numbers: list[str]


class OpenPurchaseOut(BaseModel):
    """A purchase the reseller hasn't fully paid yet."""
    sale_id: int
    reseller_id: int
    reseller_name: str
    date: datetime
    days_old: int
    total_centimes: int
    paid_centimes: int
    remaining_centimes: int
    seller_name: str
    items: list[OpenPurchaseItem]


class ResellerDetail(ResellerOut):
    statement: list[StatementEntry]          # newest first
    open_purchases: list[OpenPurchaseOut]    # not fully paid, oldest first
