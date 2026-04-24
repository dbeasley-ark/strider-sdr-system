"""Parse model-emitted Brief JSON: defaults, null coercion, Pydantic validate."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from agent.brief import Brief

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_ALLOWED_HALT_REASONS = frozenset(
    {
        "tool_budget_exhausted",
        "context_budget_exhausted",
        "cost_budget_exhausted",
        "wall_budget_exhausted",
        "max_output_tokens_exhausted",
        "safety_filter",
        "compliance_hard_stop",
        "internal_error",
    }
)

# Models often echo user-facing copy ("budget exceeded") instead of the schema literal.
_HALT_REASON_ALIASES: dict[str, str] = {
    "wall_budget_exceeded": "wall_budget_exhausted",
    "tool_budget_exceeded": "tool_budget_exhausted",
    "cost_budget_exceeded": "cost_budget_exhausted",
    "context_budget_exceeded": "context_budget_exhausted",
}

_ALLOWED_BUYER_TIERS = frozenset(
    {
        "tier_1_strike_zone",
        "tier_2_displacement",
        "tier_3_future_growth",
        "unknown",
    }
)
_BUYER_TIER_ALIASES: dict[str, str] = {
    "tier_1": "tier_1_strike_zone",
    "strike_zone": "tier_1_strike_zone",
    "tier1": "tier_1_strike_zone",
    "tier_2": "tier_2_displacement",
    "displacement": "tier_2_displacement",
    "tier2": "tier_2_displacement",
    "tier_3": "tier_3_future_growth",
    "future_growth": "tier_3_future_growth",
    "tier3": "tier_3_future_growth",
    "sbir_growth": "tier_3_future_growth",
}

_ALLOWED_PRODUCT_ANGLES = frozenset(
    {
        "foundation_primary",
        "cohort_primary",
        "foundation_then_cohort",
        "unclear",
    }
)
_PRODUCT_ANGLE_ALIASES: dict[str, str] = {
    "foundation": "foundation_primary",
    "cohort": "cohort_primary",
    "foundation_first": "foundation_then_cohort",
    "foundation_then_cohort_primary": "foundation_then_cohort",
}

_ALLOWED_CONTACT_PRIORITY = frozenset({"p1", "p2", "p3", "unknown"})
_CONTACT_PRIORITY_ALIASES: dict[str, str] = {
    "priority_1": "p1",
    "priority1": "p1",
    "priority_2": "p2",
    "priority2": "p2",
    "priority_3": "p3",
    "priority3": "p3",
}

_ALLOWED_TIER_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})

_ALLOWED_REVENUE_SOURCES = frozenset(
    {
        "sec_filing",
        "press_release",
        "analyst_estimate",
        "federal_awards_proxy",
        "inferred_from_headcount",
        "not_determinable",
    }
)

# Models often invent enum strings that are semantically close to the schema.
_REVENUE_SOURCE_ALIASES: dict[str, str] = {
    "press_estimate": "press_release",
    "press": "press_release",
    "news": "press_release",
    "media": "press_release",
    "third_party_estimate": "analyst_estimate",
    "third_party_database": "analyst_estimate",
    "third_party": "analyst_estimate",
    "database_estimate": "analyst_estimate",
    "crm_estimate": "analyst_estimate",
    "vendor_estimate": "analyst_estimate",
    "marketplace_estimate": "analyst_estimate",
    "web_search": "analyst_estimate",
    "web_estimate": "analyst_estimate",
    "public_estimate": "analyst_estimate",
}


def _canonical_key(s: str) -> str:
    return s.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_halt_reason(raw: dict[str, Any]) -> None:
    hr = raw.get("halt_reason")
    if hr is None or not isinstance(hr, str):
        return
    s = hr.strip()
    if s in _ALLOWED_HALT_REASONS:
        return
    key = _canonical_key(s)
    if key in _HALT_REASON_ALIASES:
        raw["halt_reason"] = _HALT_REASON_ALIASES[key]
        return
    for allowed in _ALLOWED_HALT_REASONS:
        if _canonical_key(allowed) == key:
            raw["halt_reason"] = allowed
            return
    # Unknown invented literal — drop so Brief accepts null default.
    raw["halt_reason"] = None


def _normalize_enum_field(
    raw: dict[str, Any],
    key: str,
    allowed: frozenset[str],
    aliases: dict[str, str],
    *,
    fallback: str,
) -> None:
    val = raw.get(key)
    if not isinstance(val, str):
        return
    s = val.strip()
    if s in allowed:
        raw[key] = s
        return
    k = _canonical_key(s)
    if k in aliases:
        raw[key] = aliases[k]
        return
    for a in allowed:
        if _canonical_key(a) == k:
            raw[key] = a
            return
    raw[key] = fallback


def _normalize_playbook_fields(raw: dict[str, Any]) -> None:
    _normalize_enum_field(
        raw,
        "buyer_tier",
        _ALLOWED_BUYER_TIERS,
        _BUYER_TIER_ALIASES,
        fallback="unknown",
    )
    _normalize_enum_field(
        raw,
        "product_angle",
        _ALLOWED_PRODUCT_ANGLES,
        _PRODUCT_ANGLE_ALIASES,
        fallback="unclear",
    )
    _normalize_enum_field(
        raw,
        "suggested_contact_priority",
        _ALLOWED_CONTACT_PRIORITY,
        _CONTACT_PRIORITY_ALIASES,
        fallback="unknown",
    )
    _normalize_enum_field(
        raw,
        "buyer_tier_confidence",
        _ALLOWED_TIER_CONFIDENCE,
        {},
        fallback="unknown",
    )


def _normalize_revenue_estimate_source(raw: dict[str, Any]) -> None:
    rev = raw.get("revenue_estimate")
    if not isinstance(rev, dict):
        return
    src = rev.get("source")
    if not isinstance(src, str):
        return
    s = src.strip()
    if s in _ALLOWED_REVENUE_SOURCES:
        return
    key = _canonical_key(s)
    if key in _REVENUE_SOURCE_ALIASES:
        rev["source"] = _REVENUE_SOURCE_ALIASES[key]
        return
    for allowed in _ALLOWED_REVENUE_SOURCES:
        if _canonical_key(allowed) == key:
            rev["source"] = allowed
            return
    # Unknown invented literal — prefer honest "not_determinable" over parse failure.
    rev["source"] = "not_determinable"


def _truncate_list_fields(raw: dict[str, Any]) -> None:
    """Enforce max lengths the model sometimes exceeds (Pydantic rejects overflow)."""
    scp = raw.get("sales_conversation_prep")
    if isinstance(scp, dict):
        awards = scp.get("federal_prime_awards")
        if isinstance(awards, list) and len(awards) > 5:
            scp["federal_prime_awards"] = awards[:5]
    roles = raw.get("target_roles")
    if isinstance(roles, list) and len(roles) > 5:
        raw["target_roles"] = roles[:5]
    hooks = raw.get("hooks")
    if isinstance(hooks, list) and len(hooks) > 8:
        raw["hooks"] = hooks[:8]


def _normalize_brief_raw(raw: dict[str, Any]) -> None:
    _normalize_halt_reason(raw)
    _normalize_revenue_estimate_source(raw)
    _normalize_playbook_fields(raw)
    _truncate_list_fields(raw)


def parse_brief_from_model_text(
    text: str,
    *,
    run_id: str,
    company: str,
    generated_at: datetime,
    max_tool_calls: int,
) -> tuple[Brief | None, str | None]:
    """Extract JSON from model text, fill defaults, coerce JSON nulls, validate."""
    if not text.strip():
        return None, "empty model response"

    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None, "no JSON object in response"

    try:
        raw: dict[str, Any] = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return None, f"JSON decode error: {e}"

    raw.setdefault("run_id", run_id)
    raw.setdefault("generated_at", generated_at.isoformat())
    raw.setdefault("confidentiality", "internal_only")
    raw.setdefault("company_name_queried", company)
    raw.setdefault("tool_calls_used", 0)
    raw.setdefault("tool_calls_budget", max_tool_calls)
    raw.setdefault("wall_seconds", 0.0)
    raw.setdefault("cost_usd", 0.0)
    raw.setdefault("hooks", [])
    raw.setdefault("target_roles", [])
    raw.setdefault("sources_used", [])

    # JSON null leaves keys present; setdefault only fills missing keys.
    # The model often nulls fields the loop finalizes (see system prompt).
    if raw.get("wall_seconds") is None:
        raw["wall_seconds"] = 0.0
    if raw.get("cost_usd") is None:
        raw["cost_usd"] = 0.0
    if raw.get("tool_calls_used") is None:
        raw["tool_calls_used"] = 0
    if raw.get("tool_calls_budget") is None:
        raw["tool_calls_budget"] = max_tool_calls
    if raw.get("hooks") is None:
        raw["hooks"] = []
    if raw.get("target_roles") is None:
        raw["target_roles"] = []
    if raw.get("sources_used") is None:
        raw["sources_used"] = []
    # Omit null so Brief.default_factory fills full nested defaults.
    if raw.get("sales_conversation_prep") is None:
        raw.pop("sales_conversation_prep", None)

    _normalize_brief_raw(raw)

    try:
        return Brief.model_validate(raw), None
    except ValidationError as e:
        return None, f"schema validation failed: {e}"
