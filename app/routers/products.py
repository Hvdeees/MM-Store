from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import SerialStatus
from app.database import get_db
from app.images import MAX_UPLOAD_BYTES, delete_product_image, save_product_image
from app.models import Category, Product, SerialUnit, StockMovement, User
from app.schemas import MovementOut, ProductCreate, ProductOut, ProductUpdate, Restock, SerialOut, StockAdjust
from app.security import get_current_user, require_admin
from app.stock import normalize_serials, record_movement

router = APIRouter(prefix="/api/products", tags=["Produits"])


def to_out(product: Product, user: User) -> ProductOut:
    out = ProductOut.model_validate(product)
    if user.role != "admin":
        out.cost_centimes = None   # sellers never see purchase prices or margins
    return out


def get_product_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produit introuvable")
    return product


def check_category(db: Session, category_id: int) -> None:
    if db.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Catégorie introuvable")


@router.get("", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(default=None, description="Recherche : nom, référence, marque ou IMEI"),
    category_id: int | None = None,
    low_stock: bool = False,
    include_inactive: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Same order as the category chips at the till: phones first, then tablets, computers, accessories...
    query = select(Product).join(Category, Product.category_id == Category.id).order_by(Category.position, Product.name)
    if q:
        pattern = f"%{q.strip()}%"
        # Scanning a phone's IMEI at the till finds its product directly.
        by_serial = select(SerialUnit.product_id).where(SerialUnit.serial == q.strip().upper())
        query = query.where(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern),
                                Product.brand.ilike(pattern), Product.id.in_(by_serial)))
    if category_id:
        query = query.where(Product.category_id == category_id)
    if low_stock:
        query = query.where(Product.quantity <= Product.low_stock_threshold)
    if not include_inactive:
        query = query.where(Product.is_active.is_(True))
    products = db.scalars(query.limit(limit).offset(offset)).all()
    return [to_out(p, user) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_out(get_product_or_404(db, product_id), user)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    check_category(db, body.category_id)
    product = Product(**body.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        # The UNIQUE constraint on sku is the real guard; checking first in Python would have a race condition.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"La référence « {body.sku} » existe déjà")
    db.refresh(product)
    return to_out(product, admin)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    product = get_product_or_404(db, product_id)
    changes = body.model_dump(exclude_unset=True)
    if "category_id" in changes:
        check_category(db, changes["category_id"])
    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return to_out(product, admin)


@router.post("/{product_id}/restock", response_model=ProductOut)
def restock(product_id: int, body: Restock, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Goods received from a supplier. Phones/computers need one IMEI or serial number per unit."""
    product = get_product_or_404(db, product_id)
    if product.tracks_serial:
        serials = normalize_serials(body.serials)
        if len(serials) != body.quantity:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Il faut exactement {body.quantity} IMEI / numéro(s) de série (reçu : {len(serials)})")
        already = db.scalars(select(SerialUnit.serial).where(SerialUnit.serial.in_(serials))).all()
        if already:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Déjà enregistré(s) : {', '.join(sorted(already))}")
        db.add_all(SerialUnit(product_id=product.id, serial=s) for s in serials)
    elif body.serials:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ce produit n'utilise pas de numéros de série")

    # "quantity = quantity + n" is computed inside the database, so two restocks at once can't overwrite each other.
    db.execute(update(Product).where(Product.id == product.id).values(quantity=Product.quantity + body.quantity))
    if body.cost_centimes is not None:
        product.cost_centimes = body.cost_centimes
    record_movement(db, product_id=product.id, change=body.quantity, reason="achat", user_id=admin.id, note=body.note)
    try:
        db.commit()
    except IntegrityError:   # two people registering the same IMEI at the same moment
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Un de ces numéros vient d'être enregistré")
    db.refresh(product)
    return to_out(product, admin)


@router.post("/{product_id}/adjust", response_model=ProductOut)
def adjust_stock(product_id: int, body: StockAdjust, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """Manual correction after a stock count (broken, lost, miscounted). Not for IMEI-tracked products."""
    product = get_product_or_404(db, product_id)
    if product.tracks_serial:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Les produits avec IMEI se gèrent unité par unité, pas par ajustement")
    # The WHERE clause refuses to push stock below zero, atomically.
    result = db.execute(update(Product)
                        .where(Product.id == product.id, Product.quantity + body.change >= 0)
                        .values(quantity=Product.quantity + body.change))
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Stock insuffisant (actuel : {product.quantity})")
    record_movement(db, product_id=product.id, change=body.change, reason="ajustement", user_id=admin.id,
                    note=body.note)
    db.commit()
    db.refresh(product)
    return to_out(product, admin)


@router.get("/{product_id}/movements", response_model=list[MovementOut], dependencies=[Depends(require_admin)])
def list_movements(product_id: int, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    get_product_or_404(db, product_id)
    movements = db.scalars(select(StockMovement).where(StockMovement.product_id == product_id)
                           .order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit)).all()
    return [MovementOut.model_validate(m).model_copy(update={"user_name": m.user.full_name if m.user else None})
            for m in movements]


@router.get("/{product_id}/serials", response_model=list[SerialOut], dependencies=[Depends(get_current_user)])
def list_serials(product_id: int, status_filter: SerialStatus | None = Query(default="en_stock", alias="status"),
                 db: Session = Depends(get_db)):
    get_product_or_404(db, product_id)
    query = select(SerialUnit).where(SerialUnit.product_id == product_id).order_by(SerialUnit.created_at)
    if status_filter:
        query = query.where(SerialUnit.status == status_filter)
    return db.scalars(query).all()


@router.post("/{product_id}/image", response_model=ProductOut)
def upload_image(product_id: int, file: UploadFile = File(...), admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """Add or replace the product's photo (JPG, PNG or WebP, 10 MB max). Taken with a phone works too."""
    product = get_product_or_404(db, product_id)
    data = file.file.read(MAX_UPLOAD_BYTES + 1)   # read at most 1 byte past the limit, never the whole file
    new_name = save_product_image(data)
    old_name, product.image_filename = product.image_filename, new_name
    db.commit()
    delete_product_image(old_name)               # only after the database points to the new photo
    db.refresh(product)
    return to_out(product, admin)


@router.delete("/{product_id}/image", response_model=ProductOut)
def remove_image(product_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    product = get_product_or_404(db, product_id)
    old_name, product.image_filename = product.image_filename, None
    db.commit()
    delete_product_image(old_name)
    db.refresh(product)
    return to_out(product, admin)
