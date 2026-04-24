"""Tests for Form 5500 tabular lookup tool + registry wiring."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent.config import settings
from agent.tools.lookup_form_5500_plans import LookupForm5500Plans, LookupForm5500PlansInput


def _make_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE f5500 (
          ack_id TEXT PRIMARY KEY,
          form_tax_prd TEXT,
          plan_name TEXT,
          sponsor_dfe_name TEXT,
          spons_dfe_ein TEXT,
          sponsor_ein_norm TEXT,
          admin_name TEXT,
          admin_ein TEXT,
          type_pension_bnft_code TEXT,
          type_welfare_bnft_code TEXT,
          sch_mep_attached_ind TEXT,
          tot_partcp_boy_cnt INTEGER,
          tot_active_partcp_cnt INTEGER
        );
        INSERT INTO f5500 VALUES (
          'ACK401K00000000000000000000001',
          '2024-12-31',
          'Example 401(k) Plan',
          'Example Corp',
          '123456789',
          '123456789',
          'Example Corp',
          '123456789',
          '2A',
          '',
          '0',
          120,
          115
        );
        INSERT INTO f5500 VALUES (
          'ACKWELF00000000000000000000002',
          '2024-12-31',
          'Example Welfare Plan',
          'Example Corp',
          '123456789',
          '123456789',
          'TriNet Group Inc',
          '999999999',
          '',
          '4A',
          '1',
          400,
          380
        );
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_lookup_form_5500_by_ein(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "f5500.sqlite"
    _make_sqlite(db)
    monkeypatch.setattr(settings, "form_5500_db_path", db)

    tool = LookupForm5500Plans()
    out = await tool.run(LookupForm5500PlansInput(sponsor_ein="12-3456789", max_rows=10))
    assert out.error is None
    assert out.match_mode == "ein"
    assert out.rows_returned == 2
    buckets = {p.plan_bucket for p in out.plans}
    assert "pension_dc" in buckets
    assert "welfare" in buckets
    assert any("TriNet" in p.admin_name for p in out.plans)
    assert str(out.datasets_citation_url).startswith("https://www.dol.gov/")


@pytest.mark.asyncio
async def test_lookup_form_5500_missing_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "nope.sqlite"
    monkeypatch.setattr(settings, "form_5500_db_path", missing)

    tool = LookupForm5500Plans()
    out = await tool.run(LookupForm5500PlansInput(sponsor_ein="123456789"))
    assert out.error is not None
    assert out.rows_returned == 0


def test_build_registry_includes_lookup_not_fetch_by_default() -> None:
    from agent.tools import build_registry

    reg = build_registry()
    assert "lookup_form_5500_plans" in reg._tools
    assert "fetch_form_5500_filing_pdf" not in reg._tools
