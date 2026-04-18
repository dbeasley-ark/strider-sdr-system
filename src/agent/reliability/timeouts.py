"""Async timeout helper. Keeps tool calls from hanging forever."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


class ToolTimeoutError(Exception):
    """Raised when a tool call exceeds its timeout."""


async def with_timeout(awaitable: Awaitable[T], seconds: float, *, name: str = "tool") -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError as e:
        raise ToolTimeoutError(f"{name} exceeded {seconds}s timeout") from e
