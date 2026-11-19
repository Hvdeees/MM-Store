"""Database tables (SQLAlchemy 2.0).

Money: every amount is an integer number of centimes (1 DH = 100 centimes). Never floats:
0.1 + 0.2 != 0.3 in floating point, and those errors add up over thousands of sales.

Stock rule: `Product.quantity` only ever changes together with a `StockMovement` row,
so every unit in or out of the store has a reason, a person and a time (an audit trail).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    # Always store UTC; convert to Morocco time only when displaying or building reports.
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt hash, never the password itself
    role: Mapped[str] = mapped_column(String(20), default="vendeur")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    position: Mapped[int] = mapped_column(default=0)   # display order at the till


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Last line of defence: the database itself refuses impossible values, even if the code has a bug.
        CheckConstraint("quantity >= 0", name="ck_products_quantity_nonnegative"),
        CheckConstraint("price_centimes >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint("cost_centimes >= 0", name="ck_products_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # internal reference code
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str | None] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    price_centimes: Mapped[int]                                   # selling price
    # Optional lower price for resellers (other shops buying from us). None = they pay the normal price.
    wholesale_price_centimes: Mapped[int | None] = mapped_column()
    cost_centimes: Mapped[int] = mapped_column(default=0)          # purchase price (admin only, for margins)
    quantity: Mapped[int] = mapped_column(default=0)
    low_stock_threshold: Mapped[int] = mapped_column(default=3)
    # Phones and computers: every unit has its own IMEI / serial number, tracked one by one.
    tracks_serial: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # archived instead of deleted, keeps history
    # Photo file name inside MEDIA_DIR/products/ (a random name chosen by the server, never the uploader's).
    image_filename: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    category: Mapped[Category] = relationship(lazy="joined")

    @property
    def image_url(self) -> str | None:
        return f"/media/products/{self.image_filename}" if self.image_filename else None

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.low_stock_threshold


class SerialUnit(Base):
    """One physical phone or computer, identified by its IMEI or serial number."""
    __tablename__ = "serial_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    serial: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="en_stock")
    sale_item_id: Mapped[int | None] = mapped_column(ForeignKey("sale_items.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    product: Mapped[Product] = relationship()


class Reseller(Base):
    """Another shop that buys from MM Store, often on credit ("revendeur")."""
    __tablename__ = "resellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    city: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResellerPayment(Base):
    """Money received from a reseller. What they owe = their (non-cancelled) purchases - their payments.
    The balance is always computed from these rows, never stored, so it can't drift out of sync."""
    __tablename__ = "reseller_payments"
    __table_args__ = (CheckConstraint("amount_centimes > 0", name="ck_reseller_payments_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reseller_id: Mapped[int] = mapped_column(ForeignKey("resellers.id"), index=True)
    amount_centimes: Mapped[int]
    payment_method: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(255))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))   # set when paid at the till with the sale
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    user: Mapped[User] = relationship()


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reseller_id: Mapped[int | None] = mapped_column(ForeignKey("resellers.id"), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(30))
    payment_method: Mapped[str] = mapped_column(String(20))
    subtotal_centimes: Mapped[int]
    discount_centimes: Mapped[int] = mapped_column(default=0)
    total_centimes: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="validee", index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))

    seller: Mapped[User] = relationship(foreign_keys=[seller_id])
    reseller: Mapped[Reseller | None] = relationship()
    payments: Mapped[list[ResellerPayment]] = relationship(viewonly=True)   # paid at the till with this sale
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int]
    # Prices are COPIED at the moment of sale: changing a product's price later must not rewrite old receipts.
    unit_price_centimes: Mapped[int]
    unit_cost_centimes: Mapped[int]
    # Snapshot of the IMEIs sold on this line, kept even if the sale is cancelled later.
    serial_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class StockMovement(Base):
    """Audit trail: every change to a product's quantity, with who, why and when."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    change: Mapped[int]                           # +5 = 5 units in, -2 = 2 units out
    reason: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    user: Mapped[User | None] = relationship()
