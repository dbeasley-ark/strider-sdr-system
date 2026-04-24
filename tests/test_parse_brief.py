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
        max_tool_calls=13,
    )
    assert err is None
    assert brief is not None
    assert brief.wall_seconds == 0.0
    assert brief.cost_usd == 0.0
    assert brief.tool_calls_used == 0
    assert brief.tool_calls_budget == 13


def test_parse_brief_normalizes_revenue_source_aliases() -> None:
    for alias, expected in (
        ("press_estimate", "press_release"),
        ("third_party_estimate", "analyst_estimate"),
        ("third_party_database", "analyst_estimate"),
    ):
        text = _minimal_json_text(
            revenue_estimate={
                "band": "10m_to_50m",
                "source": alias,
                "rationale": "From public estimates.",
            },
            wall_seconds=1.0,
            cost_usd=0.01,
            tool_calls_used=1,
            tool_calls_budget=13,
        )
        brief, err = parse_brief_from_model_text(
            text,
            run_id="run-alias",
            company="Acme",
            generated_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc),
            max_tool_calls=13,
        )
        assert err is None, alias
        assert brief is not None
        assert brief.revenue_estimate.source == expected


def test_parse_brief_truncates_federal_prime_awards() -> None:
    awards = [
        {
            "agency_or_context": f"Agency {i}",
            "amount_or_band": "$1M",
            "period_hint": None,
            "citation_url": None,
        }
        for i in range(8)
    ]
    text = _minimal_json_text(
        sales_conversation_prep={
            "what_they_do": {"summary": "x", "citation_url": None},
            "fedramp_posture": {"status": "unknown"},
            "hr_peo": {"status": "unknown"},
            "last_funding": {"confidence": "unknown"},
            "federal_prime_awards": awards,
        },
        wall_seconds=1.0,
        cost_usd=0.01,
        tool_calls_used=1,
        tool_calls_budget=13,
    )
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run-trunc",
        company="Acme",
        generated_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc),
        max_tool_calls=13,
    )
    assert err is None
    assert brief is not None
    assert len(brief.sales_conversation_prep.federal_prime_awards) == 5
    assert brief.sales_conversation_prep.federal_prime_awards[0].agency_or_context == "Agency 0"


def test_parse_brief_normalizes_halt_reason_wall_exceeded_alias() -> None:
    text = _minimal_json_text(
        halt_reason="wall_budget_exceeded",
        wall_seconds=125.0,
        cost_usd=0.01,
        tool_calls_used=3,
        tool_calls_budget=12,
    )
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run-halt",
        company="Tanium",
        generated_at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc),
        max_tool_calls=13,
    )
    assert err is None
    assert brief is not None
    assert brief.halt_reason == "wall_budget_exhausted"


def test_parse_brief_accepts_null_list_fields() -> None:
    text = _minimal_json_text(
        hooks=None,
        target_roles=None,
        sources_used=None,
        wall_seconds=1.0,
        cost_usd=0.01,
        tool_calls_used=1,
        tool_calls_budget=13,
    )
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run-test-2",
        company="Other Corp",
        generated_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        max_tool_calls=13,
    )
    assert err is None
    assert brief is not None
    assert brief.hooks == []
    assert brief.target_roles == []
    assert brief.sources_used == []
