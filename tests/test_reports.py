from datetime import datetime, timezone

from app.models import Sale
from tests.conftest import sell


def move_sale(db, sale_id, when):
    db.get(Sale, sale_id).created_at = when
    db.commit()


def test_daily_report(client, admin, seller, db, make_product, make_phone):
    case = make_product(stock=10, price_centimes=15000, cost_centimes=8000)
    phone = make_phone(["356789012345671"], price_centimes=399900, cost_centimes=340000)

    s1 = sell(client, seller, [{"product_id": case["id"], "quantity": 2}], payment_method="especes").json()
    s2 = sell(client, seller, [{"product_id": phone["id"], "quantity": 1, "serials": ["356789012345671"]}],
              payment_method="carte", discount_centimes=9900).json()
    s3 = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
    client.post(f"/api/sales/{s3['id']}/cancel", json={"reason": "Erreur caisse"}, headers=admin)
    for sale_id in (s1["id"], s2["id"], s3["id"]):
        move_sale(db, sale_id, datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc))

    report = client.get("/api/reports/daily", params={"day": "2026-11-18"}, headers=admin).json()
    assert report["sale_count"] == 2 and report["cancelled_count"] == 1
    assert report["items_sold"] == 3
    assert report["revenue_centimes"] == 30000 + 390000
    assert report["discount_centimes"] == 9900
    assert report["cost_centimes"] == 16000 + 340000
    assert report["margin_centimes"] == 420000 - 356000
    assert report["by_payment"] == [
        {"payment_method": "carte", "sale_count": 1, "total_centimes": 390000},
        {"payment_method": "especes", "sale_count": 1, "total_centimes": 30000},
    ]


def test_late_evening_sale_counts_on_moroccan_day(client, admin, seller, db, make_product):
    """Uses the official timezone rules, not a fixed offset.
    June 2026: Morocco was UTC+1, so 23:30 local on 18 June = 22:30 UTC on 18 June... and 00:30 local
    on 19 June = 23:30 UTC on the 18th, which must count on the 19th.
    November 2026: Morocco is back on UTC+0 (since 20 Sept 2026), so 23:30 UTC = 23:30 local."""
    case = make_product(stock=5)

    def sale_at(moment):
        sale = sell(client, seller, [{"product_id": case["id"], "quantity": 1}]).json()
        move_sale(db, sale["id"], moment)

    def count(day):
        return client.get("/api/reports/daily", params={"day": day}, headers=admin).json()["sale_count"]

    sale_at(datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc))    # 00:30 on 19 June in Casablanca (UTC+1)
    assert count("2026-06-18") == 0 and count("2026-06-19") == 1
    sale_at(datetime(2026, 11, 18, 23, 30, tzinfo=timezone.utc))   # 23:30 on 18 Nov in Casablanca (UTC+0)
    assert count("2026-11-18") == 1 and count("2026-11-19") == 0


def test_empty_day_returns_zeros(client, admin):
    report = client.get("/api/reports/daily", params={"day": "2026-01-01"}, headers=admin).json()
    assert report["sale_count"] == 0 and report["revenue_centimes"] == 0 and report["by_payment"] == []


def test_top_products_and_daily_totals(client, admin, seller, db, make_product):
    a = make_product(name="Câble", stock=20, price_centimes=5000)
    b = make_product(name="Chargeur", stock=20, price_centimes=30000)
    for product, qty in ((a, 3), (b, 1), (a, 1)):
        sale = sell(client, seller, [{"product_id": product["id"], "quantity": qty}]).json()
        move_sale(db, sale["id"], datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc))

    params = {"from_date": "2026-11-16", "to_date": "2026-11-18"}
    top = client.get("/api/reports/top-products", params=params, headers=admin).json()
    assert [(t["name"], t["quantity_sold"], t["revenue_centimes"]) for t in top] == [
        ("Chargeur", 1, 30000), ("Câble", 4, 20000)]   # ranked by revenue, not by units
    totals = client.get("/api/reports/daily-totals", params=params, headers=admin).json()
    assert [(t["date"], t["revenue_centimes"]) for t in totals] == [
        ("2026-11-16", 0), ("2026-11-17", 50000), ("2026-11-18", 0)]


def test_reports_are_admin_only(client, seller):
    assert client.get("/api/reports/daily", params={"day": "2026-11-18"}, headers=seller).status_code == 403


def test_bad_date_range(client, admin):
    params = {"from_date": "2026-11-18", "to_date": "2026-11-01"}
    assert client.get("/api/reports/top-products", params=params, headers=admin).status_code == 400
