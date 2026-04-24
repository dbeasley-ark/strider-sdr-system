#!/usr/bin/env python3
"""Build a SQLite index from DOL F_5500_*_Latest.zip (EBSA FOIA).

Example:
  curl -L -o /tmp/F_5500_2024_Latest.zip \\
    "https://www.askebsa.dol.gov/FOIA%20Files/2024/Latest/F_5500_2024_Latest.zip"
  PYTHONPATH=src python scripts/form5500_build_index.py \\
    --zip /tmp/F_5500_2024_Latest.zip --output ./data/form5500/index.sqlite --replace

The prospect agent reads AGENT_FORM_5500_DB_PATH (default ./data/form5500/index.sqlite).
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import zipfile
from pathlib import Path


def _normalize_ein(raw: str | None) -> str:
    if not raw:
        return ""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) < 9:
        return ""
    return digits[-9:].zfill(9)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS f5500 (
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
CREATE INDEX IF NOT EXISTS idx_f5500_sponsor_ein ON f5500(sponsor_ein_norm);
CREATE INDEX IF NOT EXISTS idx_f5500_sponsor_name ON f5500(sponsor_dfe_name);
"""


def _open_csv_from_zip(zip_path: Path) -> tuple[str, csv.DictReader[str]]:
    zf = zipfile.ZipFile(zip_path)
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not names:
        raise SystemExit(f"No CSV in zip: {zip_path}")
    member = names[0]
    stream = zf.open(member, "r")
    text = __import__("io").TextIOWrapper(stream, encoding="utf-8", errors="replace")
    return member, csv.DictReader(text)


def build_index(*, zip_path: Path, output_sqlite: Path, replace: bool) -> int:
    if replace and output_sqlite.exists():
        output_sqlite.unlink()
    output_sqlite.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output_sqlite)
    conn.executescript(CREATE_SQL)
    member, reader = _open_csv_from_zip(zip_path)
    rows = 0
    for row in reader:
        ack = (row.get("ACK_ID") or "").strip()
        if not ack:
            continue
        ein_raw = (row.get("SPONS_DFE_EIN") or "").strip()
        ein_norm = _normalize_ein(ein_raw)
        try:
            tot_boy = int(float(row.get("TOT_PARTCP_BOY_CNT") or 0))
        except (TypeError, ValueError):
            tot_boy = 0
        try:
            tot_act = int(float(row.get("TOT_ACTIVE_PARTCP_CNT") or 0))
        except (TypeError, ValueError):
            tot_act = 0
        conn.execute(
            """
            INSERT OR REPLACE INTO f5500 (
              ack_id, form_tax_prd, plan_name, sponsor_dfe_name, spons_dfe_ein,
              sponsor_ein_norm, admin_name, admin_ein,
              type_pension_bnft_code, type_welfare_bnft_code, sch_mep_attached_ind,
              tot_partcp_boy_cnt, tot_active_partcp_cnt
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ack,
                (row.get("FORM_TAX_PRD") or "").strip(),
                (row.get("PLAN_NAME") or "").strip(),
                (row.get("SPONSOR_DFE_NAME") or "").strip(),
                ein_raw,
                ein_norm,
                (row.get("ADMIN_NAME") or "").strip(),
                (row.get("ADMIN_EIN") or "").strip(),
                (row.get("TYPE_PENSION_BNFT_CODE") or "").strip(),
                (row.get("TYPE_WELFARE_BNFT_CODE") or "").strip(),
                (row.get("SCH_MEP_ATTACHED_IND") or "").strip(),
                tot_boy,
                tot_act,
            ),
        )
        rows += 1
        if rows % 50_000 == 0:
            conn.commit()
    conn.commit()
    conn.close()
    print(f"Indexed {rows} rows from {member} into {output_sqlite}", file=sys.stderr)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Form 5500 F_5500 SQLite index from EBSA zip.",
    )
    parser.add_argument("--zip", type=Path, required=True, help="Path to F_5500_YYYY_Latest.zip")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/form5500/index.sqlite"),
        help="Output SQLite path",
    )
    parser.add_argument("--replace", action="store_true", help="Delete existing output first")
    args = parser.parse_args()
    if not args.zip.is_file():
        raise SystemExit(f"Zip not found: {args.zip}")
    build_index(zip_path=args.zip, output_sqlite=args.output, replace=args.replace)


if __name__ == "__main__":
    main()
