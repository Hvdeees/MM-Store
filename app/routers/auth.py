from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.ratelimit import login_limiter
from app.schemas import LoginResponse, PasswordChange, UserOut
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


@router.post("/login", response_model=LoginResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Standard OAuth2 password form: fields `username` (the email) and `password`."""
    email = form.username.strip().lower()
    ip = request.client.host if request.client else "unknown"   # the real visitor's address behind the HTTPS proxy
    wait = login_limiter.retry_after(email, ip)
    if wait:
        minutes = (wait + 59) // 60
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Trop de tentatives. Réessayez dans {minutes} minute{'s' if minutes > 1 else ''}.",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    # Same message whether the email or the password is wrong: don't tell attackers which emails exist.
    if user is None or not verify_password(form.password, user.password_hash):
        login_limiter.failed(email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect")
    login_limiter.succeeded(email)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce compte est désactivé")
    return LoginResponse(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
