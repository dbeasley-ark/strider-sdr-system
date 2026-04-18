# Eval fixtures

Canned HTML documents used by the adversarial eval suite. Never served
by a live agent run.

## A5 — `classified_marker.html`

Fixture for spec §8.2 A5. Contains both a CUI marker and multiple
classified banners so the §7.3 output filter's HARD_STOP path fires.

### Harness integration — known gap for v1

The live `agents.research()` end-to-end path in `evals/run.py` does NOT
currently serve this fixture over HTTP and redirect the agent to it.
That means the A5 case as wired runs the LLM against the real web for
"Arkenstone Test Fixture", which will return `insufficient_data` (non-
existent company) rather than exercising the `ComplianceHardStop`
code path.

The `ComplianceHardStop` behavior IS covered at the unit level by
`tests/test_output_filter.py::test_hard_stop_raises_on_classified`,
which passes today. For v1 we rely on that unit test plus the
production code path that runs the filter on every brief.

v1.x follow-up: wire a local HTTP server into `evals/run.py` that
serves `evals/fixtures/classified_marker.html` on a fixed port, seed
the allowlist with that host, and force the LLM to call
`fetch_company_page` against it. Tracked in §10 graduation items
alongside deterministic page-snapshot replay.
