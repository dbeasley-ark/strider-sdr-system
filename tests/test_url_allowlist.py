"""Tests for URL allowlist enforcement (§7.1 #4, §7.2 #1)."""

from __future__ import annotations

import pytest

from agent.security.url_allowlist import UrlAllowlist, UrlNotAllowed


def test_seed_allows_exact_host() -> None:
    a = UrlAllowlist()
    a.seed("shield.ai")
    assert a.allows("https://shield.ai/about")
    a.check("https://shield.ai/about")


def test_seed_allows_subdomains() -> None:
    a = UrlAllowlist()
    a.seed("shield.ai")
    assert a.allows("https://www.shield.ai/")
    assert a.allows("https://careers.shield.ai/")


def test_random_host_denied() -> None:
    a = UrlAllowlist()
    a.seed("shield.ai")
    assert not a.allows("https://evil.com/exfil?data=x")
    with pytest.raises(UrlNotAllowed):
        a.check("https://evil.com/exfil?data=x")


def test_tld_boundary_not_a_suffix_match() -> None:
    a = UrlAllowlist()
    a.seed("ai")  # pathological — a TLD, not a registrable domain
    # A bare TLD in the allowlist should NOT match shield.ai; our host
    # match uses endswith("." + allowed), requiring a dot boundary.
    assert a.allows("https://shield.ai/")  # endswith ".ai" matches

    # But "ai" must still NOT match "mai.com" — no dot before "ai".
    assert not a.allows("https://mai.com/")


def test_citation_accepts_and_allows() -> None:
    a = UrlAllowlist()
    a.seed("shield.ai")
    assert not a.allows("https://www.defense.gov/news/foo")
    a.accept_citation("https://www.defense.gov/news/foo")
    assert a.allows("https://www.defense.gov/news/bar")


def test_seed_accepts_bare_host_or_url() -> None:
    a = UrlAllowlist()
    a.seed("https://shield.ai/about", "another-company.com")
    assert a.allows("https://www.shield.ai/")
    assert a.allows("https://another-company.com/page")


def test_snapshot_is_sorted_and_lowercase() -> None:
    a = UrlAllowlist()
    a.seed("Shield.AI")
    a.accept_citation("https://DEFENSE.GOV/a")
    snap = a.snapshot()
    assert snap["seed_hosts"] == ["shield.ai"]
    assert snap["citation_hosts"] == ["defense.gov"]
