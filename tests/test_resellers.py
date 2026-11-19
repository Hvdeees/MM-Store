from tests.conftest import sell


def make_reseller(client, admin, name="Phone House Agadir", **extra):
    response = client.post("/api/resellers", headers=admin, json={"name": name, "city": "Agadir", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def balance(client, headers, reseller):
    return client.get(f"/api/resellers/{reseller['id']}", headers=headers).json()["balance_centimes"]


def test_sale_on_credit_uses_reseller_price_and_creates_debt(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=50, price_centimes=9900, wholesale_price_centimes=6000)
    cable = make_product(stock=50, price_centimes=7900)            # no reseller price: normal price
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 10}, {"product_id": cable["id"], "quantity": 2}],
                    reseller_id=shop["id"])
    assert response.status_code == 201
    sale = response.json()
    assert sale["payment_method"] == "credit" and sale["reseller_name"] == "Phone House Agadir"
    assert sale["total_centimes"] == 10 * 6000 + 2 * 7900
    assert balance(client, seller, shop) == 75800


def test_partial_payment_at_the_till_then_later(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=50, price_centimes=10000)
    sell(client, seller, [{"product_id": case["id"], "quantity": 5}], reseller_id=shop["id"],
         paid_now_centimes=20000, paid_now_method="especes")
    assert balance(client, seller, shop) == 30000

    response = client.post(f"/api/resellers/{shop['id']}/payments", headers=seller,
                           json={"amount_centimes": 25000, "payment_method": "virement", "note": "Virement CIH"})
    assert response.status_code == 201
    out = response.json()
    assert (out["purchases_centimes"], out["paid_centimes"], out["balance_centimes"]) == (50000, 45000, 5000)


def test_statement_has_running_balance(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=50, price_centimes=10000)
    sell(client, seller, [{"product_id": case["id"], "quantity": 3}], reseller_id=shop["id"], paid_now_centimes=10000)
    client.post(f"/api/resellers/{shop['id']}/payments", headers=admin, json={"amount_centimes": 5000})
    statement = client.get(f"/api/resellers/{shop['id']}", headers=admin).json()["statement"]
    # newest first
    assert [(e["kind"], e["debit_centimes"], e["credit_centimes"], e["balance_centimes"]) for e in statement] == [
        ("paiement", 0, 5000, 15000),
        ("paiement", 0, 10000, 20000),
        ("achat", 30000, 0, 30000),
    ]
    assert statement[0]["by"] == "Admin Test"


def test_cancelled_sale_no_longer_counts_as_debt(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=50, price_centimes=10000)
    sale = sell(client, seller, [{"product_id": case["id"], "quantity": 2}], reseller_id=shop["id"]).json()
    client.post(f"/api/sales/{sale['id']}/cancel", headers=admin, json={"reason": "Marchandise rendue"})
    detail = client.get(f"/api/resellers/{shop['id']}", headers=admin).json()
    assert detail["balance_centimes"] == 0
    assert detail["statement"][0]["kind"] == "achat_annule"


def test_list_puts_biggest_debts_first(client, admin, seller, make_product):
    small = make_reseller(client, admin, "Small Shop")
    big = make_reseller(client, admin, "Big Shop")
    make_reseller(client, admin, "Nothing Owed")
    case = make_product(stock=100, price_centimes=10000)
    sell(client, seller, [{"product_id": case["id"], "quantity": 1}], reseller_id=small["id"])
    sell(client, seller, [{"product_id": case["id"], "quantity": 5}], reseller_id=big["id"])
    names = [r["name"] for r in client.get("/api/resellers", headers=seller).json()]
    assert names == ["Big Shop", "Small Shop", "Nothing Owed"]


def test_payment_rules(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=10, price_centimes=10000)
    # can't pay more than the purchase at the till
    response = sell(client, seller, [{"product_id": case["id"], "quantity": 1}], reseller_id=shop["id"], paid_now_centimes=20000)
    assert response.status_code == 400
    assert client.get(f"/api/products/{case['id']}", headers=seller).json()["quantity"] == 10   # rolled back
    # credit only for resellers, deposits only for resellers
    assert sell(client, seller, [{"product_id": case["id"], "quantity": 1}], payment_method="credit").status_code == 400
    assert sell(client, seller, [{"product_id": case["id"], "quantity": 1}], paid_now_centimes=100).status_code == 400
    # payments must be positive
    assert client.post(f"/api/resellers/{shop['id']}/payments", headers=seller, json={"amount_centimes": 0}).status_code == 422


