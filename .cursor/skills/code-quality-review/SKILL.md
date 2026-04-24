---
name: code-quality-review
description: Runs an audit-first code quality pass (AI-shaped patterns, indirection, duplication, comment noise, narrator comments) with conservative remediation; auto-fixes only mechanical bucket-A changes. Use when the user asks for slop cleanup, a code quality audit, conservative refactor, comment cleanup, unused imports, or to reduce AI slop without broad rewrites or migrations.
---

# Code quality review

## Quick start

1. **Inventory** — `git status`, branch, commit SHA, stack markers, convention files; run tests, lint, and type-check; record baseline.
2. **Gate** — Apply the refusal table before any edit; if baseline fails or scope is unsafe, stay detection-only or stop.
3. **Detect** — Read-only scan; for each finding record path, line range, category, evidence, confidence, proposed action.
4. **Classify** — One bucket per finding (A / B / C); if unsure, choose the stricter bucket.
5. **Fix** — Apply **only** bucket A; re-run validation; revert on regression.
6. **Report** — Full pass summaries use [report-template.md](report-template.md); list B proposals and C flags with verification steps.

## Core principle

**Detection is broad. Remediation is conservative.**

Find more issues than you auto-fix. Most problems need human judgment. When in doubt: **flag** instead of changing, **propose** instead of applying, **preserve behavior** over cleanliness. If a cleanup is not clearly safe, do not apply it automatically.

## Engineering standard

The final code should read as if a **pragmatic senior engineer** wrote it: simple, clean, idiomatic, minimal ceremony. Prefer straightforward control flow and names that carry meaning. Avoid verbose AI-style patterns (over-explaining in code, needless layers, generic helpers, comment walls that restate logic).

## Comments

Treat comments as a liability unless they earn their place.

**Remove aggressively:**

- Line-by-line or "narrator" comments that restate what the code already says
- Obvious comments (`// increment i`, `// return the result`)
- Banner / section divider blocks and decorative framing
- Large multi-line explanatory comments that duplicate what clearer structure or naming should convey

**Keep only** comments that document **non-obvious intent**, **business rules**, **invariants**, or **edge cases** where the code alone would mislead a maintainer. When in doubt, delete the comment and improve the code (names, structure, small extraction) instead.

Comment cleanup is in-bounds during remediation when removal is clearly non-behavioral; if a comment might encode a rule you cannot verify, **flag** (bucket C) rather than delete.

## Operating posture

Default to **audit-first**. Do not edit code until you have:

1. Understood repo layout and entry points
2. Identified project conventions (from repo docs and existing code)
3. Established whether tests, lint, and type-check exist and how to run them
4. Confirmed a safe rollback path (git)

Prefer: small diffs, isolated commits, reversible edits, explicit justification per change. Avoid cleanup churn.

---

## Refusal and narrowing (check before edits)

| Condition | Action |
|-----------|--------|
| **No git / no rollback** | Refuse auto-fix; detection-only; explain why remediation is unsafe |
| **No meaningful tests** | Do not remove abstractions, deduplicate logic, or delete possibly dead code. Auto-fix only narrow mechanical cases (see below). State clearly: *I can identify problems, but without tests I cannot safely remove abstractions or consolidate logic while preserving behavior.* |
| **Dirty working tree** | Ask user to commit or stash; do not clean on top of unrelated work |
| **`main` / `master` / production branch** | Recommend a remediation branch; no broad cleanup on primary branch |
| **Baseline already failing** (tests/lint/types) | No behavior-adjacent cleanup; stop or detection-only; separate pre-existing vs new failures |

**Mechanical auto-fixes allowed without tests** (only when provably safe):

- Verifiably unused imports
- Obviously unreachable trivial code with zero behavioral surface
- Exact duplicates only when clearly safe **and** user explicitly requested consolidation
- Removal of comments that are purely redundant with the code (no domain knowledge asserted)

---

## Required workflow (phases — do not skip)

### Phase 1: Inventory and baseline (before any code change)

**Repo state:** `git status`, branch, recent commits, current commit SHA (rollback anchor).

**Stack:** Infer from markers (`package.json`, `tsconfig.json`, `pyproject.toml`, `go.mod`, CI configs, etc.).

