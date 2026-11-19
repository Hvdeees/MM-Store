from tests.conftest import sell

IMEIS = ["356789012345671", "356789012345672", "356789012345673"]


def test_phone_restock_registers_each_imei(client, seller, make_phone):
    phone = make_phone(IMEIS)
    assert phone["quantity"] == 3
    serials = client.get(f"/api/products/{phone['id']}/serials", headers=seller).json()
    assert [s["serial"] for s in serials] == IMEIS


def test_restock_count_must_match_imeis(client, admin, make_phone):
    phone = make_phone(IMEIS[:1])
    response = client.post(f"/api/products/{phone['id']}/restock", headers=admin,
                           json={"quantity": 2, "serials": ["111"]})
    assert response.status_code == 400


def test_same_imei_cannot_be_registered_twice(client, admin, make_phone):
    phone = make_phone(IMEIS[:1])
    response = client.post(f"/api/products/{phone['id']}/restock", headers=admin,
                           json={"quantity": 1, "serials": [IMEIS[0]]})
    assert response.status_code == 409


def test_selling_a_phone_requires_its_imei(client, seller, make_phone):
    phone = make_phone(IMEIS)
    response = sell(client, seller, [{"product_id": phone["id"], "quantity": 1}])
    assert response.status_code == 400 and "IMEI" in response.json()["detail"]


def test_sell_phone_by_imei_then_lookup(client, seller, make_phone):
    phone = make_phone(IMEIS)
    response = sell(client, seller, [{"product_id": phone["id"], "quantity": 1, "serials": [IMEIS[1]]}],
                    customer_name="Youssef B.", customer_phone="0612345678")
    assert response.status_code == 201
    assert response.json()["items"][0]["serial_numbers"] == [IMEIS[1]]

    lookup = client.get(f"/api/serials/{IMEIS[1]}", headers=seller).json()
    assert lookup["status"] == "vendu" and lookup["customer_name"] == "Youssef B."
    assert lookup["sale_id"] == response.json()["id"]
    remaining = client.get(f"/api/products/{phone['id']}/serials", headers=seller).json()
    assert [s["serial"] for s in remaining] == [IMEIS[0], IMEIS[2]]


def test_same_imei_cannot_be_sold_twice(client, seller, make_phone):
    phone = make_phone(IMEIS)
    line = [{"product_id": phone["id"], "quantity": 1, "serials": [IMEIS[0]]}]
    assert sell(client, seller, line).status_code == 201
    assert sell(client, seller, line).status_code == 409


def test_imei_of_another_product_is_refused(client, seller, make_phone):
    samsung = make_phone(IMEIS[:1])
    iphone = make_phone(["990000000000001"], name="iPhone 15")
    response = sell(client, seller, [{"product_id": iphone["id"], "quantity": 1, "serials": [IMEIS[0]]}])
    assert response.status_code == 409
    assert client.get(f"/api/products/{samsung['id']}", headers=seller).json()["quantity"] == 1


def test_search_by_imei_finds_the_product(client, seller, make_phone, make_product):
    phone = make_phone(IMEIS)
    make_product(name="Câble")
    found = client.get("/api/products", params={"q": IMEIS[2]}, headers=seller).json()
    assert [p["id"] for p in found] == [phone["id"]]


def test_unknown_imei_lookup(client, seller):
    assert client.get("/api/serials/000", headers=seller).status_code == 404


def test_cannot_adjust_imei_products(client, admin, make_phone):
    phone = make_phone(IMEIS)
    response = client.post(f"/api/products/{phone['id']}/adjust", json={"change": -1, "note": "perdu"}, headers=admin)
    assert response.status_code == 400
