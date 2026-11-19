"""Shared stock helpers used by the products and sales routers."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import StockMovement


def normalize_serials(serials: list[str]) -> list[str]:
    """Trim + uppercase IMEIs/serials, and refuse empty or repeated ones."""
    cleaned = [s.strip().upper() for s in serials]
    if any(not s or len(s) > 64 for s in cleaned):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Numéro de série / IMEI vide ou trop long")
    duplicates = sorted({s for s in cleaned if cleaned.count(s) > 1})
    if duplicates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Numéro(s) en double : {', '.join(duplicates)}")
    return cleaned


def record_movement(db: Session, *, product_id: int, change: int, reason: str,
                    user_id: int | None, sale_id: int | None = None, note: str | None = None) -> None:
    db.add(StockMovement(product_id=product_id, change=change, reason=reason,
                         user_id=user_id, sale_id=sale_id, note=note))
