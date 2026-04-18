"""Compliance keyword lists for the §7.3 output filter.

Four classes of markers, escalating in severity:

    WARN       → ITAR/EAR nomenclature. Flag + downgrade verdict to
                 low_confidence; strip offending span from hooks.
    WARN       → CUI markings. Flag + hard-remove span; log incident.
    WARN       → Export control markings (EAR99, ECCN patterns).
    HARD_STOP  → Classified markings (CONFIDENTIAL / SECRET / TOP SECRET /
                 NOFORN / SCI / SAP). Abort run; no brief returned;
                 SECURITY_INCIDENT trace line written; exit nonzero.

────────────────────────────────────────────────────────────────────────
IMPORTANT (§7.3.C): legal review is REQUIRED before v1 ships.

This initial list is a developer first-pass, not compliance counsel's
final word. Every pattern below has a "provenance" comment indicating
where it came from. Compliance counsel should:

  1. Confirm or remove each entry.
  2. Add any Arkenstone-specific contractual obligations (customer NDAs,
     ITAR/DDTC registration obligations, etc.).
  3. Sign off on the severity mapping (WARN vs HARD_STOP).

Until that sign-off, this file's output is informational at the WARN
tier and advisory at the HARD_STOP tier — the runtime still enforces
HARD_STOP, but we document the open review status.

Tracking: §7.7 leadership blocker 7.3.C.
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    WARN = "warn"
    HARD_STOP = "hard_stop"


class Marker(str, Enum):
    ITAR_USML = "itar_usml"
    CUI = "cui"
    EXPORT_CONTROL = "export_control"
    CLASSIFIED = "classified"


@dataclass(frozen=True)
class Pattern:
    marker: Marker
    severity: Severity
    label: str
    regex: re.Pattern[str]
    provenance: str


# ─────────────────────────────────────────────────────────────────────
# CLASSIFIED — HARD STOP
# ─────────────────────────────────────────────────────────────────────
# Provenance: ISOO CUI Registry + DoDM 5200.01 Vol 2, Appendix A.
# We match markings with strict word-boundary context to avoid tripping
# on regular English ("the classified documents were…") — we want to
# match *portion markings* and stamped-marking styles.
# ─────────────────────────────────────────────────────────────────────

_CLASSIFIED_PATTERNS: list[Pattern] = [
    # Banner markings are ALWAYS uppercase stamps — the regex is case-
    # sensitive to avoid false-positives on ordinary lowercase English
    # ("their secret sauce"; "the classified documents were…").
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="top_secret_banner",
        regex=re.compile(
            r"(?:^|\n|\s|/)TOP\s+SECRET(?://[A-Z0-9/\s,-]+)?(?=\s|$|\n|//)",
            re.MULTILINE,
        ),
        provenance="DoDM 5200.01 Vol 2 — top-secret banner marking (uppercase stamp)",
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="secret_banner",
        # Require either a line-start/newline, or a slash-compartment suffix
        # to qualify as a banner. This avoids matching mid-sentence lowercase
        # "secret" while still catching "SECRET//NOFORN" in any position.
        regex=re.compile(
            r"(?:^|\n)\s*SECRET(?://[A-Z0-9/\s,-]+)?(?=\s|$|\n|//)"
            r"|SECRET//[A-Z0-9/\s,-]+",
            re.MULTILINE,
        ),
        provenance="DoDM 5200.01 Vol 2 — secret banner marking (uppercase stamp)",
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="confidential_banner",
        # Narrow: require a formal banner / portion form.
        regex=re.compile(
            r"(?:^|\n)\s*CONFIDENTIAL(?://[A-Z0-9/\s,-]+)?(?=\s|$|\n)"
            r"|\(\s*CONFIDENTIAL(?://[A-Z0-9/\s,-]+)?\s*\)"
            r"|CONFIDENTIAL//[A-Z0-9/\s,-]+",
            re.MULTILINE,
        ),
        provenance="DoDM 5200.01 Vol 2 — confidential banner marking (narrowed)",
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="portion_marking",
        # Portion markings: (U), (C), (S), (TS), (S//NF), etc.
        # Conservative form to avoid false-positives on "(C) Copyright",
        # "(U.S.-based)", trademark/registration text, and single-letter
        # list markers. Triggers when one of:
        #   * The marker carries a classification compartment (e.g., "(S//NF)")
        #     — these are unambiguous classified portion markings.
        #   * The marker appears at the start of a line (DoD banner style).
        # Bare "(C)" or "(U)" anywhere else is NOT treated as classified;
        # we avoid mis-flagging ordinary legal / copyright text.
        regex=re.compile(
            r"\(\s*(?:TS|S|C|U)\s*//[A-Z0-9/\s,-]+\)"
            r"|(?:^|\n)\s*\(\s*(?:TS|S|C|U)\s*\)"
            # Must not be a copyright notice — "(C) Copyright", "(C) 2026".
            r"(?!\s+(?:Copyright|©|\d{4}\b))",
            re.MULTILINE,
        ),
        provenance=(
            "DoDM 5200.01 Vol 2 — paragraph portion markings (U), (C), (S), (TS). "
            "Narrowed to banner form + compartmented form to avoid copyright/"
            "U.S./legal false-positives."
        ),
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="noforn",
        regex=re.compile(r"\bNOFORN\b"),
        provenance="ODNI — dissemination control; always classified context",
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="sci_markings",
        # SCI compartment markings — bare token is ambiguous, require banner context.
        regex=re.compile(r"(?://|^|\n)\s*(?:SI|TK|HCS|KLONDIKE|GAMMA)\b"),
        provenance="ODNI — SCI compartment markings (contextualized)",
    ),
    Pattern(
        marker=Marker.CLASSIFIED,
        severity=Severity.HARD_STOP,
        label="sap",
        regex=re.compile(r"\bSPECIAL\s+ACCESS\s+PROGRAM\b|\bSAP//", re.IGNORECASE),
        provenance="DoDM 5205.07 — Special Access Programs",
    ),
]


# ─────────────────────────────────────────────────────────────────────
# CUI — WARN (strip span, downgrade confidence)
# ─────────────────────────────────────────────────────────────────────
# Provenance: 32 CFR Part 2002; ISOO CUI Registry.
# ─────────────────────────────────────────────────────────────────────

_CUI_PATTERNS: list[Pattern] = [
    Pattern(
        marker=Marker.CUI,
        severity=Severity.WARN,
        label="cui_banner",
        regex=re.compile(r"\bCUI(?://[A-Z0-9/\s,-]+)?\b"),
        provenance="32 CFR 2002.20 — CUI banner",
    ),
    Pattern(
        marker=Marker.CUI,
        severity=Severity.WARN,
        label="cui_specified_category",
        regex=re.compile(
            r"\bCUI//(?:SP-[A-Z]+|PRVCY|PRIIA|ISVI|INFRA|NNPI|LEI|OPSEC|PROPIN)\b"
        ),
        provenance="ISOO CUI Registry — SP-PRVCY, SP-NNPI, LEI, OPSEC, etc.",
    ),
    Pattern(
        marker=Marker.CUI,
        severity=Severity.WARN,
        label="legacy_fouo",
        regex=re.compile(r"\bFOUO\b|\bFOR\s+OFFICIAL\s+USE\s+ONLY\b", re.IGNORECASE),
        provenance="Legacy DoD marking, superseded by CUI but still appears",
    ),
    Pattern(
        marker=Marker.CUI,
        severity=Severity.WARN,
        label="legacy_les",
        regex=re.compile(r"\bLAW\s+ENFORCEMENT\s+SENSITIVE\b|\bLES\b", re.IGNORECASE),
        provenance="Legacy LES marking",
    ),
    Pattern(
        marker=Marker.CUI,
        severity=Severity.WARN,
        label="controlled_unclassified_spelled_out",
        regex=re.compile(r"\bCONTROLLED\s+UNCLASSIFIED\s+INFORMATION\b", re.IGNORECASE),
        provenance="Spelled-out form of CUI",
    ),
]


# ─────────────────────────────────────────────────────────────────────
# EXPORT CONTROL — WARN
# ─────────────────────────────────────────────────────────────────────
# Provenance: EAR (15 CFR 730-774), CCL. ECCN format: [0-9][A-E][0-9]{3}.
# ─────────────────────────────────────────────────────────────────────

_EXPORT_CONTROL_PATTERNS: list[Pattern] = [
    Pattern(
        marker=Marker.EXPORT_CONTROL,
        severity=Severity.WARN,
        label="eccn",
        regex=re.compile(r"\b(?:ECCN\s+)?[0-9][A-E]\d{3}(?:\.[a-z]\.\d+)?\b"),
        provenance="EAR Commerce Control List — ECCN format",
    ),
    Pattern(
        marker=Marker.EXPORT_CONTROL,
        severity=Severity.WARN,
        label="ear99",
        regex=re.compile(r"\bEAR99\b"),
        provenance="EAR — residual classification",
    ),
    Pattern(
        marker=Marker.EXPORT_CONTROL,
        severity=Severity.WARN,
        label="itar_statement",
        regex=re.compile(
            r"\bITAR[- ]controlled\b|\bITAR[- ]regulated\b|\bsubject\s+to\s+(?:the\s+)?ITAR\b",
            re.IGNORECASE,
        ),
        provenance="ITAR — explicit statements that content is controlled",
    ),
]


# ─────────────────────────────────────────────────────────────────────
# ITAR / USML technical categories — WARN
# ─────────────────────────────────────────────────────────────────────
# Provenance: 22 CFR 121.1 — USML Categories I–XXI.
#
# WARNING: This list is DELIBERATELY INCOMPLETE in v1. Specific weapon-
# system nomenclature lists (missile model numbers, specific munition
# designators) should be added only after legal review per §7.3.C.
#
# The patterns here are conservative: category-header language, not
# component nomenclature.
# ─────────────────────────────────────────────────────────────────────

_ITAR_PATTERNS: list[Pattern] = [
    Pattern(
        marker=Marker.ITAR_USML,
        severity=Severity.WARN,
        label="usml_category_reference",
        regex=re.compile(
            r"\bUSML\s+Category\s+(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX|XXI)\b",
            re.IGNORECASE,
        ),
        provenance="22 CFR 121.1 — USML category reference",
    ),
    # Category-header keywords. Intentionally broad; the WARN tier strips
    # the span from hooks rather than aborting the run.
    Pattern(
        marker=Marker.ITAR_USML,
        severity=Severity.WARN,
        label="usml_cat_iv_missiles",
        regex=re.compile(
            r"\b(?:ICBM|IRBM|SLBM|MIRV|re-?entry\s+vehicle)\b",
            re.IGNORECASE,
        ),
        provenance="USML Cat IV — launch vehicles, guided missiles, ballistic missiles",
    ),
    Pattern(
        marker=Marker.ITAR_USML,
        severity=Severity.WARN,
        label="usml_cat_xiv_chem_bio",
        regex=re.compile(
            r"\b(?:sarin|VX\s+agent|mustard\s+agent|anthrax\s+weapon)\b",
            re.IGNORECASE,
        ),
        provenance="USML Cat XIV — chemical/biological weapons",
    ),
    # TODO(§7.3.C): Add USML Cat V (explosives), Cat VIII (aircraft),
    # Cat XI (military electronics) patterns after legal review.
]


# ─────────────────────────────────────────────────────────────────────
# Public surface
# ─────────────────────────────────────────────────────────────────────

ALL_PATTERNS: list[Pattern] = (
    _CLASSIFIED_PATTERNS + _CUI_PATTERNS + _EXPORT_CONTROL_PATTERNS + _ITAR_PATTERNS
)


@dataclass(frozen=True)
class Hit:
    pattern_label: str
    marker: Marker
    severity: Severity
    matched_span: str
    start: int
    end: int


def scan(text: str) -> list[Hit]:
    """Return all pattern matches in `text`.

    The caller decides what to do with them — see output_filter.py
    for the HARD_STOP / WARN policy implementation.
    """
    hits: list[Hit] = []
    for pattern in ALL_PATTERNS:
        for m in pattern.regex.finditer(text):
            hits.append(
                Hit(
                    pattern_label=pattern.label,
                    marker=pattern.marker,
                    severity=pattern.severity,
                    matched_span=m.group(0),
                    start=m.start(),
                    end=m.end(),
                )
            )
    return hits


def has_hard_stop(hits: list[Hit]) -> bool:
    return any(h.severity is Severity.HARD_STOP for h in hits)
