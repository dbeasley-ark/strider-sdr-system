"""Eval runner. CI gate per spec §8.3.

Usage:
    python evals/run.py                        # all cases
    python evals/run.py --golden               # only golden
    python evals/run.py --adversarial          # only adversarial

Exit codes:
    0  – all thresholds met
    1  – one or more thresholds failed
    2  – runtime error

Threshold policy (§8.3):
    golden:      ≥ 85% Track classification accuracy (<80% hard fail)
    adversarial: 100% pass (one failure blocks merge unconditionally)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from agent.agent import Agent
from agent.brief import Brief
from agent.tools import build_registry

console = Console()

EVALS_DIR = Path(__file__).parent
GOLDEN_DIR = EVALS_DIR / "golden"
ADVERSARIAL_DIR = EVALS_DIR / "adversarial"

THRESHOLDS: dict[str, float] = {
    "golden": 0.85,        # §8.3: >=85%, <80% blocks merge
    "adversarial": 1.00,   # §8.3: 100%, unconditional
}
GOLDEN_HARD_FAIL = 0.80


@dataclass
class EvalCase:
    name: str
    kind: str  # "golden" | "adversarial"
    input: dict[str, Any]           # {"company": ..., "domain": ...}
    expected: dict[str, Any]        # track, verdict_minimum, etc.
    rationale: str = ""


@dataclass
class EvalResult:
    case: EvalCase
    passed: bool
    brief_summary: dict[str, Any]
    status: str
    cost_usd: float
    wall_seconds: float
    tool_calls_used: int
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def load_cases(path: Path, kind: str) -> list[EvalCase]:
    cases: list[EvalCase] = []
    if not path.exists():
        return cases
    for file in sorted(path.glob("*.json")):
        data = json.loads(file.read_text())
        items = data if isinstance(data, list) else [data]
        for item in items:
            cases.append(
                EvalCase(
                    name=item["name"],
                    kind=kind,
                    input=item["input"],
                    expected=item.get("expected", {}),
                    rationale=item.get("rationale", ""),
                )
            )
    return cases


async def _run_case(case: EvalCase) -> EvalResult:
    registry = build_registry()
    agent = Agent(registry=registry)
    result = await agent.research(
        case.input["company"],
        domain=case.input.get("domain"),
    )
    return _grade(
        case,
        result.brief,
        result.status,
        result.cost_usd,
        result.wall_seconds,
        result.tool_calls_used,
    )


_VERDICT_RANK = {
    "insufficient_data": 0,
    "low_confidence": 1,
    "medium_confidence": 2,
    "high_confidence": 3,
}


def _grade(
    case: EvalCase,
    brief: Brief,
    status: str,
    cost_usd: float,
    wall_seconds: float,
    tool_calls_used: int,
) -> EvalResult:
    failures: list[str] = []
    notes: list[str] = []
    exp = case.expected

    if "track" in exp and exp["track"] != brief.track:
        failures.append(f"track={brief.track!r}, expected {exp['track']!r}")

    if "verdict_minimum" in exp:
        actual = _VERDICT_RANK.get(brief.verdict, -1)
        want = _VERDICT_RANK.get(exp["verdict_minimum"], -1)
        if actual < want:
            failures.append(
                f"verdict={brief.verdict!r}, minimum was {exp['verdict_minimum']!r}"
            )

    if "verdict" in exp and exp["verdict"] != brief.verdict:
        failures.append(f"verdict={brief.verdict!r}, expected {exp['verdict']!r}")

    if "status" in exp and exp["status"] != status:
        failures.append(f"agent status={status!r}, expected {exp['status']!r}")

    if exp.get("forbid_high_confidence") and brief.verdict == "high_confidence":
        failures.append("forbid_high_confidence: got high_confidence")

    if "buyer_tier" in exp and exp["buyer_tier"] != brief.buyer_tier:
        failures.append(
            f"buyer_tier={brief.buyer_tier!r}, expected {exp['buyer_tier']!r}"
        )

    if "product_angle" in exp and exp["product_angle"] != brief.product_angle:
        failures.append(
            f"product_angle={brief.product_angle!r}, expected {exp['product_angle']!r}"
        )

    if "suggested_contact_priority" in exp and (
        exp["suggested_contact_priority"] != brief.suggested_contact_priority
    ):
        failures.append(
            "suggested_contact_priority="
            f"{brief.suggested_contact_priority!r}, "
            f"expected {exp['suggested_contact_priority']!r}"
        )

    if "buyer_tier_confidence" in exp and (
        exp["buyer_tier_confidence"] != brief.buyer_tier_confidence
    ):
        failures.append(
            "buyer_tier_confidence="
            f"{brief.buyer_tier_confidence!r}, "
            f"expected {exp['buyer_tier_confidence']!r}"
        )

    if cost_usd > 0.60:
        notes.append(f"cost overshoot: ${cost_usd}")
    if wall_seconds > 120:
        notes.append(f"wall overshoot: {wall_seconds}s")

    return EvalResult(
        case=case,
        passed=not failures,
        brief_summary={
            "track": brief.track,
            "verdict": brief.verdict,
            "buyer_tier": brief.buyer_tier,
            "product_angle": brief.product_angle,
            "why_not_confident": brief.why_not_confident,
            "halt_reason": brief.halt_reason,
            "hooks": len(brief.hooks),
            "target_roles": len(brief.target_roles),
        },
        status=status,
        cost_usd=cost_usd,
        wall_seconds=wall_seconds,
        tool_calls_used=tool_calls_used,
        failure_reason="; ".join(failures) if failures else None,
        notes=notes,
    )


async def run_suite(cases: list[EvalCase]) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        console.print(f"  running: [cyan]{case.kind}/{case.name}[/cyan]")
        try:
            result = await _run_case(case)
        except Exception as e:  # noqa: BLE001
            result = EvalResult(
                case=case,
                passed=False,
                brief_summary={},
                status="error",
                cost_usd=0.0,
                wall_seconds=0.0,
                tool_calls_used=0,
                failure_reason=f"{type(e).__name__}: {e}",
            )
        results.append(result)
    return results


def report(results: list[EvalResult]) -> int:
    by_kind: dict[str, list[EvalResult]] = {}
    for r in results:
        by_kind.setdefault(r.case.kind, []).append(r)

    table = Table(title="Eval Results", show_lines=True)
    table.add_column("kind")
    table.add_column("name")
    table.add_column("pass")
    table.add_column("track")
    table.add_column("verdict")
    table.add_column("cost $")
    table.add_column("wall s")
    table.add_column("failure", overflow="fold")
    for r in results:
        table.add_row(
            r.case.kind,
            r.case.name,
            "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]",
            str(r.brief_summary.get("track", "")),
            str(r.brief_summary.get("verdict", "")),
            f"{r.cost_usd:.4f}",
            f"{r.wall_seconds:.1f}",
            r.failure_reason or "",
        )
    console.print(table)

    exit_code = 0
    for kind, rs in by_kind.items():
        rate = sum(1 for r in rs if r.passed) / len(rs)
        threshold = THRESHOLDS.get(kind, 1.0)
        if kind == "golden" and rate < GOLDEN_HARD_FAIL:
            console.print(
                f"[red]golden hard fail[/red]: "
                f"{rate:.1%} < {GOLDEN_HARD_FAIL:.0%} — blocks merge."
            )
            exit_code = 1
        elif rate < threshold:
            console.print(
                f"[yellow]{kind}[/yellow]: {rate:.1%} (threshold {threshold:.0%}) [red]FAIL[/red]"
            )
            exit_code = 1
        else:
            console.print(
                f"{kind}: {rate:.1%} (threshold {threshold:.0%}) [green]OK[/green]"
            )

    total_cost = sum(r.cost_usd for r in results)
    console.print(f"[bold]total cost: ${total_cost:.4f}[/bold]")
    return exit_code


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", action="store_true")
    parser.add_argument("--adversarial", action="store_true")
    args = parser.parse_args(argv)

    cases: list[EvalCase] = []
    if args.golden or not args.adversarial:
        cases.extend(load_cases(GOLDEN_DIR, "golden"))
    if args.adversarial or not args.golden:
        cases.extend(load_cases(ADVERSARIAL_DIR, "adversarial"))

    if not cases:
        console.print(
            "[yellow]No cases found. Populate evals/golden/ or evals/adversarial/[/yellow]"
        )
        return 2

    console.print(f"running [bold]{len(cases)}[/bold] cases\n")
    results = await run_suite(cases)
    return report(results)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Runtime error: {e}[/red]")
        sys.exit(2)
