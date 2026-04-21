"""Final brief schema. The one artifact the SDR actually reads.

Every field here is load-bearing — the output validator rejects briefs
that violate this schema, and the §7 threat model depends on certain
fields (citations, verdict) being well-formed.

Spec references: §1 (acceptance criteria), §7.1 (citation validation),
§9 (confidence signaling).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

Track = Literal["track_1", "track_2", "neither"]
Verdict = Literal["high_confidence", "low_confidence", "insufficient_data"]


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

    ICP bands (§1): Track 1 $10M–$2B, Track 2 $50M–$2B.
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
        last_funding=LastFundingPrep(confidence="unknown"),
        federal_prime_awards=[],
    )


class Brief(BaseModel):
    """The final, machine-readable prospect research brief.

    Emitted to ./runs/<company>/<ts>/brief.json and to stdout. Read by an
    SDR in ≤60 seconds (per §1 goal).
    """

    # ── Meta ─────────────────────────────────────────────────────────
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    generated_at: datetime
    confidentiality: Literal["internal_only"] = "internal_only"

    # ── Identity ─────────────────────────────────────────────────────
    company_name_queried: str
    company_name_canonical: str | None = Field(
        default=None,
        description="Legal name resolved via SAM.gov, when available.",
    )
    domain: str | None = None
    uei: str | None = Field(default=None, pattern=r"^[A-Z0-9]{12}$")

    # ── Verdict ──────────────────────────────────────────────────────
    track: Track
    verdict: Verdict
    why_not_confident: str | None = Field(
        default=None,
        max_length=800,
        description=(
            "Populated when verdict != high_confidence. Human-readable reason "
            "(e.g. 'SAM.gov returned name_fuzzy_low'). Required by §9."
        ),
    )
    rationale: str = Field(
        ...,
        min_length=40,
        max_length=2000,
        description="2–4 sentence defense of the Track call, citing signals.",
    )

    # ── Decision content ─────────────────────────────────────────────
    revenue_estimate: RevenueEstimate
    target_roles: list[TargetRole] = Field(..., min_length=0, max_length=5)
    hooks: list[PersonalizationHook] = Field(..., min_length=0, max_length=8)

    # ── Sales conversation prep (structured) ─────────────────────────
    sales_conversation_prep: SalesConversationPrep = Field(
        default_factory=default_sales_conversation_prep,
        description="FedRAMP check, PEO, funding, mission, top awards — unknown-safe.",
    )

    # ── Provenance ───────────────────────────────────────────────────
    sources_used: list[SourceSummary] = Field(default_factory=list)
    tool_calls_used: int = Field(ge=0)
    tool_calls_budget: int = Field(ge=0)
    wall_seconds: float = Field(ge=0)
    cost_usd: float = Field(ge=0)

    # ── Halt reason (when agent bailed) ───────────────────────────────
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
        track="neither",
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
