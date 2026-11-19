"""Which reseller purchases are still unpaid?

Payments are not tied to one purchase (a shop pays "1 500 DH" against its whole account), so we
allocate them the way accountants do:
1. money paid at the till with a purchase goes to that purchase first;
2. every other payment (and anything left over) pays off the OLDEST unpaid purchases first (FIFO).
What's left on each purchase is what the shop still owes for it.

Like the balance, this is computed from the sales and payments every time, never stored, so it is
always consistent: the sum of what's left on every purchase equals the reseller's balance.
"""
from dataclasses import dataclass, field
from datetime import datetime

from app.models import ResellerPayment, Sale


@dataclass
class OpenPurchase:
    sale: Sale
    paid_centimes: int = 0
    payments: list[int] = field(default_factory=list)   # ids of the payments applied (for the record)

    @property
    def remaining_centimes(self) -> int:
        return self.sale.total_centimes - self.paid_centimes


def allocate(sales: list[Sale], payments: list[ResellerPayment]) -> list[OpenPurchase]:
    """Apply payments to the reseller's non-cancelled sales. Returns every sale with what was paid on it, oldest first."""
    valid = sorted((s for s in sales if s.status == "validee"), key=lambda s: (s.created_at, s.id))
    purchases = {s.id: OpenPurchase(s) for s in valid}
    pool = 0

    # 1. Paid at the till with a purchase: that purchase first, any excess goes to the pool.
    for payment in sorted(payments, key=lambda p: (p.created_at, p.id)):
        target = purchases.get(payment.sale_id) if payment.sale_id else None
        if target is None:
            pool += payment.amount_centimes
            continue
        applied = min(payment.amount_centimes, target.remaining_centimes)
        target.paid_centimes += applied
        pool += payment.amount_centimes - applied

    # 2. Everything else pays off the oldest purchases first.
    for purchase in purchases.values():
        if pool <= 0:
            break
        applied = min(pool, purchase.remaining_centimes)
        purchase.paid_centimes += applied
        pool -= applied
    return list(purchases.values())


def days_since(moment: datetime, now: datetime) -> int:
    if moment.tzinfo is None:
        from datetime import timezone
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, (now - moment).days)
