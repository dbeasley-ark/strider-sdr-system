"""Tool: lookup_fedramp_marketplace_products.

Fetches the public FedRAMP Marketplace **machine-readable catalog**
(`marketplace/products.json` — the JSON sibling of the `?view=cards` UI)
and scores rows against a search phrase (company / CSP name).

Empty matches after a successful fetch are **normal** — the prospect is
not required to appear on FedRAMP. That is not an error and must not
halt the research workflow.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl

from agent.config import settings
from agent.reliability import TransientError, with_retry, with_timeout
from agent.tools._base import Tool
from agent.tools.fetch_company_page import _robots_allows

# Public catalog (SvelteKit data). Same origin as the cards UI.
FEDRAMP_PRODUCTS_JSON_URL = "https://www.fedramp.gov/marketplace/products.json"
FEDRAMP_MARKETPLACE_UI_URL = "https://www.fedramp.gov/marketplace/products/?view=cards"


class LookupFedrampMarketplaceProductsInput(BaseModel):
    search_phrase: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Company legal name, brand, or CSP string to match against "
            "FedRAMP product `name`, `cloud_service_provider`, "
            "`cloud_service_offering`, and a short slice of "
            "`service_description`. Use the SAM canonical name when available."
        ),
    )
    max_matches: int = Field(
        default=8,
        ge=1,
        le=25,
        description="Maximum marketplace rows to return after scoring.",
    )
    max_catalog_bytes: int = Field(
        default=4_000_000,
        ge=500_000,
        le=8_000_000,
        description="Hard cap on catalog JSON bytes read from the response.",
    )
    timeout_seconds: float = Field(
        default=45.0,
        ge=5.0,
        le=90.0,
        description="HTTP timeout for the single catalog GET.",
    )


class FedrampMarketplaceMatch(BaseModel):
    fedramp_id: str = Field(..., description="FedRAMP product id (F-prefixed).")
    product_name: str = Field(..., description="Display name from marketplace.")
    cloud_service_provider: str = Field(default="", description="CSP field.")
    cloud_service_offering: str = Field(default="", description="CSO field.")
    marketplace_status: str = Field(
        ...,
        description=(
            "Authorization bucket from the listing: FedRAMP Authorized, "
            "FedRAMP In Process, Agency In Process, or FedRAMP Ready."
        ),
    )
    detail_url: HttpUrl = Field(
        ...,
        description="Canonical public product page on fedramp.gov.",
    )
    match_score: float = Field(ge=0.0, description="Internal relevance score.")


MarketplaceResolution = Literal[
    "no_marketplace_listing",
    "matches_found",
    "catalog_fetch_error",
]


class LookupFedrampMarketplaceProductsOutput(BaseModel):
    search_phrase_query: str
    marketplace_resolution: MarketplaceResolution
    matches: list[FedrampMarketplaceMatch] = Field(default_factory=list)
    catalog_request_url: HttpUrl = Field(
        ...,
        description="Exact catalog URL retrieved (for citation allowlist).",
    )
    marketplace_ui_url: HttpUrl = Field(
        ...,
        description="Human-visible marketplace cards URL (also allowlisted).",
    )
    products_in_catalog: int = Field(
        default=0,
        ge=0,
        description="Row count in the parsed catalog (for transparency).",
    )
    fetched_at: datetime
    error: str | None = Field(
        default=None,
        description="Set on transport/parse/robots failure — not set when matches are empty.",
    )


class LookupFedrampMarketplaceProducts(
    Tool[LookupFedrampMarketplaceProductsInput, LookupFedrampMarketplaceProductsOutput]
):
    name = "lookup_fedramp_marketplace_products"
    description = (
        "Query the **public FedRAMP Marketplace product catalog** (JSON export "
        "of all listings) for rows whose CSP / product / offering text matches "
        "your `search_phrase`. Call **once per run** after you have a solid "
        "company string (ideally post-SAM). "
        "**Zero matches is normal** — most companies are not listed; record "
        "`marketplace_resolution=no_marketplace_listing` and continue the full "
        "brief (Track verdict, hooks, etc.). Never treat an empty match list as "
        "a reason to stop or return `insufficient_data`. "
        "When matches exist, use `marketplace_status` as the **stage** for "
        "sales (Authorized / In Process / Ready / Agency In Process). "
        "Use `detail_url` as a trace-backed citation for that row. "
        "Do not copy sales_email / security_email from tool rows into the brief."
    )
    Input = LookupFedrampMarketplaceProductsInput
    Output = LookupFedrampMarketplaceProductsOutput
    examples: ClassVar[list[dict[str, Any]]] = [
        {"search_phrase": "Second Front Systems"},
        {"search_phrase": "Amazon Web Services", "max_matches": 5},
    ]
    idempotent = True
    side_effects: ClassVar[list[str]] = ["outbound HTTPS to www.fedramp.gov"]

    async def run(
        self, inputs: LookupFedrampMarketplaceProductsInput
    ) -> LookupFedrampMarketplaceProductsOutput:
        now = datetime.now(UTC)
        catalog_url = FEDRAMP_PRODUCTS_JSON_URL
        ui_url = FEDRAMP_MARKETPLACE_UI_URL

        allowed, robots_err = await _robots_allows(
            catalog_url, user_agent=settings.user_agent
        )
        if not allowed:
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(catalog_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error=robots_err or "robots_disallowed",
            )

        final_url = catalog_url
        try:
            body_text, final_url = await _fetch_catalog_text(
                catalog_url,
                max_bytes=inputs.max_catalog_bytes,
                timeout_s=inputs.timeout_seconds,
            )
        except TransientError as e:
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(catalog_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error=f"transient: {e}",
            )
        except Exception as e:  # noqa: BLE001
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(catalog_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error=f"fetch_error: {type(e).__name__}: {e}",
            )

        try:
            payload: Any = json.loads(body_text)
        except json.JSONDecodeError as e:
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(final_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error=f"json_parse_error: {e}",
            )

        try:
            products = payload["data"]["Products"]
        except (KeyError, TypeError):
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(final_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error="catalog_shape_unexpected: missing data.Products",
            )

        if not isinstance(products, list):
            return LookupFedrampMarketplaceProductsOutput(
                search_phrase_query=inputs.search_phrase,
                marketplace_resolution="catalog_fetch_error",
                catalog_request_url=HttpUrl(final_url),
                marketplace_ui_url=HttpUrl(ui_url),
                fetched_at=now,
                error="catalog_shape_unexpected: Products is not a list",
            )

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in products:
            if not isinstance(row, dict):
                continue
            s = _score_row(inputs.search_phrase, row)
            if s > 0:
                scored.append((s, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: inputs.max_matches]

        matches: list[FedrampMarketplaceMatch] = []
        for s, row in top:
            fid = str(row.get("fedramp_id") or "").strip()
            if not fid:
                continue
            name = str(row.get("name") or "").strip() or "(unnamed)"
            csp = str(row.get("cloud_service_provider") or "").strip()
            cso = str(row.get("cloud_service_offering") or "").strip()
            status = str(row.get("status") or "").strip() or "Unknown"
            detail = f"https://www.fedramp.gov/marketplace/products/{fid}/"
            matches.append(
                FedrampMarketplaceMatch(
                    fedramp_id=fid,
                    product_name=name[:500],
                    cloud_service_provider=csp[:500],
                    cloud_service_offering=cso[:500],
                    marketplace_status=status[:120],
                    detail_url=HttpUrl(detail),
                    match_score=round(s, 3),
                )
            )

        resolution: MarketplaceResolution = (
            "matches_found" if matches else "no_marketplace_listing"
        )

        return LookupFedrampMarketplaceProductsOutput(
            search_phrase_query=inputs.search_phrase,
            marketplace_resolution=resolution,
            matches=matches,
            catalog_request_url=HttpUrl(final_url),
            marketplace_ui_url=HttpUrl(ui_url),
            products_in_catalog=len(products),
            fetched_at=now,
            error=None,
        )


async def _fetch_catalog_text(
    url: str, *, max_bytes: int, timeout_s: float
) -> tuple[str, str]:
    async def _do() -> tuple[str, str]:
        headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json, */*;q=0.1",
        }
        async with httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            try:
                resp = await client.get(url, headers=headers)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                raise TransientError(str(e)) from e
            if resp.status_code >= 400:
                raise RuntimeError(f"http_{resp.status_code}")
            raw = resp.content
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            return raw.decode(resp.encoding or "utf-8", errors="replace"), str(resp.url)

    return await with_timeout(
        with_retry(_do, max_attempts=3, initial_wait=0.5, max_wait=8.0),
        seconds=timeout_s + 3.0,
        name="lookup_fedramp_marketplace_products",
    )


_WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    t = s.casefold().strip()
    t = _WS_RE.sub(" ", t)
    return t


def _tokens(s: str) -> list[str]:
    return [tok for tok in re.split(r"[^\w]+", _norm(s)) if len(tok) > 2]


def _score_row(phrase: str, row: dict[str, Any]) -> float:
    q = _norm(phrase)
    if not q:
        return 0.0
    q_tokens = _tokens(phrase)
    hay_parts = [
        str(row.get("name") or ""),
        str(row.get("cloud_service_provider") or ""),
        str(row.get("cloud_service_offering") or ""),
        str(row.get("service_description") or "")[:600],
    ]
    hay = " \n".join(hay_parts)
    hay_n = _norm(hay)
    score = 0.0
    if q in hay_n:
        score += 120.0
    for tok in q_tokens:
        if tok in hay_n:
            score += 18.0
    if len(q) <= 4 and q in hay_n:
        score += 40.0
    return score
