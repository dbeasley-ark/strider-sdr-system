# Prospect Research

**Arkenstone Defense** — Claude-powered agent that qualifies inbound defense-tech companies against **Track 1** and **Track 2** ICP criteria and produces a structured **brief** an SDR can scan in about a minute (classification, hooks with citations, target roles, confidence).

The authoritative product and safety spec is [`AGENT_SPEC.md`](./AGENT_SPEC.md). This README is the operational entry point: install, run, batch UI, evals, and layout.

---

## What you get

- **CLI:** `python -m agent --company "<name-or-domain>"` — runs the research loop, prints JSON to stdout, streams progress to stderr, writes `trace.jsonl` and `brief.json` under `./runs/<slug>/<timestamp>/`.
- **Tooling:** Pydantic tool contracts, retries/timeouts/circuit breaker, structured tracing, cost and wall-clock budgets, URL allowlisting, compliance-oriented output filtering (see `src/agent/`).
- **Batch sales UI (optional):** FastAPI service + React (Vite) app — upload a spreadsheet, map company/domain columns, run one subprocess per row against the same CLI.
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
| `ARKENSTONE_AGENT_ENABLED` | Kill switch — must be `true` to run |

Model, budgets (tool calls, USD cost, wall seconds, context), runs directory, and profile are also configured via `AGENT_*` env vars.

**Importing config without keys** (e.g. lightweight helpers): set `_AGENT_SKIP_STARTUP_CHECKS=1` — used internally so tooling does not require secrets at import time.

---

## CLI usage

```bash
uv run python -m agent --company "Shield AI"
uv run python -m agent --company shield.ai --domain shield.ai
uv run python -m agent --company "Hadrian" --quiet
uv run python -m agent --company "Contoso" --poc-name "Alex Kim" --poc-title "CTO"
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

Open `http://localhost:5173`, use Single run for one company (optional website and POC fields) or upload a CSV/XLSX for a batch job; events stream the same way.

**Production-style:** build the UI and serve it from the same process:

```bash
cd sales-ui && npm run build
uv run prospect-sales-ui
```

If `sales-ui/dist` exists, the FastAPI app mounts it at `/`; API routes remain under `/api/...`.

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
├── src/agent/
│   ├── __main__.py         CLI entry
│   ├── agent.py            Orchestration loop
│   ├── brief.py            Brief schema
│   ├── config.py           Settings and startup validation
│   ├── identity.py         Company identity resolution
│   ├── sales_app.py        FastAPI batch UI + static mount
│   ├── spreadsheet_import.py
│   ├── prompts/
│   ├── tools/              fetch_company_page, SAM, USASpending, SBIR, registry
│   ├── reliability/
│   ├── observability/
│   └── security/
├── evals/
│   ├── run.py
│   ├── golden/
│   └── adversarial/
├── tests/
├── sales-ui/               Vite + React (batch workspace, brief cards)
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
