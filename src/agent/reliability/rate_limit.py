"""Async token-bucket rate limiter.

Used to stay under per-domain API ceilings. SAM.gov's free tier in
particular is 10 req/min — we run at 9/min with headroom (§4.4).

Tokens refill continuously. Each `acquire()` waits until a token is
available or the given deadline is reached.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


class RateLimitTimeout(Exception):
    """Raised when `acquire(timeout=)` expires before a token is available."""


@dataclass
class TokenBucket:
    name: str
    rate_per_minute: float
    capacity: int = 1
    """Burst capacity. 1 = strict one-at-a-time. Set higher when the
    upstream lets you burst."""

    _tokens: float = field(default=1.0, init=False)
    _updated_at: float = field(default_factory=time.monotonic, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)

    async def acquire(self, *, timeout: float | None = None) -> None:
        """Block until a token is available (or timeout elapses)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_needed = (1.0 - self._tokens) * (60.0 / self.rate_per_minute)
            if deadline is not None and time.monotonic() + wait_needed > deadline:
                raise RateLimitTimeout(
                    f"{self.name}: no token within {timeout}s (need {wait_needed:.2f}s more)"
                )
            await asyncio.sleep(wait_needed)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated_at
        self._updated_at = now
        self._tokens = min(
            float(self.capacity),
            self._tokens + elapsed * (self.rate_per_minute / 60.0),
        )
