"""Final brief schema. The one artifact the SDR actually reads.

Every field here is load-bearing — the output validator rejects briefs
that violate this schema, and the §7 threat model depends on certain
fields (citations, verdict) being well-formed.

Naming vs. ``docs/arkenstone_sales_playbook_master.docx``: Part 2 ICP uses
**Tier 1–3** (Strike Zone, Displacement, Future Growth) — that is
``buyer_tier``. ``federal_revenue_posture`` is a separate federal-revenue
segmentation axis (sponsorship vs pre-sponsorship path) used for research;
it is not called "Track" in the playbook. ``verdict`` is agent research
confidence in that posture, not playbook P1–P3 (see
``suggested_contact_priority``).

Spec references: §1 (acceptance criteria), §7.1 (citation validation),
§9 (confidence signaling).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

FederalRevenuePosture = Literal[
    "sponsorship_in_hand",
    "pre_sponsorship_path",
    "not_in_federal_icp",
]
_LEGACY_TRACK_TO_POSTURE: dict[str, str] = {
    "track_1": "sponsorship_in_hand",
    "track_2": "pre_sponsorship_path",
    "neither": "not_in_federal_icp",
}


def migrate_raw_brief_legacy_federal_posture(raw: dict[str, Any]) -> None:
    """In-place: move legacy ``track`` / old enum strings to ``federal_revenue_posture``."""
    frp = raw.get("federal_revenue_posture")
    if isinstance(frp, str):
        s = frp.strip()
        if s in _LEGACY_TRACK_TO_POSTURE:
            raw["federal_revenue_posture"] = _LEGACY_TRACK_TO_POSTURE[s]
        raw.pop("track", None)
        return
    if "track" in raw:
        t = raw.get("track")
        if isinstance(t, str):
            key = t.strip()
            raw["federal_revenue_posture"] = _LEGACY_TRACK_TO_POSTURE.get(
                key, key if key else "not_in_federal_icp"
            )
        else:
            raw["federal_revenue_posture"] = "not_in_federal_icp"
        del raw["track"]


Verdict = Literal[
    "high_confidence",
    "medium_confidence",
    "low_confidence",
    "insufficient_data",
]

BuyerTier = Literal[
    "tier_1_strike_zone",
    "tier_2_displacement",
    "tier_3_future_growth",
    "unknown",
]
ProductAngle = Literal[
    "foundation_primary",
    "cohort_primary",
    "foundation_then_cohort",
    "unclear",
]
ContactPriority = Literal["p1", "p2", "p3", "unknown"]
TierConfidence = Literal["high", "medium", "low", "unknown"]


class PersonalizationHook(BaseModel):
    """A single outreach-ready hook the SDR can lead with.

    citation_url is hard-required by §7.1: the output validator rejects
    hooks whose URL did not appear in the run trace.
    """

    text: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="1–3 sentence hook, outreach-ready.",
    )
    citation_url: HttpUrl = Field(
        ...,
        description=(
            "URL backing the hook. Must resolve to a fetch_company_page or "
            "web_search citation recorded earlier in the trace."
        ),
    )
    snippet_only: bool = Field(
        default=False,
        description=(
            "True when we have the search snippet but the URL 404'd on "
            "follow-up fetch. §4.2 failure mode."
        ),
    )


class TargetRole(BaseModel):
    """A persona to approach inside the company."""

    title: str = Field(..., max_length=120, description="Role title, e.g. 'VP of Federal'.")
    rationale: str = Field(
        ...,
        max_length=400,
        description="One line on why this role is the right entry point.",
    )


class RevenueEstimate(BaseModel):
    """Revenue-band estimate, honest about uncertainty.

    Federal posture bands (product spec / agent rubric, not Part 2 tiers):
    ``sponsorship_in_hand`` $10M–$2B, ``pre_sponsorship_path`` $50M–$2B.
    """

    band: Literal[
        "under_10m",
        "10m_to_50m",
        "50m_to_250m",
        "250m_to_1b",
        "1b_to_2b",
        "over_2b",
        "unknown",
    ] = Field(..., description="Coarse band — granularity matches what public signal supports.")
    source: Literal[
        "sec_filing",
        "press_release",
        "analyst_estimate",
        "federal_awards_proxy",
        "inferred_from_headcount",
        "not_determinable",
    ] = Field(..., description="Where the estimate came from.")
    rationale: str = Field(
        ...,
        max_length=400,
        description="One line on how we arrived at the band.",
    )


class SourceSummary(BaseModel):
    """Tally of sources touched during this run."""

    tool_name: str
    calls: int = Field(ge=0)
    citations_used_in_brief: int = Field(
        default=0,
        ge=0,
        description="How many URLs from this source appear in hooks or rationales.",
    )


FedrampPostureStatus = Literal[
    "unknown",
    "no_marketplace_ties",
    "fedramp_authorized",
    "fedramp_in_process",
    "agency_in_process",
    "fedramp_ready",
]


class WhatTheyDoPrep(BaseModel):
    """One-line what the company does (SDR-facing)."""

    summary: str = Field(
        default="Unknown.",
        max_length=600,
        description="Factual one-liner; cite a URL when not generic unknown.",
    )
    citation_url: HttpUrl | None = Field(
        default=None,
        description="Trace-backed URL when summary is specific.",
    )


class FedrampPosturePrep(BaseModel):
    """FedRAMP marketplace posture — check every run; empty listing is normal."""

    status: FedrampPostureStatus = Field(
        default="unknown",
        description=(
            "no_marketplace_ties after a successful catalog lookup with zero "
            "relevant rows; never use insufficient_data for this alone."
        ),
    )
    stage: str | None = Field(
        default=None,
        max_length=120,
        description="Raw marketplace status when listed (Authorized, In Process, …).",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional press-only 'pursuing FedRAMP' context when marketplace silent.",
    )
    citation_url: HttpUrl | None = Field(
        default=None,
        description="Product detail URL or catalog/UI URL from tool trace.",
    )


class HrPeoPrep(BaseModel):
    """HR PEO (co-employment) signal — company-level only."""

    status: Literal["yes", "no", "unknown"] = Field(
        default="unknown",
        description="Whether the company appears to use an HR PEO.",
    )
    provider_hint: str | None = Field(
        default=None,
        max_length=120,
        description="Named PEO vendor when status=yes and evidence supports it.",
    )
    citation_url: HttpUrl | None = None


ParticipantScaleHint = Literal["unknown", "lt_50", "50_200", "200_1000", "1000_plus"]
Form5500SignalSource = Literal["unknown", "tabular_index", "tabular_plus_filing_pdf"]


class Form5500BenefitsPrep(BaseModel):
    """Form 5500 / EFAST2 tabular signal for benefits + PEO conversation prep."""

    signal_source: Form5500SignalSource = Field(
        default="unknown",
        description="tabular_index from FOIA SQLite; tabular_plus_filing_pdf when PDF tool used.",
    )
    dc_retirement_summary: str | None = Field(
        default=None,
        max_length=500,
        description="One or two sentences on pension/DC filing row(s) from tool output.",
    )
    group_health_welfare_summary: str | None = Field(
        default=None,
        max_length=500,
        description="One or two sentences on welfare / group health row(s) from tool output.",
    )
    participant_scale_hint: ParticipantScaleHint = Field(
        default="unknown",
        description="Coarse scale from TOT_PARTCP_BOY_CNT / active counts in tabular tool.",
    )
    administrator_or_service_provider_hint: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Named plan administrator from Form 5500 ADMIN_NAME when distinct "
            "from sponsor."
        ),
    )
    multi_employer_plan_schedule: bool | None = Field(
        default=None,
        description="True when SCH_MEP_ATTACHED_IND indicates MEP schedule attached.",
    )
    citation_url: HttpUrl | None = Field(
        default=None,
        description="Trace-backed DOL datasets or EFAST citation from lookup_form_5500_plans.",
    )
    confidence: TierConfidence = Field(
        default="unknown",
        description="Confidence in summaries given EIN vs name match and row coverage.",
    )
    limitations: str | None = Field(
        default=None,
        max_length=500,
        description="E.g. tabular-only (no PDF) or sponsor-name fuzzy match.",
    )


class LastFundingPrep(BaseModel):
    """Last observed funding event (public signal only)."""

    round_label: str | None = Field(default=None, max_length=80)
    observed_date: date | None = Field(
        default=None,
        description="Closing or announcement date when known.",
    )
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    citation_url: HttpUrl | None = None


class FederalPrimeAwardLine(BaseModel):
    """Top federal prime award line for the SDR."""

    agency_or_context: str = Field(..., max_length=220)
    amount_or_band: str = Field(..., max_length=120)
    period_hint: str | None = Field(default=None, max_length=120)
    citation_url: HttpUrl | None = Field(
        default=None,
        description="Prefer USAspending source_url from lookup_usaspending_awards.",
    )


class SalesConversationPrep(BaseModel):
    """Structured answers sales asked for before the first call."""

    what_they_do: WhatTheyDoPrep = Field(default_factory=WhatTheyDoPrep)
    fedramp_posture: FedrampPosturePrep = Field(default_factory=FedrampPosturePrep)
    hr_peo: HrPeoPrep = Field(default_factory=HrPeoPrep)
    form_5500_benefits: Form5500BenefitsPrep = Field(default_factory=Form5500BenefitsPrep)
    last_funding: LastFundingPrep = Field(default_factory=LastFundingPrep)
    federal_prime_awards: list[FederalPrimeAwardLine] = Field(
        default_factory=list,
        max_length=5,
    )


def default_sales_conversation_prep() -> SalesConversationPrep:
    """Conservative defaults for parse fallbacks and insufficient_data."""
    return SalesConversationPrep(
        what_they_do=WhatTheyDoPrep(summary="Not gathered in this run.", citation_url=None),
        fedramp_posture=FedrampPosturePrep(status="unknown"),
        hr_peo=HrPeoPrep(status="unknown"),
        form_5500_benefits=Form5500BenefitsPrep(signal_source="unknown"),
        last_funding=LastFundingPrep(confidence="unknown"),
        federal_prime_awards=[],
    )


class Brief(BaseModel):
    """The final, machine-readable prospect research brief.

    Emitted to ./runs/<company>/<ts>/brief.json and to stdout. Read by an
    SDR in ≤60 seconds (per §1 goal).
    """

    schema_version: Literal["1.0", "1.1", "1.2"] = "1.2"
    run_id: str
    generated_at: datetime
    confidentiality: Literal["internal_only"] = "internal_only"

    company_name_queried: str
    company_name_canonical: str | None = Field(
        default=None,
        description="Legal name resolved via SAM.gov, when available.",
    )
    domain: str | None = None
    uei: str | None = Field(default=None, pattern=r"^[A-Z0-9]{12}$")

    federal_revenue_posture: FederalRevenuePosture
    verdict: Verdict

    @model_validator(mode="before")
    @classmethod
    def _legacy_track_to_posture(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            migrate_raw_brief_legacy_federal_posture(data)
        return data

    buyer_tier: BuyerTier = Field(
        default="unknown",
        description=(
            "Playbook Part 2 tier (orthogonal to federal_revenue_posture): "
            "Tier 1 Strike Zone, Tier 2 Displacement, Tier 3 Future Growth."
        ),
    )
    buyer_tier_rationale: str | None = Field(
        default=None,
        max_length=900,
        description="Trace-backed rationale for buyer_tier; null when unknown.",
    )
    buyer_tier_confidence: TierConfidence = Field(
        default="unknown",
        description="high only with ≥2 independent tier signals in trace (per AGENT_SPEC §8).",
    )
    product_angle: ProductAngle = Field(
        default="unclear",
        description="Foundation vs Cohort lead for first conversation (playbook).",
    )
    suggested_contact_priority: ContactPriority = Field(
        default="unknown",
        description="P1 same-day only with multiple urgency signals; else unknown is honest.",
    )

    why_not_confident: str | None = Field(
        default=None,
        max_length=800,
        description=(
            "Populated when verdict is not high_confidence. Human-readable reason "
            "(e.g. 'SAM.gov returned name_fuzzy_low'). Required by §9 for "
            "medium_confidence, low_confidence, and insufficient_data."
        ),
    )
    rationale: str = Field(
        ...,
        min_length=40,
        max_length=2000,
        description="2–4 sentence defense of the federal_revenue_posture call, citing signals.",
    )

    revenue_estimate: RevenueEstimate
    target_roles: list[TargetRole] = Field(..., min_length=0, max_length=5)
    hooks: list[PersonalizationHook] = Field(..., min_length=0, max_length=8)

    sales_conversation_prep: SalesConversationPrep = Field(
        default_factory=default_sales_conversation_prep,
        description="FedRAMP check, PEO, funding, mission, top awards — unknown-safe.",
    )

    sources_used: list[SourceSummary] = Field(default_factory=list)
    tool_calls_used: int = Field(ge=0)
    tool_calls_budget: int = Field(ge=0)
    wall_seconds: float = Field(ge=0)
    cost_usd: float = Field(ge=0)

    halt_reason: (
        Literal[
            "tool_budget_exhausted",
            "context_budget_exhausted",
            "cost_budget_exhausted",
            "wall_budget_exhausted",
            "max_output_tokens_exhausted",
            "safety_filter",
            "compliance_hard_stop",
            "internal_error",
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "Populated when verdict=insufficient_data and the reason was a "
            "budget or safety halt. §6."
        ),
    )


def insufficient_data(
    *,
    run_id: str,
    generated_at: datetime,
    company_name_queried: str,
    why: str,
    halt_reason: (
        Literal[
            "tool_budget_exhausted",
            "context_budget_exhausted",
            "cost_budget_exhausted",
            "wall_budget_exhausted",
            "max_output_tokens_exhausted",
            "safety_filter",
            "compliance_hard_stop",
            "internal_error",
        ]
        | None
    ) = None,
    tool_calls_used: int = 0,
    tool_calls_budget: int = 13,
    wall_seconds: float = 0.0,
    cost_usd: float = 0.0,
) -> Brief:
    """Construct a graceful-failure brief (§9 "graceful failures")."""
    return Brief(
        run_id=run_id,
        generated_at=generated_at,
        company_name_queried=company_name_queried,
        federal_revenue_posture="not_in_federal_icp",
        verdict="insufficient_data",
        why_not_confident=why,
        rationale=(
            "Agent returned insufficient_data. See why_not_confident for the specific reason."
        ),
        revenue_estimate=RevenueEstimate(
            band="unknown",
            source="not_determinable",
            rationale="Insufficient data gathered.",
        ),
        target_roles=[],
        hooks=[],
        sales_conversation_prep=default_sales_conversation_prep(),
        halt_reason=halt_reason,
        tool_calls_used=tool_calls_used,
        tool_calls_budget=tool_calls_budget,
        wall_seconds=wall_seconds,
        cost_usd=cost_usd,
    )
