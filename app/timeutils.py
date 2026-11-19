"""Turning a store-local calendar day into a UTC time range.

Sales are stored in UTC. "Sales of 18 November" means midnight-to-midnight *in Casablanca*, which is a
different UTC window (and the offset changes during Ramadan). Getting this wrong puts late-evening sales
on the wrong day in reports, a classic real-world bug.
"""
from datetime import date, datetime, time, timedelta, timezone

from app.config import settings


def local_midnight_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=settings.store_timezone).astimezone(timezone.utc)


def local_range_utc(first_day: date, last_day: date) -> tuple[datetime, datetime]:
    """[start, end) in UTC covering first_day through last_day inclusive, in store time."""
    return local_midnight_utc(first_day), local_midnight_utc(last_day + timedelta(days=1))


def local_date(moment: datetime) -> date:
    if moment.tzinfo is None:          # SQLite returns naive datetimes; they're UTC by our convention
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(settings.store_timezone).date()
