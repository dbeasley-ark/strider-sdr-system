"""Tool: lookup_sam_registration (spec §4.4).

Given a company name (and optional UEI), return the SAM.gov entity
registration record. Gatekeeper for the other federal lookups —
§4.4 says if SAM returns not_found/inactive/expired, skip USAspending
and SBIR.

Free tier: 10 req/min, 1000/day. Token-bucket limits us to 9/min.

POC (point-of-contact) fields are NEVER fetched — spec §4.4 scope
decision. Contact enrichment is out of scope for v1.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl

from agent.config import settings
from agent.identity import (
    IdentityCache,
    ResolvedIdentity,
    token_sort_ratio,
)
from agent.reliability import (
    TokenBucket,
    TransientError,
    with_retry,
    with_timeout,
)
from agent.tools._base import Tool

_BASE_URL = "https://api.sam.gov/entity-information/v3/entities"
_FUZZY_HIGH = 0.92  # §4.4 fuzzy threshold

_sam_bucket = TokenBucket(name="sam.gov", rate_per_minute=9.0, capacity=1)
_identity_cache = IdentityCache()


class LookupSamRegistrationInput(BaseModel):
    recipient_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description=(
            "Legal or DBA name to search. URL-shaped inputs are accepted and "
            "resolved via the host portion (e.g., 'shield.ai' → 'SHIELD')."
        ),
    )
    uei: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{12}$",
        description="Optional 12-char SAM UEI. When provided, drives exact match.",
    )
    include_inactive: bool = Field(
        default=False,
        description="Set True only when researching formerly-registered entities.",
    )


class SamEntityRecord(BaseModel):
    uei: str
    legal_business_name: str
    cage_code: str | None = None
    registration_status: Literal[
        "active", "inactive", "expired", "submitted", "work_in_progress"
    ]
    registration_date: date | None = None
    expiration_date: date | None = None
    activation_date: date | None = None
    purpose_of_registration: str | None = None
    entity_structure: str | None = None
    naics_codes: list[str] = Field(default_factory=list)
    primary_naics: str | None = None
    business_types: list[str] = Field(default_factory=list)
    sba_business_types: list[str] = Field(default_factory=list)
    state_of_incorporation: str | None = None
    city: str | None = None       # NO street address (§4.4)
    state: str | None = None
    source_url: HttpUrl


class LookupSamRegistrationOutput(BaseModel):
    recipient_name_query: str
    identity_resolution: Literal[
        "exact_uei", "name_fuzzy_high", "name_fuzzy_low", "not_found"
    ]
    identity_candidates: list[str] = Field(default_factory=list)
    records_found: int = 0
    records: list[SamEntityRecord] = Field(default_factory=list)
    fetched_at: datetime
    error: str | None = None


class LookupSamRegistration(Tool[LookupSamRegistrationInput, LookupSamRegistrationOutput]):
    name = "lookup_sam_registration"
    description = (
        "Look up a company's SAM.gov entity registration. Returns UEI, legal "
        "name, registration status, NAICS codes, and small-business "
        "certifications (8(a), HUBZone, WOSB). Use this BEFORE any other "
        "federal lookup — it's the canonical source for the company's "
        "UEI, and an inactive/expired status gates whether to even bother "
        "with USAspending or SBIR. Never returns POC/contact data. City + "
        "state only (no street address)."
    )
    Input = LookupSamRegistrationInput
    Output = LookupSamRegistrationOutput
    examples: ClassVar[list[dict[str, Any]]] = [
        {"recipient_name": "Shield AI"},
        {"recipient_name": "Anduril Industries", "uei": "KXN8C4WDQK92"},
        {"recipient_name": "Firestorm Labs", "include_inactive": False},
    ]
    idempotent = True
    side_effects: ClassVar[list[str]] = ["outbound HTTPS to api.sam.gov"]

    def __init__(self, *, identity_cache: IdentityCache | None = None) -> None:
        super().__init__() if False else None  # Tool has no __init__
        self._cache = identity_cache or _identity_cache

    async def run(
        self,
        inputs: LookupSamRegistrationInput,
    ) -> LookupSamRegistrationOutput:
        now = datetime.utcnow()
        query = inputs.recipient_name.strip()

        api_key = settings.sam_gov_api_key.get_secret_value().strip()
        if not api_key:
            return LookupSamRegistrationOutput(
                recipient_name_query=query,
                identity_resolution="not_found",
                records_found=0,
                records=[],
                fetched_at=now,
                error=(
                    "SAM.gov lookup skipped: no SAM_GOV_API_KEY. "
                    "Use web_search for company signal; set a key when available."
                ),
            )

        params: dict[str, Any] = {
            "api_key": api_key,
            "samRegistered": "Yes" if not inputs.include_inactive else "All",
        }
        if inputs.uei:
            params["ueiSAM"] = inputs.uei
        else:
            params["legalBusinessName"] = _search_name_from(query)

        try:
            data = await _sam_get(params)
        except TransientError as e:
            return LookupSamRegistrationOutput(
                recipient_name_query=query,
                identity_resolution="not_found",
                records_found=0,
                records=[],
                fetched_at=now,
                error=f"transient: {e}",
            )

        entities = data.get("entityData", []) or []
        records = [_parse_entity(e) for e in entities if _parse_entity(e) is not None]

        # Identity-resolution method
        if inputs.uei and records:
            resolution: ResolvedIdentity = ResolvedIdentity(
                query=query,
                uei=records[0].uei,
                legal_business_name=records[0].legal_business_name,
                method="exact_uei",
                match_score=1.0,
            )
        else:
            resolution = _name_resolve(query, records)

        # Cache for downstream tools
        self._cache.put(query, resolution, uei_hint=inputs.uei)
        if inputs.uei:
            self._cache.put(inputs.uei, resolution)

        # Truncate long result sets
        records = records[:10]

        return LookupSamRegistrationOutput(
            recipient_name_query=query,
            identity_resolution=_as_output_resolution(resolution.method),
            identity_candidates=resolution.candidates,
            records_found=len(entities),
            records=records,
            fetched_at=now,
        )


def _search_name_from(query: str) -> str:
    """Turn 'https://shield.ai/' into 'shield'; leave plain names alone."""
    q = query.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if q.startswith(prefix):
            q = q[len(prefix):]
    q = q.split("/", 1)[0]
    # "shield.ai" → "shield"  (simple heuristic; SAM name search will
    # apply its own loose matching — we're just removing TLDs)
    if "." in q:
        q = q.rsplit(".", 1)[0]
    return q or query


def _name_resolve(query: str, records: list[SamEntityRecord]) -> ResolvedIdentity:
    if not records:
        return ResolvedIdentity(query=query, method="not_found")
    best = records[0]
    best_score = token_sort_ratio(query, best.legal_business_name)
    for r in records[1:]:
        s = token_sort_ratio(query, r.legal_business_name)
        if s > best_score:
            best = r
            best_score = s

    if best_score >= _FUZZY_HIGH:
        return ResolvedIdentity(
            query=query,
            uei=best.uei,
            legal_business_name=best.legal_business_name,
            method="name_fuzzy_high",
            match_score=best_score,
            candidates=[r.legal_business_name for r in records[:5]],
        )
    return ResolvedIdentity(
        query=query,
        uei=best.uei,
        legal_business_name=best.legal_business_name,
        method="name_fuzzy_low",
        match_score=best_score,
        candidates=[r.legal_business_name for r in records[:5]],
    )


def _as_output_resolution(
    method: str,
) -> Literal["exact_uei", "name_fuzzy_high", "name_fuzzy_low", "not_found"]:
    if method in ("exact_uei", "name_fuzzy_high", "name_fuzzy_low", "not_found"):
        return method  # type: ignore[return-value]
    return "not_found"


def _parse_entity(entity: dict[str, Any]) -> SamEntityRecord | None:
    """Parse one SAM entityData record. Returns None if shape is unexpected."""
    try:
        reg = entity.get("entityRegistration", {}) or {}
        core = entity.get("coreData", {}) or {}
        naics_data = (entity.get("assertions", {}) or {}).get("goodsAndServices", {}) or {}
        address = (core.get("physicalAddress", {}) or {})

        uei = reg.get("ueiSAM")
        if not uei:
            return None

        status_raw = (reg.get("registrationStatus") or "").lower()
        status: Literal[
            "active", "inactive", "expired", "submitted", "work_in_progress"
        ] = "inactive"
        if status_raw in ("active", "inactive", "expired", "submitted"):
            status = status_raw  # type: ignore[assignment]
        elif status_raw in ("work in progress", "work_in_progress"):
            status = "work_in_progress"

        naics_list = naics_data.get("naicsList", []) or []
        naics_codes: list[str] = []
        primary_naics: str | None = None
        for n in naics_list:
            code = n.get("naicsCode")
            if not code:
                continue
            naics_codes.append(str(code))
            if n.get("isPrimary") is True or n.get("primary") is True:
                primary_naics = str(code)

        biz = (entity.get("assertions", {}) or {}).get("entityInformation", {}) or {}

        return SamEntityRecord(
            uei=uei,
            legal_business_name=reg.get("legalBusinessName", "") or "",
            cage_code=reg.get("cageCode"),
            registration_status=status,
            registration_date=_parse_date(reg.get("registrationDate")),
            expiration_date=_parse_date(reg.get("registrationExpirationDate")),
            activation_date=_parse_date(reg.get("activationDate")),
            purpose_of_registration=reg.get("purposeOfRegistrationDesc"),
            entity_structure=biz.get("entityStructureDesc") or core.get("entityStructureDesc"),
            naics_codes=naics_codes,
            primary_naics=primary_naics,
            business_types=[str(x) for x in (biz.get("businessTypes") or [])],
            sba_business_types=[str(x) for x in (biz.get("sbaBusinessTypes") or [])],
            state_of_incorporation=core.get("stateOfIncorporationCode"),
            city=address.get("city"),
            state=address.get("stateOrProvinceCode"),
            source_url=_permalink_for(uei),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _permalink_for(uei: str) -> str:
    return f"https://sam.gov/entity/{uei}/coreData"


async def _sam_get(params: dict[str, Any]) -> dict[str, Any]:
    """Rate-limited, retrying HTTPS GET against SAM v3."""
    await _sam_bucket.acquire(timeout=30.0)

    async def _do() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_BASE_URL, params=params)
        if resp.status_code == 429:
            raise TransientError(f"SAM 429 rate-limited (retry_after={resp.headers.get('retry-after')})")
        if 500 <= resp.status_code < 600:
            raise TransientError(f"SAM {resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(f"SAM {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    return await with_timeout(
        with_retry(_do, max_attempts=3, initial_wait=2.0, max_wait=60.0),
        seconds=45.0,
        name="lookup_sam_registration",
    )


def _use_test_base_url() -> None:
    """Set SAM_BASE_URL env var before import to override the endpoint."""
    global _BASE_URL
    override = os.environ.get("SAM_BASE_URL")
    if override:
        _BASE_URL = override


_use_test_base_url()
