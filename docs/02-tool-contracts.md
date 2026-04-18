# 02 · Tool Contracts

Vague schemas are the #1 source of agent hallucination. If you define `user_id` as "a string," the LLM will pass "John" and "User 123" and "bob@example.com" arbitrarily.

## Contract checklist

Every tool in this template must have:

1. **A Pydantic `Input` model** with `Field(..., description=...)` on every field.
2. **Pydantic `Output` model** — yes, outputs too. If the tool returns garbage, you want Pydantic to catch it, not the LLM.
3. **At least one concrete example.** This is the "Tool Use Example" pattern. It measurably reduces parameter errors on Claude.
4. **An action-oriented description** that explains *when* to use the tool, not just *what* it does.
5. **A `side_effects` list** documenting what changes in the world when this runs. If the list is non-empty, consider whether it should be gated in `PermissionScope.require_confirmation`.

The base class enforces all of this at import time. You cannot register a sloppy tool.

## Idempotency

If the tool is not idempotent, set `idempotent = False` and document the idempotency key in `AGENT_SPEC.md §4`. Retries on non-idempotent tools cause duplicate charges, duplicate emails, duplicate refunds.

## When you have a lot of tools

Above ~20 tools, the schema bloat in every request starts hurting you. Use the `to_search_schema()` mode in `ToolRegistry` to let Claude discover tools on demand. Reduces context by ~85% in published measurements.
