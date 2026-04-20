"""CLI entry point for the prospect-research agent.

Usage:
    python -m agent --company "Shield AI"
    python -m agent --company shield.ai --domain shield.ai
    python -m agent --company "Hadrian" --json

Writes brief + trace to ./runs/<slug>/<ts>/ (see spec §2, §3).
Streams progress to stderr (§9). Final brief goes to stdout as JSON
by default so the CLI composes cleanly with other tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from agent.agent import Agent
from agent.brief import insufficient_data
from agent.observability.tracing import new_run_dir, slugify
from agent.tools import build_registry

stderr = Console(stderr=True)


def _peek_company_argv(argv: list[str]) -> str:
    """Best-effort company name for fatal-error briefs (argv before full parse)."""
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--company" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--company="):
            return tok.split("=", 1)[1]
        i += 1
    return "(unknown)"


def _build_progress(started: float):
    """Return a callable that streams timestamped progress lines to stderr."""

    def _emit(msg: str) -> None:
        elapsed = time.monotonic() - started
        stderr.print(f"[dim][{elapsed:5.1f}s][/dim] {msg}")

    return _emit


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent",
        description="Arkenstone prospect-research agent — classify a company against Track 1 / Track 2 ICP.",
    )
    parser.add_argument(
        "--company",
        required=True,
        help="Company name or domain (e.g., 'Shield AI' or 'shield.ai').",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Optional explicit domain hint. Improves URL allowlist seeding.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help=(
            "Override the run output directory. Default: "
            "./runs/<company-slug>/<ts>/"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the brief as JSON to stdout (default behavior — kept for explicit intent).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress lines on stderr.",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    progress = None if args.quiet else _build_progress(started)

    run_dir = Path(args.run_dir) if args.run_dir else new_run_dir(args.domain or args.company)
    registry = build_registry()
    agent = Agent(registry=registry)

    result = await agent.research(
        args.company,
        domain=args.domain,
        run_dir=run_dir,
        progress=progress,
    )

    # Brief to stdout, run dir path and summary to stderr.
    stdout_payload = result.brief.model_dump(mode="json")
    print(json.dumps(stdout_payload, indent=2, default=str))

    if not args.quiet:
        stderr.print(
            f"\n[bold]=== RESULT ===[/bold]\n"
            f"status:      {result.status}\n"
            f"track:       {result.brief.track}\n"
            f"verdict:     {result.brief.verdict}\n"
            f"tool calls:  {result.tool_calls_used}/{result.brief.tool_calls_budget}\n"
            f"wall:        {result.wall_seconds}s\n"
            f"cost:        ${result.cost_usd}\n"
            f"run dir:     {result.run_dir}\n"
        )
        if result.error:
            stderr.print(f"[red]error:[/red] {result.error}")

    # Exit codes: 0 ok, 1 insufficient/budget halts, 2 hard error/compliance stop.
    if result.status == "ok":
        return 0
    if result.status in ("error", "compliance_hard_stop"):
        return 2
    return 1


def main() -> None:
    argv = sys.argv[1:]
    try:
        code = asyncio.run(_main(argv))
    except KeyboardInterrupt:
        stderr.print("[yellow]interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        stderr.print(f"[red]fatal:[/red] {type(e).__name__}: {e}")
        company = _peek_company_argv(argv)
        brief = insufficient_data(
            run_id=str(uuid.uuid4()),
            generated_at=datetime.now(UTC),
            company_name_queried=company,
            why=f"Unhandled error before a normal brief was written: {type(e).__name__}: {e}",
            halt_reason="internal_error",
        )
        print(json.dumps(brief.model_dump(mode="json"), indent=2, default=str))
        sys.exit(1)
    else:
        sys.exit(code)


if __name__ == "__main__":
    main()

# Silence unused-import warnings; keep these available for `python -c` one-liners.
_unused = (slugify,)
