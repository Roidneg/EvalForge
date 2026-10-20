# EvalForge session checkpoint — October 20, 2026

## What changed

The original service stored user-supplied pass/fail labels. EvalForge now computes deterministic results for supplied responses, records complete runs, and exposes them through a Streamlit dashboard. Existing records and endpoints remain intact.

## Why this scope

Supplied responses let us build and validate a useful evaluation workflow without API costs or unstable generated results. FastAPI separates backend behavior from the interface. SQLite persists results across restarts. Run snapshots preserve the exact rubric and evidence for each evaluation.

## Data flow to explain

An uploaded dataset is parsed and validated in the dashboard. The dashboard sends a run request over HTTP. FastAPI validates it again at the trust boundary. Each response is checked, and every case receives a pass/fail and fractional check score. One SQLite transaction saves the complete run. Inspection retrieves its snapshot; comparison checks a fingerprint of test definitions before calculating changes.

## Key tradeoffs

- Deterministic string/JSON checks are reproducible but shallow. They do not establish semantic correctness.
- JSON snapshots make auditability straightforward but are less suitable for large SQL analytics.
- Runs must have identical definitions for comparison, preventing changed tests from masquerading as model improvements.
- Counts determine percentage-point change before rounding.
- Legacy manual evaluations are separate from computed runs to avoid misleading combined metrics.

## Verification

36 tests pass on Python 3.12: original service, valid/invalid runs, rule behavior, persistence across application lifespans, comparisons, dataset formats, errors, and dashboard-to-API workflow. Windows and GitHub CI remain to verify.

## Next action for Jorge

Extract the updated ZIP into a separate folder, open it in PyCharm, install requirements, and run `python -m pytest -q`. Then launch the two processes using the README and complete the sample walkthrough.

After that: review `create_run` and `compare_runs` together, capture screenshots and a brief demo, and publish the repository. Live LLM integrations and Docker are optional follow-ups, not blockers for this local evaluation workflow.
