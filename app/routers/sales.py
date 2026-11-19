from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.constants import SaleStatus
from app.database import get_db
from app.models import Product, Reseller, ResellerPayment, Sale, SaleItem, SerialUnit, User
from app.schemas import SaleCancel, SaleCreate, SaleItemOut, SaleOut
from app.security import get_current_user, require_admin
from app.stock import normalize_serials, record_movement
from app.timeutils import local_range_utc

router = APIRouter(prefix="/api/sales", tags=["Ventes"])


def to_out(sale: Sale) -> SaleOut:
    items = [SaleItemOut(product_id=i.product_id, product_name=i.product.name, quantity=i.quantity,
                         unit_price_centimes=i.unit_price_centimes,
                         line_total_centimes=i.quantity * i.unit_price_centimes,
                         serial_numbers=i.serial_numbers or []) for i in sale.items]
    return SaleOut(id=sale.id, created_at=sale.created_at, seller_name=sale.seller.full_name,
                   reseller_id=sale.reseller_id, reseller_name=sale.reseller.name if sale.reseller else None,
                   paid_now_centimes=sum(p.amount_centimes for p in sale.payments),
                   customer_name=sale.customer_name, customer_phone=sale.customer_phone,
                   payment_method=sale.payment_method, subtotal_centimes=sale.subtotal_centimes,
                   discount_centimes=sale.discount_centimes, total_centimes=sale.total_centimes,
                   status=sale.status, cancelled_at=sale.cancelled_at, cancel_reason=sale.cancel_reason,
                   items=items)


