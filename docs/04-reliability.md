# 04 · Reliability Engineering

Agents call networked services. Networked services fail. If you haven't handled failure explicitly, you've handled it implicitly — badly.

## What's wired up by default

In this template, every tool call runs through:

1. **Permission check.** The scope either allows the call or rejects it.
2. **Circuit breaker (per tool).** After N failures in a row, the breaker opens and rejects calls fast for the timeout window. This protects downstream services and keeps your agent from wasting budget on a dead dependency.
3. **Retry with exponential backoff + jitter.** Only on exceptions marked `TransientError`. Bugs do not get retried — that way lies CPU-melting loops.
4. **Timeout.** A tool that hangs takes down the loop. Every call has a ceiling.

## Idempotency

Retries are safe only when the tool is idempotent. For non-idempotent operations (charges, emails, irreversible writes), use an idempotency key: generate one at the start of the operation, pass it through, let the downstream service deduplicate.

## Budget rails

The loop enforces three hard ceilings, set in `config.py`:
- **`max_iterations`** — prevents infinite loops.
- **`max_cost_usd`** — prevents runaway spend.
- **`max_wall_seconds`** — prevents runaway latency.

When any is crossed, the loop halts cleanly and returns a structured `AgentResult` with `status="halted_budget_*"`. You can inspect the trace to see what happened.

## The failure-modes table in the spec

`AGENT_SPEC.md §6` asks you to enumerate failures and responses. Do it. "I'll figure it out at runtime" is how production agents end up stuck in retry loops eating money.
