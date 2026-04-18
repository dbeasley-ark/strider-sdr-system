# 06 · Evaluation and Observability

"It seems better" is not a deployment criterion. If you can't measure it, you can't improve it.

## Two kinds of tests

**Golden set** — known-good input/output pairs. Start with 10. Grow to 50+ before production. These catch regressions when you change the prompt, the model, the retriever, or a tool contract.

**Adversarial set** — prompt injections, edge cases, ambiguous inputs. Threshold should be 100% correct handling (which means *safely refused or handled*, not *gave a specific answer*). These catch security regressions.

Both live in `evals/`. `evals/run.py` enforces thresholds on every run. CI should call this on every PR.

## Tracing

Every run writes a JSONL trace to `settings.trace_dir`. One line per decision: agent start/end, LLM request/response, tool call/result, halt events. The rule: *if you can't reconstruct what happened from the trace, you're flying blind.*

When a user reports "the agent did something weird," the first question is the run ID. The trace tells you exactly what happened, in order, with inputs and outputs.

## Cost

`CostTracker` accumulates every API usage dict into a dollar total. Budgets are enforced as hard rails. The prices in `observability/cost.py` need to be kept current — Anthropic pricing is at https://docs.claude.com/en/docs/about-claude/pricing.

One nuance with Opus 4.7: the tokenizer can produce up to 35% more tokens than 4.6 for the same input, especially on code and structured data. Budget accordingly.

## The scaffolding trap

Don't build bespoke "interim status" message systems. Claude 4.7 emits native progress updates during tool use. Read the trace; surface the useful parts. Building your own spinner logic on top of this is wasted effort.
