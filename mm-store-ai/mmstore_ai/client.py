"""A small async client for the MM Store REST API.

The MCP server never touches the store's database directly. It goes through the same API as the
web interface, with its own user account. So every rule of MM Store still applies to the AI
(permissions, stock checks, validation), and every action it takes is recorded under that account.
"""
from __future__ import annotations

from typing import Any

import httpx


class StoreError(Exception):
    """A problem worth showing to the person: the message is in French and safe to display."""


class StoreClient:
    def __init__(self, base_url: str, email: str, password: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 15.0) -> None:
        self._email = email
        self._password = password
        self._token: str | None = None
        self.user: dict[str, Any] | None = None
        # `transport` lets the tests run the real MM Store app in-process, with no network at all.
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/api", transport=transport, timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    async def _login(self) -> None:
        try:
            response = await self._http.post("/auth/login", data={"username": self._email, "password": self._password})
        except httpx.HTTPError as exc:
            raise StoreError("MM Store ne répond pas. Vérifiez que le serveur est démarré.") from exc
        if response.status_code != 200:
            raise StoreError("Connexion à MM Store refusée : vérifiez l'email et le mot de passe de l'assistant.")
        body = response.json()
        self._token, self.user = body["access_token"], body["user"]

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._token is None:
            await self._login()
        for attempt in (1, 2):
            try:
                response = await self._http.request(method, path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
            except httpx.HTTPError as exc:
                raise StoreError("MM Store ne répond pas. Vérifiez que le serveur est démarré.") from exc
            if response.status_code == 401 and attempt == 1:   # token expired: log in again once
                await self._login()
                continue
            break
        if response.status_code == 403:
            raise StoreError("Action réservée au gérant : le compte de l'assistant n'a pas ce droit.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise StoreError(detail if isinstance(detail, str) else f"MM Store a répondu par une erreur {response.status_code}.")
        return response.json() if response.content else None

    # ---- the endpoints the tools use ----
    async def products(self, **params: Any) -> list[dict]:
        return await self.request("GET", "/products", params={k: v for k, v in params.items() if v not in (None, "", False)})

    async def categories(self) -> list[dict]:
        return await self.request("GET", "/categories")

    async def serials(self, product_id: int) -> list[dict]:
        return await self.request("GET", f"/products/{product_id}/serials")

    async def lookup_serial(self, serial: str) -> dict:
        return await self.request("GET", f"/serials/{serial}")

    async def daily_report(self, day: str) -> dict:
        return await self.request("GET", "/reports/daily", params={"day": day})

    async def top_products(self, from_date: str, to_date: str, limit: int) -> list[dict]:
        return await self.request("GET", "/reports/top-products", params={"from_date": from_date, "to_date": to_date, "limit": limit})

    async def resellers(self, q: str = "") -> list[dict]:
        return await self.request("GET", "/resellers", params={"q": q} if q else None)

    async def reseller(self, reseller_id: int) -> dict:
        return await self.request("GET", f"/resellers/{reseller_id}")

    async def record_payment(self, reseller_id: int, amount_centimes: int, method: str, note: str | None) -> dict:
        return await self.request("POST", f"/resellers/{reseller_id}/payments",
                                  json={"amount_centimes": amount_centimes, "payment_method": method, "note": note})
