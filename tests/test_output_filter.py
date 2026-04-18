"""Tests for the §7 output filter.

Covers:
  * HARD_STOP classified markings raise ComplianceHardStop.
  * CUI WARN markings downgrade a high_confidence verdict to low_confidence.
  * Hooks whose citation_url is not in the trace are dropped.
  * Mass hook drops downgrade verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.brief import Brief, PersonalizationHook, RevenueEstimate
from agent.security.output_filter import ComplianceHardStop, apply_filter


def _base_brief(
    *,
    hooks: list[PersonalizationHook] | None = None,
    rationale: str = "Two-plus signals support this call. SAM is active; USAspending shows primes.",
    verdict: str = "high_confidence",
) -> Brief:
    return Brief(
        schema_version="1.0",
        run_id="test-run",
        generated_at=datetime.now(timezone.utc),
        company_name_queried="Shield AI",
        company_name_canonical="SHIELD AI",
        domain="shield.ai",
        uei="KXN8C4WDQK92",
        track="track_1",
        verdict=verdict,  # type: ignore[arg-type]
        why_not_confident=None,
        rationale=rationale,
        revenue_estimate=RevenueEstimate(
            band="250m_to_1b",
            source="analyst_estimate",
            rationale="Analyst coverage estimates $500M ARR.",
        ),
        target_roles=[],
        hooks=hooks or [],
        tool_calls_used=5,
        tool_calls_budget=12,
        wall_seconds=60.0,
        cost_usd=0.35,
    )


def test_hard_stop_raises_on_classified() -> None:
    brief = _base_brief(
        rationale="Our analysis references (S//NF) a classified program of record.",
    )
    with pytest.raises(ComplianceHardStop):
        apply_filter(brief, fetched_urls=set(), citation_urls=set())


def test_cui_downgrades_verdict() -> None:
    brief = _base_brief(
        rationale=(
            "Active DoD primes visible. The public page was marked CUI//SP-PRVCY "
            "which we flag for compliance review."
        ),
    )
    filtered, report = apply_filter(brief, fetched_urls=set(), citation_urls=set())
    assert filtered.verdict == "low_confidence"
    assert report.downgraded_verdict
    assert "compliance" in (report.downgrade_reason or "")


def test_hook_without_matching_citation_is_dropped() -> None:
    hook_ok = PersonalizationHook(
        text="Cited a real press hit about their Navy contract.",
        citation_url="https://www.defense.gov/News/Releases/shield-ai",
    )
    hook_hallucinated = PersonalizationHook(
        text="Claim the $900M phantom contract from nowhere.",
        citation_url="https://evil.com/phantom",
    )
    brief = _base_brief(hooks=[hook_ok, hook_hallucinated])

    filtered, report = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls={"https://www.defense.gov/News/Releases/shield-ai"},
    )
    assert len(filtered.hooks) == 1
    assert str(filtered.hooks[0].citation_url).startswith("https://www.defense.gov")
    assert report.dropped_hooks == [("https://evil.com/phantom", "url_not_in_trace")]


def test_all_hooks_dropped_downgrades() -> None:
    brief = _base_brief(
        hooks=[
            PersonalizationHook(
                text="Made-up hook one. " * 2,
                citation_url="https://evil.com/a",
            ),
            PersonalizationHook(
                text="Made-up hook two. " * 2,
                citation_url="https://evil.com/b",
            ),
        ]
    )
    filtered, report = apply_filter(brief, fetched_urls=set(), citation_urls=set())
    assert filtered.verdict == "low_confidence"
    assert filtered.hooks == []
    assert report.downgraded_verdict
