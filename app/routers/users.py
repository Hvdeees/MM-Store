"""Staff accounts. Admin only."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password, require_admin

router = APIRouter(prefix="/api/users", tags=["Utilisateurs"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.full_name)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet email")
    user = User(email=email, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    changes = body.model_dump(exclude_unset=True)
    # Safety: an admin can't lock themselves out (otherwise the store could end up with no admin at all).
    if user.id == admin.id and (changes.get("is_active") is False or changes.get("role") == "vendeur"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vous ne pouvez pas désactiver ou rétrograder votre propre compte")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return user
