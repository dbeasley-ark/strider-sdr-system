"""Tests for the Brief schema (§9, §7.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.brief import (
    Brief,
    PersonalizationHook,
    RevenueEstimate,
    TargetRole,
    insufficient_data,
)


def _minimal_brief(**overrides):
    defaults = dict(
        run_id="r",
        generated_at=datetime.now(timezone.utc),
        company_name_queried="Shield AI",
        track="track_1",
        verdict="high_confidence",
        rationale="Two-plus signals: SAM active + USAspending primes visible.",
        revenue_estimate=RevenueEstimate(
            band="250m_to_1b",
            source="analyst_estimate",
            rationale="Analysts estimate ~$500M ARR.",
        ),
        target_roles=[],
        hooks=[],
        tool_calls_used=5,
        tool_calls_budget=12,
        wall_seconds=60.0,
        cost_usd=0.35,
    )
    defaults.update(overrides)
    return Brief(**defaults)


def test_minimal_brief_validates() -> None:
    b = _minimal_brief()
    assert b.track == "track_1"


def test_hook_requires_citation_url() -> None:
    with pytest.raises(ValidationError):
        PersonalizationHook(text="a"*30, citation_url="not-a-url")  # type: ignore[arg-type]


def test_rationale_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        _minimal_brief(rationale="too short")


def test_insufficient_data_helper() -> None:
    b = insufficient_data(
        run_id="r",
        generated_at=datetime.now(timezone.utc),
        company_name_queried="Unknown",
        why="tool budget exhausted",
        halt_reason="tool_budget_exhausted",
    )
    assert b.verdict == "insufficient_data"
    assert b.track == "neither"
    assert b.halt_reason == "tool_budget_exhausted"
    assert b.hooks == []


def test_insufficient_data_max_output_tokens_halt() -> None:
    b = insufficient_data(
        run_id="r",
        generated_at=datetime.now(timezone.utc),
        company_name_queried="X",
        why="model output hit max_tokens (8192)",
        halt_reason="max_output_tokens_exhausted",
    )
    assert b.halt_reason == "max_output_tokens_exhausted"


def test_target_role_caps_hooks_at_8() -> None:
    hooks = [
        PersonalizationHook(
            text="valid hook of reasonable length " * 2,
            citation_url="https://example.com/p",
        )
        for _ in range(9)
    ]
    with pytest.raises(ValidationError):
        _minimal_brief(hooks=hooks)


def test_target_role_caps_at_5() -> None:
    roles = [
        TargetRole(title="VP", rationale="why")
        for _ in range(6)
    ]
    with pytest.raises(ValidationError):
        _minimal_brief(target_roles=roles)
