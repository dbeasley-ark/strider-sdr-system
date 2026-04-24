"""Tool: lookup_sbir_awards (spec §4.5).

Return SBIR / STTR phase awards for a company. Strong signal for
``pre_sponsorship_path`` (proactive federal posture) and for Phase III
(sole-source follow-on — the cleanest ``sponsorship_in_hand`` discriminator
for an early-stage company).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl

from agent.reliability import TokenBucket, TransientError, with_retry, with_timeout
from agent.tools._base import Tool

_BASE_URL = "https://api.www.sbir.gov/public/api/awards"

# SBIR.gov ~10 req/10min; client bucket ~0.9/min avoids quota 403s in batch runs.
_sbir_bucket = TokenBucket(name="sbir.gov", rate_per_minute=0.9, capacity=1)


class LookupSbirAwardsInput(BaseModel):
    recipient_name: str = Field(
        ...,
        min_length=2,
        description="Firm name as it appears on SBIR.gov.",
    )
    uei: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{12}$",
        description="Optional 12-char SAM UEI for exact match.",
    )
    duns: str | None = Field(
        default=None,
        pattern=r"^\d{9}$",
        description="Retired DUNS. Older SBIR awards still reference it.",
    )
    lookback_years: int = Field(
        default=5,
        ge=1,
        le=15,
        description="SBIR cycles are longer than contracts; 5-year default.",
    )
    agencies: list[Literal["DOD", "USAF", "USA", "USN", "DARPA", "MDA", "other"]] | None = (
        Field(
            default=None,
            description="Restrict to agencies. None = all.",
        )
    )
    phases: list[Literal["I", "II", "III"]] | None = Field(
        default=None,
        description="Restrict to phases. None = all (I, II, III).",
    )
    programs: list[Literal["SBIR", "STTR"]] = Field(
        default_factory=lambda: ["SBIR", "STTR"],
        description="Programs to include. Default: both SBIR and STTR.",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Cap on returned awards. Full count is in total_awards_found.",
    )


class SbirAward(BaseModel):
    award_id: str
    firm_name: str
    phase: Literal["I", "II", "III", "other"]
    program: Literal["SBIR", "STTR"]
    agency: str
    branch: str | None = None
    amount_usd: float | None = None
    award_date: date | None = None
    fiscal_year: int | None = None
    topic_code: str | None = None
    topic_title: str | None = None
    solicitation_year: int | None = None
    source_url: HttpUrl


class LookupSbirAwardsOutput(BaseModel):
    recipient_name_query: str
    identity_resolution: Literal[
        "exact_uei", "exact_duns", "name_fuzzy_high", "name_fuzzy_low", "not_found"
    ]
    identity_candidates: list[str] = Field(default_factory=list)
    awards: list[SbirAward] = Field(default_factory=list)
    total_awards_found: int = 0
    total_amount_usd: float = 0.0
    unknown_amount_count: int = 0
    phase_iii_count: int = 0
    fetched_at: datetime
    error: str | None = None


class LookupSbirAwards(Tool[LookupSbirAwardsInput, LookupSbirAwardsOutput]):
    name = "lookup_sbir_awards"
    description = (
        "Look up SBIR / STTR awards for a company. Phase I/II indicate a "
        "proactive federal posture (strong pre_sponsorship_path signal); Phase III "
        "(`phase_iii_count`) is the single cleanest sponsorship_in_hand discriminator "
        "for an early-stage company — Phase IIIs are sole-source follow-on "
        "contracts that don't need competitive solicitation. Zero SBIR is "
        "NOT evidence against sponsorship_in_hand — many large primes never did SBIR. "
        "Use this in parallel with USAspending, after SAM confirms the "
        "entity is active."
    )
    Input = LookupSbirAwardsInput
    Output = LookupSbirAwardsOutput
    examples: ClassVar[list[dict[str, Any]]] = [
        {"recipient_name": "Shield AI", "phases": ["II", "III"]},
        {"recipient_name": "Firestorm Labs", "agencies": ["USAF", "DARPA"]},
    ]
    idempotent = True
    side_effects: ClassVar[list[str]] = ["outbound HTTPS to api.www.sbir.gov"]

    async def run(self, inputs: LookupSbirAwardsInput) -> LookupSbirAwardsOutput:
        now = datetime.now(UTC)
        end_year = date.today().year
        start_year = end_year - inputs.lookback_years

        params: dict[str, Any] = {
            "firm": inputs.recipient_name,
            "rows": inputs.max_results,
            "year_start": start_year,
            "year_end": end_year,
        }
        if inputs.agencies:
            params["agency"] = ",".join(inputs.agencies)
        if inputs.phases:
            params["phase"] = ",".join(inputs.phases)
        if inputs.programs:
            params["program"] = ",".join(inputs.programs)

        try:
            data = await _sbir_get(params)
        except TransientError as e:
            return LookupSbirAwardsOutput(
                recipient_name_query=inputs.recipient_name,
                identity_resolution=_resolution(inputs),
                awards=[],
                fetched_at=now,
                error=f"transient: {e}",
            )
        except RuntimeError as e:
            # Quota 403 → rate_limited payload (no blind retries).
            msg = str(e)
            if "403" in msg and "rate limit" in msg.lower():
                return LookupSbirAwardsOutput(
                    recipient_name_query=inputs.recipient_name,
                    identity_resolution=_resolution(inputs),
                    awards=[],
                    fetched_at=now,
                    error=(
                        "rate_limited: SBIR.gov quota hit "
                        "(10 requests / 10 minutes). Skip SBIR for this run "
                        "and rely on web_search."
                    ),
                )
            raise

        if isinstance(data, dict):
            items = data.get("data") or data.get("awards") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        awards = [_parse_sbir(r) for r in items]
        awards = [a for a in awards if a is not None]

        total = sum(a.amount_usd or 0.0 for a in awards)
        unknown = sum(1 for a in awards if a.amount_usd is None)
        phase_iii = sum(1 for a in awards if a.phase == "III")

        return LookupSbirAwardsOutput(
            recipient_name_query=inputs.recipient_name,
            identity_resolution=_resolution(inputs),
            awards=awards[: inputs.max_results],
            total_awards_found=len(items),
            total_amount_usd=total,
            unknown_amount_count=unknown,
            phase_iii_count=phase_iii,
            fetched_at=now,
        )


def _resolution(
    inputs: LookupSbirAwardsInput,
) -> Literal["exact_uei", "exact_duns", "name_fuzzy_high", "name_fuzzy_low", "not_found"]:
    if inputs.uei:
        return "exact_uei"
    if inputs.duns:
        return "exact_duns"
    return "name_fuzzy_high"


def _parse_sbir(r: dict[str, Any]) -> SbirAward | None:
    try:
        phase_raw = str(r.get("phase") or "").strip()
        phase: Literal["I", "II", "III", "other"]
        if phase_raw in ("I", "II", "III"):
            phase = phase_raw  # type: ignore[assignment]
        elif phase_raw == "1":
            phase = "I"
        elif phase_raw == "2":
            phase = "II"
        elif phase_raw == "3":
            phase = "III"
        else:
            phase = "other"

        program_raw = str(r.get("program") or "SBIR").upper()
        program: Literal["SBIR", "STTR"] = "STTR" if "STTR" in program_raw else "SBIR"

        amount: float | None = None
        amount_raw = r.get("award_amount")
        if amount_raw not in (None, "", "N/A"):
            try:
                amount = float(amount_raw)
            except (ValueError, TypeError):
                amount = None

        award_id = str(r.get("contract") or r.get("award_id") or r.get("id") or "")

        return SbirAward(
            award_id=award_id,
            firm_name=str(r.get("firm") or ""),
            phase=phase,
            program=program,
            agency=str(r.get("agency") or "Unknown"),
            branch=r.get("branch") or r.get("agency_tracking_number"),
            amount_usd=amount,
            award_date=_parse_date(r.get("award_start_date") or r.get("proposal_award_date")),
            fiscal_year=_to_int(r.get("award_year")),
            topic_code=r.get("topic_code") or r.get("topic"),
            topic_title=r.get("award_title"),
            solicitation_year=_to_int(r.get("solicitation_year")),
            source_url=_source_url_for(r),  # type: ignore[arg-type]
        )
    except (TypeError, ValueError):
        return None


def _source_url_for(r: dict[str, Any]) -> str:
    url = r.get("award_link") or r.get("url")
    if url:
        return str(url)
    award_id = r.get("contract") or r.get("award_id") or r.get("id")
    return f"https://www.sbir.gov/awards/{award_id}" if award_id else "https://www.sbir.gov/"


def _to_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value)[: len(fmt.replace("%", ""))], fmt).date()
        except ValueError:
            continue
    return None


async def _sbir_get(params: dict[str, Any]) -> Any:
    await _sbir_bucket.acquire(timeout=30.0)

    async def _do() -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_BASE_URL, params=params)
        if resp.status_code == 429:
            raise TransientError("SBIR 429 rate-limited")
        if 500 <= resp.status_code < 600:
            raise TransientError(f"SBIR {resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(f"SBIR {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    return await with_timeout(
        with_retry(_do, max_attempts=3, initial_wait=1.0, max_wait=30.0),
        seconds=30.0,
        name="lookup_sbir_awards",
    )


def _use_test_base_url() -> None:
    global _BASE_URL
    override = os.environ.get("SBIR_BASE_URL")
    if override:
        _BASE_URL = override


_use_test_base_url()
