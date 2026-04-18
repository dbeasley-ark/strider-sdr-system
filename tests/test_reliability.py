"""Tests for retry, circuit breaker, and timeouts."""

from __future__ import annotations

import asyncio

import pytest

from agent.reliability import (
    BreakerState,
    CircuitBreaker,
    CircuitOpenError,
    ToolTimeoutError,
    TransientError,
    with_retry,
    with_timeout,
)


# ── Retry ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("still warming up")
        return "ok"

    result = await with_retry(flaky, max_attempts=5, initial_wait=0.01, max_wait=0.05)
    assert result == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_retry_does_not_retry_non_transient() -> None:
    attempts = {"n": 0}

    async def hard_fail() -> str:
        attempts["n"] += 1
        raise ValueError("bug")

    with pytest.raises(ValueError):
        await with_retry(hard_fail, max_attempts=5, initial_wait=0.01)

    assert attempts["n"] == 1  # no retries on non-TransientError


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts() -> None:
    attempts = {"n": 0}

    async def always_transient() -> str:
        attempts["n"] += 1
        raise TransientError("nope")

    with pytest.raises(TransientError):
        await with_retry(always_transient, max_attempts=3, initial_wait=0.01, max_wait=0.05)

    assert attempts["n"] == 3


# ── Circuit breaker ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_s=0.05)

    async def fail() -> None:
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.state is BreakerState.OPEN

    # Next call should fail fast with CircuitOpenError
    with pytest.raises(CircuitOpenError):
        await breaker.call(fail)


@pytest.mark.asyncio
async def test_breaker_recovers_on_success() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=2, reset_timeout_s=0.05)

    async def fail() -> None:
        raise RuntimeError("boom")

    async def ok() -> str:
        return "ok"

    # Trip the breaker
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)
    assert breaker.state is BreakerState.OPEN

    # Wait for half-open
    await asyncio.sleep(0.07)

    # Successful call should close the breaker
    result = await breaker.call(ok)
    assert result == "ok"
    assert breaker.state is BreakerState.CLOSED


# ── Timeout ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_raises_on_slow_call() -> None:
    async def slow() -> str:
        await asyncio.sleep(0.2)
        return "ok"

    with pytest.raises(ToolTimeoutError):
        await with_timeout(slow(), seconds=0.05, name="slow_tool")


@pytest.mark.asyncio
async def test_timeout_passes_through_fast_call() -> None:
    async def fast() -> str:
        return "ok"

    result = await with_timeout(fast(), seconds=1.0, name="fast_tool")
    assert result == "ok"
