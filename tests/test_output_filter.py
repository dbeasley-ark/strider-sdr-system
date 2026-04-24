"""Tests for the §7 output filter.

Covers:
  * HARD_STOP classified markings raise ComplianceHardStop.
  * CUI WARN markings downgrade a high_confidence verdict to low_confidence.
  * Hook-only mass drops downgrade high_confidence to medium_confidence.
  * Hooks whose citation_url is not in the trace are dropped.
  * Mass hook drops downgrade verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.brief import (
    Brief,
    FedrampPosturePrep,
    Form5500BenefitsPrep,
    PersonalizationHook,
    RevenueEstimate,
    SalesConversationPrep,
    WhatTheyDoPrep,
)
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
        federal_revenue_posture="sponsorship_in_hand",
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
        tool_calls_budget=13,
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


def test_cui_plus_hook_drops_stays_low_not_medium() -> None:
    """Compliance WARN wins over hook-only medium tier."""
    brief = _base_brief(
        rationale=(
            "CUI//SP-PRVCY flagged text. Also citing hooks that are not in trace."
        ),
        hooks=[
            PersonalizationHook(
                text="Made-up hook one. " * 2,
                citation_url="https://evil.com/a",
            ),
        ],
    )
    filtered, report = apply_filter(brief, fetched_urls=set(), citation_urls=set())
    assert filtered.verdict == "low_confidence"
    assert filtered.hooks == []
    assert report.downgraded_verdict
    assert "compliance" in (report.downgrade_reason or "")
    assert "validator" in (report.downgrade_reason or "").lower()


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
    assert filtered.verdict == "medium_confidence"
    assert filtered.hooks == []
    assert report.downgraded_verdict


def test_seed_domain_citation_is_accepted_without_fetch() -> None:
    """Hooks citing the prospect's own domain should be accepted even
    when no fetch landed on that exact URL — the domain was on the
    run's allowlist from the start.
    """
    hook = PersonalizationHook(
        text="Cited the company's own press page about Game Warden.",
        citation_url="https://www.secondfront.com/resources/news/some-press",
    )
    brief = _base_brief(
        hooks=[hook],
        rationale=(
            "Strong Track 1 signal: active DoD primes, Game Warden ATOs, "
            "and Series C momentum put this squarely in the target band."
        ),
    )
    filtered, report = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls=set(),
        seed_hosts={"secondfront.com"},
    )
    assert len(filtered.hooks) == 1
    assert filtered.verdict == "high_confidence"
    assert report.dropped_hooks == []


def test_seed_domain_subdomain_matches() -> None:
    hook = PersonalizationHook(
        text="Press page on a subdomain of the company's site.",
        citation_url="https://ir.example.com/news/q4-results",
    )
    brief = _base_brief(
        hooks=[hook],
        rationale=(
            "Strong public signal from the IR subdomain plus DoD primes "
            "in USAspending make this a confident Track 1 call."
        ),
    )
    filtered, _ = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls=set(),
        seed_hosts={"example.com"},
    )
    assert len(filtered.hooks) == 1


def test_sales_prep_citation_dropped_when_not_in_trace() -> None:
    good = "https://www.fedramp.gov/marketplace/products.json"
    sp = SalesConversationPrep(
        what_they_do=WhatTheyDoPrep(
            summary="They build widgets for agencies.",
            citation_url="https://evil.com/fake-about",
        ),
        fedramp_posture=FedrampPosturePrep(
            status="no_marketplace_ties",
            citation_url=good,
        ),
    )
    brief = _base_brief()
    brief = brief.model_copy(update={"sales_conversation_prep": sp})
    filtered, report = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls={good},
        seed_hosts=set(),
    )
    assert filtered.sales_conversation_prep.what_they_do.citation_url is None
    assert str(filtered.sales_conversation_prep.fedramp_posture.citation_url) == good
    assert any("evil.com" in u for u, _ in report.dropped_sp_citations)


def test_form_5500_benefits_citation_dropped_when_not_in_trace() -> None:
    dol = "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"
    sp = SalesConversationPrep(
        form_5500_benefits=Form5500BenefitsPrep(
            signal_source="tabular_index",
            dc_retirement_summary="Synthetic DC row.",
            citation_url="https://evil.com/fake-5500",
        ),
    )
    brief = _base_brief()
    brief = brief.model_copy(update={"sales_conversation_prep": sp})
    filtered, report = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls={dol},
        seed_hosts=set(),
    )
    assert filtered.sales_conversation_prep.form_5500_benefits.citation_url is None
    assert any("evil.com" in u for u, _ in report.dropped_sp_citations)


def test_seed_domain_does_not_accept_lookalike() -> None:
    hook = PersonalizationHook(
        text="Lookalike domain should not piggyback on the seed.",
        citation_url="https://notexample.com/news/bad",
    )
    brief = _base_brief(
        hooks=[hook],
        rationale=(
            "Track 1 signals from elsewhere; testing that lookalikes "
            "cannot exploit the seed-host bypass in the validator."
        ),
    )
    filtered, report = apply_filter(
        brief,
        fetched_urls=set(),
        citation_urls=set(),
        seed_hosts={"example.com"},
    )
    assert filtered.hooks == []
    assert report.dropped_hooks and report.dropped_hooks[0][0].startswith(
        "https://notexample.com"
    )
