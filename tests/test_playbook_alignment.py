"""Playbook messaging guardrails and brief field defaults."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.brief import Brief, PersonalizationHook, RevenueEstimate
from agent.brief_parse import parse_brief_from_model_text
from agent.security.output_filter import apply_filter, playbook_messaging_hook_violation


def test_playbook_messaging_violation_cmmc_before_cohort() -> None:
    text = (
        "CMMC Level 2 is tightening — Cohort gives you a GovCon-native PEO "
        "built for cleared workforce HR."
    )
    assert playbook_messaging_hook_violation(text) is True


def test_playbook_messaging_no_violation_cohort_first() -> None:
    text = (
        "Cohort handles DCAA-aligned payroll on your DoD programs; separately, "
        "Foundation covers CMMC/NIST posture if you need that path."
    )
    assert playbook_messaging_hook_violation(text) is False


def test_playbook_messaging_no_violation_foundation_only() -> None:
    text = (
        "CMMC and DFARS 7012 baseline is a Foundation conversation for their "
        "secure operating environment roadmap."
    )
    assert playbook_messaging_hook_violation(text) is False


def test_playbook_messaging_trinet_counts_as_vendor_context() -> None:
    text = (
        "CMMC audits are coming — TriNet was not built for cleared PII at "
        "Pentagon standards."
    )
    assert playbook_messaging_hook_violation(text) is True


def test_apply_filter_drops_playbook_violation_hook() -> None:
    ok = PersonalizationHook(
        text="Cohort is positioned for GovCon payroll complexity as you scale primes.",
        citation_url="https://www.defense.gov/News/Releases/release-ok",
    )
    bad = PersonalizationHook(
        text=(
            "CMMC readiness is urgent — Cohort was built for defense workforce "
            "compliance on DoD contracts."
        ),
        citation_url="https://www.defense.gov/News/Releases/release-bad",
    )
    brief = Brief(
        schema_version="1.1",
        run_id="t",
        generated_at=datetime.now(UTC),
        company_name_queried="Example",
        track="track_2",
        verdict="high_confidence",
        rationale=(
            "SAM active with SBIR history; enough to defend Track 2 with "
            "multiple public federal signals in this synthetic brief."
        ),
        revenue_estimate=RevenueEstimate(
            band="50m_to_250m",
            source="press_release",
            rationale="Press suggests mid-market revenue.",
        ),
        target_roles=[],
        hooks=[ok, bad],
        tool_calls_used=3,
        tool_calls_budget=13,
        wall_seconds=10.0,
        cost_usd=0.05,
    )
    urls = {
        "https://www.defense.gov/News/Releases/release-ok",
        "https://www.defense.gov/News/Releases/release-bad",
    }
    filtered, report = apply_filter(brief, fetched_urls=set(), citation_urls=urls)
    assert len(filtered.hooks) == 1
    assert "playbook_messaging_violation" in {r[1] for r in report.dropped_hooks}


def test_parse_brief_normalizes_buyer_tier_alias() -> None:
    payload = {
        "schema_version": "1.1",
        "track": "track_2",
        "verdict": "medium_confidence",
        "why_not_confident": "Single-pillar federal signal only.",
        "rationale": (
            "SBIR awards visible with moderate USAspending; SAM active — "
            "defensible Track 2 call with thin second pillar for this parse test."
        ),
        "revenue_estimate": {
            "band": "unknown",
            "source": "not_determinable",
            "rationale": "No revenue signal in this stub.",
        },
        "buyer_tier": "tier_1",
        "buyer_tier_confidence": "low",
        "product_angle": "foundation",
        "suggested_contact_priority": "priority_2",
        "target_roles": [],
        "hooks": [],
        "sources_used": [],
        "halt_reason": None,
    }
    text = json.dumps(payload)
    brief, err = parse_brief_from_model_text(
        text,
        run_id="run",
        company="Co",
        generated_at=datetime.now(UTC),
        max_tool_calls=13,
    )
    assert err is None
    assert brief is not None
    assert brief.buyer_tier == "tier_1_strike_zone"
    assert brief.product_angle == "foundation_primary"
    assert brief.suggested_contact_priority == "p2"
