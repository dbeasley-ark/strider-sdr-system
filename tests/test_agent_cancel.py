"""Agent always leaves a brief.json even on cancellation.

Before this change, a CancelledError/KeyboardInterrupt between LLM
iterations exited the run without writing a brief. The sales UI surfaced
that as "Agent produced no stdout", and runs/cape-co/2026-04-20T21-22-28Z
and a handful of other directories held only a trace.jsonl.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent.agent import Agent
from agent.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_cancelled_run_still_writes_insufficient_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If CancelledError fires in the loop, the agent must still emit a
    brief.json with verdict=insufficient_data and re-raise the exception.
    """

    async def fake_llm(  # noqa: ANN001, ARG001
        self: Agent,
        messages: list,
        *,
        allow_tools: bool,
        container_id: str | None = None,
    ):
        raise asyncio.CancelledError()

    monkeypatch.setattr(Agent, "_call_llm", fake_llm, raising=True)

    registry = ToolRegistry()
    agent = Agent(registry=registry)

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with pytest.raises(asyncio.CancelledError):
        await agent.research("Test Co", domain="test.co", run_dir=run_dir)

    brief_path = run_dir / "brief.json"
    assert brief_path.is_file(), "brief.json must exist even after cancellation"

    brief = json.loads(brief_path.read_text())
    assert brief["verdict"] == "insufficient_data"
    assert "cancelled" in (brief["why_not_confident"] or "").lower()
    assert brief["halt_reason"] == "internal_error"
