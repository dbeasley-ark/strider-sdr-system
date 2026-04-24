"""Eval harness grading for optional playbook `expected` keys."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.brief import Brief, RevenueEstimate
from evals.run import EvalCase, _grade


def _brief(**overrides: Any) -> Brief:
    base: dict = {
        "schema_version": "1.1",
        "run_id": "eval-test",
        "generated_at": datetime.now(UTC),
        "company_name_queried": "Acme",
        "federal_revenue_posture": "pre_sponsorship_path",
        "verdict": "high_confidence",
        "rationale": (
            "SAM active with SBIR Phase II history and moderate USAspending — "
            "multiple independent signals support Track 2 in this fixture."
        ),
        "revenue_estimate": RevenueEstimate(
            band="10m_to_50m",
            source="federal_awards_proxy",
            rationale="Federal awards proxy suggests sub-50M band.",
        ),
        "target_roles": [],
        "hooks": [],
        "tool_calls_used": 4,
        "tool_calls_budget": 13,
        "wall_seconds": 5.0,
        "cost_usd": 0.02,
    }
    base.update(overrides)
    return Brief(**base)


def test_grade_passes_when_buyer_tier_matches() -> None:
    brief = _brief(buyer_tier="tier_3_future_growth", product_angle="foundation_then_cohort")
    case = EvalCase(
        name="fixture",
        kind="golden",
        input={},
        expected={
            "buyer_tier": "tier_3_future_growth",
            "product_angle": "foundation_then_cohort",
        },
    )
    r = _grade(case, brief, "ok", 0.01, 1.0, 3)
    assert r.passed


def test_grade_fails_when_buyer_tier_mismatches() -> None:
    brief = _brief(buyer_tier="unknown")
    case = EvalCase(
        name="fixture",
        kind="golden",
        input={},
        expected={"buyer_tier": "tier_1_strike_zone"},
    )
    r = _grade(case, brief, "ok", 0.01, 1.0, 3)
    assert not r.passed
    assert r.failure_reason and "buyer_tier" in r.failure_reason
