"""Company identity resolution.

Shared by the three federal lookup tools (§4.3/§4.4/§4.5). Resolves a
caller-provided company name or domain to a canonical UEI + legal name
via SAM.gov's entity-search, with a conservative fuzzy threshold (≥92)
to avoid confusing "Shield AI" with "Shield Capital" (§4.3 scope
decision).

Cached per-run so downstream tools don't re-resolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ResolutionMethod = Literal[
    "exact_uei",
    "exact_duns",
    "name_fuzzy_high",
    "name_fuzzy_low",
    "not_found",
]


@dataclass
class ResolvedIdentity:
    """A single identity-resolution result."""

    query: str
    uei: str | None = None
    duns: str | None = None
    legal_business_name: str | None = None
    method: ResolutionMethod = "not_found"
    match_score: float = 0.0  # 0..1 for name_fuzzy_*; 1.0 for exact_*
    candidates: list[str] = field(default_factory=list)
    """Top candidate legal names when method=='name_fuzzy_low'. Lets the
    LLM disambiguate by reading context."""


class IdentityCache:
    """Per-run memoization keyed by (name_or_domain, uei_hint)."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str | None], ResolvedIdentity] = {}

    def get(self, query: str, *, uei_hint: str | None = None) -> ResolvedIdentity | None:
        return self._cache.get((query.strip().lower(), uei_hint))

    def put(self, query: str, ident: ResolvedIdentity, *, uei_hint: str | None = None) -> None:
        self._cache[(query.strip().lower(), uei_hint)] = ident


def token_sort_ratio(a: str, b: str) -> float:
    """Cheap token-sort similarity without pulling in rapidfuzz.

    Returns a 0..1 Jaccard-like score on sorted tokens. We keep this
    dependency-free because the v1 tool uses this only for a boolean
    threshold check; if we ever need real fuzzy ranking we'll graduate
    to rapidfuzz.
    """
    a_tokens = set(_tokenize(a))
    b_tokens = set(_tokenize(b))
    if not a_tokens or not b_tokens:
        return 0.0
    inter = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(inter) / len(union)


def _tokenize(text: str) -> list[str]:
    """Strip corporate suffixes and non-alphanumeric, then lower-case."""
    # Drop common suffixes so "Shield AI, Inc." matches "SHIELD AI" in SAM.
    # This is conservative — we keep a single-token corporate-form list.
    stops = {
        "inc", "incorporated", "llc", "llp", "ltd", "limited",
        "corp", "corporation", "co", "company", "plc", "gmbh",
        "ag", "sa", "sas", "srl", "lp", "pbc",
    }
    words = []
    current = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                words.append("".join(current))
                current = []
    if current:
        words.append("".join(current))
    return [w for w in words if w and w not in stops]
