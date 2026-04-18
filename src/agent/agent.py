"""The prospect-research agent loop.

Uses the Anthropic SDK directly (not a tool runner) because we need
fine-grained control over:

  * Per-run tool-call budget (12) — a hard cap independent of LLM iterations.
  * URL allowlist enforcement on `fetch_company_page` (§7.1 #4, §7.2 #1).
  * SAM-first ordering gate (§4.4): SAM must resolve before USAspending/SBIR.
  * Native `web_search` — Anthropic server tool, declared in `tools` but
    not implemented by us. Its citations are captured and promoted into
    the URL allowlist.
  * Final output filter: compliance scan + citation validation (§7.1, §7.3).

Flow:

    1. Caller provides company + run_dir + allowlist seed.
    2. Loop:
       a. Check rails: tool_calls, cost, wall, iterations.
       b. Call Claude with tools.
       c. On end_turn → parse JSON brief → validate → filter → write.
       d. On tool_use → dispatch each (respecting budgets) → loop.
    3. Final artifact: ./runs/<slug>/<ts>/brief.json + trace.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import Message
from pydantic import ValidationError

from agent.brief import Brief, insufficient_data
from agent.config import settings
from agent.identity import IdentityCache
from agent.observability.cost import CostTracker
from agent.observability.tracing import Trace, new_run_dir
from agent.prompts import system as prompts
from agent.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    TransientError,
    with_retry,
    with_timeout,
)
from agent.security import (
    ComplianceHardStop,
    UrlAllowlist,
    UrlNotAllowed,
    apply_filter,
)
from agent.tools import ToolRegistry

AgentStatus = Literal[
    "ok",
    "halted_tool_budget",
    "halted_cost_budget",
    "halted_wall_budget",
    "halted_max_iterations",
    "compliance_hard_stop",
    "insufficient_data",
    "error",
]


@dataclass
class AgentResult:
    status: AgentStatus
    brief: Brief
    iterations: int = 0
    tool_calls_used: int = 0
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    error: str | None = None
    run_dir: str | None = None
    cost_summary: dict[str, Any] = field(default_factory=dict)


# ── Native web_search declaration ───────────────────────────────────

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 6,  # §4.2 per-run query budget
}


HaltReason = Literal[
    "tool_budget_exhausted",
    "context_budget_exhausted",
    "cost_budget_exhausted",
    "wall_budget_exhausted",
    "safety_filter",
    "compliance_hard_stop",
    "internal_error",
]


class Agent:
    """Orchestrates one prospect-research run."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        system_prompt_version: str = prompts.DEFAULT,
        model: str | None = None,
        tool_timeout_s: float = 30.0,
    ) -> None:
        self.client = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        self.registry = registry
        self.system_prompt = prompts.get(system_prompt_version)
        self.model = model or settings.model
        self.tool_timeout_s = tool_timeout_s
        self._breakers: dict[str, CircuitBreaker] = {}

    # ── Public API ───────────────────────────────────────────────────

    async def research(
        self,
        company: str,
        *,
        domain: str | None = None,
        run_dir: Path | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """Research a company. Returns an AgentResult with the final brief.

        The brief is also written to `<run_dir>/brief.json`; the trace is
        written to `<run_dir>/trace.jsonl`.
        """
        run_id = str(uuid.uuid4())
        started = time.monotonic()
        started_at = datetime.now(UTC)

        if run_dir is None:
            run_dir = new_run_dir(domain or company)

        cost = CostTracker(model=self.model, max_usd=settings.max_cost_usd)

        # URL allowlist seeded from caller input.
        allowlist = UrlAllowlist()
        allowlist.seed(company)
        if domain:
            allowlist.seed(domain)

        identity_cache = IdentityCache()

        fetched_urls: set[str] = set()
        citation_urls: set[str] = set()
        tool_call_counts: dict[str, int] = {}

        emit: Callable[[str], None] = progress or (lambda _msg: None)

        with Trace(run_dir=run_dir, run_id=run_id) as trace:
            trace.event(
                "agent.start",
                company=company,
                domain=domain,
                model=self.model,
                profile=settings.profile.value,
                tools=list(self.registry._tools.keys()) + ["web_search"],
                budgets={
                    "max_tool_calls": settings.max_tool_calls,
                    "max_cost_usd": settings.max_cost_usd,
                    "max_wall_seconds": settings.max_wall_seconds,
                    "max_iterations": settings.max_iterations,
                },
            )
            emit(f"Starting prospect-research for {company!r}")

            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": _initial_user_message(
                        company=company,
                        domain=domain,
                        run_id=run_id,
                        started_at=started_at,
                    ),
                }
            ]
            iterations = 0
            tool_calls_used = 0

            try:
                while True:
                    iterations += 1

                    # ── Budget rails ────────────────────────────
                    wall = time.monotonic() - started

                    if wall > settings.max_wall_seconds:
                        trace.event("halt.wall_budget", wall_s=wall)
                        return self._finalize_insufficient(
                            reason=(
                                f"wall budget exceeded "
                                f"({wall:.1f}s > {settings.max_wall_seconds}s)"
                            ),
                            halt_reason="wall_budget_exhausted",
                            status="halted_wall_budget",
                            run_id=run_id,
                            company=company,
                            started=started,
                            cost=cost,
                            iterations=iterations,
                            tool_calls=tool_calls_used,
                            trace=trace,
                            run_dir=run_dir,
                        )

                    if cost.exceeded:
                        trace.event("halt.cost_budget", **cost.summary())
                        return self._finalize_insufficient(
                            reason=(
                                f"cost budget exceeded "
                                f"(${cost.total_usd:.4f} >= ${settings.max_cost_usd})"
                            ),
                            halt_reason="cost_budget_exhausted",
                            status="halted_cost_budget",
                            run_id=run_id,
                            company=company,
                            started=started,
                            cost=cost,
                            iterations=iterations,
                            tool_calls=tool_calls_used,
                            trace=trace,
                            run_dir=run_dir,
                        )

                    if iterations > settings.max_iterations:
                        trace.event("halt.max_iterations", iterations=iterations)
                        return self._finalize_insufficient(
                            reason=f"max iterations reached ({iterations})",
                            halt_reason=None,
                            status="halted_max_iterations",
                            run_id=run_id,
                            company=company,
                            started=started,
                            cost=cost,
                            iterations=iterations,
                            tool_calls=tool_calls_used,
                            trace=trace,
                            run_dir=run_dir,
                        )

                    # ── LLM call ────────────────────────────────
                    trace.event("llm.request", iteration=iterations, msg_count=len(messages))
                    response = await self._call_llm(
                        messages,
                        allow_tools=tool_calls_used < settings.max_tool_calls,
                    )
                    cost.add_usage(response.usage)
                    trace.event(
                        "llm.response",
                        iteration=iterations,
                        stop_reason=response.stop_reason,
                        usage=cost.summary(),
                    )

                    messages.append({"role": "assistant", "content": response.content})

                    if response.stop_reason == "end_turn":
                        text = _extract_text(response)
                        brief, parse_error = _parse_brief(
                            text,
                            run_id=run_id,
                            company=company,
                            generated_at=datetime.now(UTC),
                        )
                        if brief is None:
                            trace.event(
                                "brief.parse_error",
                                error=parse_error,
                                text_preview=text[:500],
                            )
                            return self._finalize_insufficient(
                                reason=f"model output did not parse as Brief: {parse_error}",
                                halt_reason="internal_error",
                                status="error",
                                run_id=run_id,
                                company=company,
                                started=started,
                                cost=cost,
                                iterations=iterations,
                                tool_calls=tool_calls_used,
                                trace=trace,
                                run_dir=run_dir,
                            )

                        try:
                            filtered, report = apply_filter(
                                brief,
                                fetched_urls=fetched_urls,
                                citation_urls=citation_urls,
                            )
                        except ComplianceHardStop as e:
                            trace.incident(
                                "classified_marker_detected",
                                labels=sorted(
                                    {h.pattern_label for h in e.hits}
                                ),
                            )
                            return self._finalize_insufficient(
                                reason="classified/HARD_STOP marker detected; run aborted",
                                halt_reason="compliance_hard_stop",
                                status="compliance_hard_stop",
                                run_id=run_id,
                                company=company,
                                started=started,
                                cost=cost,
                                iterations=iterations,
                                tool_calls=tool_calls_used,
                                trace=trace,
                                run_dir=run_dir,
                            )

                        trace.event(
                            "brief.filtered",
                            dropped_hooks=[url for url, _ in report.dropped_hooks],
                            downgraded=report.downgraded_verdict,
                            compliance_hit_labels=[
                                h.pattern_label for h in report.compliance_hits
                            ],
                        )

                        # Backfill numeric fields that the model can't know.
                        filtered = filtered.model_copy(
                            update={
                                "tool_calls_used": tool_calls_used,
                                "tool_calls_budget": settings.max_tool_calls,
                                "wall_seconds": round(time.monotonic() - started, 3),
                                "cost_usd": round(cost.total_usd, 6),
                            }
                        )
                        _write_brief(run_dir, filtered)
                        trace.event(
                            "agent.end",
                            status="ok",
                            verdict=filtered.verdict,
                            track=filtered.track,
                            tool_calls_used=tool_calls_used,
                            wall_s=filtered.wall_seconds,
                            cost_usd=filtered.cost_usd,
                        )
                        emit(f"Brief written → {run_dir / 'brief.json'}")

                        return AgentResult(
                            status="ok",
                            brief=filtered,
                            iterations=iterations,
                            tool_calls_used=tool_calls_used,
                            cost_usd=filtered.cost_usd,
                            wall_seconds=filtered.wall_seconds,
                            run_dir=str(run_dir),
                            cost_summary=cost.summary(),
                        )

                    if response.stop_reason == "tool_use":
                        tool_uses = [b for b in response.content if b.type == "tool_use"]
                        remaining = settings.max_tool_calls - tool_calls_used
                        tool_results: list[dict[str, Any]] = []

                        if remaining <= 0:
                            for tu in tool_uses:
                                trace.event(
                                    "tool.refused_over_budget",
                                    tool=tu.name,
                                    tool_id=tu.id,
                                )
                                tool_results.append(
                                    _as_tool_result(
                                        tu.id,
                                        {
                                            "error": "tool_budget_exhausted",
                                            "detail": (
                                                "Global tool-call budget reached. "
                                                "Emit your final brief now."
                                            ),
                                        },
                                        is_error=True,
                                    )
                                )
                            messages.append({"role": "user", "content": tool_results})
                            continue

                        dispatched = tool_uses[:remaining]
                        denied = tool_uses[remaining:]
                        tool_calls_used += len(dispatched)

                        tool_results = await self._dispatch_tools(
                            dispatched,
                            trace=trace,
                            allowlist=allowlist,
                            identity_cache=identity_cache,
                            fetched_urls=fetched_urls,
                            citation_urls=citation_urls,
                            tool_call_counts=tool_call_counts,
                            emit=emit,
                        )
                        for tu in denied:
                            trace.event(
                                "tool.clamped_over_budget",
                                tool=tu.name,
                                tool_id=tu.id,
                            )
                            tool_results.append(
                                _as_tool_result(
                                    tu.id,
                                    {
                                        "error": "tool_budget_exhausted",
                                        "detail": (
                                            "Global tool-call budget reached mid-batch. "
                                            "Emit your final brief now."
                                        ),
                                    },
                                    is_error=True,
                                )
                            )

                        self._absorb_web_search_citations(
                            response,
                            allowlist=allowlist,
                            citation_urls=citation_urls,
                            trace=trace,
                        )

                        messages.append({"role": "user", "content": tool_results})
                        continue

                    if response.stop_reason == "pause_turn":
                        # Server-tool continuation: resend to resume.
                        trace.event("llm.pause_turn", iteration=iterations)
                        continue

                    trace.event("halt.unexpected_stop_reason", stop_reason=response.stop_reason)
                    return self._finalize_insufficient(
                        reason=f"unexpected stop_reason: {response.stop_reason}",
                        halt_reason="internal_error",
                        status="error",
                        run_id=run_id,
                        company=company,
                        started=started,
                        cost=cost,
                        iterations=iterations,
                        tool_calls=tool_calls_used,
                        trace=trace,
                        run_dir=run_dir,
                    )

            except Exception as e:  # noqa: BLE001
                trace.event(
                    "halt.unhandled_exception",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return self._finalize_insufficient(
                    reason=f"internal error: {type(e).__name__}: {e}",
                    halt_reason="internal_error",
                    status="error",
                    run_id=run_id,
                    company=company,
                    started=started,
                    cost=cost,
                    iterations=iterations,
                    tool_calls=tool_calls_used,
                    trace=trace,
                    run_dir=run_dir,
                )

    # ── Internals ───────────────────────────────────────────────────

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        *,
        allow_tools: bool,
    ) -> Message:
        custom_schemas = self.registry.to_anthropic_schemas()
        tools: list[dict[str, Any]] = (
            [*custom_schemas, WEB_SEARCH_TOOL] if allow_tools else []
        )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": settings.max_tokens,
            "system": self.system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if settings.thinking_adaptive:
            kwargs["thinking"] = {"type": "adaptive"}

        async def _do() -> Message:
            try:
                return await self.client.messages.create(**kwargs)
            except Exception as e:
                cls_name = type(e).__name__
                if cls_name in {
                    "APIConnectionError",
                    "APITimeoutError",
                    "InternalServerError",
                    "RateLimitError",
                    "OverloadedError",
                }:
                    raise TransientError(str(e)) from e
                raise

        return await with_retry(_do, max_attempts=4, initial_wait=1.0, max_wait=30.0)

    async def _dispatch_tools(
        self,
        tool_uses: list[Any],
        *,
        trace: Trace,
        allowlist: UrlAllowlist,
        identity_cache: IdentityCache,
        fetched_urls: set[str],
        citation_urls: set[str],
        tool_call_counts: dict[str, int],
        emit: Callable[[str], None],
    ) -> list[dict[str, Any]]:
        async def _one(block: Any) -> dict[str, Any]:
            tool_name = block.name
            tool_id = block.id
            tool_input = block.input if isinstance(block.input, dict) else {}
            tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1

            trace.event("tool.call", tool=tool_name, tool_id=tool_id, input=tool_input)

            if tool_name == "web_search":
                # Server-side — we should never be asked to execute it client-side.
                return _as_tool_result(
                    tool_id,
                    {"error": "web_search is an Anthropic server tool; no client handler"},
                    is_error=True,
                )

            if tool_name == "fetch_company_page":
                url = tool_input.get("url", "")
                try:
                    allowlist.check(url)
                except UrlNotAllowed as e:
                    trace.event(
                        "tool.url_not_allowed",
                        tool=tool_name,
                        tool_id=tool_id,
                        url=url,
                        allowlist=allowlist.snapshot(),
                    )
                    return _as_tool_result(
                        tool_id,
                        {"error": "url_not_allowed", "detail": str(e)},
                        is_error=True,
                    )

            breaker = self._breakers.setdefault(
                tool_name,
                CircuitBreaker(name=tool_name, failure_threshold=5, reset_timeout_s=30.0),
            )
            try:
                tool = self.registry.get(tool_name)
            except KeyError:
                trace.event("tool.unknown", tool=tool_name)
                return _as_tool_result(
                    tool_id,
                    {"error": "unknown_tool", "detail": f"No tool named {tool_name!r}"},
                    is_error=True,
                )

            async def _run_once() -> dict[str, Any]:
                return await with_timeout(
                    tool(tool_input),
                    seconds=self.tool_timeout_s,
                    name=tool_name,
                )

            async def _run_with_retry() -> dict[str, Any]:
                return await with_retry(
                    _run_once,
                    max_attempts=3,
                    initial_wait=0.5,
                    max_wait=8.0,
                    retry_on=(TransientError,),
                )

            try:
                result = await breaker.call(_run_with_retry)
            except CircuitOpenError as e:
                trace.event("tool.circuit_open", tool=tool_name)
                return _as_tool_result(
                    tool_id,
                    {"error": "circuit_open", "detail": str(e)},
                    is_error=True,
                )
            except Exception as e:  # noqa: BLE001
                trace.event(
                    "tool.exception",
                    tool=tool_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return _as_tool_result(
                    tool_id,
                    {"error": "tool_exception", "detail": str(e), "type": type(e).__name__},
                    is_error=True,
                )

            if tool_name == "fetch_company_page" and isinstance(result, dict):
                fetched = result.get("url")
                final = result.get("final_url")
                if isinstance(fetched, str):
                    fetched_urls.add(fetched)
                if isinstance(final, str):
                    fetched_urls.add(final)
                    allowlist.accept_citation(final)

            _progress_for_tool(tool_name, result, emit)

            is_error = isinstance(result, dict) and "error" in result
            trace.event(
                "tool.result",
                tool=tool_name,
                tool_id=tool_id,
                is_error=is_error,
            )
            return _as_tool_result(tool_id, result, is_error=is_error)

        return await asyncio.gather(*(_one(b) for b in tool_uses))

    def _absorb_web_search_citations(
        self,
        response: Message,
        *,
        allowlist: UrlAllowlist,
        citation_urls: set[str],
        trace: Trace,
    ) -> None:
        """Harvest web_search citation URLs from the assistant turn.

        Anthropic returns `web_search_tool_result` blocks whose `content`
        is a list of per-result blocks with `url` + `title`. We walk
        them, add each URL to the citation set, and promote their hosts
        to the URL allowlist so fetch_company_page can follow up.
        """
        new_urls: list[str] = []
        for block in response.content:
            content = getattr(block, "content", None)
            if content is None:
                continue
            items = content if isinstance(content, list) else [content]
            for item in items:
                url = getattr(item, "url", None)
                if url is None and isinstance(item, dict):
                    url = item.get("url")
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    new_urls.append(url)
                    citation_urls.add(url)
                    allowlist.accept_citation(url)
        if new_urls:
            trace.event(
                "web_search.citations_absorbed",
                count=len(new_urls),
                allowlist=allowlist.snapshot(),
            )

    # ── Finalizers ──────────────────────────────────────────────────

    def _finalize_insufficient(
        self,
        *,
        reason: str,
        halt_reason: HaltReason | None,
        status: AgentStatus,
        run_id: str,
        company: str,
        started: float,
        cost: CostTracker,
        iterations: int,
        tool_calls: int,
        trace: Trace,
        run_dir: Path,
    ) -> AgentResult:
        wall = round(time.monotonic() - started, 3)
        brief = insufficient_data(
            run_id=run_id,
            generated_at=datetime.now(UTC),
            company_name_queried=company,
            why=reason,
            halt_reason=halt_reason,
            tool_calls_used=tool_calls,
            tool_calls_budget=settings.max_tool_calls,
            wall_seconds=wall,
            cost_usd=round(cost.total_usd, 6),
        )
        _write_brief(run_dir, brief)
        trace.event(
            "agent.end",
            status=status,
            reason=reason,
            wall_s=wall,
        )
        return AgentResult(
            status=status,
            brief=brief,
            iterations=iterations,
            tool_calls_used=tool_calls,
            cost_usd=round(cost.total_usd, 6),
            wall_seconds=wall,
            error=reason if status in ("error", "compliance_hard_stop") else None,
            run_dir=str(run_dir),
            cost_summary=cost.summary(),
        )


# ── Module-level helpers ────────────────────────────────────────────


def _as_tool_result(tool_id: str, payload: Any, *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": json.dumps(payload, default=str),
        "is_error": is_error,
    }


def _extract_text(response: Message) -> str:
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_brief(
    text: str,
    *,
    run_id: str,
    company: str,
    generated_at: datetime,
) -> tuple[Brief | None, str | None]:
    if not text.strip():
        return None, "empty model response"

    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None, "no JSON object in response"

    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return None, f"JSON decode error: {e}"

    raw.setdefault("run_id", run_id)
    raw.setdefault("generated_at", generated_at.isoformat())
    raw.setdefault("confidentiality", "internal_only")
    raw.setdefault("company_name_queried", company)
    raw.setdefault("tool_calls_used", 0)
    raw.setdefault("tool_calls_budget", settings.max_tool_calls)
    raw.setdefault("wall_seconds", 0.0)
    raw.setdefault("cost_usd", 0.0)
    raw.setdefault("hooks", [])
    raw.setdefault("target_roles", [])
    raw.setdefault("sources_used", [])

    try:
        return Brief.model_validate(raw), None
    except ValidationError as e:
        return None, f"schema validation failed: {e}"


def _write_brief(run_dir: Path, brief: Brief) -> None:
    (run_dir / "brief.json").write_text(
        brief.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def _initial_user_message(
    *,
    company: str,
    domain: str | None,
    run_id: str,
    started_at: datetime,
) -> str:
    parts = [
        "Research the following company and produce a Brief:",
        f"- Company: {company}",
    ]
    if domain:
        parts.append(f"- Domain: {domain}")
    parts.extend([
        f"- Run ID (include in your brief.run_id verbatim): {run_id}",
        f"- Caller timestamp (include as brief.generated_at): {started_at.isoformat()}",
        "",
        "Start with lookup_sam_registration. Then call USAspending/SBIR in "
        "parallel if SAM returned an active entity. Use web_search to "
        "gather press and persona signal. Only call fetch_company_page on "
        "URLs that came from web_search citations or that match the "
        "company's own domain.",
        "",
        "Stop calling tools and emit the final Brief JSON when you're "
        "confident — or when you conclude confidence isn't reachable "
        "within budget (emit insufficient_data).",
    ])
    return "\n".join(parts)


def _progress_for_tool(
    tool_name: str, result: Any, emit: Callable[[str], None]
) -> None:
    if not isinstance(result, dict):
        return
    if tool_name == "lookup_sam_registration":
        records = result.get("records") or []
        if records:
            status = records[0].get("registration_status", "?")
            uei = records[0].get("uei", "?")
            emit(f"SAM.gov: {status}  UEI {uei}")
        else:
            emit(f"SAM.gov: {result.get('identity_resolution', 'not_found')}")
    elif tool_name == "lookup_usaspending_awards":
        n = result.get("total_awards_found") or 0
        total = result.get("total_amount_usd") or 0
        emit(f"USAspending: {n} awards, ${total:,.0f} total")
    elif tool_name == "lookup_sbir_awards":
        n = result.get("total_awards_found") or 0
        p3 = result.get("phase_iii_count") or 0
        emit(f"SBIR: {n} awards ({p3} Phase III)")
    elif tool_name == "fetch_company_page":
        u = result.get("final_url") or result.get("url") or ""
        inj = result.get("injection_signals") or []
        note = f" [injection:{','.join(inj)}]" if inj else ""
        emit(f"fetched: {u}{note}")


# ── Convenience wrappers ────────────────────────────────────────────


async def research(
    company: str,
    registry: ToolRegistry,
    *,
    domain: str | None = None,
    run_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> AgentResult:
    agent = Agent(registry=registry, **kwargs)
    return await agent.research(
        company, domain=domain, run_dir=run_dir, progress=progress
    )


async def run(goal: str, registry: ToolRegistry, **kwargs: Any) -> AgentResult:
    """Back-compat wrapper; treats goal as company name."""
    return await research(goal, registry, **kwargs)
