from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.images import ensure_media_dir
from app.routers import auth, categories, products, reports, resellers, sales, serials, users

app = FastAPI(
    title=f"{settings.store_name} — API de gestion",
    description="Stock, ventes, IMEI et rapports pour un magasin de téléphones, ordinateurs et accessoires.",
    version="1.0.0",
)

for module in (auth, users, categories, products, serials, sales, resellers, reports):
    app.include_router(module.router)


FIELD_NAMES = {"price_centimes": "prix", "cost_centimes": "prix d'achat", "quantity": "quantité",
               "email": "email", "password": "mot de passe", "new_password": "nouveau mot de passe",
               "name": "nom", "sku": "référence", "full_name": "nom complet", "items": "articles",
               "note": "motif", "reason": "motif", "change": "variation", "category_id": "catégorie",
               "discount_centimes": "remise", "payment_method": "mode de paiement",
               "amount_centimes": "montant", "paid_now_centimes": "montant payé", "wholesale_price_centimes": "prix revendeur",
               "phone": "téléphone", "city": "ville", "contact_name": "contact"}


@app.exception_handler(RequestValidationError)
async def validation_error_in_french(request: Request, exc: RequestValidationError):
    """Pydantic's validation messages are in English; give staff a short French summary instead,
    and keep the technical details in `errors` for developers."""
    fields = []
    for error in exc.errors():
        field = str(error["loc"][-1]) if error["loc"] else "?"
        name = FIELD_NAMES.get(field, field)
        if name not in fields:
            fields.append(name)
    return JSONResponse(status_code=422,
                        content={"detail": f"Données invalides : {', '.join(fields)}", "errors": exc.errors()})


@app.get("/api/health", tags=["Système"])
def health():
    """Used by hosting platforms to check the app is alive, and by the web interface for the store name."""
    return {"status": "ok", "store_name": settings.store_name}


# Product photos, saved by app/images.py.
ensure_media_dir()
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

# The French web interface (plain HTML/JS) is served from the same server. Mounted last so /api/* wins.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
