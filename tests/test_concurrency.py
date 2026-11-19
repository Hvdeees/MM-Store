"""Proof that the conditional UPDATE prevents overselling under real concurrency.

10 threads try to sell the LAST unit at the same instant. Exactly one must win.
Runs only on PostgreSQL (TEST_DATABASE_URL): SQLite in-memory has a single shared connection,
so it can't run transactions truly in parallel.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs PostgreSQL (set TEST_DATABASE_URL)")

THREADS = 10


def test_ten_sellers_one_last_item(client, seller, make_product, make_phone):
    case = make_product(stock=1)
    phone = make_phone(["356789012345671"])
    start_together = Barrier(THREADS)

    def attempt(product, serials):
        with TestClient(app) as own_client:   # each thread = its own HTTP client and DB session
            start_together.wait()             # release all threads at the same moment
            r = own_client.post("/api/sales", headers=seller,
                                json={"items": [{"product_id": product["id"], "quantity": 1, "serials": serials}]})
            return r.status_code

    for product, serials in ((case, []), (phone, ["356789012345671"])):
        with ThreadPoolExecutor(THREADS) as pool:
            codes = list(pool.map(lambda _: attempt(product, serials), range(THREADS)))
        assert codes.count(201) == 1, codes
        assert codes.count(409) == THREADS - 1, codes
        assert client.get(f"/api/products/{product['id']}", headers=seller).json()["quantity"] == 0
