"""IMEI / serial number lookup: "was this phone bought here, when, and by whom?" (warranty, returns, theft)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SaleItem, SerialUnit
from app.schemas import SerialLookup
from app.security import get_current_user

router = APIRouter(prefix="/api/serials", tags=["IMEI / Numéros de série"], dependencies=[Depends(get_current_user)])


@router.get("/{serial}", response_model=SerialLookup)
def lookup_serial(serial: str, db: Session = Depends(get_db)):
    unit = db.scalar(select(SerialUnit).where(SerialUnit.serial == serial.strip().upper()))
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "IMEI / numéro de série inconnu")
    result = SerialLookup(serial=unit.serial, status=unit.status, product_id=unit.product_id,
                          product_name=unit.product.name, received_at=unit.created_at)
    if unit.sale_item_id:
        sale = db.get(SaleItem, unit.sale_item_id).sale
        result.sale_id, result.sold_at = sale.id, sale.created_at
        result.customer_name, result.customer_phone = sale.customer_name, sale.customer_phone
    return result
