"""Tool: lookup_usaspending_awards (spec §4.3).

Return federal prime awards (contracts, IDVs) for a resolved company —
the strongest single ``sponsorship_in_hand`` signal. Public API, no key required.

No sub-awards in v1 (§4.3 scope decision). Logged as §10 gap.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl

from agent.reliability import TransientError, with_retry, with_timeout
from agent.tools._base import Tool

_BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


class LookupUSAspendingAwardsInput(BaseModel):
    recipient_name: str = Field(
        ...,
        min_length=2,
        description="Preferred legal entity name. Ideally from SAM.gov resolution.",
    )
    uei: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{12}$",
        description="Exact-match key when available. Highest confidence.",
    )
    duns: str | None = Field(
        default=None,
        pattern=r"^\d{9}$",
        description="DUNS is retired but older awards still cite it.",
    )
    lookback_years: int = Field(
        default=3, ge=1, le=10,
        description=(
            "How far back to look. 3 is the default; extend to 5 for close-call "
            "pre_sponsorship_path classifications."
        ),
    )
    award_types: list[Literal["contract", "idv"]] = Field(
        default_factory=lambda: ["contract", "idv"],
        description="Award categories to include.",
    )
    max_results: int = Field(
        default=25,
        ge=1,
        le=200,
        description="Cap on returned awards. Full count is in total_awards_found.",
    )


class FederalAward(BaseModel):
    award_id: str
    recipient_name_matched: str
    agency_top_tier: str
    agency_sub_tier: str | None = None
    award_type: Literal["contract", "idv"]
    amount_usd: float = 0.0
    period_start: date | None = None
    period_end: date | None = None
    description: str = ""
    naics_code: str | None = None
    naics_description: str | None = None
    source_url: HttpUrl


class LookupUSAspendingAwardsOutput(BaseModel):
    recipient_name_query: str
    identity_resolution: Literal[
        "exact_uei", "exact_duns", "name_fuzzy_high", "name_fuzzy_low", "not_found"
    ]
    identity_candidates: list[str] = Field(default_factory=list)
    awards: list[FederalAward] = Field(default_factory=list)
    total_awards_found: int = 0
    total_amount_usd: float = 0.0
    data_as_of: date | None = None
    fetched_at: datetime
    error: str | None = None


_AWARD_CODES = {
    "contract": ["A", "B", "C", "D"],
    "idv": ["IDV_A", "IDV_B", "IDV_C"],
}


class LookupUSAspendingAwards(
    Tool[LookupUSAspendingAwardsInput, LookupUSAspendingAwardsOutput]
):
    name = "lookup_usaspending_awards"
    description = (
        "Look up federal prime awards (contracts + IDVs) for a company "
        "over a lookback window. Strongest single sponsorship_in_hand signal — "
        "multiple active DoD primes + recent award activity is the "
        "cleanest positive indicator. Empty result is ALSO signal: a "
        "sponsorship_in_hand candidate with zero federal primes is probably not "
        "sponsorship_in_hand. UEI match is preferred; name-only is conservative "
        "(fuzzy threshold 92) to avoid confusing similarly-named "
        "companies. Does NOT query sub-awards in v1. The tool fans out "
        "one request per award-type group (contracts vs. IDVs) "
        "automatically; you can leave `award_types` at its default."
    )
    Input = LookupUSAspendingAwardsInput
    Output = LookupUSAspendingAwardsOutput
    examples: ClassVar[list[dict[str, Any]]] = [
        {"recipient_name": "Shield AI, Inc.", "uei": "KXN8C4WDQK92"},
        {"recipient_name": "Epirus", "lookback_years": 5},
        {
            "recipient_name": "Anduril Industries",
            "award_types": ["contract"],
            "max_results": 50,
        },
    ]
    idempotent = True
    side_effects: ClassVar[list[str]] = ["outbound HTTPS to api.usaspending.gov"]

    async def run(
        self, inputs: LookupUSAspendingAwardsInput
    ) -> LookupUSAspendingAwardsOutput:
        now = datetime.now(UTC)
        end = date.today()
        start = date(end.year - inputs.lookback_years, end.month, min(end.day, 28))

        # API 422 if award_type_codes mix groups — one POST per group, merge results.
        requested_groups = list(dict.fromkeys(inputs.award_types))  # preserve order, unique
        if not requested_groups:
            requested_groups = ["contract", "idv"]

        bodies = [
            _build_body(
                group=g,
                start=start,
                end=end,
                inputs=inputs,
            )
            for g in requested_groups
        ]

        try:
            results_per_group = await asyncio.gather(
                *(_usaspending_post(b) for b in bodies),
                return_exceptions=True,
            )
        except Exception as e:  # noqa: BLE001 — network glue, surface cleanly
            return LookupUSAspendingAwardsOutput(
                recipient_name_query=inputs.recipient_name,
                identity_resolution=_resolution(inputs),
                awards=[],
                total_awards_found=0,
                total_amount_usd=0.0,
                fetched_at=now,
                error=f"transient: {e}",
            )

        merged_rows: list[dict[str, Any]] = []
        total_rows_reported = 0
        errors: list[str] = []
        for group, outcome in zip(requested_groups, results_per_group, strict=True):
            if isinstance(outcome, TransientError):
                errors.append(f"{group}: transient: {outcome}")
                continue
            if isinstance(outcome, Exception):
                errors.append(f"{group}: {type(outcome).__name__}: {outcome}")
                continue
            data = outcome
            merged_rows.extend(data.get("results", []) or [])
            total_rows_reported += int(
                (data.get("page_metadata") or {}).get("total") or 0
            )

        if not merged_rows and errors:
            return LookupUSAspendingAwardsOutput(
                recipient_name_query=inputs.recipient_name,
                identity_resolution=_resolution(inputs),
                awards=[],
                total_awards_found=0,
                total_amount_usd=0.0,
                fetched_at=now,
                error="; ".join(errors),
            )

        seen_ids: set[str] = set()
        awards: list[FederalAward] = []
        for r in merged_rows:
            parsed = _parse_award(r)
            if parsed is None:
                continue
            if parsed.award_id and parsed.award_id in seen_ids:
                continue
            if parsed.award_id:
                seen_ids.add(parsed.award_id)
            awards.append(parsed)

        awards.sort(key=lambda a: a.amount_usd, reverse=True)
        awards = awards[: inputs.max_results]

        total = sum(a.amount_usd for a in awards)

        return LookupUSAspendingAwardsOutput(
            recipient_name_query=inputs.recipient_name,
            identity_resolution=_resolution(inputs),
            awards=awards,
            total_awards_found=total_rows_reported or len(awards),
            total_amount_usd=total,
            data_as_of=now.date(),
            fetched_at=now,
            error="; ".join(errors) if errors else None,
        )


def _build_body(
    *,
    group: Literal["contract", "idv"],
    start: date,
    end: date,
    inputs: LookupUSAspendingAwardsInput,
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "time_period": [
            {"start_date": start.isoformat(), "end_date": end.isoformat()}
        ],
        "award_type_codes": list(_AWARD_CODES[group]),
    }
    if inputs.uei:
        filters["recipient_id"] = inputs.uei
    else:
        filters["recipient_search_text"] = [inputs.recipient_name]

    return {
        "filters": filters,
        "fields": [
            "Award ID",
            "Recipient Name",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Award Amount",
            "Start Date",
            "End Date",
            "Description",
            "NAICS",
            "generated_internal_id",
            "award_type",
        ],
        "page": 1,
        "limit": inputs.max_results,
        "sort": "Award Amount",
        "order": "desc",
    }


def _resolution(
    inputs: LookupUSAspendingAwardsInput,
) -> Literal[
    "exact_uei", "exact_duns", "name_fuzzy_high", "name_fuzzy_low", "not_found"
]:
    """We don't re-run fuzzy logic here; if the caller gave UEI it was
    presumably resolved upstream. Name-only is reported as name_fuzzy_high
    because USAspending does its own exact-phrase search; the agent should
    rely on SAM's resolution when more precision is needed."""
    if inputs.uei:
        return "exact_uei"
    if inputs.duns:
        return "exact_duns"
    return "name_fuzzy_high"


