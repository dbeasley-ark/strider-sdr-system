"""Tests for the §7.3 compliance scanner.

The compliance scanner is the LAST line of defense against a brief
leaking classified / CUI / ITAR content. These tests pin the HARD_STOP
behavior and guard against false-positives on ordinary English.
"""

from __future__ import annotations

from agent.security.compliance_keywords import (
    Marker,
    Severity,
    has_hard_stop,
    scan,
)


def test_hard_stop_top_secret_banner() -> None:
    text = "TOP SECRET//NOFORN"
    hits = scan(text)
    assert has_hard_stop(hits)
    assert any(h.marker == Marker.CLASSIFIED for h in hits)


def test_hard_stop_portion_marking() -> None:
    text = "(U) Unclassified paragraph. (S//NF) Classified paragraph."
    hits = scan(text)
    assert has_hard_stop(hits)


def test_portion_marking_no_fp_on_copyright() -> None:
    # "(C) Copyright 2026" is NOT a classified marking. Requires this
    # common legal boilerplate to not trip the hard-stop path.
    assert not has_hard_stop(scan("(C) Copyright 2026 Acme Corp, all rights reserved."))


def test_portion_marking_no_fp_on_us_abbreviation() -> None:
    assert not has_hard_stop(scan("Our company is a (U.S.)-based manufacturer."))


def test_portion_marking_no_fp_on_list_marker() -> None:
    # Bullet-list-ish usage like "(C) Second item" — not a classified banner.
    assert not has_hard_stop(scan("Options were: (A) wait, (B) retry, (C) escalate."))


def test_hard_stop_noforn_alone() -> None:
    hits = scan("Distribution: NOFORN")
    assert has_hard_stop(hits)


def test_cui_warn_only_not_hard_stop() -> None:
    hits = scan("Please treat this as CUI//SP-PRVCY until further notice.")
    assert not has_hard_stop(hits)
    assert any(h.marker == Marker.CUI for h in hits)
    assert all(h.severity == Severity.WARN for h in hits)


def test_legacy_fouo_warn() -> None:
    hits = scan("FOR OFFICIAL USE ONLY")
    assert not has_hard_stop(hits)
    assert any(h.marker == Marker.CUI for h in hits)


def test_eccn_warn() -> None:
    hits = scan("Classified as ECCN 9E001.")
    assert not has_hard_stop(hits)
    assert any(h.marker == Marker.EXPORT_CONTROL for h in hits)


def test_ear99_warn() -> None:
    assert any(h.marker == Marker.EXPORT_CONTROL for h in scan("EAR99 item"))


def test_ordinary_english_no_false_positive_for_confidential() -> None:
    # "Confidential" in an NDA context should NOT fire the classified banner.
    text = (
        "Under our Confidential and Proprietary information agreement, "
        "the parties shall treat all non-public data as confidential."
    )
    hits = scan(text)
    assert not has_hard_stop(hits), f"False positive on ordinary NDA text: {hits}"


def test_ordinary_english_no_false_positive_for_secret_word() -> None:
    # "Their secret sauce is…" should not match the SECRET banner.
    hits = scan("Their secret sauce is a proprietary optimization algorithm.")
    assert not has_hard_stop(hits)


def test_itar_statement_warn() -> None:
    hits = scan("This component is ITAR-controlled and requires export licensing.")
    assert any(h.marker == Marker.ITAR_USML or h.marker == Marker.EXPORT_CONTROL for h in hits)
