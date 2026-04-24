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
       a. Check rails: tool_calls, cost, wall, iterations (wall may trigger
          one tools-off synthesis round before stub insufficient_data).
       b. Call Claude with tools (or without, in the final buffer / synthesis).
       c. On end_turn → parse JSON brief → validate → filter → write.
       d. On tool_use → dispatch each (respecting budgets) → loop.
    3. Final artifact: ./runs/<slug>/<ts>/brief.json + trace.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import Message

from agent.brief import Brief, insufficient_data
from agent.brief_parse import parse_brief_from_model_text
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
    Severity,
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
    "halted_wall_budget_synthesized",
    "halted_context_budget",
    "halted_max_output_tokens",
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


WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
    "name": "web_search",
    # §4.2: web_search cap (4) — largest driver of input-token growth per turn.
    "max_uses": 4,
}


HaltReason = Literal[
    "tool_budget_exhausted",
    "context_budget_exhausted",
    "cost_budget_exhausted",
    "wall_budget_exhausted",
    "max_output_tokens_exhausted",
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

    async def research(
        self,
        company: str,
        *,
        domain: str | None = None,
        poc_name: str | None = None,
        poc_title: str | None = None,
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
            start_payload: dict[str, Any] = {
                "company": company,
                "domain": domain,
                "model": self.model,
                "profile": settings.profile.value,
                "tools": list(self.registry._tools.keys()) + ["web_search"],
                "budgets": {
                    "max_tool_calls": settings.max_tool_calls,
                    "max_cost_usd": settings.max_cost_usd,
                    "max_wall_seconds": settings.max_wall_seconds,
                    "max_iterations": settings.max_iterations,
                },
            }
            if poc_name:
                start_payload["poc_name"] = poc_name
            if poc_title:
                start_payload["poc_title"] = poc_title
            trace.event("agent.start", **start_payload)
            emit(f"Starting prospect-research for {company!r}")

            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": _initial_user_message(
                        company=company,
                        domain=domain,
                        poc_name=poc_name,
                        poc_title=poc_title,
                        run_id=run_id,
                        started_at=started_at,
                    ),
                }
            ]
            iterations = 0
            tool_calls_used = 0
            repair_attempts = 0  # One citation-repair LLM turn; not charged to tool budget.
            # Thread container_id on tool-enabled turns when required; omit when allow_tools=False.
            container_id: str | None = None
            wall_synthesis_attempted = False
            reserve_nudge_sent = False
            brief_parse_repair_attempts = 0

            try:
                while True:
                    iterations += 1

                    wall = time.monotonic() - started

                    if wall > settings.max_wall_seconds:
                        wall_reason = (
                            f"wall budget exceeded "
                            f"({wall:.1f}s > {settings.max_wall_seconds}s)"
                        )
                        if settings.wall_synthesis_enabled and not wall_synthesis_attempted:
                            wall_synthesis_attempted = True
                            trace.event(
                                "halt.wall_budget",
                                wall_s=wall,
                                phase="synthesis_attempt",
                            )
                            # If we stopped on a server-tool pause (`pause_turn`), the
                            # transcript still ends with an assistant turn until the API
                            # resumes. Capture that before appending the synthesis user
                            # message (which would hide the trailing-assistant signal).
                            wall_synth_allow_tools = _assistant_turn_pending(messages)
                            wall_synth_code_exec_needs_container = (
                                wall_synth_allow_tools
                                and _last_assistant_has_pending_code_execution_tool(
                                    messages
                                )
                                and not container_id
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": _wall_synthesis_user_message(
                                        company=company,
                                        wall_reason=wall_reason,
                                    ),
                                }
                            )
                            trace.event(
                                "llm.request",
                                iteration=iterations,
                                msg_count=len(messages),
                                phase="wall_synthesis",
                            )
                            if wall_synth_code_exec_needs_container:
                                trace.event(
                                    "wall_synthesis.missing_container_for_code_exec",
                                    iteration=iterations,
                                )
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; cannot resume code-execution "
                                        "pause without a container id from the API"
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
                            try:
                                synth = await self._call_llm(
                                    messages,
                                    allow_tools=wall_synth_allow_tools,
                                    container_id=container_id,
                                    max_tokens=settings.wall_synthesis_max_tokens,
                                )
                            except Exception as e:  # noqa: BLE001
                                trace.event(
                                    "wall_synthesis.api_error",
                                    error=str(e),
                                    error_type=type(e).__name__,
                                )
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; post-wall synthesis failed "
                                        f"({type(e).__name__}: {e})"
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
                            new_cid = _container_id_from_message(synth)
                            if new_cid:
                                container_id = new_cid
                            cost.add_usage(synth.usage)
                            trace.event(
                                "llm.response",
                                iteration=iterations,
                                stop_reason=synth.stop_reason,
                                usage=cost.summary(),
                                phase="wall_synthesis",
                            )
                            req_in = getattr(synth.usage, "input_tokens", None) or 0
                            if req_in > settings.max_context_tokens:
                                trace.event(
                                    "wall_synthesis.context_budget",
                                    input_tokens=req_in,
                                )
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; synthesis request exceeded "
                                        f"context cap ({req_in} tokens)"
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
                            if synth.stop_reason == "max_tokens":
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; synthesis hit max_tokens "
                                        f"({settings.wall_synthesis_max_tokens})"
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
                            if synth.stop_reason != "end_turn":
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; synthesis stop_reason="
                                        f"{synth.stop_reason!r}"
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
                            messages.append(
                                {"role": "assistant", "content": synth.content}
                            )
                            text = _extract_text(synth)
                            brief, parse_error = parse_brief_from_model_text(
                                text,
                                run_id=run_id,
                                company=company,
                                generated_at=datetime.now(UTC),
                                max_tool_calls=settings.max_tool_calls,
                            )
                            if brief is None:
                                trace.event(
                                    "wall_synthesis.parse_error",
                                    error=parse_error,
                                    text_preview=text[:500],
                                )
                                return self._finalize_insufficient(
                                    reason=f"{wall_reason}; synthesis parse failed: {parse_error}",
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
                            try:
                                filtered, report = apply_filter(
                                    brief,
                                    fetched_urls=fetched_urls,
                                    citation_urls=citation_urls,
                                    seed_hosts=set(allowlist.seed_hosts),
                                )
                            except ComplianceHardStop as e:
                                trace.incident(
                                    "classified_marker_detected",
                                    labels=sorted(
                                        {h.pattern_label for h in e.hits}
                                    ),
                                )
                                return self._finalize_insufficient(
                                    reason=(
                                        f"{wall_reason}; synthesis brief failed "
                                        "compliance scan"
                                    ),
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
                                phase="wall_synthesis",
                                dropped_hooks=[url for url, _ in report.dropped_hooks],
                                downgraded=report.downgraded_verdict,
                                compliance_hit_labels=[
                                    h.pattern_label for h in report.compliance_hits
                                ],
                            )
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
                                status="halted_wall_budget_synthesized",
                                verdict=filtered.verdict,
                                federal_revenue_posture=filtered.federal_revenue_posture,
                                tool_calls_used=tool_calls_used,
                                wall_s=filtered.wall_seconds,
                                cost_usd=filtered.cost_usd,
                                reason=wall_reason,
                            )
                            emit(
                                f"Brief written (post-wall synthesis) → "
                                f"{run_dir / 'brief.json'}"
                            )
                            return AgentResult(
                                status="halted_wall_budget_synthesized",
                                brief=filtered,
                                iterations=iterations,
                                tool_calls_used=tool_calls_used,
                                cost_usd=round(cost.total_usd, 6),
                                wall_seconds=filtered.wall_seconds,
                                run_dir=str(run_dir),
                                cost_summary=cost.summary(),
                            )

                        trace.event("halt.wall_budget", wall_s=wall, phase="stub")
                        return self._finalize_insufficient(
                            reason=wall_reason,
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

                    if (
                        settings.wall_reserve_seconds > 0
                        and wall
                        >= settings.max_wall_seconds - settings.wall_reserve_seconds
                        and not reserve_nudge_sent
                    ):
                        reserve_nudge_sent = True
                        messages.append(
                            {
                                "role": "user",
                                "content": _wall_reserve_nudge_message(
                                    max_wall_seconds=settings.max_wall_seconds,
                                    reserve_seconds=settings.wall_reserve_seconds,
                                ),
                            }
                        )

                    allow_tools = tool_calls_used < settings.max_tool_calls
                    if (
                        allow_tools
                        and settings.wall_no_tools_buffer_seconds > 0
                        and wall
                        >= settings.max_wall_seconds
                        - settings.wall_no_tools_buffer_seconds
                    ):
                        allow_tools = False

                    llm_allow_tools = allow_tools or _assistant_turn_pending(messages)
                    if llm_allow_tools and not allow_tools:
                        trace.event(
                            "llm.tools_for_trailing_assistant",
                            iteration=iterations,
                            wall_s=wall,
                        )
                    trace.event("llm.request", iteration=iterations, msg_count=len(messages))
                    if (
                        llm_allow_tools
                        and _last_assistant_has_pending_code_execution_tool(messages)
                        and not container_id
                    ):
                        trace.event(
                            "halt.missing_container_for_code_exec",
                            iteration=iterations,
                        )
                        return self._finalize_insufficient(
                            reason=(
                                "Cannot resume a code-execution server-tool pause: "
                                "no container id was captured from the prior API response. "
                                "Try upgrading the anthropic package; if it persists, "
                                "report with trace.jsonl."
                            ),
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
                    response = await self._call_llm(
                        messages,
                        allow_tools=llm_allow_tools,
                        container_id=container_id,
                    )
                    new_cid = _container_id_from_message(response)
                    if new_cid:
                        container_id = new_cid
                    cost.add_usage(response.usage)
                    trace.event(
                        "llm.response",
                        iteration=iterations,
                        stop_reason=response.stop_reason,
                        usage=cost.summary(),
                    )

                    req_in = getattr(response.usage, "input_tokens", None) or 0
                    if req_in > settings.max_context_tokens:
                        trace.event(
                            "halt.context_budget",
                            input_tokens=req_in,
                            max_context_tokens=settings.max_context_tokens,
                        )
                        return self._finalize_insufficient(
                            reason=(
                                f"context budget exceeded ({req_in} input tokens > "
                                f"{settings.max_context_tokens}); raise AGENT_MAX_CONTEXT_TOKENS "
                                "or rely on fewer/lighter web_search and fetch results."
                            ),
                            halt_reason="context_budget_exhausted",
                            status="halted_context_budget",
                            run_id=run_id,
                            company=company,
                            started=started,
                            cost=cost,
                            iterations=iterations,
                            tool_calls=tool_calls_used,
                            trace=trace,
                            run_dir=run_dir,
                        )

                    if response.stop_reason == "max_tokens":
                        trace.event("halt.max_output_tokens")
                        return self._finalize_insufficient(
                            reason=(
                                f"model output hit max_tokens ({settings.max_tokens}); "
                                "raise AGENT_MAX_TOKENS or use a leaner tool plan."
                            ),
                            halt_reason="max_output_tokens_exhausted",
                            status="halted_max_output_tokens",
                            run_id=run_id,
                            company=company,
                            started=started,
                            cost=cost,
                            iterations=iterations,
                            tool_calls=tool_calls_used,
                            trace=trace,
                            run_dir=run_dir,
                        )

                    messages.append({"role": "assistant", "content": response.content})

                    if response.stop_reason == "end_turn":
                        text = _extract_text(response)
                        brief, parse_error = parse_brief_from_model_text(
                            text,
                            run_id=run_id,
                            company=company,
                            generated_at=datetime.now(UTC),
                            max_tool_calls=settings.max_tool_calls,
                        )
                        if brief is None:
                            trace.event(
                                "brief.parse_error",
                                error=parse_error,
                                text_preview=text[:500],
                            )
                            if brief_parse_repair_attempts == 0:
                                brief_parse_repair_attempts += 1
                                trace.event(
                                    "brief.parse_repair_requested",
                                    error=parse_error,
                                )
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": _brief_parse_repair_user_message(
                                            parse_error=parse_error,
                                        ),
                                    }
                                )
                                continue
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
                                seed_hosts=set(allowlist.seed_hosts),
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

                        # One repair turn when hooks cite URLs not from trace (no extra tool calls).
                        hook_drops_only = (
                            report.dropped_hooks
                            and not any(
                                h.severity is Severity.WARN
                                for h in report.compliance_hits
                            )
                        )
                        if (
                            hook_drops_only
                            and repair_attempts == 0
                            and brief.verdict != "insufficient_data"
                        ):
                            repair_attempts += 1
                            repair_msg = _repair_user_message(
                                dropped=[u for u, _ in report.dropped_hooks],
                                fetched_urls=fetched_urls,
                                citation_urls=citation_urls,
                                seed_hosts=set(allowlist.seed_hosts),
                            )
                            trace.event(
                                "brief.repair_requested",
                                dropped_hooks=[
                                    url for url, _ in report.dropped_hooks
                                ],
                            )
                            messages.append(
                                {"role": "user", "content": repair_msg}
                            )
                            continue

                        trace.event(
                            "brief.filtered",
                            dropped_hooks=[url for url, _ in report.dropped_hooks],
                            downgraded=report.downgraded_verdict,
                            compliance_hit_labels=[
                                h.pattern_label for h in report.compliance_hits
                            ],
                        )

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
                            federal_revenue_posture=filtered.federal_revenue_posture,
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
            except BaseException as e:
                # Still emit brief.json on cancel/signal; then re-raise.
                trace.event(
                    "halt.cancelled",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._finalize_insufficient(
                    reason=(
                        "run cancelled before brief emitted: "
                        f"{type(e).__name__}"
                    ),
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
                raise

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        *,
        allow_tools: bool,
        container_id: str | None = None,
        max_tokens: int | None = None,
    ) -> Message:
        custom_schemas = self.registry.to_anthropic_schemas()
        tools: list[dict[str, Any]] = (
            [*custom_schemas, WEB_SEARCH_TOOL] if allow_tools else []
        )

        # Ephemeral cache_control on static system+tools prefix (cache read vs full input).
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        cached_tools: list[dict[str, Any]] = list(tools)
        if cached_tools:
            last = dict(cached_tools[-1])
            last["cache_control"] = {"type": "ephemeral"}
            cached_tools[-1] = last

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if cached_tools:
            kwargs["tools"] = cached_tools
        if settings.thinking_adaptive:
            kwargs["thinking"] = {"type": "adaptive"}
        # Forward the code-exec / server-tool container only when this request
        # includes `tools`. Callers set allow_tools True for normal tool turns and
        # for "trailing assistant" resume (pause_turn / pending server tool uses).
        if container_id and allow_tools:
            kwargs["container"] = container_id

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

            if tool_name == "lookup_fedramp_marketplace_products" and isinstance(
                result, dict
            ):
                if "error" not in result:
                    for key in ("catalog_request_url", "marketplace_ui_url"):
                        u = result.get(key)
                        if isinstance(u, str) and u.startswith(("http://", "https://")):
                            citation_urls.add(u)
                            allowlist.accept_citation(u)
                    for m in result.get("matches") or []:
                        if isinstance(m, dict):
                            du = m.get("detail_url")
                            if isinstance(du, str) and du.startswith(
                                ("http://", "https://")
                            ):
                                citation_urls.add(du)
                                allowlist.accept_citation(du)

            if tool_name == "lookup_usaspending_awards" and isinstance(result, dict):
                if "error" not in result:
                    for a in result.get("awards") or []:
                        if not isinstance(a, dict):
                            continue
                        u = a.get("source_url")
                        if isinstance(u, str) and u.startswith(("http://", "https://")):
                            citation_urls.add(u)
                            allowlist.accept_citation(u)

            if tool_name == "lookup_form_5500_plans" and isinstance(result, dict):
                if "error" not in result:
                    for key in ("datasets_citation_url", "efast_search_citation_url"):
                        u = result.get(key)
                        if isinstance(u, str) and u.startswith(("http://", "https://")):
                            citation_urls.add(u)
                            allowlist.accept_citation(u)
                    for p in result.get("plans") or []:
                        if not isinstance(p, dict):
                            continue
                        du = p.get("filing_download_url")
                        if isinstance(du, str) and du.startswith(("http://", "https://")):
                            citation_urls.add(du)
                            allowlist.accept_citation(du)

            if tool_name == "fetch_form_5500_filing_pdf" and isinstance(result, dict):
                if "error" not in result:
                    u = result.get("pdf_url")
                    if isinstance(u, str) and u.startswith(("http://", "https://")):
                        citation_urls.add(u)
                        allowlist.accept_citation(u)

            _progress_for_tool(tool_name, result, emit)

            is_error = isinstance(result, dict) and _tool_payload_indicates_failure(
                result
            )
            trace_kwargs: dict[str, Any] = {
                "tool": tool_name,
                "tool_id": tool_id,
                "is_error": is_error,
            }
            if is_error and isinstance(result, dict):
                err_val = result.get("error")
                if isinstance(err_val, str) and err_val.strip():
                    trace_kwargs["tool_error"] = err_val.strip()[:500]
                elif err_val is not None and not isinstance(err_val, str):
                    trace_kwargs["tool_error"] = str(err_val)[:500]
                detail = result.get("detail")
                if detail is not None:
                    trace_kwargs["tool_detail_preview"] = (
                        json.dumps(detail, default=str)[:800]
                    )
            trace.event("tool.result", **trace_kwargs)
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


def _tool_payload_indicates_failure(payload: dict[str, Any]) -> bool:
    """True when the tool returned a structured failure (not ``error: null``).

    Pydantic tool outputs include an ``error`` key even on success; the trace
    and Anthropic ``tool_result.is_error`` must only flip for real failures.
    """
    err = payload.get("error")
    if err is None:
        return False
    if isinstance(err, str):
        return bool(err.strip())
    return True


def _as_tool_result(tool_id: str, payload: Any, *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": json.dumps(payload, default=str),
        "is_error": is_error,
    }


_CODE_EXEC_SERVER_TOOLS = frozenset(
    {"code_execution", "bash_code_execution", "text_editor_code_execution"}
)


def _content_block_type_and_name(block: Any) -> tuple[str | None, str | None]:
    t = getattr(block, "type", None)
    name = getattr(block, "name", None)
    if isinstance(block, dict):
        if t is None:
            t = block.get("type")
        if name is None:
            name = block.get("name")
    ts = str(t) if t is not None else None
    ns = str(name) if name is not None else None
    return ts, ns


def _last_assistant_has_pending_code_execution_tool(
    messages: list[dict[str, Any]],
) -> bool:
    """True when the last message is assistant and includes code-exec server tools.

    Those turns require ``container=`` on the next :meth:`Messages.create` when
    ``tools`` is present; otherwise the API returns ``invalid_request_error`` about
    ``container_id`` (see ``_assistant_turn_pending``).
    """
    if not _assistant_turn_pending(messages):
        return False
    content = messages[-1].get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        typ, name = _content_block_type_and_name(block)
        if typ == "server_tool_use" and name in _CODE_EXEC_SERVER_TOOLS:
            return True
    return False


def _container_id_from_message(msg: Message) -> str | None:
    """Best-effort ``container.id`` from a Messages API response."""
    cont = getattr(msg, "container", None)
    if cont is not None:
        cid = getattr(cont, "id", None)
        if isinstance(cid, str) and cid.strip():
            return cid.strip()
    extra = getattr(msg, "model_extra", None)
    if isinstance(extra, dict):
        raw = extra.get("container")
        if isinstance(raw, dict):
            rid = raw.get("id")
            if isinstance(rid, str) and rid.strip():
                return rid.strip()
    try:
        dumped = msg.model_dump(mode="python")
    except Exception:
        return None
    c2 = dumped.get("container")
    if isinstance(c2, dict):
        rid = c2.get("id")
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
    return None


def _assistant_turn_pending(messages: list[dict[str, Any]]) -> bool:
    """True when the last message is from the assistant.

    After ``stop_reason == "pause_turn"`` (native web_search / server tools), the
    client must call :meth:`Messages.create` again with the same ``tools`` list
    and, when code-execution server tools are pending, the same ``container`` id
    (see Anthropic ``invalid_request_error`` about ``container_id``).
    """
    return bool(messages) and messages[-1].get("role") == "assistant"


def _extract_text(response: Message) -> str:
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def _write_brief(run_dir: Path, brief: Brief) -> None:
    (run_dir / "brief.json").write_text(
        brief.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def _wall_synthesis_user_message(*, company: str, wall_reason: str) -> str:
    return "\n".join(
        [
            "SYSTEM: The wall-clock budget for this run is exhausted.",
            f"({wall_reason})",
            "",
            "You must NOT call any tools. Emit exactly one JSON object matching "
            "the Brief schema using ONLY evidence already present in this "
            "conversation (tool results and prior assistant text).",
            "",
            "Requirements:",
            f"  • company_name_queried: use the queried company ({company!r}) verbatim.",
            "  • verdict: prefer medium_confidence or low_confidence unless the transcript "
            "already contains multiple independent, explicit signals for high_confidence.",
            "  • why_not_confident: one sentence mentioning the wall-clock limit and "
            "anything you could not verify without more time/tools.",
            "  • Every hook.citation_url must appear in this run's tool trace "
            "(web_search citations or fetch_company_page URLs). Do not invent URLs.",
            "  • sales_conversation_prep.federal_prime_awards: at most 5 items.",
            "  • revenue_estimate.source must be one of: sec_filing, press_release, "
            "analyst_estimate, federal_awards_proxy, inferred_from_headcount, "
            "not_determinable.",
            "  • Do not fabricate contracts, UEIs, or FedRAMP status — use unknown / "
            "null where the transcript is silent.",
            "  • halt_reason: if set for this timeout, must be the exact string "
            '"wall_budget_exhausted" (schema literal — not "wall_budget_exceeded").',
            "",
            "Emit exactly one JSON object. No other text.",
        ]
    )


def _wall_reserve_nudge_message(
    *, max_wall_seconds: int, reserve_seconds: int
) -> str:
    return "\n".join(
        [
            "SYSTEM: You are inside the final reserve window on wall-clock budget "
            f"({reserve_seconds}s before the {max_wall_seconds}s cap).",
            "",
            "Prefer at most one more high-leverage tool turn if absolutely needed, "
            "then STOP and emit the final Brief JSON. If you already have enough "
            "signal, emit the JSON now without additional tools.",
            "",
            "When uncertain, prefer medium_confidence or low_confidence with honest "
            "why_not_confident over insufficient_data, as long as hooks only cite "
            "trace-backed URLs.",
        ]
    )


def _brief_parse_repair_user_message(*, parse_error: str) -> str:
    return "\n".join(
        [
            "Your last message was supposed to be exactly one JSON Brief object, "
            "but it failed schema validation.",
            "",
            f"Validation error: {parse_error}",
            "",
            "Fix the JSON and re-emit exactly one Brief object. Common fixes:",
            "  • federal_revenue_posture — must be sponsorship_in_hand | "
            "pre_sponsorship_path | not_in_federal_icp (do not use legacy `track`).",
            "  • revenue_estimate.source — use only allowed enum values (see prior "
            "system instructions).",
            "  • sales_conversation_prep.federal_prime_awards — at most 5 entries.",
            "  • sales_conversation_prep.form_5500_benefits — use only allowed enums "
            "for signal_source, participant_scale_hint, and confidence.",
            "  • target_roles ≤ 5, hooks ≤ 8.",
            "",
            "Do NOT call any tools. Emit only the corrected JSON object.",
        ]
    )


def _initial_user_message(
    *,
    company: str,
    domain: str | None,
    poc_name: str | None,
    poc_title: str | None,
    run_id: str,
    started_at: datetime,
) -> str:
    parts = [
        "Research the following company and produce a Brief:",
        f"- Company: {company}",
    ]
    if domain:
        parts.append(f"- Domain: {domain}")
    if poc_name or poc_title:
        parts.append(
            "- Sales-provided context (not verified by tools; do not treat as SAM or "
            "registry fact):"
        )
        if poc_name:
            parts.append(f"  - Stated point of contact: {poc_name}")
        if poc_title:
            parts.append(f"  - Stated role / position: {poc_title}")
    parts.extend([
        f"- Run ID (include in your brief.run_id verbatim): {run_id}",
        f"- Caller timestamp (include as brief.generated_at): {started_at.isoformat()}",
        "",
        "Start with lookup_sam_registration. Then call USAspending/SBIR in "
        "parallel if SAM returned an active entity. Always call "
        "lookup_fedramp_marketplace_products once with your best search phrase "
        "(SAM legal name or queried name); empty matches are normal — set "
        "sales_conversation_prep.fedramp_posture and continue. Use web_search to "
        "gather press and persona signal. Only call fetch_company_page on "
        "URLs that came from web_search citations or that match the "
        "company's own domain.",
        "",
        "Stop calling tools and emit the final Brief JSON when you're "
        "confident — or when you conclude confidence isn't reachable "
        "within budget (emit insufficient_data).",
    ])
    return "\n".join(parts)


def _repair_user_message(
    *,
    dropped: list[str],
    fetched_urls: set[str],
    citation_urls: set[str],
    seed_hosts: set[str],
) -> str:
    """Ask the model once to re-emit the brief with trace-backed hook URLs."""
    allowed_sorted = sorted(fetched_urls | citation_urls)
    allowed_preview = allowed_sorted[:30]
    seed_list = ", ".join(sorted(seed_hosts)) or "(none)"
    lines = [
        "Your last brief cited URLs that were not returned by any tool "
        "in this run. The output validator will drop them.",
        "",
        "Dropped URLs:",
        *(f"  - {u}" for u in dropped),
        "",
        "Fix this and re-emit the final brief:",
        "  • Replace each dropped URL with one of the trace-backed URLs "
        "below, OR remove the hook entirely.",
        "  • You MAY also cite any URL on the prospect's own domain "
        f"(seed hosts: {seed_list}); those are pre-allowlisted.",
        "  • Do NOT invent new URLs. Do NOT call any more tools.",
        "",
        "Trace-backed URLs from this run (truncated to first 30):",
        *(f"  - {u}" for u in allowed_preview),
    ]
    if len(allowed_sorted) > len(allowed_preview):
        lines.append(f"  … and {len(allowed_sorted) - len(allowed_preview)} more.")
    lines.extend(
        [
            "",
            "Emit exactly one JSON object matching the Brief schema. No "
            "other text.",
        ]
    )
    return "\n".join(lines)


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
    elif tool_name == "lookup_fedramp_marketplace_products":
        res = result.get("marketplace_resolution", "?")
        n = len(result.get("matches") or [])
        emit(f"FedRAMP marketplace: {res} ({n} matches)")
    elif tool_name == "fetch_company_page":
        u = result.get("final_url") or result.get("url") or ""
        inj = result.get("injection_signals") or []
        note = f" [injection:{','.join(inj)}]" if inj else ""
        emit(f"fetched: {u}{note}")
    elif tool_name == "lookup_form_5500_plans":
        n = result.get("rows_returned") or 0
        mode = result.get("match_mode") or "?"
        emit(f"Form 5500 index: {n} plan(s) ({mode})")
    elif tool_name == "fetch_form_5500_filing_pdf":
        err = result.get("error")
        if err:
            emit(f"Form 5500 PDF: error {err}")
        else:
            b = result.get("bytes_read") or 0
            emit(f"Form 5500 PDF: {b} bytes, excerpt returned")


async def research(
    company: str,
    registry: ToolRegistry,
    *,
    domain: str | None = None,
    poc_name: str | None = None,
    poc_title: str | None = None,
    run_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> AgentResult:
    agent = Agent(registry=registry, **kwargs)
    return await agent.research(
        company,
        domain=domain,
        poc_name=poc_name,
        poc_title=poc_title,
        run_dir=run_dir,
        progress=progress,
    )


async def run(goal: str, registry: ToolRegistry, **kwargs: Any) -> AgentResult:
    """Back-compat wrapper; treats goal as company name."""
    return await research(goal, registry, **kwargs)
