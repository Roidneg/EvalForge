![EvalForge run comparison showing improvements and a regression](docs/evalforge-comparison.png)

# EvalForge

**Know how your AI actually performs.**

A local AI evaluation workbench for importing supplied model responses, running deterministic checks, saving results, inspecting evidence, and comparing versions. Built by Jorge Arenas with AI-assisted development, extending the original AI Evaluation Service.

## Quick start — Windows / PyCharm

Use Python 3.12 or 3.13. Extract this folder into a new project directory (keep your existing project as a backup), then open it in PyCharm. In the terminal, run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Start the API in terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Start the dashboard in terminal 2, from the same project directory:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Open http://localhost:8501 for the workbench. API documentation: http://127.0.0.1:8000/docs. Keep both terminals running; Ctrl+C stops either process. No API key or paid service is required.

If PyCharm already has an active virtual environment, `python` can replace the explicit `.venv` executable above. An occupied port usually means an older server is still running; stop it before starting this one.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m uvicorn main:app --reload
# In a second terminal, activate the same environment:
python -m streamlit run dashboard.py
```

## Three-minute demo

1. On **Run evaluations**, choose **Sample baseline**, name it `Baseline`, set version `v1`, and click **Evaluate and save**.
2. Choose **Sample candidate**, name it `Candidate`, set version `v2`, and save it.
3. On **Inspect results**, select either run. Expand a case to inspect its prompt, supplied response, checks, and evidence. Filter failures or export full JSON results.
4. On **Compare runs**, select Baseline as the baseline and Candidate as the candidate. Click **Compare selected runs**.
5. Expect baseline **7/12 (58.33%)**, candidate **11/12 (91.67%)**, **+33.33 percentage points**, **5 improvements**, and **1 regression** (TC-007). The delta uses unrounded counts, so displayed rounded rates may differ by 0.01 when subtracted.
6. Restart the API. The saved runs remain available.

All sample prompts and responses are synthetic, including the deliberate failures. The improved candidate still fails the support-address check. Aggregate improvement does not mean every behavior improved.

## Import your own data

Upload a UTF-8 JSON array or CSV (at most 5 MB, 500 cases). Download the samples from the dashboard or use `data/baseline.json` and `data/baseline.csv` as templates. CSV columns must be `case_id,prompt,response,checks` in that order; `checks` is a JSON array within a properly quoted CSV cell.

```json
[
  {
    "case_id": "TC-001",
    "prompt": "Reply with exactly hello.",
    "response": "Hello",
    "checks": [{"kind": "exact_match", "value": "hello", "case_sensitive": false}]
  }
]
```

Rules:

| Check | Meaning |
| --- | --- |
| `exact_match` | Full response equals expected text after trimming outer whitespace |
| `contains` | Required substring occurs anywhere |
| `not_contains` | Forbidden substring does not occur |
| `valid_json` | Response parses as JSON; no schema or semantic validation |

Text checks are case-insensitive by default (Unicode casefold); set `case_sensitive: true` when needed. Text values must be nonblank. A JSON check omits `value` or uses an empty value. JSON scalars are allowed; NaN and Infinity are rejected. Markdown code fences are not removed.

A case passes only if every check passes. Case score is the fraction of checks passing; run pass rate is the fraction of fully passing cases. No LLM judge or model-generation call is made. For example, a forbidden-substring check also fails a negated sentence containing that phrase. These checks do **not** establish correctness, safety, or policy compliance.

## Architecture and persistence

Streamlit → HTTP requests → FastAPI → Pydantic validation → deterministic evaluator → SQLite.

- `main.py`: existing endpoints plus run and comparison routes; initializes tables on startup.
- `models.py`, `database.py`, `test_main.py`: original manual-evaluation service, retained with a configurable database path.
- `workbench.py`: dataset validation, checks, atomic run persistence, comparison safeguards.
- `dashboard.py`: dataset upload, execution, evidence review, export, comparisons.
- `test_workbench.py`, `test_dashboard.py`: API/rule tests and UI-to-API integration test.

`evaluations.db` is included from your original upload with its existing records. The new `runs` table is added without changing the legacy `evaluations` table. A complete run snapshot contains test definitions, responses, scores, evidence, timestamps, and evaluator version, committed as one SQLite transaction. Legacy manual entries remain separate from automatically evaluated runs.

Run snapshots are JSON in SQLite: simple and auditable for a local MVP, but not optimized for large analytical queries. Comparisons require identical case IDs, prompts, checks, and evaluator version. Changing only responses or their order is allowed. Each click creates a separate run; there is no automatic retry of writes.

Optional environment variables are documented in `.env.example`; the app does **not** automatically read that file. Set them in the terminal before starting the relevant process. The API owns SQLite access; the dashboard calls the API.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health |
| POST / GET | `/evaluations` | Original manually labeled evaluations |
| GET | `/summary` | Original manual-evaluation summary |
| POST / GET | `/runs` | Create / list automatic evaluation runs |
| GET | `/runs/{run_id}` | Full saved results |
| GET | `/compare?baseline_id=…&candidate_id=…` | Matched-definition comparison |

POST `/runs` takes `name`, `agent_version`, and `cases` (the imported dataset array). Invalid inputs return 422, unknown runs return 404, and database failures return 503. Interactive request examples are in `/docs`.

## Validation and current limits

Tested in Python 3.12 with **36 passing tests**, including the original seven tests. A Streamlit AppTest starts a real API on a temporary port, saves both samples, compares results, filters failures, and checks the API-unavailable message. Tests use temporary databases and do not modify your original records. GitHub Actions is configured for Python 3.12 and 3.13; it will run once you push to a repository. The workflow has not yet run on GitHub.

This release is a local MVP. Windows/PyCharm launch still needs verification on your machine. No live provider integration, authentication, background queue, deployment, screenshot gallery, or recorded walkthrough is included. Keep servers bound to localhost; public hosting requires additional access controls, request limits, and operational hardening. Use synthetic or approved data; SQLite stores responses in plaintext.

Before calling this portfolio release complete: run it locally, review the critical code paths, capture a real walkthrough/screenshots, create the GitHub repository, and verify CI. See `docs/SESSION_NOTES.md` for what changed and what to learn next.
