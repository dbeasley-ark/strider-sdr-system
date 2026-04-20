"""Batch runner stdout parsing."""

from __future__ import annotations

from agent.sales_app import _try_parse_brief_stdout


def test_parse_brief_plain_stdout() -> None:
    raw = '{"schema_version": "1.0", "track": "neither", "verdict": "insufficient_data"}\n'
    b = _try_parse_brief_stdout(raw)
    assert b is not None
    assert b["track"] == "neither"
    assert b["verdict"] == "insufficient_data"


def test_parse_brief_after_log_noise() -> None:
    noise = '{"level": "info", "msg": "hello"}\n'
    body = '{"schema_version": "1.0", "track": "track_1", "verdict": "high_confidence"}'
    b = _try_parse_brief_stdout(noise + body)
    assert b is not None
    assert b["track"] == "track_1"


def test_parse_brief_missing_returns_none() -> None:
    assert _try_parse_brief_stdout('{"foo": 1}') is None
    assert _try_parse_brief_stdout("") is None
