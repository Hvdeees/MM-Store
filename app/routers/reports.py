"""Business reports (admin only). Cancelled sales are always excluded from money totals.

All the arithmetic (COUNT, SUM, GROUP BY) runs inside the database: it's faster and avoids loading
thousands of rows into Python just to add them up.
"""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, ResellerPayment, Sale, SaleItem
from app.schemas import DailyReport, DayTotal, PaymentBreakdown, TopProduct
from app.security import require_admin
from app.timeutils import local_date, local_range_utc

router = APIRouter(prefix="/api/reports", tags=["Rapports"], dependencies=[Depends(require_admin)])


def in_period(first_day: date, last_day: date):
    start, end = local_range_utc(first_day, last_day)
    return Sale.created_at >= start, Sale.created_at < end


def check_range(from_date: date, to_date: date) -> None:
    if to_date < from_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La date de fin est avant la date de début")
    if (to_date - from_date).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Période limitée à un an")


@router.get("/daily", response_model=DailyReport)
def daily_report(day: date, db: Session = Depends(get_db)):
    """Everything the manager needs at closing time for one day (Casablanca time)."""
    period = in_period(day, day)
    valid = (*period, Sale.status == "validee")

    sale_count, revenue, discounts = db.execute(
        select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_centimes), 0),
               func.coalesce(func.sum(Sale.discount_centimes), 0)).where(*valid)
    ).one()
    items_sold, cost = db.execute(
        select(func.coalesce(func.sum(SaleItem.quantity), 0),
               func.coalesce(func.sum(SaleItem.quantity * SaleItem.unit_cost_centimes), 0))
        .join(Sale, SaleItem.sale_id == Sale.id).where(*valid)
    ).one()
    cancelled = db.scalar(select(func.count(Sale.id)).where(*period, Sale.status == "annulee"))
    by_payment = db.execute(
        select(Sale.payment_method, func.count(Sale.id), func.sum(Sale.total_centimes))
        .where(*valid).group_by(Sale.payment_method).order_by(Sale.payment_method)
    ).all()

    start, end = local_range_utc(day, day)
    reseller_payments = db.scalar(select(func.coalesce(func.sum(ResellerPayment.amount_centimes), 0))
                                  .where(ResellerPayment.created_at >= start, ResellerPayment.created_at < end))

    return DailyReport(
        date=day, reseller_payments_centimes=reseller_payments, sale_count=sale_count, cancelled_count=cancelled, items_sold=items_sold,
        revenue_centimes=revenue, discount_centimes=discounts, cost_centimes=cost,
        margin_centimes=revenue - cost,
        by_payment=[PaymentBreakdown(payment_method=m, sale_count=c, total_centimes=t) for m, c, t in by_payment],
    )


@router.get("/top-products", response_model=list[TopProduct])
def top_products(from_date: date, to_date: date, limit: int = Query(default=10, ge=1, le=100),
                 db: Session = Depends(get_db)):
    check_range(from_date, to_date)
    revenue = func.sum(SaleItem.quantity * SaleItem.unit_price_centimes)
    rows = db.execute(
        select(Product.id, Product.name, func.sum(SaleItem.quantity), revenue)
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, SaleItem.sale_id == Sale.id)
        .where(*in_period(from_date, to_date), Sale.status == "validee")
        .group_by(Product.id, Product.name)
        .order_by(revenue.desc())
        .limit(limit)
    ).all()
    return [TopProduct(product_id=i, name=n, quantity_sold=q, revenue_centimes=r) for i, n, q, r in rows]


@router.get("/daily-totals", response_model=list[DayTotal])
def daily_totals(from_date: date, to_date: date, db: Session = Depends(get_db)):
    """Revenue per day over a period, for a chart. Days with no sales are included as zeros."""
    check_range(from_date, to_date)
    rows = db.execute(select(Sale.created_at, Sale.total_centimes)
                      .where(*in_period(from_date, to_date), Sale.status == "validee")).all()
    # Grouping by *local* date is done in Python: SQL date functions differ between SQLite and
    # PostgreSQL and don't know Morocco's timezone rules. One period's rows is a small amount of data.
    totals: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for created_at, total in rows:
        bucket = totals[local_date(created_at)]
        bucket[0] += 1
        bucket[1] += total
    days = [from_date + timedelta(days=n) for n in range((to_date - from_date).days + 1)]
    return [DayTotal(date=d, sale_count=totals[d][0], revenue_centimes=totals[d][1]) for d in days]
