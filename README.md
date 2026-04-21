# Prospect Research

**Arkenstone Defense** — Claude-powered agent that qualifies inbound defense-tech companies against **Track 1** and **Track 2** ICP criteria and produces a structured **brief** an SDR can scan in about a minute (classification, hooks with citations, target roles, confidence).

The authoritative product and safety spec is [`AGENT_SPEC.md`](./AGENT_SPEC.md). This README is the operational entry point: install, run, batch UI, evals, and layout.

**Source repository:** [dbeasley-ark/strider-sdr-system](https://github.com/dbeasley-ark/strider-sdr-system) on GitHub.

---

## What you get

- **CLI:** `python -m agent --company "<name-or-domain>"` — runs the research loop, prints JSON to stdout, streams progress to stderr, writes `trace.jsonl` and `brief.json` under `./runs/<slug>/<timestamp>/` (override with `--run-dir` if needed).
- **Research tools:** Custom tools for **SAM.gov** entity registration, **USAspending** awards, **SBIR/STTR** awards, **FedRAMP Marketplace** product search, and **allowlisted page fetch**; the model may also use Anthropic **web search** on the server side (not part of the local registry). Contracts, retries, timeouts, and a circuit breaker wrap HTTP calls.
- **Guardrails:** Structured tracing, cost and wall-clock budgets, URL allowlisting, compliance-oriented output filtering, and optional **wall-budget synthesis** (tools-off finalization when time runs low — see `AGENT_WALL_*` in `.env.example`).
- **Batch sales UI (optional):** FastAPI service + React (Vite) app — single-company runs or spreadsheet batch with streaming progress; export completed briefs as **JSON** (per row or bundled).
- **Evals:** Golden and adversarial JSON suites with threshold gates (`evals/run.py`).

Non-goals and trust model (who may call this, what data is allowed) are spelled out in the spec — read **§1–§3** before changing behavior or deploying.

---

## Requirements

- **Python** 3.11+
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip with a virtualenv
- **Node.js** 18+ — only if you use the `sales-ui` dev server or build static assets

---

## Install

From the repository root:

```bash
uv sync --extra dev --extra ui
```

Minimal install (CLI + tests, no FastAPI batch server):

```bash
uv sync --extra dev
```

Optional dependency groups in `pyproject.toml`: `ui` (batch API + spreadsheets), `rag`, `mcp` — add with e.g. `uv sync --extra dev --extra ui --extra rag`.

---

## Configuration

```bash
cp .env.example .env
```

Required variables (see `.env.example` for the full list and comments):

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API |
| `SAM_GOV_API_KEY` | SAM.gov entity lookup ([GSA open data](https://open.gsa.gov/api/sam-api-key/)) |
| `SAM_GOV_OPTIONAL` | Set to `true` to allow startup without a SAM key (SAM tool returns empty / not found until you add a key). |
| `ARKENSTONE_AGENT_ENABLED` | Kill switch — must be `true` to run |

Model, budgets (tool calls, USD cost, wall seconds, context, wall synthesis), runs directory, and profile are configured via `AGENT_*` env vars (defaults and comments live in `.env.example`).

**Importing config without keys** (e.g. lightweight helpers): set `_AGENT_SKIP_STARTUP_CHECKS=1` — used internally so tooling does not require secrets at import time.

---

## CLI usage

```bash
uv run python -m agent --company "Shield AI"
uv run python -m agent --company shield.ai --domain shield.ai
uv run python -m agent --company "Hadrian" --quiet
uv run python -m agent --company "Contoso" --poc-name "Alex Kim" --poc-title "CTO"
uv run python -m agent --company "Acme" --run-dir ./runs/manual/acme-run
```

- **Stdout:** final brief as JSON (default; `--json` is explicit alias).
- **Stderr:** progress and a short result summary unless `--quiet`.
- **Exit codes:** `0` success, `1` insufficient data / budget halt, `2` error or compliance hard stop.

Artifacts: `./runs/<company-slug>/<timestamp>/` — `brief.json`, `trace.jsonl`.

---

## Sales batch UI

Two processes in development: API on **8765**, Vite on **5173** with `/api` proxied to the API.

**Terminal 1 — API** (requires `uv sync --extra ui`):

```bash
uv run prospect-sales-ui
```

Optional: `AGENT_SALES_UI_HOST`, `AGENT_SALES_UI_PORT` (default `127.0.0.1:8765`), `AGENT_SALES_UI_RELOAD=true` for uvicorn reload.

**Terminal 2 — React dev server:**

```bash
cd sales-ui && npm install && npm run dev
```

Open `http://localhost:5173`, use **Single** for one company (optional domain and POC fields) or upload a **CSV/XLSX** for a batch job; events stream the same way. When briefs are ready, use **Export** to download JSON for one row or a versioned bundle of the whole job.

**Production-style:** build the UI and serve it from the same process:

```bash
cd sales-ui && npm run build
uv run prospect-sales-ui
```

If `sales-ui/dist` exists, the FastAPI app mounts it at `/`; API routes remain under `/api/...`.

---

## Scripts

`scripts/rerun_sample.sh` — runs a fixed eight-company validation sample through the CLI (expects a project `.venv` with dependencies) and prints a **TSV** summary (verdict, track, cost, wall time, tool calls) for quick regression checks.

---

## Tests

```bash
uv run pytest
```

---

## Evals

Evals invoke the **real** agent (network + API usage). Ensure `.env` is configured, then:

```bash
uv run python evals/run.py
uv run python evals/run.py --golden
uv run python evals/run.py --adversarial
```

Thresholds and policies are documented in `evals/run.py` and **AGENT_SPEC §8**.

---

## Repository layout

```
├── AGENT_SPEC.md           Product, ICP, data flow, security, eval policy
├── pyproject.toml          Package: prospect-research; extras: dev, ui, rag, mcp
├── .env.example
├── scripts/                Optional helper scripts (e.g. sample batch rerun)
├── src/agent/
│   ├── __main__.py         CLI entry
│   ├── agent.py            Orchestration loop (+ web_search attachment)
│   ├── brief.py            Brief schema
│   ├── config.py           Settings and startup validation
│   ├── identity.py         Company identity resolution
│   ├── sales_app.py        FastAPI batch UI + static mount
│   ├── spreadsheet_import.py
│   ├── prompts/
│   ├── tools/              SAM, USAspending, SBIR, FedRAMP marketplace, fetch, registry
│   ├── reliability/
│   ├── observability/
│   └── security/
├── evals/
│   ├── run.py
│   ├── golden/
│   └── adversarial/
├── tests/
├── sales-ui/               Vite + React (batch workspace, brief cards, JSON export)
├── docs/                   Agent engineering notes; design system draft
└── assets/logos/
```

Console script: **`prospect-sales-ui`** → `agent.sales_app:main`.

---

## Further reading

- [`docs/README.md`](./docs/README.md) — short index of system design, tools, reliability, security, evals, and product-thinking notes
- [`docs/ARKENSTONE_DESIGN_SYSTEM.md`](./docs/ARKENSTONE_DESIGN_SYSTEM.md) — UI tokens and patterns (sales UI)

---

## License / usage

Internal Arkenstone Defense project context is assumed in `AGENT_SPEC.md`. Add a `LICENSE` file at the repo root if you intend open distribution.
