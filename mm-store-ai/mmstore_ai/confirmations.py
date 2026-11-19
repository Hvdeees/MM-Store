"""Two-step confirmation, used only when the AI app can't show a confirmation form to the person.

record_reseller_payment returns a short code instead of acting; confirm_payment(code) then does it.
Codes are random, single-use, and expire after a few minutes, so an old or guessed code does nothing.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingAction:
    kind: str
    payload: dict[str, Any]
    summary: str
    expires_at: float


@dataclass
class PendingActions:
    ttl_seconds: float = 300
    clock: Any = time.monotonic          # replaceable in tests
    _items: dict[str, PendingAction] = field(default_factory=dict)

    def create(self, kind: str, payload: dict[str, Any], summary: str) -> str:
        self._purge()
        code = secrets.token_hex(3).upper()          # e.g. "4F9A2C": easy to read out loud
        self._items[code] = PendingAction(kind, payload, summary, self.clock() + self.ttl_seconds)
        return code

    def take(self, code: str) -> PendingAction | None:
        """Return the action and forget it (single use). None if unknown or expired."""
        self._purge()
        return self._items.pop(code.strip().upper(), None)

    def _purge(self) -> None:
        now = self.clock()
        for code in [c for c, a in self._items.items() if a.expires_at <= now]:
            del self._items[code]
