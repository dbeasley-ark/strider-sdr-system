"""Tests for tool result → trace / Anthropic is_error semantics."""

from __future__ import annotations

from agent.agent import _tool_payload_indicates_failure


def test_payload_not_failure_when_error_absent_or_null() -> None:
    assert not _tool_payload_indicates_failure({})
    assert not _tool_payload_indicates_failure({"error": None})
    assert not _tool_payload_indicates_failure(
        {"error": None, "identity_resolution": "not_found", "records": []}
    )


def test_payload_not_failure_when_error_blank_string() -> None:
    assert not _tool_payload_indicates_failure({"error": ""})
    assert not _tool_payload_indicates_failure({"error": "   "})


def test_payload_failure_when_error_non_empty() -> None:
    assert _tool_payload_indicates_failure({"error": "SAM.gov lookup skipped"})
    assert _tool_payload_indicates_failure({"error": "x"})


def test_payload_failure_when_error_non_string_truthy() -> None:
    assert _tool_payload_indicates_failure({"error": ["validation"]})
