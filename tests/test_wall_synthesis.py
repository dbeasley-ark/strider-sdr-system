"""Wall-budget post-synthesis and parse-repair paths."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent.agent import Agent
from agent.config import settings
from agent.tools.registry import ToolRegistry


def _end_turn_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=12, output_tokens=80),
        container=None,
    )


def _minimal_brief_json(*, company_name_queried: str) -> str:
    obj = {
        "schema_version": "1.0",
        "confidentiality": "internal_only",
        "company_name_queried": company_name_queried,
        "company_name_canonical": None,
        "domain": None,
        "uei": None,
        "track": "neither",
        "verdict": "low_confidence",
        "why_not_confident": "Wall-clock budget exhausted after transcript review.",
        "rationale": (
            "Limited transcript; no federal tools succeeded in the fixture. "
            "Classifying as neither with low confidence pending more research."
        ),
        "revenue_estimate": {
            "band": "unknown",
            "source": "not_determinable",
            "rationale": "No revenue signal in transcript.",
        },
        "target_roles": [],
        "hooks": [],
        "sources_used": [],
        "halt_reason": None,
    }
    return json.dumps(obj)


@pytest.mark.asyncio
async def test_wall_budget_synthesis_writes_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "max_wall_seconds", 10)
    monkeypatch.setattr(settings, "wall_synthesis_enabled", True)
    monkeypatch.setattr(settings, "wall_synthesis_max_tokens", 2048)

    _mono_n = {"i": 0}

    def fake_monotonic() -> float:
        _mono_n["i"] += 1
        if _mono_n["i"] == 1:
            return 0.0
        return 150.0

    monkeypatch.setattr("agent.agent.time.monotonic", fake_monotonic)

    async def fake_llm(  # noqa: ANN001
        self: Agent,
        messages: list,
        *,
        allow_tools: bool,
        container_id: str | None = None,
        max_tokens: int | None = None,
    ):
        assert allow_tools is False
        assert max_tokens == settings.wall_synthesis_max_tokens
        return _end_turn_response(_minimal_brief_json(company_name_queried="Synth Co"))

    monkeypatch.setattr(Agent, "_call_llm", fake_llm, raising=True)

    registry = ToolRegistry()
    agent = Agent(registry=registry)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = await agent.research(
        "Synth Co",
        domain=None,
        run_dir=run_dir,
    )

    assert result.status == "halted_wall_budget_synthesized"
    assert result.brief.verdict == "low_confidence"
    brief_path = run_dir / "brief.json"
    assert brief_path.is_file()
    data = json.loads(brief_path.read_text())
    assert data["verdict"] == "low_confidence"


@pytest.mark.asyncio
async def test_wall_budget_stub_when_synthesis_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "max_wall_seconds", 10)
    monkeypatch.setattr(settings, "wall_synthesis_enabled", False)

    _mono_n = {"i": 0}

    def fake_monotonic() -> float:
        _mono_n["i"] += 1
        if _mono_n["i"] == 1:
            return 0.0
        return 150.0

    monkeypatch.setattr("agent.agent.time.monotonic", fake_monotonic)

    registry = ToolRegistry()
    agent = Agent(registry=registry)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = await agent.research("No Synth Co", run_dir=run_dir)

    assert result.status == "halted_wall_budget"
    assert result.brief.verdict == "insufficient_data"
    assert result.brief.halt_reason == "wall_budget_exhausted"


@pytest.mark.asyncio
async def test_wall_synthesis_api_error_falls_back_to_stub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "max_wall_seconds", 10)
    monkeypatch.setattr(settings, "wall_synthesis_enabled", True)

    _mono_n = {"i": 0}

    def fake_monotonic() -> float:
        _mono_n["i"] += 1
        if _mono_n["i"] == 1:
            return 0.0
        return 150.0

    monkeypatch.setattr("agent.agent.time.monotonic", fake_monotonic)

    async def fake_llm(  # noqa: ANN001
        self: Agent,
        messages: list,
        *,
        allow_tools: bool,
        container_id: str | None = None,
        max_tokens: int | None = None,
    ):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(Agent, "_call_llm", fake_llm, raising=True)

    registry = ToolRegistry()
    agent = Agent(registry=registry)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = await agent.research("Err Co", run_dir=run_dir)

    assert result.status == "halted_wall_budget"
    assert result.brief.verdict == "insufficient_data"
    assert "API unavailable" in (result.brief.why_not_confident or "")


@pytest.mark.asyncio
async def test_brief_parse_repair_one_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid JSON once, then valid brief on second end_turn."""
    monkeypatch.setattr(settings, "max_wall_seconds", 3600)

    calls: list[Any] = []

    async def fake_llm(  # noqa: ANN001
        self: Agent,
        messages: list,
        *,
        allow_tools: bool,
        container_id: str | None = None,
        max_tokens: int | None = None,
    ):
        calls.append(1)
        if len(calls) == 1:
            return _end_turn_response("Here is not valid json {")
        return _end_turn_response(
            _minimal_brief_json(company_name_queried="Parse Repair Co")
        )

    monkeypatch.setattr(Agent, "_call_llm", fake_llm, raising=True)

    registry = ToolRegistry()
    agent = Agent(registry=registry)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = await agent.research("Parse Repair Co", run_dir=run_dir)

    assert result.status == "ok"
    assert len(calls) == 2
    assert result.brief.verdict == "low_confidence"


@pytest.mark.asyncio
async def test_call_llm_omits_container_when_tools_disabled() -> None:
    """Tools-off requests must not send `container`; API 400s otherwise."""
    registry = ToolRegistry()
    agent = Agent(registry=registry)
    create_mock = AsyncMock(
        return_value=SimpleNamespace(
            stop_reason="end_turn",
            content=[],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            container=None,
        )
    )
    agent.client.messages.create = create_mock  # type: ignore[method-assign]

    await agent._call_llm(
        [{"role": "user", "content": [{"type": "text", "text": "x"}]}],
        allow_tools=False,
        container_id="cntr_fake",
    )
    assert "container" not in create_mock.call_args.kwargs

    await agent._call_llm(
        [{"role": "user", "content": [{"type": "text", "text": "x"}]}],
        allow_tools=True,
        container_id="cntr_fake",
    )
    assert create_mock.call_args.kwargs.get("container") == "cntr_fake"