def _parse_award(r: dict[str, Any]) -> FederalAward | None:
    try:
        award_type_code = (r.get("award_type") or "").upper()
        if award_type_code.startswith("IDV"):
            award_type: Literal["contract", "idv"] = "idv"
        else:
            award_type = "contract"

        gid = r.get("generated_internal_id") or ""

        return FederalAward(
            award_id=str(r.get("Award ID") or ""),
            recipient_name_matched=r.get("Recipient Name") or "",
            agency_top_tier=r.get("Awarding Agency") or "",
            agency_sub_tier=r.get("Awarding Sub Agency"),
            award_type=award_type,
            amount_usd=float(r.get("Award Amount") or 0.0),
            period_start=_parse_date(r.get("Start Date")),
            period_end=_parse_date(r.get("End Date")),
            description=(r.get("Description") or "")[:1000],
            naics_code=(r.get("NAICS") or {}).get("code")
                if isinstance(r.get("NAICS"), dict) else None,
            naics_description=(r.get("NAICS") or {}).get("description")
                if isinstance(r.get("NAICS"), dict) else None,
            source_url=f"https://www.usaspending.gov/award/{gid}",  # type: ignore[arg-type]
        )
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


async def _usaspending_post(body: dict[str, Any]) -> dict[str, Any]:
    async def _do() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(_BASE_URL, json=body)
        if resp.status_code == 429:
            raise TransientError("USAspending 429 rate-limited")
        if 500 <= resp.status_code < 600:
            raise TransientError(f"USAspending {resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(f"USAspending {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    return await with_timeout(
        with_retry(_do, max_attempts=3, initial_wait=1.0, max_wait=30.0),
        seconds=30.0,
        name="lookup_usaspending_awards",
    )


def _use_test_base_url() -> None:
    global _BASE_URL
    override = os.environ.get("USASPENDING_BASE_URL")
    if override:
        _BASE_URL = override


_use_test_base_url()
