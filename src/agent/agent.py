"""The agent loop.

Uses the Anthropic Client SDK directly (not the Agent SDK) so we retain
explicit control over every tool call. This is the price of building in
reliability, cost tracking, permissions, and tracing — and it's worth it.

Flow:
    1. User goal → first message.
    2. Send messages + tool schemas to Claude.
    3. If stop_reason == "end_turn", return the final text.
    4. If stop_reason == "tool_use", execute each tool call under
       retry + timeout + circuit breaker, append tool_result messages,
       loop.
    5. On every iteration, check budget rails (iterations, cost, wall time).
       Halt cleanly if any is exceeded.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import Message

from agent.config import settings
from agent.observability.cost import CostTracker
from agent.observability.tracing import Trace
from agent.prompts import system as prompts
from agent.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    TransientError,
    with_retry,
    with_timeout,
)
from agent.security.permissions import (
    UNRESTRICTED,
    PermissionDenied,
    PermissionScope,
)
from agent.tools import ToolRegistry

AgentStatus = Literal[
    "ok",
    "halted_max_iterations",
    "halted_budget_cost",
    "halted_budget_time",
    "error",
    "rejected_permission",
]


@dataclass
class AgentResult:
    status: AgentStatus
    output: str = ""
    iterations: int = 0
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    error: str | None = None
    trace_path: str | None = None
    cost_summary: dict[str, Any] = field(default_factory=dict)


class Agent:
    """The top-level agent.

    Usage:
        registry = ToolRegistry()
        registry.register(GetUser())
        agent = Agent(registry=registry, scope=my_scope)
        result = await agent.run("What's the email for user 12345?")
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        scope: PermissionScope = UNRESTRICTED,
        system_prompt_version: str = prompts.DEFAULT,
        model: str | None = None,
        tool_timeout_s: float = 30.0,
    ) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.registry = registry
        self.scope = scope
        self.system_prompt = prompts.get(system_prompt_version)
        self.model = model or settings.model
        self.tool_timeout_s = tool_timeout_s
        # One breaker per tool name, created lazily.
        self._breakers: dict[str, CircuitBreaker] = {}

    # ── Public API ───────────────────────────────────────────────────

    async def run(self, goal: str) -> AgentResult:
        started = time.monotonic()
        cost = CostTracker(model=self.model, max_usd=settings.max_cost_usd)

        with Trace() as trace:
            trace.event(
                "agent.start",
                goal=goal,
                model=self.model,
                profile=settings.profile.value,
                tools=[name for name in self.registry._tools],
                scope=self.scope.name,
            )

            messages: list[dict[str, Any]] = [{"role": "user", "content": goal}]
            iterations = 0

            try:
                while True:
                    iterations += 1

                    # ── Budget rails ─────────────────────────────────
                    if iterations > settings.max_iterations:
                        trace.event("halt.max_iterations", iterations=iterations)
                        return self._finalize(
                            "halted_max_iterations",
                            trace,
                            started,
                            cost,
                            iterations,
                            output="Halted: max iterations exceeded.",
                        )

                    wall = time.monotonic() - started
                    if wall > settings.max_wall_seconds:
                        trace.event("halt.max_wall", wall_s=wall)
                        return self._finalize(
                            "halted_budget_time",
                            trace,
                            started,
                            cost,
                            iterations,
                            output="Halted: wall-clock budget exceeded.",
                        )

                    if cost.exceeded:
                        trace.event("halt.cost_exceeded", **cost.summary())
                        return self._finalize(
                            "halted_budget_cost",
                            trace,
                            started,
                            cost,
                            iterations,
                            output="Halted: cost budget exceeded.",
                        )

                    # ── LLM call ─────────────────────────────────────
                    trace.event("llm.request", iteration=iterations, msg_count=len(messages))
                    response = await self._call_llm(messages)
                    cost.add_usage(response.usage)
                    trace.event(
                        "llm.response",
                        iteration=iterations,
                        stop_reason=response.stop_reason,
                        usage=cost.summary(),
                    )

                    # Append assistant turn
                    messages.append({"role": "assistant", "content": response.content})

                    if response.stop_reason == "end_turn":
                        text = _extract_text(response)
                        return self._finalize(
                            "ok",
                            trace,
                            started,
                            cost,
                            iterations,
                            output=text,
                        )

                    if response.stop_reason == "tool_use":
                        tool_results = await self._dispatch_tools(response, trace)
                        messages.append({"role": "user", "content": tool_results})
                        continue

                    # Any other stop_reason (max_tokens, etc.) — fail explicit.
                    trace.event("halt.unexpected_stop_reason", stop_reason=response.stop_reason)
                    return self._finalize(
                        "error",
                        trace,
                        started,
                        cost,
                        iterations,
                        error=f"Unexpected stop_reason: {response.stop_reason}",
                    )

            except PermissionDenied as e:
                trace.event("halt.permission_denied", detail=str(e))
                return self._finalize(
                    "rejected_permission",
                    trace,
                    started,
                    cost,
                    iterations,
                    error=str(e),
                )
            except Exception as e:  # noqa: BLE001
                trace.event("halt.unhandled_exception", error=str(e), type=type(e).__name__)
                return self._finalize(
                    "error",
                    trace,
                    started,
                    cost,
                    iterations,
                    error=f"{type(e).__name__}: {e}",
                )

    # ── Internals ────────────────────────────────────────────────────

    async def _call_llm(self, messages: list[dict[str, Any]]) -> Message:
        """Wrapped in retry for transient API errors."""

        async def _do() -> Message:
            try:
                return await self.client.messages.create(
                    model=self.model,
                    max_tokens=settings.max_tokens,
                    system=self.system_prompt,
                    tools=self.registry.to_anthropic_schemas(),
                    messages=messages,  # type: ignore[arg-type]
                )
            except Exception as e:
                # Map SDK errors to our Transient category where appropriate.
                # Being conservative — only retry on server/network errors.
                cls_name = type(e).__name__
                if cls_name in {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError"}:
                    raise TransientError(str(e)) from e
                raise

        return await with_retry(_do, max_attempts=4, initial_wait=1.0, max_wait=30.0)

    async def _dispatch_tools(self, response: Message, trace: Trace) -> list[dict[str, Any]]:
        """Execute all tool_use blocks in parallel and collect results."""
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        async def _one(block: Any) -> dict[str, Any]:
            tool_name = block.name
            tool_id = block.id
            tool_input = block.input if isinstance(block.input, dict) else {}

            trace.event("tool.call", tool=tool_name, tool_id=tool_id, input=tool_input)

            # Permission gate
            try:
                self.scope.check(tool_name)
            except PermissionDenied as e:
                trace.event("tool.permission_denied", tool=tool_name, detail=str(e))
                return _as_tool_result(tool_id, {"error": "permission_denied", "detail": str(e)}, is_error=True)

            # Circuit breaker per tool
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

            # Wrap: circuit breaker → retry → timeout → tool
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
                trace.event("tool.exception", tool=tool_name, error=str(e), type=type(e).__name__)
                return _as_tool_result(
                    tool_id,
                    {"error": "tool_exception", "detail": str(e), "type": type(e).__name__},
                    is_error=True,
                )

            is_error = isinstance(result, dict) and "error" in result
            trace.event("tool.result", tool=tool_name, tool_id=tool_id, is_error=is_error)
            return _as_tool_result(tool_id, result, is_error=is_error)

        return await asyncio.gather(*(_one(b) for b in tool_uses))

    def _finalize(
        self,
        status: AgentStatus,
        trace: Trace,
        started: float,
        cost: CostTracker,
        iterations: int,
        *,
        output: str = "",
        error: str | None = None,
    ) -> AgentResult:
        wall = time.monotonic() - started
        trace.event(
            "agent.end",
            status=status,
            iterations=iterations,
            wall_s=round(wall, 3),
            cost=cost.summary(),
        )
        return AgentResult(
            status=status,
            output=output,
            iterations=iterations,
            cost_usd=round(cost.total_usd, 6),
            wall_seconds=round(wall, 3),
            error=error,
            trace_path=str(trace.path),
            cost_summary=cost.summary(),
        )


# ── Helpers ──────────────────────────────────────────────────────────


def _as_tool_result(tool_id: str, payload: Any, *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": json.dumps(payload, default=str),
        "is_error": is_error,
    }


def _extract_text(response: Message) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "\n".join(parts).strip()


# ── Convenience function ────────────────────────────────────────────


async def run(goal: str, registry: ToolRegistry, **kwargs: Any) -> AgentResult:
    """One-shot convenience wrapper."""
    agent = Agent(registry=registry, **kwargs)
    return await agent.run(goal)
