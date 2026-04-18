"""Retry with exponential backoff.

Every tool call is wrapped in this by default. If you turn it off for a
specific tool, document why in AGENT_SPEC.md §6.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from agent.observability.tracing import logger

T = TypeVar("T")


class TransientError(Exception):
    """Mark exceptions as retryable by raising or wrapping in this."""


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 4,
    initial_wait: float = 0.5,
    max_wait: float = 16.0,
    retry_on: tuple[type[BaseException], ...] = (TransientError,),
) -> T:
    """Run `fn` with exponential backoff + jitter.

    Only exceptions matching `retry_on` are retried. Everything else
    propagates immediately — we don't want to retry a bug.
    """
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential_jitter(initial=initial_wait, max=max_wait),
            retry=retry_if_exception_type(retry_on),
            before_sleep=before_sleep_log(logger, 30),  # WARNING
            reraise=True,
        ):
            with attempt:
                return await fn()
    except RetryError as e:
        raise e.last_attempt.exception() from e  # type: ignore[misc]
    raise RuntimeError("unreachable")
