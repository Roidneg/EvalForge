import os
import sqlite3
from contextlib import closing
from pathlib import Path

from models import EvaluationInput, EvaluationResult, EvaluationSummary
DB_PATH = Path(os.environ.get("EVALFORGE_DB", str(Path(__file__).resolve().parent / "evaluations.db")))


def initialize_database() -> None:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id INTEGER PRIMARY KEY,
                test_case_id TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('pass', 'fail')),
                latency_ms INTEGER NOT NULL
                    CHECK (latency_ms >= 0),
                review_required INTEGER NOT NULL
                    CHECK (review_required IN (0, 1))
            )
        """)
        connection.commit()


def save_evaluation(evaluation: EvaluationInput) -> int:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO evaluations (
                test_case_id,
                agent_version,
                status,
                latency_ms,
                review_required
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                evaluation.test_case_id,
                evaluation.agent_version,
                evaluation.status,
                evaluation.latency_ms,
                int(evaluation.review_required),
            ),
        )

        evaluation_id = cursor.lastrowid
        if evaluation_id is None:
            raise RuntimeError("Database did not return an evaluation ID.")

        connection.commit()
        return evaluation_id

def get_evaluations() -> list[EvaluationResult]:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute("""
            SELECT
                evaluation_id,
                test_case_id,
                agent_version,
                status,
                latency_ms,
                review_required
            FROM evaluations
            ORDER BY evaluation_id
        """).fetchall()

    results = []
    for row in rows:
        data = dict(row)
        data["review_required"] = bool(data["review_required"])
        results.append(EvaluationResult.model_validate(data))

    return results

def get_evaluation_summary() -> EvaluationSummary:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row

        row = connection.execute("""
            SELECT
                COUNT(*) AS total_evaluations,
                COUNT(CASE WHEN status = 'pass' THEN 1 END)
                    AS passed_evaluations,
                COUNT(CASE WHEN status = 'fail' THEN 1 END)
                    AS failed_evaluations,
                AVG(latency_ms) AS average_latency_ms
            FROM evaluations
        """).fetchone()

    total = row["total_evaluations"]
    passed = row["passed_evaluations"]

    return EvaluationSummary(
        total_evaluations=total,
        passed_evaluations=passed,
        failed_evaluations=row["failed_evaluations"],
        pass_rate_percent=(
            round(passed / total * 100, 2) if total > 0 else None
        ),
        average_latency_ms=row["average_latency_ms"],
    )

if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DB_PATH}")