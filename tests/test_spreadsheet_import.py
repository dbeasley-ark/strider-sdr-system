"""Tests for batch spreadsheet parsing."""

from __future__ import annotations

import io

import pytest

from agent.spreadsheet_import import SpreadsheetParseError, parse_prospect_spreadsheet


def test_parse_csv_company_column() -> None:
    raw = b"Company,Notes\nAcme Corp,West\nBeta LLC,\n"
    sheet = parse_prospect_spreadsheet(raw, filename="t.csv")
    assert sheet.rows == [("Acme Corp", None), ("Beta LLC", None)]


def test_parse_csv_domain_column() -> None:
    raw = b"Organization,Domain\nAcme Corp,acme.com\n"
    sheet = parse_prospect_spreadsheet(raw, filename="list.csv")
    assert sheet.rows == [("Acme Corp", "acme.com")]


def test_parse_csv_explicit_columns() -> None:
    raw = b"A,B,C\nx.com,Acme,ignored\n"
    sheet = parse_prospect_spreadsheet(
        raw,
        filename="m.csv",
        company_column="B",
        domain_column="A",
    )
    assert sheet.rows == [("Acme", "x.com")]


def test_parse_xlsx_roundtrip() -> None:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Company", "Domain"])
    ws.append(["Gamma Inc", "gamma.io"])
    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()
    sheet = parse_prospect_spreadsheet(raw, filename="p.xlsx")
    assert sheet.rows == [("Gamma Inc", "gamma.io")]


def test_empty_company_rows_skipped() -> None:
    raw = b"Company\nAcme\n\nBeta\n"
    sheet = parse_prospect_spreadsheet(raw, filename="t.csv")
    assert sheet.rows == [("Acme", None), ("Beta", None)]


def test_bad_extension() -> None:
    with pytest.raises(SpreadsheetParseError):
        parse_prospect_spreadsheet(b"a", filename="x.bin")


def test_parse_txt_as_csv() -> None:
    raw = b"Company\nDelta Co\n"
    sheet = parse_prospect_spreadsheet(raw, filename="export.txt")
    assert sheet.rows == [("Delta Co", None)]