**Conventions:** Read what exists, e.g. `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `copilot-instructions.md`, `CONTRIBUTING.md`, `README.md`. If none: note as systemic gap.

**Baseline:** Run and record tests, lint, type-check (and coverage if standard). Capture pass/fail, error counts, duration if useful. If tests fail before changes → **no behavior-sensitive remediation**; detection-only or stop.

### Phase 2: Detection (read-only)

Search broadly for:

- **Structural:** pass-through wrappers, speculative abstractions, one-use utility layers, premature generics, needless hierarchies, config mirroring defaults only
- **Logic:** duplicated logic with drift, broad exception handling, dead/unreachable branches, copied business logic with inconsistency, misleading names
- **Quality:** unused imports/vars/helpers, cargo-cult retries, low-signal and narrator comments, stale TODOs, redundant guards vs actual types, thin indirection with no test seam
- **Fingerprints:** vague helpers (`processData`, `handleResponse`, `executeOperation`), duplicate util files, comments restating code, banner blocks, unused "future-proof" layers, broad interfaces with one implementation, style mismatch with surroundings

**Exclusions** (never cleanup targets unless user explicitly asks):

Generated, vendored, build artifacts, lockfiles, `node_modules/`, `dist/`, `build/`, `vendor/`, `third_party/`, code marked `@generated` / autogenerated.

**Per finding, record:** file path, line range, category, evidence, confidence (`high` / `medium` / `low`), proposed action (`auto-fix` / `propose` / `flag` / `investigate`).

### Phase 3: Classification (exactly one bucket per finding)

| Bucket | Criteria |
|--------|----------|
| **A — Auto-fix** | Mechanical, reversible, **no** behavioral change by construction, narrow/obvious, validation can run after, pattern explicitly safe |
| **B — Propose** | Likely correct but has behavioral surface (dedupe logic, tighten exceptions, consolidate utils, dynamic imports, call-structure changes) |
| **C — Flag** | Business logic, security, concurrency, correctness edges, architecture, unclear ownership, low confidence, below ~90% confidence |

**Defaults:** unsure A vs B → **B**; unsure B vs C → **C**. Prefer stricter bucket.

### Phase 4: Remediation (apply only bucket A)

For each change: smallest edit → run validation → confirm metrics do not worsen → revert immediately on regression → avoid unrelated formatting. Prefer one logical fix per commit. After batches: rerun full test suite where available. On unclear regression: revert to last good state, stop, report.

### Phase 5: Bucket B proposals

For each: why it is a quality issue; why not auto-applied; exact risk surface; how to verify after apply; test gaps. Frame as **review items**, not certainties.

### Phase 6: Reporting

Use the structure in [report-template.md](report-template.md) for full pass summaries. Minimum: counts by category and bucket; baseline vs after (tests/lint/types); lists for auto-fixed, awaiting review (B), flagged (C); systemic observations (no conventions file, no CI gate, missing tests on critical paths, etc.).

---

## What not to do

Do **not**: reformat unrelated code; restyle for consistency unless required by the finding; rename unless the name is the issue; remove dead code from static analysis alone in dynamic systems; merge diverged duplicates automatically; modernize or change paradigms (e.g. callbacks → async) as "cleanup"; delete comments that may encode undocumented business rules without verification; edit generated/vendored paths; ship one huge unrelated patch.

---

## New code and edits

Prefer existing patterns over generic best practices. No new abstractions without demonstrated need. No helpers unless they improve clarity, reuse, or correctness. No speculative interfaces/types/classes. No unrequested future-proofing. Direct over clever. Match local naming, errors, module layout. Comments only where intent or rules are non-obvious.

Before adding an abstraction, check: used in more than one place? reduces real complexity? matches architecture? clearer than without? If no → do not add.

---

## Preferred response style

Be concrete: file + line range; separate certainty from suspicion; explain *why* it is an issue and *why* a fix is safe or unsafe. Avoid vague praise ("maintainability", "cleaned up") without specifics. Prefer: *removed unused import*; *removed redundant comments*; *flagged duplicated parsing with drift in edge cases*; *proposed narrowing exception scope because validation errors are swallowed*; *flagged speculative abstraction: one caller, indirection without reuse*.

---

## Scope guardrails

Requests like "rewrite this module", "modernize", "migrate to framework X", "convert this pattern everywhere" are **separate refactors/migrations**, not a focused quality pass. Do the audit first; recommend deeper refactors separately. A controlled quality pass beats an uncontrolled rewrite.
