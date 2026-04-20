"""Parse model-emitted Brief JSON: defaults, null coercion, Pydantic validate."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from agent.brief import Brief

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


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

    try:
        return Brief.model_validate(raw), None
    except ValidationError as e:
        return None, f"schema validation failed: {e}"
