from contextlib import asynccontextmanager
import logging
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import database
import workbench

from database import get_evaluation_summary, get_evaluations, save_evaluation
from models import EvaluationInput, EvaluationResult, EvaluationSummary

@asynccontextmanager
async def lifespan(app):
    workbench.initialize_runs()
    database.initialize_database()
    yield


app = FastAPI(title="EvalForge", version="0.1.0", lifespan=lifespan)


@app.exception_handler(sqlite3.Error)
async def database_error(request: Request, exc: sqlite3.Error):
    logging.getLogger(__name__).exception("Database operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable. Check the server logs and database path."})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluations", status_code=201)
def submit_evaluation(evaluation: EvaluationInput) -> EvaluationResult:
    evaluation_id = save_evaluation(evaluation)

    return EvaluationResult(
        evaluation_id=evaluation_id,
        **evaluation.model_dump(),
    )

@app.get("/evaluations")
def list_evaluations() -> list[EvaluationResult]:
    return get_evaluations()

@app.get("/summary")
def evaluation_summary() -> EvaluationSummary:
    return get_evaluation_summary()

@app.post("/runs", status_code=201)
def submit_run(request: workbench.RunInput):
    return workbench.create_run(request)


@app.get("/runs")
def saved_runs():
    return workbench.list_runs()


@app.get("/runs/{run_id}")
def saved_run(run_id: str):
    try:
        return workbench.get_run(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found.")


@app.get("/compare")
def comparison(baseline_id: str, candidate_id: str):
    try:
        return workbench.compare_runs(baseline_id, candidate_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
