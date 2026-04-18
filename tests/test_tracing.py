"""Tests for SHA-256 hash-chained tracing (§7.6, AU-9)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.observability.tracing import Trace, scrub, slugify, verify_chain


def test_hash_chain_valid(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with Trace(run_dir=run_dir, run_id="r") as t:
        t.event("agent.start", foo="bar")
        t.event("tool.call", tool="lookup_sam")
        t.event("agent.end", status="ok")
    ok, reason = verify_chain(run_dir / "trace.jsonl")
    assert ok, reason


def test_tamper_detected(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with Trace(run_dir=run_dir, run_id="r") as t:
        t.event("agent.start")
        t.event("tool.call", tool="x")
        t.event("agent.end")

    # Mutate the middle line.
    path = run_dir / "trace.jsonl"
    lines = path.read_text().splitlines()
    mid = json.loads(lines[1])
    mid["tool"] = "mutated"
    lines[1] = json.dumps(mid, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")

    ok, reason = verify_chain(path)
    assert not ok
    assert "prev_hash" in (reason or "")


def test_scrubbing_removes_anthropic_key() -> None:
    value = "calling Anthropic with key sk-ant-0123456789abcdefghij_KEY"
    scrubbed = scrub(value)
    assert "sk-ant-" not in scrubbed
    assert "[REDACTED:anthropic_api_key]" in scrubbed


def test_scrubbing_removes_api_key_query_param() -> None:
    url = "https://api.sam.gov/x?api_key=abcdef123456789012345678"
    scrubbed = scrub(url)
    assert "abcdef" not in scrubbed


def test_scrubbing_recurses_into_dict() -> None:
    # The scrubber works on VALUES, not dict keys — so a secret must appear
    # inside a string value to be redacted. This mirrors how real secrets
    # would reach the trace (in a URL, error message, or API header).
    payload = {
        "inner": {"msg": "Authorization: Bearer abcdefghijklmnop1234567890"},
        "ok": [1, 2, 3],
    }
    out = scrub(payload)
    assert "[REDACTED:bearer_token]" in out["inner"]["msg"]
    assert "abcdefghijklmnop" not in out["inner"]["msg"]
    assert out["ok"] == [1, 2, 3]


def test_slugify_strips_scheme_and_tld() -> None:
    assert slugify("https://www.Shield.AI/about/") == "shield-ai"
    assert slugify("Anduril Industries, Inc.") == "anduril-industries-inc"
    assert slugify("") == "unknown"