def load_sale(db: Session, sale_id: int, user: User) -> Sale:
    sale = db.get(Sale, sale_id, options=[selectinload(Sale.items).selectinload(SaleItem.product)])
    # A seller asking for someone else's sale gets the same 404 as a missing sale: no information leak.
    if sale is None or (user.role != "admin" and sale.seller_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vente introuvable")
    return sale


@router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
def create_sale(body: SaleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record a sale at the till. All-or-nothing: if any line fails, nothing changes.

    The core trick is the conditional UPDATE:
        UPDATE products SET quantity = quantity - :n WHERE id = :id AND quantity >= :n
    It checks and decrements in ONE atomic database step. If two sellers sell the last phone at the
    same moment, only one UPDATE matches a row; the other gets rowcount 0 and its sale is rolled back.
    IMEIs use the same trick: UPDATE ... SET status='vendu' WHERE status='en_stock'.
    """
    # 1. Merge repeated lines for the same product: [{id 4, qty 1}, {id 4, qty 2}] -> {4: qty 3}
    lines: dict[int, dict] = defaultdict(lambda: {"quantity": 0, "serials": []})
    for item in body.items:
        lines[item.product_id]["quantity"] += item.quantity
        lines[item.product_id]["serials"] += item.serials

    # Sale to another shop ("revendeur"): reseller prices, and it goes on their account.
    reseller = None
    if body.reseller_id is not None:
        reseller = db.get(Reseller, body.reseller_id)
        if reseller is None or not reseller.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Revendeur introuvable ou désactivé")
    elif body.payment_method == "credit":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choisissez le revendeur pour vendre à crédit")
    elif body.paid_now_centimes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un acompte n'est possible que pour un revendeur")

    sale = Sale(seller_id=user.id, reseller_id=reseller.id if reseller else None,
                payment_method="credit" if reseller else body.payment_method,
                discount_centimes=body.discount_centimes,
                customer_name=None if reseller else (body.customer_name or None),
                customer_phone=None if reseller else (body.customer_phone or None),
                subtotal_centimes=0, total_centimes=0)
    try:
        db.add(sale)
        db.flush()   # sends the INSERT now (still inside the transaction) so sale.id exists for the movements

        for product_id, line in lines.items():
            qty = line["quantity"]
            product = db.get(Product, product_id)
            if product is None or not product.is_active:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Produit {product_id} introuvable ou archivé")

            # 2. Phones/computers: the exact units (IMEIs) being sold must be named and available.
            serials: list[str] = []
            if product.tracks_serial:
                serials = normalize_serials(line["serials"])
                if len(serials) != qty:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                        f"« {product.name} » : indiquez {qty} IMEI / numéro(s) de série")
                marked = db.execute(update(SerialUnit)
                                    .where(SerialUnit.serial.in_(serials), SerialUnit.product_id == product.id,
                                           SerialUnit.status == "en_stock")
                                    .values(status="vendu")
                                    .execution_options(synchronize_session=False))
                if marked.rowcount != qty:
                    raise HTTPException(status.HTTP_409_CONFLICT,
                                        f"« {product.name} » : IMEI inconnu, déjà vendu ou d'un autre produit")
            elif line["serials"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    f"« {product.name} » n'utilise pas de numéros de série")

            # 3. Take the units out of stock, only if enough are left (atomic check-and-decrement).
            available = product.quantity
            taken = db.execute(update(Product)
                               .where(Product.id == product.id, Product.quantity >= qty)
                               .values(quantity=Product.quantity - qty))
            if taken.rowcount == 0:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    f"Stock insuffisant pour « {product.name} » (disponible : {available}, demandé : {qty})")

            unit_price = product.price_centimes
            if reseller and product.wholesale_price_centimes is not None:
                unit_price = product.wholesale_price_centimes
            sale_item = SaleItem(product_id=product.id, quantity=qty, unit_price_centimes=unit_price,
                                 unit_cost_centimes=product.cost_centimes, serial_numbers=serials)
            sale.items.append(sale_item)
            sale.subtotal_centimes += qty * unit_price
            record_movement(db, product_id=product.id, change=-qty, reason="vente", user_id=user.id, sale_id=sale.id)

            if serials:
                db.flush()   # get sale_item.id, then link each sold unit to this sale line
                db.execute(update(SerialUnit).where(SerialUnit.serial.in_(serials))
                           .values(sale_item_id=sale_item.id).execution_options(synchronize_session=False))

        if body.discount_centimes > sale.subtotal_centimes:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La remise ne peut pas dépasser le sous-total")
        sale.total_centimes = sale.subtotal_centimes - body.discount_centimes
        if reseller and body.paid_now_centimes:
            if body.paid_now_centimes > sale.total_centimes:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le montant payé dépasse le total de l'achat")
            db.add(ResellerPayment(reseller_id=reseller.id, amount_centimes=body.paid_now_centimes,
                                   payment_method=body.paid_now_method, sale_id=sale.id, user_id=user.id,
                                   note="Payé avec l'achat"))
        db.commit()
    except Exception:
        db.rollback()   # undo EVERYTHING done in this sale: stock, IMEIs, movements, the sale row itself
        raise

    return to_out(load_sale(db, sale.id, user))


@router.get("", response_model=list[SaleOut])
def list_sales(
    from_date: date | None = None,
    to_date: date | None = None,
    status_filter: SaleStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admins see every sale; sellers only see their own."""
    query = (select(Sale).options(selectinload(Sale.items).selectinload(SaleItem.product), selectinload(Sale.reseller))
             .order_by(Sale.created_at.desc(), Sale.id.desc()))
    if user.role != "admin":
        query = query.where(Sale.seller_id == user.id)
    if from_date or to_date:
        start, end = local_range_utc(from_date or date(2000, 1, 1), to_date or date(2100, 1, 1))
        query = query.where(Sale.created_at >= start, Sale.created_at < end)
    if status_filter:
        query = query.where(Sale.status == status_filter)
    return [to_out(s) for s in db.scalars(query.limit(limit).offset(offset)).all()]


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_out(load_sale(db, sale_id, user))


@router.post("/{sale_id}/cancel", response_model=SaleOut)
def cancel_sale(sale_id: int, body: SaleCancel, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Customer return or till mistake: puts everything back in stock. The sale is kept, marked "annulee"."""
    sale = load_sale(db, sale_id, admin)
    # Conditional UPDATE again: if two admins click "cancel" at once, only one succeeds,
    # so stock can't be put back twice.
    result = db.execute(update(Sale).where(Sale.id == sale.id, Sale.status == "validee")
                        .values(status="annulee", cancelled_at=datetime.now(timezone.utc),
                                cancelled_by_id=admin.id, cancel_reason=body.reason))
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette vente est déjà annulée")
    try:
        for item in sale.items:
            db.execute(update(Product).where(Product.id == item.product_id)
                       .values(quantity=Product.quantity + item.quantity))
            if item.serial_numbers:
                db.execute(update(SerialUnit).where(SerialUnit.serial.in_(item.serial_numbers))
                           .values(status="en_stock", sale_item_id=None)
                           .execution_options(synchronize_session=False))
            record_movement(db, product_id=item.product_id, change=item.quantity, reason="annulation",
                            user_id=admin.id, sale_id=sale.id, note=body.reason)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()   # reload from the database so the response shows the new status
    return to_out(load_sale(db, sale.id, admin))
