# Code quality review backlog

Carry-over from audit-first passes (personal **code quality review** skill: `~/.cursor/skills/code-quality-review/SKILL.md`, plus User Rules — see `~/.cursor/user-rules-code-quality-review.md` — plus lint/type hygiene). **Not** a commitment to implement everything here — triage and schedule.

---

## Recently fixed (for reference)

- **`lookup_sbir_awards.py` / `lookup_usaspending_awards.py`:** `datetime.utcnow()` → `datetime.now(UTC)` for `fetched_at` (and any same-run timestamps). JSON wire format gains explicit UTC offset where serializers emit ISO-8601; behavior is timezone-correct.
- **Mechanical cleanups (earlier pass):** unused imports, import order, unused `type: ignore` on FedRAMP `HttpUrl` args; decorative `# ──` section banners trimmed across `src/agent/`.

---

## Awaiting review (likely correct; needs decision + verification)

| Area | Notes | Suggested verification |
|------|--------|-------------------------|
| **Ruff (~27 issues)** | E501 long lines, UP042 (`StrEnum`), N818 (exception `*Error` naming), ASYNC109 (`timeout` param on async), UP041 (`TimeoutError` vs `asyncio.TimeoutError`). | Run `uv run ruff check src tests`; apply `ruff check --fix` selectively; full pytest after each batch. |
| **`StrEnum` / exception renames** | Style + consistency; watch for serialized enum values and `except` clauses if names change. | Grep call sites and tests for string literals. |
| **`src/agent/agent.py` — broad `except Exception`** | Tool dispatch and loop glue swallow many failures into structured tool errors. | Narrow only with clear taxonomy + tests for each path. |
| **Module-level `research()` / `run()`** | Convenience wrappers over `Agent`; not a quality smell by itself, but duplicate entry style. | Keep unless you want a single public API surface. |
| **`fetch_company_page.py` / `lookup_sam_registration.py`** | Still use `datetime.utcnow()` (same deprecation as awards tools had). | Same fix: `datetime.now(UTC)` + import `UTC`. |
| **Mypy (~40 errors in 8 files)** | Registry generics, `openpyxl` stubs, `agent.py` message-block unions, Pydantic `Field(default_factory=...)` literal typing, etc. | `uv run mypy src/agent`; add stubs or types incrementally; do not “fix” with blanket ignores. |

---

## Flagged for human judgment (low confidence or high blast radius)

| Topic | Why a human should own it |
|-------|---------------------------|
| **Broad exception handling** | `except Exception` / `BaseException` in agent loop, FedRAMP fetch, tools — changes alter user-visible errors, traces, and retry behavior. |
| **Compliance regexes (`compliance_keywords.py`)** | Any pattern change is a legal/product call, not a linter cleanup. |
| **Output filter / citation rules** | Downgrade logic and seed-host behavior tie to spec §7.1 / §7.3; easy to regress SDR trust. |
| **Wall / synthesis / reserve nudge ordering** | Timing of tools-off and synthesis is budget- and API-contract sensitive. |
| **Renaming public exceptions** (`ComplianceHardStop`, `PermissionDenied`, …) | N818 wants `*Error`; renames break importers and documented playbooks. |

---

## Systemic observations

- **Tests are the reliable gate:** `uv run pytest` is green (106 tests). **Ruff and mypy are not green** on baseline — treat lint/type deltas as advisory until you decide to make them CI-blocking.
- **No `AGENTS.md` / minimal CI config in-repo** for those gates; conventions live in `README.md` and `AGENT_SPEC.md`.
- **SDK-heavy code (`agent.py`)** | Union types for Anthropic message blocks will keep mypy noisy until modeled with narrow helpers or typed narrowing.
- **Optional UI path (`sales-ui/`)** | Not covered by the Python code quality review passes above; separate audit if you want the same comment / deprecation discipline there.
- **Cost / pricing map (`observability/cost.py`)** | Unknown model slugs intentionally fall back to Opus pricing — document in runbooks so ops does not assume “exact” dollars for new models.

---

## How to use `code-quality-review.md`

1. Pick one row under **Awaiting review**, branch, implement, pytest.
2. Do **not** batch unrelated “cleanup” with behavior changes.
3. After a chunk ships, delete or strike the corresponding row so this doc stays honest.
