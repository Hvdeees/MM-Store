def test_create_product_starts_with_zero_stock(make_product):
    product = make_product()
    assert product["quantity"] == 0 and product["category"]["name"] == "Pochettes et coques"


def test_duplicate_sku_rejected(client, admin, make_product, categories):
    make_product(sku="DUP")
    body = {"sku": "DUP", "name": "Autre", "category_id": categories["Pochettes et coques"], "price_centimes": 100}
    response = client.post("/api/products", json=body, headers=admin)
    assert response.status_code == 409 and "DUP" in response.json()["detail"]


def test_unknown_category_rejected(client, admin):
    body = {"sku": "X", "name": "X", "category_id": 999, "price_centimes": 100}
    assert client.post("/api/products", json=body, headers=admin).status_code == 400


def test_seller_does_not_see_cost(client, seller, admin, make_product):
    product = make_product(cost_centimes=8000)
    assert client.get(f"/api/products/{product['id']}", headers=admin).json()["cost_centimes"] == 8000
    assert client.get(f"/api/products/{product['id']}", headers=seller).json()["cost_centimes"] is None


def test_restock_and_movement_history(client, admin, make_product):
    product = make_product()
    response = client.post(f"/api/products/{product['id']}/restock", headers=admin,
                           json={"quantity": 10, "note": "Facture fournisseur 42", "cost_centimes": 7500})
    assert response.json()["quantity"] == 10 and response.json()["cost_centimes"] == 7500
    history = client.get(f"/api/products/{product['id']}/movements", headers=admin).json()
    assert history[0]["change"] == 10 and history[0]["reason"] == "achat" and history[0]["user_name"] == "Admin Test"


def test_search_by_name_brand_and_low_stock(client, seller, make_product):
    make_product(name="Chargeur USB-C 20W", brand="Anker", stock=1)
    make_product(name="Écouteurs sans fil", brand="JBL", stock=50)
    names = lambda params: [p["name"] for p in client.get("/api/products", params=params, headers=seller).json()]
    assert names({"q": "anker"}) == ["Chargeur USB-C 20W"]
    assert names({"low_stock": True}) == ["Chargeur USB-C 20W"]


def test_archived_products_hidden_by_default(client, admin, make_product):
    product = make_product()
    client.patch(f"/api/products/{product['id']}", json={"is_active": False}, headers=admin)
    assert client.get("/api/products", headers=admin).json() == []
    assert len(client.get("/api/products", params={"include_inactive": True}, headers=admin).json()) == 1


def test_adjust_stock_requires_reason_and_cannot_go_negative(client, admin, make_product):
    product = make_product(stock=3)
    url = f"/api/products/{product['id']}/adjust"
    assert client.post(url, json={"change": -1}, headers=admin).status_code == 422
    assert client.post(url, json={"change": -5, "note": "casse"}, headers=admin).status_code == 409
    response = client.post(url, json={"change": -1, "note": "Écran cassé"}, headers=admin)
    assert response.json()["quantity"] == 2


def test_unknown_fields_are_rejected(client, admin, categories):
    """Typos like 'qantity' are caught instead of silently ignored. Stock can't be set at creation."""
    body = {"sku": "X", "name": "X", "category_id": categories["Pochettes et coques"], "price_centimes": 1, "quantity": 99}
    assert client.post("/api/products", json=body, headers=admin).status_code == 422


def test_products_are_listed_in_category_order(client, seller, make_product, categories):
    """At the till, phones come before accessories (category order), then alphabetical."""
    make_product(name="Adaptateur", category_id=categories["Adaptateurs"])
    make_product(name="Zeta phone", category_id=categories["Téléphones"])
    make_product(name="Alpha phone", category_id=categories["Téléphones"])
    names = [p["name"] for p in client.get("/api/products", headers=seller).json()]
    assert names == ["Alpha phone", "Zeta phone", "Adaptateur"]
