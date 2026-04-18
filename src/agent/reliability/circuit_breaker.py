"""Circuit breaker.

When a dependency starts failing, stop hammering it. A breaker lives in
one of three states:

    CLOSED      – normal operation; calls pass through.
    OPEN        – dependency is unhealthy; calls fail fast without trying.
    HALF_OPEN   – probing; a single call is allowed through. If it succeeds,
                  we return to CLOSED. If it fails, back to OPEN.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BreakerState:
        return self._state

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            self._maybe_transition_to_half_open()
            if self._state is BreakerState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker {self.name!r} is OPEN; call rejected."
                )

        try:
            result = await fn()
        except Exception:
            async with self._lock:
                self._record_failure()
            raise
        else:
            async with self._lock:
                self._record_success()
            return result

    # ── State transitions ───────────────────────────────────────────

    def _maybe_transition_to_half_open(self) -> None:
        if self._state is BreakerState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.reset_timeout_s:
                self._state = BreakerState.HALF_OPEN

    def _record_failure(self) -> None:
        self._failures += 1
        if self._state is BreakerState.HALF_OPEN:
            self._state = BreakerState.OPEN
            self._opened_at = time.monotonic()
        elif self._failures >= self.failure_threshold:
            self._state = BreakerState.OPEN
            self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        self._failures = 0
        self._state = BreakerState.CLOSED
        self._opened_at = None
