"""Tool: lookup_form_5500_plans — EBSA Form 5500 FOIA SQLite index (tabular only).

Reads a local SQLite built by ``scripts/form5500_build_index.py`` from DOL
``F_5500_*_Latest.zip``. Use after SAM when ``employer_ein`` is known, or with
``sponsor_name`` (fuzzy) when EIN is missing. Does not download PDFs; see
``fetch_form_5500_filing_pdf`` when ``AGENT_FORM_5500_FETCH_FILINGS`` is enabled.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, HttpUrl

from agent.config import settings
from agent.form5500.constants import (
    DOL_FORM5500_DATASETS_URL,
    EFAST_5500_SEARCH_URL,
    EFAST_PUBLIC_DOWNLOAD_TEMPLATE,
    normalize_ein,
    plan_bucket,
)
from agent.tools._base import Tool


class LookupForm5500PlansInput(BaseModel):
    sponsor_ein: str | None = Field(
        default=None,
        description=(
            "Employer EIN (9 digits, optional dashes). Preferred join key for "
            "the FOIA index. Pass SAM ``employer_identification_number`` when present."
        ),
    )
    sponsor_name: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "Plan sponsor legal name substring when EIN is unknown. Uses "
            "case-insensitive LIKE — lower confidence than EIN match."
        ),
    )
    max_rows: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Cap on returned plan rows (most recent form_tax_prd first).",
    )


class Form5500PlanRow(BaseModel):
    ack_id: str = Field(..., max_length=30)
    form_tax_prd: str = Field(default="", max_length=12)
    plan_name: str = Field(default="", max_length=200)
    sponsor_dfe_name: str = Field(default="", max_length=200)
    spons_dfe_ein: str = Field(default="", max_length=12)
    admin_name: str = Field(default="", max_length=120)
    admin_ein: str = Field(default="", max_length=12)
    type_pension_bnft_code: str = Field(default="", max_length=80)
    type_welfare_bnft_code: str = Field(default="", max_length=80)
    sch_mep_attached_ind: str = Field(default="", max_length=4)
    tot_partcp_boy_cnt: int = Field(default=0, ge=0)
    tot_active_partcp_cnt: int = Field(default=0, ge=0)
    plan_bucket: Literal["pension_dc", "welfare", "combined", "other"] = "other"
    filing_download_url: str = Field(
        default="",
        max_length=500,
        description="Public EFAST Download.aspx URL for this Ack ID (optional PDF tool).",
    )


class LookupForm5500PlansOutput(BaseModel):
    sponsor_ein_query: str | None = None
    sponsor_name_query: str | None = None
    match_mode: Literal["ein", "name", "none"] = "none"
    rows_returned: int = 0
    plans: list[Form5500PlanRow] = Field(default_factory=list)
    datasets_citation_url: HttpUrl = Field(
        ...,
        description="DOL Form 5500 datasets disclosure page (trace citation).",
    )
    efast_search_citation_url: HttpUrl = Field(
        ...,
        description="EFAST2 Form 5500 Series Search (human verification).",
    )
    notes: str | None = Field(
        default=None,
        max_length=600,
        description="Index coverage / limitations (e.g. tabular-only, no PDF text).",
    )
    fetched_at: datetime
    error: str | None = None


def _download_url_for_ack(ack_id: str) -> str:
    return EFAST_PUBLIC_DOWNLOAD_TEMPLATE.format(ack_id=ack_id.strip())


def _query_sqlite(
    db_path: str,
    *,
    ein_norm: str,
    sponsor_name: str | None,
    max_rows: int,
) -> tuple[Literal["ein", "name", "none"], list[Form5500PlanRow]]:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    rows_out: list[Form5500PlanRow] = []
    mode: Literal["ein", "name", "none"] = "none"
    try:
        if ein_norm:
            mode = "ein"
            cur = conn.execute(
                """
                SELECT ack_id, form_tax_prd, plan_name, sponsor_dfe_name, spons_dfe_ein,
                       admin_name, admin_ein, type_pension_bnft_code, type_welfare_bnft_code,
                       sch_mep_attached_ind, tot_partcp_boy_cnt, tot_active_partcp_cnt
                FROM f5500
                WHERE sponsor_ein_norm = ?
                ORDER BY form_tax_prd DESC
                LIMIT ?
                """,
                (ein_norm, max_rows),
            )
        elif sponsor_name and len(sponsor_name.strip()) >= 3:
            mode = "name"
            # LIKE pattern: escape SQL wildcards conservatively
            pat = sponsor_name.strip().replace("%", r"\%").replace("_", r"\_")
            cur = conn.execute(
                r"""
                SELECT ack_id, form_tax_prd, plan_name, sponsor_dfe_name, spons_dfe_ein,
                       admin_name, admin_ein, type_pension_bnft_code, type_welfare_bnft_code,
                       sch_mep_attached_ind, tot_partcp_boy_cnt, tot_active_partcp_cnt
                FROM f5500
                WHERE UPPER(sponsor_dfe_name) LIKE UPPER(?) ESCAPE '\'
                ORDER BY form_tax_prd DESC
                LIMIT ?
                """,
                (f"%{pat}%", max_rows),
            )
        else:
            return "none", []

        for r in cur.fetchall():
            ack = str(r["ack_id"] or "").strip()
            if not ack:
                continue
            p = str(r["type_pension_bnft_code"] or "")
            w = str(r["type_welfare_bnft_code"] or "")
            bucket = plan_bucket(p, w)
            dl = _download_url_for_ack(ack)
            rows_out.append(
                Form5500PlanRow(
                    ack_id=ack,
                    form_tax_prd=str(r["form_tax_prd"] or "")[:12],
                    plan_name=str(r["plan_name"] or "")[:200],
                    sponsor_dfe_name=str(r["sponsor_dfe_name"] or "")[:200],
                    spons_dfe_ein=str(r["spons_dfe_ein"] or "")[:12],
                    admin_name=str(r["admin_name"] or "")[:120],
                    admin_ein=str(r["admin_ein"] or "")[:12],
                    type_pension_bnft_code=p[:80],
                    type_welfare_bnft_code=w[:80],
                    sch_mep_attached_ind=str(r["sch_mep_attached_ind"] or "")[:4],
                    tot_partcp_boy_cnt=max(0, int(r["tot_partcp_boy_cnt"] or 0)),
                    tot_active_partcp_cnt=max(0, int(r["tot_active_partcp_cnt"] or 0)),
                    plan_bucket=bucket,
                    filing_download_url=dl[:500],
                )
            )
    finally:
        conn.close()
    return mode, rows_out


class LookupForm5500Plans(Tool[LookupForm5500PlansInput, LookupForm5500PlansOutput]):
    name = "lookup_form_5500_plans"
    description = (
        "Query the local EBSA Form 5500 FOIA SQLite index (tabular fields only). "
        "After SAM: pass sponsor_ein when employer_identification_number is known; "
        "otherwise pass sponsor_name (≥3 chars) — case-insensitive substring match "
        "on plan sponsor legal name (SAM legal_business_name or queried company). "
        "EIN is higher confidence; name-only is still valid when EIN is redacted. "
        "Returns recent 401(k)/pension vs welfare rows, "
        "participant counts, administrator vs sponsor fields, MEP schedule flag, "
        "and EFAST download URLs per Ack ID. Requires a pre-built index at "
        "AGENT_FORM_5500_DB_PATH (see scripts/form5500_build_index.py). "
        "Does not fetch PDF text unless the separate filing tool is enabled."
    )
    Input = LookupForm5500PlansInput
    Output = LookupForm5500PlansOutput
    examples: ClassVar[list[dict[str, Any]]] = [
        {"sponsor_ein": "123456789"},
        {"sponsor_name": "Example Corp", "max_rows": 10},
    ]
    idempotent = True
    side_effects: ClassVar[list[str]] = ["read-only local SQLite (Form 5500 index)"]

    async def run(self, inputs: LookupForm5500PlansInput) -> LookupForm5500PlansOutput:
        now = datetime.utcnow()
        db_path = settings.form_5500_db_path
        if not db_path.is_file():
            return LookupForm5500PlansOutput(
                sponsor_ein_query=inputs.sponsor_ein,
                sponsor_name_query=inputs.sponsor_name,
                match_mode="none",
                rows_returned=0,
                plans=[],
                datasets_citation_url=DOL_FORM5500_DATASETS_URL,  # type: ignore[arg-type]
                efast_search_citation_url=EFAST_5500_SEARCH_URL,  # type: ignore[arg-type]
                notes="No SQLite index at AGENT_FORM_5500_DB_PATH; tabular lookup skipped.",
                fetched_at=now,
                error=(
                    f"Form 5500 index not found at {db_path}. "
                    "Build with: PYTHONPATH=src python scripts/form5500_build_index.py "
                    "--zip /path/to/F_5500_YYYY_Latest.zip --output ./data/form5500/index.sqlite"
                ),
            )

        ein_norm = normalize_ein(inputs.sponsor_ein) if inputs.sponsor_ein else ""
        name_q = inputs.sponsor_name.strip() if inputs.sponsor_name else None
        if not ein_norm and not (name_q and len(name_q) >= 3):
            return LookupForm5500PlansOutput(
                sponsor_ein_query=inputs.sponsor_ein,
                sponsor_name_query=inputs.sponsor_name,
                match_mode="none",
                rows_returned=0,
                plans=[],
                datasets_citation_url=DOL_FORM5500_DATASETS_URL,  # type: ignore[arg-type]
                efast_search_citation_url=EFAST_5500_SEARCH_URL,  # type: ignore[arg-type]
                notes="Provide sponsor_ein (9 digits) or sponsor_name (≥3 chars).",
                fetched_at=now,
                error="missing_query: need sponsor_ein or sponsor_name",
            )

        mode, plans = await asyncio.to_thread(
            _query_sqlite,
            str(db_path.resolve()),
            ein_norm=ein_norm,
            sponsor_name=name_q,
            max_rows=inputs.max_rows,
        )
        note_parts = [
            "Signal is EBSA FOIA tabular index only (not full PDF) unless filing fetch flag is on."
        ]
        if mode == "name":
            note_parts.append("Name match is fuzzy — prefer sponsor_ein from SAM when public.")
        return LookupForm5500PlansOutput(
            sponsor_ein_query=inputs.sponsor_ein,
            sponsor_name_query=inputs.sponsor_name,
            match_mode=mode,
            rows_returned=len(plans),
            plans=plans,
            datasets_citation_url=DOL_FORM5500_DATASETS_URL,  # type: ignore[arg-type]
            efast_search_citation_url=EFAST_5500_SEARCH_URL,  # type: ignore[arg-type]
            notes=" ".join(note_parts),
            fetched_at=now,
        )
