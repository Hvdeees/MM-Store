"""Revendeurs: other shops that buy from MM Store, usually on credit.

What a reseller owes is never stored: it is always computed as
    sum(their non-cancelled sales) - sum(their payments)
so it can't drift out of sync, and cancelling a sale automatically removes it from their debt.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.ledger import allocate, days_since
from app.models import Reseller, ResellerPayment, Sale, SaleItem, User
from app.schemas import (OpenPurchaseItem, OpenPurchaseOut, ResellerDetail, ResellerIn, ResellerOut,
                         ResellerPaymentIn, ResellerUpdate, StatementEntry)
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/resellers", tags=["Revendeurs"])

PAYMENT_LABELS = {"especes": "espèces", "carte": "carte", "virement": "virement", "cheque": "chèque"}


def _totals_query():
    """One row per reseller with their purchases, payments and last activity: two grouped subqueries, one query."""
    purchases = (select(Sale.reseller_id.label("rid"), func.sum(Sale.total_centimes).label("amount"),
                        func.max(Sale.created_at).label("last"))
                 .where(Sale.reseller_id.is_not(None), Sale.status == "validee")
                 .group_by(Sale.reseller_id).subquery())
    payments = (select(ResellerPayment.reseller_id.label("rid"), func.sum(ResellerPayment.amount_centimes).label("amount"),
                       func.max(ResellerPayment.created_at).label("last"))
                .group_by(ResellerPayment.reseller_id).subquery())
    return (select(Reseller, func.coalesce(purchases.c.amount, 0), func.coalesce(payments.c.amount, 0),
                   purchases.c.last, payments.c.last)
            .outerjoin(purchases, purchases.c.rid == Reseller.id)
            .outerjoin(payments, payments.c.rid == Reseller.id))


def _to_out(reseller: Reseller, bought: int, paid: int, last_sale, last_payment) -> ResellerOut:
    last = max((d for d in (last_sale, last_payment) if d is not None), default=None)
    return ResellerOut(id=reseller.id, name=reseller.name, contact_name=reseller.contact_name, phone=reseller.phone,
                       city=reseller.city, notes=reseller.notes, is_active=reseller.is_active,
                       purchases_centimes=bought, paid_centimes=paid, balance_centimes=bought - paid, last_activity=last)


def _get_out(db: Session, reseller_id: int) -> ResellerOut:
    row = db.execute(_totals_query().where(Reseller.id == reseller_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revendeur introuvable")
    return _to_out(*row)


def _open_purchases(reseller: Reseller, sales: list[Sale], payments: list[ResellerPayment]) -> list[OpenPurchaseOut]:
    now = datetime.now(timezone.utc)
    return [OpenPurchaseOut(
        sale_id=p.sale.id, reseller_id=reseller.id, reseller_name=reseller.name, date=p.sale.created_at,
        days_old=days_since(p.sale.created_at, now), total_centimes=p.sale.total_centimes,
        paid_centimes=p.paid_centimes, remaining_centimes=p.remaining_centimes, seller_name=p.sale.seller.full_name,
        items=[OpenPurchaseItem(product_name=i.product.name, quantity=i.quantity, unit_price_centimes=i.unit_price_centimes,
                                serial_numbers=i.serial_numbers or []) for i in p.sale.items])
        for p in allocate(sales, payments) if p.remaining_centimes > 0]


def _load(db: Session, reseller_ids: list[int]):
    sales = db.scalars(select(Sale).where(Sale.reseller_id.in_(reseller_ids))
                       .options(selectinload(Sale.items).selectinload(SaleItem.product), selectinload(Sale.seller))).all()
    payments = db.scalars(select(ResellerPayment).where(ResellerPayment.reseller_id.in_(reseller_ids))
                          .options(selectinload(ResellerPayment.user))).all()
    return sales, payments


@router.get("/unpaid", response_model=list[OpenPurchaseOut], dependencies=[Depends(get_current_user)])
def all_unpaid(db: Session = Depends(get_db)):
    """Every purchase not fully paid yet, all resellers together, oldest first: the list to chase."""
    resellers = db.scalars(select(Reseller)).all()
    sales, payments = _load(db, [r.id for r in resellers])
    result = []
    for reseller in resellers:
        result += _open_purchases(reseller, [s for s in sales if s.reseller_id == reseller.id],
                                  [p for p in payments if p.reseller_id == reseller.id])
    return sorted(result, key=lambda o: (o.date, o.sale_id))


@router.get("", response_model=list[ResellerOut], dependencies=[Depends(get_current_user)])
def list_resellers(q: str | None = None, include_inactive: bool = False, db: Session = Depends(get_db)):
    query = _totals_query()
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Reseller.name.ilike(pattern), Reseller.city.ilike(pattern),
                                Reseller.contact_name.ilike(pattern), Reseller.phone.ilike(pattern)))
    if not include_inactive:
        query = query.where(Reseller.is_active.is_(True))
    resellers = [_to_out(*row) for row in db.execute(query).all()]
    # Those who owe the most first: that's who the manager needs to call.
    return sorted(resellers, key=lambda r: (-r.balance_centimes, r.name.lower()))


@router.post("", response_model=ResellerOut, status_code=status.HTTP_201_CREATED)
def create_reseller(body: ResellerIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    reseller = Reseller(**body.model_dump())
    db.add(reseller)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Un revendeur s'appelle déjà « {body.name} »")
    return _get_out(db, reseller.id)


@router.patch("/{reseller_id}", response_model=ResellerOut)
def update_reseller(reseller_id: int, body: ResellerUpdate, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    reseller = db.get(Reseller, reseller_id)
    if reseller is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revendeur introuvable")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(reseller, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Un autre revendeur porte déjà ce nom")
    return _get_out(db, reseller.id)


@router.get("/{reseller_id}", response_model=ResellerDetail, dependencies=[Depends(get_current_user)])
def reseller_statement(reseller_id: int, db: Session = Depends(get_db)):
    """Their account statement ("relevé"): every purchase and payment with the running balance."""
    summary = _get_out(db, reseller_id)
    sales, payments = _load(db, [reseller_id])

    events = []
    for sale in sales:
        items = sum(i.quantity for i in sale.items)
        if sale.status == "validee":
            events.append((sale.created_at, StatementEntry(date=sale.created_at, kind="achat", sale_id=sale.id,
                           label=f"Achat n° {sale.id} ({items} article{'s' if items > 1 else ''})",
                           debit_centimes=sale.total_centimes, balance_centimes=0, by=sale.seller.full_name)))
        else:   # shown for the record, but it no longer counts
            events.append((sale.created_at, StatementEntry(date=sale.created_at, kind="achat_annule", sale_id=sale.id,
                           label=f"Achat n° {sale.id} annulé : {sale.cancel_reason}", balance_centimes=0,
                           by=sale.seller.full_name)))
    for payment in payments:
        label = f"Paiement en {PAYMENT_LABELS[payment.payment_method]}" + (f" : {payment.note}" if payment.note else "")
        events.append((payment.created_at, StatementEntry(date=payment.created_at, kind="paiement", label=label,
                       sale_id=payment.sale_id, credit_centimes=payment.amount_centimes, balance_centimes=0,
                       by=payment.user.full_name)))

    # Oldest first to compute the running balance; a payment made with a sale comes right after that sale.
    events.sort(key=lambda e: (e[0], e[1].kind == "paiement"))
    balance = 0
    for _, entry in events:
        balance += entry.debit_centimes - entry.credit_centimes
        entry.balance_centimes = balance
    return ResellerDetail(**summary.model_dump(), statement=[e for _, e in reversed(events)],
                          open_purchases=_open_purchases(db.get(Reseller, reseller_id), sales, payments))


@router.post("/{reseller_id}/payments", response_model=ResellerOut, status_code=status.HTTP_201_CREATED)
def record_payment(reseller_id: int, body: ResellerPaymentIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Money received from a reseller. Any seller can record it; the statement shows who did."""
    if db.get(Reseller, reseller_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revendeur introuvable")
    db.add(ResellerPayment(reseller_id=reseller_id, amount_centimes=body.amount_centimes,
                           payment_method=body.payment_method, note=body.note, user_id=user.id))
    db.commit()
    return _get_out(db, reseller_id)
