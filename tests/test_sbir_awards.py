"""SBIR tool: 403 rate-limit becomes a clean `rate_limited` result.

Without this, every back-to-back run in a batch burned the 10-req/10-min
SBIR quota and the agent treated 403 as a tool exception — wasting an
iteration on retry before giving up.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.tools import lookup_sbir_awards as mod


@pytest.mark.asyncio
async def test_403_rate_limit_is_reported_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(_params: dict[str, Any]) -> Any:
        raise RuntimeError(
            "SBIR 403: You've exceeded the rate limit for API usage. "
            "Please restrict your usage to 10 requests in 10 minutes."
        )

    monkeypatch.setattr(mod, "_sbir_get", fake_get)

    tool = mod.LookupSbirAwards()
    result = await tool({"recipient_name": "Test Corp"})

    assert result["awards"] == []
    assert result["error"].startswith("rate_limited:")


@pytest.mark.asyncio
async def test_other_runtime_errors_still_bubble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-rate-limit runtime errors must not be silently swallowed: the
    agent loop catches them at `tool.exception` level and retries / moves on.
    """

    async def fake_get(_params: dict[str, Any]) -> Any:
        raise RuntimeError("SBIR 400: bad request")

    monkeypatch.setattr(mod, "_sbir_get", fake_get)

    tool = mod.LookupSbirAwards()
    with pytest.raises(RuntimeError, match="SBIR 400"):
        await tool({"recipient_name": "Test Corp"})
