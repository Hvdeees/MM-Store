from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category
from app.schemas import CategoryIn, CategoryOut
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/categories", tags=["Catégories"])


@router.get("", response_model=list[CategoryOut], dependencies=[Depends(get_current_user)])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.position, Category.name)).all()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    # New categories go at the end of the list.
    last = db.scalar(select(func.max(Category.position))) or 0
    category = Category(name=body.name, position=last + 1)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette catégorie existe déjà")
    return category


@router.patch("/{category_id}", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def rename_category(category_id: int, body: CategoryIn, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    category.name = body.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette catégorie existe déjà")
    return category
