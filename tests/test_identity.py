"""Tests for the §4.3 / §4.4 identity resolver."""

from __future__ import annotations

from agent.identity import IdentityCache, ResolvedIdentity, token_sort_ratio


def test_token_sort_ratio_handles_suffixes() -> None:
    # Corporate suffixes are stripped before comparison.
    s = token_sort_ratio("Shield AI, Inc.", "SHIELD AI")
    assert s == 1.0


def test_token_sort_ratio_distinct_names() -> None:
    # Shield AI vs. Shield Capital must score low — the §4.3 regression.
    s = token_sort_ratio("Shield AI", "Shield Capital")
    assert s < 0.92, f"Expected <0.92, got {s}"


def test_token_sort_ratio_empty_inputs() -> None:
    assert token_sort_ratio("", "anything") == 0.0
    assert token_sort_ratio("x", "") == 0.0


def test_identity_cache_roundtrip() -> None:
    c = IdentityCache()
    ident = ResolvedIdentity(
        query="Shield AI",
        uei="KXN8C4WDQK92",
        legal_business_name="SHIELD AI",
        method="name_fuzzy_high",
        match_score=0.95,
    )
    c.put("Shield AI", ident)
    got = c.get("shield ai")  # normalization is lowercase strip
    assert got is ident
    assert c.get("Different Company") is None


def test_identity_cache_uei_hint_is_keyed_separately() -> None:
    c = IdentityCache()
    without_hint = ResolvedIdentity(query="Shield", method="not_found")
    with_hint = ResolvedIdentity(query="Shield", method="exact_uei", uei="KXN8C4WDQK92")
    c.put("Shield", without_hint)
    c.put("Shield", with_hint, uei_hint="KXN8C4WDQK92")

    assert c.get("Shield") is without_hint
    assert c.get("Shield", uei_hint="KXN8C4WDQK92") is with_hint
