"""Test setup: the REAL MM Store app runs in-process on a fresh in-memory database, the MCP server talks to it
through httpx's ASGI transport (no network), and the tests talk to the MCP server with the official MCP client,
exactly like Claude Desktop would. No AI model is involved: tests call the tools directly.

MM Store's code is found through MMSTORE_APP_DIR, the parent folder (this repo's layout), or a sibling folder named boutique-manager or boutique.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="mmstore-ai-media-"))
os.environ.setdefault("PYTHONTZPATH", "")

_here = Path(__file__).resolve().parents[1]
_candidates = [os.getenv("MMSTORE_APP_DIR"), _here.parent, _here.parent / "boutique-manager", _here.parent / "boutique"]
APP_DIR = next((Path(c) for c in _candidates if c and (Path(c) / "app" / "main.py").exists()), None)
if APP_DIR is None:
    raise RuntimeError("MM Store introuvable : définissez MMSTORE_APP_DIR (dossier qui contient app/main.py)")
sys.path.insert(0, str(APP_DIR))

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.constants import DEFAULT_CATEGORIES  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app as store_app  # noqa: E402
from app.models import Base, Category, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from mmstore_ai.client import StoreClient  # noqa: E402

ADMIN = ("gerant@test.ma", "admin-pass-123")
ASSISTANT = ("assistant@test.ma", "assistant-pass-1")     # the AI's own account (seller role)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add_all(Category(name=n, position=i) for i, n in enumerate(DEFAULT_CATEGORIES, 1))
        db.add_all([User(email=ADMIN[0], full_name="Gérant", role="admin", password_hash=hash_password(ADMIN[1])),
                    User(email=ASSISTANT[0], full_name="Assistant IA", role="vendeur", password_hash=hash_password(ASSISTANT[1]))])
        db.commit()

    def override():
        with factory() as session:
            yield session

    store_app.dependency_overrides[get_db] = override
    yield factory
    store_app.dependency_overrides.clear()
    engine.dispose()


def make_store_client(account) -> StoreClient:
    return StoreClient("http://mmstore", *account, transport=httpx.ASGITransport(app=store_app))


@pytest.fixture
async def admin_api(store_db):
    """A plain HTTP client logged in as the manager, to set up test data through MM Store's own API."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=store_app), base_url="http://mmstore/api") as http:
        token = (await http.post("/auth/login", data={"username": ADMIN[0], "password": ADMIN[1]})).json()["access_token"]
        http.headers["Authorization"] = f"Bearer {token}"
        yield http


@pytest.fixture
async def shop(admin_api):
    """A small store: products, IMEIs, two resellers, a few sales. Returns ids by name."""
    cats = {c["name"]: c["id"] for c in (await admin_api.get("/categories")).json()}

    async def product(name, category, price, stock=0, serials=None, wholesale=None, threshold=3):
        body = {"sku": name[:10].upper().replace(" ", "-"), "name": name, "brand": "Test", "category_id": cats[category],
                "price_centimes": price, "cost_centimes": price // 2, "wholesale_price_centimes": wholesale,
                "low_stock_threshold": threshold, "tracks_serial": bool(serials)}
        p = (await admin_api.post("/products", json=body)).json()
        qty = len(serials) if serials else stock
        if qty:
            await admin_api.post(f"/products/{p['id']}/restock", json={"quantity": qty, "serials": serials or []})
        return p["id"]

    ids = {
        "case": await product("Coque silicone Galaxy A55", "Pochettes et coques", 9900, stock=40, wholesale=6000),
        "charger": await product("Chargeur USB-C 20W", "Chargeurs", 19900, stock=2),
        "phone": await product("Samsung Galaxy A55", "Téléphones", 399900, serials=["356789012345671", "356789012345672"]),
    }
    for name in ("Phone House Agadir", "Tech Corner Casablanca"):
        r = (await admin_api.post("/resellers", json={"name": name, "city": name.split()[-1]})).json()
        ids[name] = r["id"]
    await admin_api.post("/sales", json={"reseller_id": ids["Phone House Agadir"], "paid_now_centimes": 10000,
                                         "items": [{"product_id": ids["case"], "quantity": 10},
                                                   {"product_id": ids["phone"], "quantity": 1, "serials": ["356789012345671"]}]})
    await admin_api.post("/sales", json={"customer_name": "Youssef", "payment_method": "carte",
                                         "items": [{"product_id": ids["case"], "quantity": 1}]})
    return ids
