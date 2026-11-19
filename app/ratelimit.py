"""Login attempt limits: stops someone from guessing passwords endlessly.

Two independent limits, both counted on FAILED attempts only:
- per account (email): 5 failures in 15 minutes locks that email for the rest of the window,
  however many computers the attacker uses;
- per network address (IP): 20 failures in 15 minutes blocks that address, so one machine
  can't try one password on every account either.
A successful login clears the account's counter. Counters live in memory: right for one server
(a restart clears them, which is acceptable). Several servers would need a shared store like Redis.
"""
import threading
import time
from collections import defaultdict, deque


class LoginLimiter:
    def __init__(self, per_account: int = 5, per_ip: int = 20, window_seconds: int = 15 * 60, clock=time.monotonic):
        self.per_account, self.per_ip, self.window = per_account, per_ip, window_seconds
        self.clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()   # FastAPI runs sync routes in a thread pool

    def _recent(self, key: str) -> deque:
        q = self._failures[key]
        cutoff = self.clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def retry_after(self, email: str, ip: str) -> int:
        """Seconds to wait before trying again (0 = allowed now)."""
        with self._lock:
            waits = []
            for key, limit in ((f"email:{email}", self.per_account), (f"ip:{ip}", self.per_ip)):
                q = self._recent(key)
                if len(q) >= limit:
                    waits.append(int(q[0] + self.window - self.clock()) + 1)
            return max(waits, default=0)

    def failed(self, email: str, ip: str) -> None:
        with self._lock:
            now = self.clock()
            self._failures[f"email:{email}"].append(now)
            self._failures[f"ip:{ip}"].append(now)

    def succeeded(self, email: str) -> None:
        with self._lock:
            self._failures.pop(f"email:{email}", None)


login_limiter = LoginLimiter()
