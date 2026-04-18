"""Tests for the async token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from agent.reliability import RateLimitTimeout, TokenBucket


@pytest.mark.asyncio
async def test_first_n_acquires_immediate() -> None:
    b = TokenBucket(name="t", rate_per_minute=60.0, capacity=3)
    t0 = time.monotonic()
    for _ in range(3):
        await b.acquire()
    assert time.monotonic() - t0 < 0.05  # all within burst


@pytest.mark.asyncio
async def test_excess_waits_for_refill() -> None:
    # 60/min = 1/sec refill; capacity 1 means 4th call must wait ~1s total.
    b = TokenBucket(name="t", rate_per_minute=120.0, capacity=1)
    await b.acquire()
    t0 = time.monotonic()
    await b.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.4, f"Expected a wait, got {elapsed}s"


@pytest.mark.asyncio
async def test_timeout_raises_when_budget_too_small() -> None:
    b = TokenBucket(name="t", rate_per_minute=10.0, capacity=1)
    await b.acquire()  # consume the only token
    with pytest.raises(RateLimitTimeout):
        await b.acquire(timeout=0.1)
