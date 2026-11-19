"""Test setup.

By default tests use a fresh in-memory SQLite database (fast, nothing to install).
Set TEST_DATABASE_URL to run the exact same tests against real PostgreSQL (CI does this).
"""
import os
import tempfile

os.environ.setdefault("BCRYPT_ROUNDS", "4")  # must run before app imports read the settings
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="boutique-media-"))  # photos never touch the real folder

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants import DEFAULT_CATEGORIES
from app.database import get_db
from app.main import app
from app.models import Base, Category, User
from app.security import hash_password

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def session_factory():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add_all(Category(name=n, position=i) for i, n in enumerate(DEFAULT_CATEGORIES, 1))
        db.add_all([
            User(email="admin@test.ma", full_name="Admin Test", role="admin", password_hash=hash_password("admin-pass-123")),
            User(email="vendeur@test.ma", full_name="Vendeur Test", role="vendeur", password_hash=hash_password("vendeur-pass-123")),
        ])
        db.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def fresh_login_limits():
    from app.ratelimit import login_limiter
    login_limiter._failures.clear()
    yield


@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, email, password):
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin@test.ma", "admin-pass-123")


@pytest.fixture
def seller(client):
    return login(client, "vendeur@test.ma", "vendeur-pass-123")


@pytest.fixture
def categories(client, admin):
    return {c["name"]: c["id"] for c in client.get("/api/categories", headers=admin).json()}


@pytest.fixture
def make_product(client, admin, categories):
    """make_product(stock=5) creates a product and (optionally) receives stock for it."""
    counter = {"n": 0}

    def _make(stock=0, serials=None, **overrides):
        counter["n"] += 1
        body = {"sku": f"REF-{counter['n']}", "name": f"Coque iPhone {counter['n']}", "brand": "Generic",
                "category_id": categories["Pochettes et coques"], "price_centimes": 15000, "cost_centimes": 8000,
                "low_stock_threshold": 2}
        body.update(overrides)
        response = client.post("/api/products", json=body, headers=admin)
        assert response.status_code == 201, response.text
        product = response.json()
        if serials:
            stock = len(serials)
        if stock:
            r = client.post(f"/api/products/{product['id']}/restock", headers=admin,
                            json={"quantity": stock, "serials": serials or []})
            assert r.status_code == 200, r.text
            product = r.json()
        return product
    return _make


@pytest.fixture
def make_phone(make_product, categories):
    def _make(serials, **overrides):
        body = {"name": "Samsung Galaxy A55", "brand": "Samsung", "category_id": categories["Téléphones"],
                "price_centimes": 399900, "cost_centimes": 340000, "tracks_serial": True}
        body.update(overrides)
        return make_product(serials=serials, **body)
    return _make


def sell(client, headers, items, **extra):
    return client.post("/api/sales", headers=headers, json={"items": items, **extra})
