# Agent Template

An opinionated starter for building Claude-powered agents that don't fall over in production.

> **Before you write any code, fill out [`AGENT_SPEC.md`](./AGENT_SPEC.md).**
> If you can't fill it out in 15 minutes, you don't understand the problem yet. That's not a ceremony — it's the highest-leverage 15 minutes you'll spend on this project.

---

## Philosophy

This template encodes seven disciplines from agent engineering:

1. **System Design** — data flow, failure handling, context boundaries (see `AGENT_SPEC.md` §3)
2. **Tool / Contract Design** — Pydantic schemas, no vague strings (`src/agent/tools/_base.py`)
3. **Retrieval Engineering** — chunking, embeddings, re-ranking (`src/agent/modules/rag/`)
4. **Reliability Engineering** — retry, timeout, circuit breaker (`src/agent/reliability/`)
5. **Security Engineering** — input validation, permission scopes (`src/agent/security/`)
6. **Evaluation & Observability** — golden sets, tracing, cost (`evals/`, `src/agent/observability/`)
7. **Product Thinking** — confidence signaling, human-in-the-loop (`src/agent/modules/human_in_loop/`)

The core loop uses the **Anthropic Client SDK** (not the Agent SDK) because we want explicit control over every tool call so we can wrap it with our reliability and observability machinery.

---

## Profiles

Pick one when you scaffold a new agent. You can upgrade later.

| Profile | Use for | What you get |
|---|---|---|
| `lean` | Throwaway scripts, personal automations | Core loop + Pydantic tool contracts + basic tracing. No evals folder, no optional modules. Ships in an afternoon. |
| `standard` | Internal work automations, client work | Everything in lean + `evals/` + reliability stack + AGENT_SPEC enforced. **Default.** |
| `production` | Customer-facing SaaS | Everything in standard + security module + human-in-the-loop + CI eval gates + external tracing hooks. |

---

## Quickstart

```bash
# 1. Clone and enter
git clone <this-repo> my-agent && cd my-agent

# 2. Install
uv sync  # or: pip install -e ".[dev]"

# 3. Fill out the spec. DO NOT SKIP.
$EDITOR AGENT_SPEC.md

# 4. Set your API key
cp .env.example .env
# edit .env with your ANTHROPIC_API_KEY

# 5. Scaffold a new agent from your spec (optional convenience)
python scripts/new_agent.py --name my-agent --profile standard

# 6. Run the example agent
python -m agent

# 7. Run evals
python evals/run.py
```

---

## Directory Layout

```
agent-template/
├── AGENT_SPEC.md              ← FILL OUT FIRST
├── src/agent/
│   ├── config.py              Model, effort, budgets
│   ├── agent.py               Main loop — thin orchestration
│   ├── tools/                 Tool contracts (Pydantic-enforced)
│   ├── prompts/               Versioned system prompts
│   ├── reliability/           Retry, timeout, circuit breaker
│   ├── observability/         Tracing, cost tracking
│   ├── security/              Input validation, permissions
│   └── modules/               OPTIONAL — delete what you don't use
│       ├── rag/               Retrieval (chunking, embed, rerank)
│       ├── memory/            Long-running session state
│       ├── multi_agent/       Subagents + verifier pattern
│       ├── mcp/               Model Context Protocol client
│       └── human_in_loop/     Escalation, confidence gating
├── evals/                     Golden + adversarial test sets
├── scripts/new_agent.py       Scaffolder
└── tests/                     Unit tests (tool contracts, reliability)
```

---

## The Non-Negotiables

These ship on by default. You can turn them off, but you'll have to work at it — which is the point.

- Every tool call goes through `reliability.with_retry()` + timeout + circuit breaker.
- Every tool's inputs and outputs are validated against a Pydantic schema.
- Every agent run emits a structured trace (JSONL, one line per decision).
- Every run tracks token + dollar cost against a budget from `config.py`.
- Eval runner refuses to pass if success rate drops below your threshold.

---

## What This Template Does NOT Do

- **It does not pick your problem for you.** The spec document does.
- **It does not replace evals with "vibes."** If you skip `evals/run.py`, that's on you.
- **It does not prevent prompt injection by magic.** The validators are a starting point; your threat model is yours.
- **It does not run long-lived sessions, multi-agent swarms, or MCP servers out of the box.** Those are optional modules — deliberately stubs — because they're overkill for most agents.

---

## Next Steps After Cloning

1. Read `AGENT_SPEC.md` end-to-end. Fill it in. Have a second human review it.
2. Replace `src/agent/tools/example_tool.py` with your actual tools.
3. Write 10 golden cases in `evals/golden/` before you ship anything.
4. Delete the modules in `src/agent/modules/` that you don't need. Don't carry dead code.

See [`docs/`](./docs) for deeper notes on each discipline.
