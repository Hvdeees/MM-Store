"""Turning store data into short, clear values for the AI to repeat to staff."""
from __future__ import annotations

import difflib
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("Africa/Casablanca")
PAYMENT_LABELS = {"especes": "espèces", "carte": "carte", "virement": "virement", "cheque": "chèque", "credit": "à crédit (revendeur)"}


def dh(centimes: int | None) -> str | None:
    """129950 -> '1 299,50 DH' (French formatting, as the staff write it)."""
    if centimes is None:
        return None
    sign = "-" if centimes < 0 else ""
    whole, cents = divmod(abs(centimes), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{cents:02d} DH"


def to_centimes(amount_dh: float) -> int:
    return round(amount_dh * 100)


def store_today() -> str:
    return datetime.now(timezone.utc).astimezone(STORE_TZ).date().isoformat()


def local_time(iso: str) -> str:
    """'2026-11-17T22:15:00+00:00' -> '17/11/2026 22:15' in Casablanca time."""
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(STORE_TZ).strftime("%d/%m/%Y %H:%M")


def plain(text: str) -> str:
    """Lowercase, no accents: 'Pochettes et coques' -> 'pochettes et coques', 'Écouteurs' -> 'ecouteurs'."""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower().strip()


def best_matches(query: str, names: list[str], cutoff: float = 0.6) -> list[str]:
    """Names that contain the query, else names that look like it (typos, missing accents, 'phone hous')."""
    q = plain(query)
    contains = [n for n in names if q and q in plain(n)]
    if contains:
        return contains
    by_plain = {plain(n): n for n in names}
    return [by_plain[m] for m in difflib.get_close_matches(q, list(by_plain), n=5, cutoff=cutoff)]
