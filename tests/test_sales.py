from tests.conftest import sell


def stock_of(client, headers, product):
    return client.get(f"/api/products/{product['id']}", headers=headers).json()["quantity"]


def test_sale_reduces_stock_and_computes_totals(client, seller, make_product):
    case = make_product(stock=10, price_centimes=15000)
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 3}],
                    discount_centimes=5000, payment_method="carte")
    assert response.status_code == 201
    sale = response.json()
    assert (sale["subtotal_centimes"], sale["discount_centimes"], sale["total_centimes"]) == (45000, 5000, 40000)
    assert sale["seller_name"] == "Vendeur Test" and sale["status"] == "validee"
    assert stock_of(client, seller, case) == 7


def test_cannot_oversell(client, seller, make_product):
    case = make_product(stock=2)
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 3}])
    assert response.status_code == 409
    assert "Stock insuffisant" in response.json()["detail"]
    assert stock_of(client, seller, case) == 2


def test_failed_sale_changes_nothing(client, admin, seller, make_product, make_phone):
    """Line 2 fails, so line 1's stock, the IMEI and the sale itself must all be rolled back."""
    case = make_product(stock=10)
    phone = make_phone(["356789012345671"])
    empty = make_product(stock=0)
    items = [{"product_id": case["id"], "quantity": 1},
             {"product_id": phone["id"], "quantity": 1, "serials": ["356789012345671"]},
             {"product_id": empty["id"], "quantity": 1}]
    assert sell(client, seller, items).status_code == 409
    assert stock_of(client, seller, case) == 10 and stock_of(client, seller, phone) == 1
    assert client.get("/api/serials/356789012345671", headers=seller).json()["status"] == "en_stock"
    assert client.get("/api/sales", headers=admin).json() == []
    assert len(client.get(f"/api/products/{case['id']}/movements", headers=admin).json()) == 1  # only the restock


def test_discount_cannot_exceed_subtotal(client, seller, make_product):
    case = make_product(stock=5, price_centimes=1000)
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 1}], discount_centimes=2000)
    assert response.status_code == 400
    assert stock_of(client, seller, case) == 5


def test_price_is_frozen_at_time_of_sale(client, admin, seller, make_product):
    case = make_product(stock=5, price_centimes=15000)
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
    client.patch(f"/api/products/{case['id']}", json={"price_centimes": 99900}, headers=admin)
    assert client.get(f"/api/sales/{sale['id']}", headers=seller).json()["total_centimes"] == 15000


def test_repeated_lines_are_merged(client, seller, make_product):
    case = make_product(stock=10)
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 1},
                                 {"product_id": case["id"], "quantity": 2}]).json()
    assert len(sale["items"]) == 1 and sale["items"][0]["quantity"] == 3


def test_archived_product_cannot_be_sold(client, admin, seller, make_product):
    case = make_product(stock=5)
    client.patch(f"/api/products/{case['id']}", json={"is_active": False}, headers=admin)
    assert sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).status_code == 404


def test_invalid_payment_method(client, seller, make_product):
    case = make_product(stock=5)
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 1}], payment_method="bitcoin")
    assert response.status_code == 422


def test_seller_only_sees_own_sales(client, admin, seller, make_product):
    case = make_product(stock=10)
    mine = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
    admins = sell(client, admin, [{"product_id": case["id"], "quantity": 1}]).json()
    assert [s["id"] for s in client.get("/api/sales", headers=seller).json()] == [mine["id"]]
    assert client.get(f"/api/sales/{admins['id']}", headers=seller).status_code == 404
    assert len(client.get("/api/sales", headers=admin).json()) == 2


def test_cancel_sale_restores_stock_and_imei(client, admin, seller, make_product, make_phone):
    case = make_product(stock=5)
    phone = make_phone(["356789012345671"])
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 2},
                                 {"product_id": phone["id"], "quantity": 1, "serials": ["356789012345671"]}]).json()
    response = client.post(f"/api/sales/{sale['id']}/cancel", json={"reason": "Retour client"}, headers=admin)
    assert response.status_code == 200
    assert response.json()["status"] == "annulee" and response.json()["cancel_reason"] == "Retour client"
    assert stock_of(client, admin, case) == 5 and stock_of(client, admin, phone) == 1
    lookup = client.get("/api/serials/356789012345671", headers=admin).json()
    assert lookup["status"] == "en_stock" and lookup["sale_id"] is None
    # The receipt still shows which IMEI was on it, for the history.
    assert response.json()["items"][1]["serial_numbers"] == ["356789012345671"]


def test_cannot_cancel_twice(client, admin, seller, make_product):
    case = make_product(stock=5)
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
    url = f"/api/sales/{sale['id']}/cancel"
    assert client.post(url, json={"reason": "Erreur"}, headers=admin).status_code == 200
    assert client.post(url, json={"reason": "Erreur"}, headers=admin).status_code == 409
    assert stock_of(client, admin, case) == 5   # restored once, not twice


def test_seller_cannot_cancel(client, seller, make_product):
    case = make_product(stock=5)
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
    assert client.post(f"/api/sales/{sale['id']}/cancel", json={"reason": "x" * 5}, headers=seller).status_code == 403
