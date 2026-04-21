"""Cost tracking.

Enforces the max_cost_usd budget from config. On every LLM response, we
add the usage to the running tally. If it crosses the budget, the agent
loop halts on the next iteration.

PRICING: verified for claude-opus-4-7 on 2026-04-18. Update as needed;
canonical source: https://docs.claude.com/en/docs/about-claude/pricing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# USD per million tokens (Anthropic pricing page, verified 2026-04-18).
PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_write_5m": 6.25,
        "cache_write_1h": 10.00,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_write_5m": 6.25,
        "cache_write_1h": 10.00,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write_5m": 3.75,
        "cache_write_1h": 6.00,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.00,
    },
}


@dataclass
class CostTracker:
    """Per-run cost accumulator.

    Usage:
        cost = CostTracker(model="claude-opus-4-7", max_usd=1.00)
        cost.add_usage(response.usage)
        if cost.exceeded:
            halt()
    """

    model: str
    max_usd: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    breakdown_by_iteration: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        p = PRICING_PER_MTOK.get(self.model)
        if p is None:
            p = PRICING_PER_MTOK["claude-opus-4-7"]  # Unknown slug: over-estimate with Opus.
        return (
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_read_tokens * p["cache_read"]
            + self.cache_write_tokens * p["cache_write_5m"]
        ) / 1_000_000

    @property
    def exceeded(self) -> bool:
        return self.total_usd >= self.max_usd

    def add_usage(self, usage: Any) -> None:
        """Accept an anthropic.types.Usage object or a dict with the same shape."""
        get = (lambda k: getattr(usage, k, 0)) if not isinstance(usage, dict) else usage.get
        self.input_tokens += get("input_tokens") or 0
        self.output_tokens += get("output_tokens") or 0
        self.cache_read_tokens += get("cache_read_input_tokens") or 0
        self.cache_write_tokens += get("cache_creation_input_tokens") or 0

        self.breakdown_by_iteration.append(
            {
                "input": get("input_tokens") or 0,
                "output": get("output_tokens") or 0,
                "cache_read": get("cache_read_input_tokens") or 0,
                "cache_write": get("cache_creation_input_tokens") or 0,
                "cumulative_usd": round(self.total_usd, 6),
            }
        )

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_usd": round(self.total_usd, 6),
            "budget_usd": self.max_usd,
            "budget_used_pct": round(100 * self.total_usd / self.max_usd, 2) if self.max_usd > 0 else 0,
        }
