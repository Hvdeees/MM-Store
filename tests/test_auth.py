from tests.conftest import login


def test_login_and_me(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["email"] == "admin@test.ma" and me["role"] == "admin"


def test_wrong_password_gives_french_error(client):
    response = client.post("/api/auth/login", data={"username": "admin@test.ma", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Email ou mot de passe incorrect"


def test_login_email_is_case_insensitive(client):
    login(client, "ADMIN@test.ma", "admin-pass-123")


def test_requests_without_token_are_rejected(client):
    assert client.get("/api/products").status_code == 401


def test_forged_token_is_rejected(client):
    assert client.get("/api/products", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401


def test_seller_cannot_use_admin_routes(client, seller, categories):
    assert client.get("/api/users", headers=seller).status_code == 403
    body = {"sku": "X", "name": "X", "category_id": categories["Pochettes et coques"], "price_centimes": 100}
    response = client.post("/api/products", json=body, headers=seller)
    assert response.status_code == 403
    assert response.json()["detail"] == "Accès réservé à l'administrateur"


def test_admin_creates_seller_who_can_log_in(client, admin):
    body = {"email": "Karim@boutique.ma", "full_name": "Karim", "password": "motdepasse1"}
    assert client.post("/api/users", json=body, headers=admin).status_code == 201
    login(client, "karim@boutique.ma", "motdepasse1")
    assert client.post("/api/users", json=body, headers=admin).status_code == 409


def test_deactivated_user_is_locked_out_immediately(client, admin, seller):
    users = client.get("/api/users", headers=admin).json()
    seller_id = next(u["id"] for u in users if u["role"] == "vendeur")
    client.patch(f"/api/users/{seller_id}", json={"is_active": False}, headers=admin)
    # The old token is still unexpired, but the account is checked on every request.
    assert client.get("/api/auth/me", headers=seller).status_code == 401


def test_admin_cannot_demote_self(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "vendeur"}, headers=admin).status_code == 400


def test_change_password(client, seller):
    body = {"current_password": "vendeur-pass-123", "new_password": "nouveau-pass-456"}
    assert client.post("/api/auth/change-password", json=body, headers=seller).status_code == 204
    login(client, "vendeur@test.ma", "nouveau-pass-456")


def test_validation_errors_are_in_french(client, admin, categories):
    body = {"sku": "X", "name": "X", "category_id": categories["Pochettes et coques"], "price_centimes": -1}
    response = client.post("/api/products", json=body, headers=admin)
    assert response.status_code == 422
    assert response.json()["detail"] == "Données invalides : prix"


def test_too_many_wrong_passwords_locks_the_account_for_a_while(client):
    for _ in range(5):
        assert client.post("/api/auth/login", data={"username": "admin@test.ma", "password": "wrong"}).status_code == 401
    blocked = client.post("/api/auth/login", data={"username": "admin@test.ma", "password": "admin-pass-123"})
    assert blocked.status_code == 429                      # even the right password waits: the attacker learns nothing
    assert "Trop de tentatives" in blocked.json()["detail"] and int(blocked.headers["Retry-After"]) > 0
    # other accounts are not affected
    login(client, "vendeur@test.ma", "vendeur-pass-123")


def test_lock_ends_after_the_window():
    from app.ratelimit import LoginLimiter
    now = [0.0]
    limiter = LoginLimiter(per_account=3, window_seconds=60, clock=lambda: now[0])
    for _ in range(3):
        limiter.failed("a@b.ma", "1.2.3.4")
    assert limiter.retry_after("a@b.ma", "1.2.3.4") > 0
    now[0] = 61
    assert limiter.retry_after("a@b.ma", "1.2.3.4") == 0


def test_one_address_cannot_try_every_account():
    from app.ratelimit import LoginLimiter
    limiter = LoginLimiter(per_account=5, per_ip=4)
    for n in range(4):
        limiter.failed(f"user{n}@b.ma", "9.9.9.9")
    assert limiter.retry_after("someone-else@b.ma", "9.9.9.9") > 0
    assert limiter.retry_after("someone-else@b.ma", "8.8.8.8") == 0


def test_successful_login_clears_the_counter(client):
    for _ in range(4):
        client.post("/api/auth/login", data={"username": "admin@test.ma", "password": "wrong"})
    login(client, "admin@test.ma", "admin-pass-123")
    for _ in range(4):
        client.post("/api/auth/login", data={"username": "admin@test.ma", "password": "wrong"})
    login(client, "admin@test.ma", "admin-pass-123")       # still allowed: the count restarted at the success
