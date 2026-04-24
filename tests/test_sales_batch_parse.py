"""Batch runner stdout parsing."""

from __future__ import annotations

from agent.sales_app import _try_parse_brief_stdout


def test_parse_brief_plain_stdout() -> None:
    raw = (
        '{"schema_version": "1.2", "federal_revenue_posture": "not_in_federal_icp", '
        '"verdict": "insufficient_data"}\n'
    )
    b = _try_parse_brief_stdout(raw)
    assert b is not None
    assert b["federal_revenue_posture"] == "not_in_federal_icp"
    assert b["verdict"] == "insufficient_data"


def test_parse_brief_after_log_noise() -> None:
    noise = '{"level": "info", "msg": "hello"}\n'
    body = (
        '{"schema_version": "1.2", "federal_revenue_posture": "sponsorship_in_hand", '
        '"verdict": "high_confidence"}'
    )
    b = _try_parse_brief_stdout(noise + body)
    assert b is not None
    assert b["federal_revenue_posture"] == "sponsorship_in_hand"


def test_parse_brief_stdout_accepts_legacy_track_key() -> None:
    raw = '{"schema_version": "1.0", "track": "track_1", "verdict": "high_confidence"}\n'
    b = _try_parse_brief_stdout(raw)
    assert b is not None
    assert b["track"] == "track_1"


def test_parse_brief_missing_returns_none() -> None:
    assert _try_parse_brief_stdout('{"foo": 1}') is None
    assert _try_parse_brief_stdout("") is None