def test_only_admin_manages_resellers(client, admin, seller):
    assert client.post("/api/resellers", headers=seller, json={"name": "X Shop"}).status_code == 403
    shop = make_reseller(client, admin)
    assert client.patch(f"/api/resellers/{shop['id']}", headers=seller, json={"phone": "06"}).status_code == 403
    assert client.post("/api/resellers", headers=admin, json={"name": "Phone House Agadir"}).status_code == 409


def test_deactivated_reseller_cannot_buy(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    client.patch(f"/api/resellers/{shop['id']}", headers=admin, json={"is_active": False})
    case = make_product(stock=10)
    assert sell(client, seller, [{"product_id": case["id"], "quantity": 1}], reseller_id=shop["id"]).status_code == 404


def test_daily_report_shows_credit_sales_and_reseller_payments(client, admin, seller, make_product):
    from datetime import datetime, timezone

    from app.timeutils import local_date
    shop = make_reseller(client, admin)
    case = make_product(stock=10, price_centimes=10000)
    sell(client, seller, [{"product_id": case["id"], "quantity": 2}], reseller_id=shop["id"], paid_now_centimes=5000)
    report = client.get("/api/reports/daily", params={"day": local_date(datetime.now(timezone.utc)).isoformat()}, headers=admin).json()
    assert {"payment_method": "credit", "sale_count": 1, "total_centimes": 20000} in report["by_payment"]
    assert report["reseller_payments_centimes"] == 5000


def test_unpaid_purchases_oldest_paid_first(client, admin, seller, db, make_product):
    """Payments pay off the oldest purchases first; money paid at the till goes to that purchase."""
    from datetime import datetime, timedelta, timezone

    from app.models import Sale
    shop = make_reseller(client, admin)
    case = make_product(stock=100, price_centimes=10000, name="Coque A15")
    first = sell(client, seller, [{"product_id": case["id"], "quantity": 3}], reseller_id=shop["id"]).json()          # 300 DH
    second = sell(client, seller, [{"product_id": case["id"], "quantity": 2}], reseller_id=shop["id"],
                  paid_now_centimes=5000).json()                                                                    # 200, 50 paid
    third = sell(client, seller, [{"product_id": case["id"], "quantity": 1}], reseller_id=shop["id"]).json()          # 100 DH
    base = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
    for n, sale in enumerate((first, second, third)):
        db.get(Sale, sale["id"]).created_at = base + timedelta(days=n)
    db.commit()
    client.post(f"/api/resellers/{shop['id']}/payments", headers=seller, json={"amount_centimes": 32000})       # 320 DH

    detail = client.get(f"/api/resellers/{shop['id']}", headers=seller).json()
    open_ = [(o["sale_id"], o["paid_centimes"], o["remaining_centimes"]) for o in detail["open_purchases"]]
    # 320 DH: 300 clears the first purchase, 20 goes on the second (which already had 50 paid at the till)
    assert open_ == [(second["id"], 7000, 13000), (third["id"], 0, 10000)]
    assert sum(o["remaining_centimes"] for o in detail["open_purchases"]) == detail["balance_centimes"]
    assert detail["open_purchases"][0]["items"] == [
        {"product_name": "Coque A15", "quantity": 2, "unit_price_centimes": 10000, "serial_numbers": []}]

    everything = client.get("/api/resellers/unpaid", headers=seller).json()
    assert [o["sale_id"] for o in everything] == [second["id"], third["id"]]
    assert everything[0]["reseller_name"] == "Phone House Agadir"


def test_fully_paid_reseller_has_no_open_purchases(client, admin, seller, make_product):
    shop = make_reseller(client, admin)
    case = make_product(stock=10, price_centimes=10000)
    sell(client, seller, [{"product_id": case["id"], "quantity": 1}], reseller_id=shop["id"], paid_now_centimes=10000)
    assert client.get(f"/api/resellers/{shop['id']}", headers=seller).json()["open_purchases"] == []
