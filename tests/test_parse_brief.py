"""Tests for Brief JSON parsing (null coercion for finalized fields)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agent.brief_parse import parse_brief_from_model_text


def _minimal_json_text(**extra_fields: object) -> str:
    base = {
        "schema_version": "1.0",
        "track": "neither",
        "verdict": "insufficient_data",
        "why_not_confident": "No reliable federal signal within budget.",
        "rationale": (
            "Insufficient evidence for Track 1 or 2; SAM and web signal "
            "did not support a confident classification in this run."
        ),
        "revenue_estimate": {
            "band": "unknown",
            "source": "not_determinable",
            "rationale": "No revenue signal gathered.",
        },
        "target_roles": [],
        "hooks": [],
        "sources_used": [],
        "halt_reason": None,
    }
    base.update(extra_fields)
    return json.dumps(base)


def test_parse_brief_accepts_null_finalized_numerics() -> None:
    text = _minimal_json_text(
        wall_seconds=None,
        cost_usd=None,
        tool_calls_used=None,
        tool_calls_budget=None,
    )
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run-test",
        company="Example Corp",
        generated_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        max_tool_calls=12,
    )
    assert err is None
    assert brief is not None
    assert brief.wall_seconds == 0.0
    assert brief.cost_usd == 0.0
    assert brief.tool_calls_used == 0
    assert brief.tool_calls_budget == 12


def test_parse_brief_accepts_null_list_fields() -> None:
    text = _minimal_json_text(
        hooks=None,
        target_roles=None,
        sources_used=None,
        wall_seconds=1.0,
        cost_usd=0.01,
        tool_calls_used=1,
        tool_calls_budget=12,
    )
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run-test-2",
        company="Other Corp",
        generated_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        max_tool_calls=12,
    )
    assert err is None
    assert brief is not None
    assert brief.hooks == []
    assert brief.target_roles == []
    assert brief.sources_used == []
