import pytest
from fastapi.testclient import TestClient

import database
from main import app


VALID_EVALUATION = {
    "test_case_id": "TC-001",
    "agent_version": "1.2",
    "status": "fail",
    "latency_ms": 850,
    "review_required": True,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database, "DB_PATH", tmp_path / "test-evaluations.db"
    )
    database.initialize_database()

    with TestClient(app) as test_client:
        yield test_client


def test_valid_evaluation_is_saved_and_retrieved(client):
    response = client.post("/evaluations", json=VALID_EVALUATION)

    assert response.status_code == 201
    expected = {**VALID_EVALUATION, "evaluation_id": 1}
    assert response.json() == expected

    retrieved = client.get("/evaluations")
    assert retrieved.status_code == 200
    assert retrieved.json() == [expected]


@pytest.mark.parametrize(
    "changes",
    [
        {"latency_ms": -850},
        {"latency_ms": "850"},
        {"status": "unknown"},
        {"unexpected_field": True},
    ],
)
def test_invalid_evaluation_is_not_saved(client, changes):
    payload = {**VALID_EVALUATION, **changes}

    response = client.post("/evaluations", json=payload)

    assert response.status_code == 422
    assert client.get("/evaluations").json() == []


def test_empty_summary(client):
    response = client.get("/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total_evaluations": 0,
        "passed_evaluations": 0,
        "failed_evaluations": 0,
        "pass_rate_percent": None,
        "average_latency_ms": None,
    }


def test_summary_calculations(client):
    examples = [
        ("fail", 850),
        ("fail", 850),
        ("pass", 1150),
    ]

    for index, (status, latency) in enumerate(examples, start=1):
        payload = {
            **VALID_EVALUATION,
            "test_case_id": f"TC-{index:03d}",
            "status": status,
            "latency_ms": latency,
            "review_required": status == "fail",
        }
        response = client.post("/evaluations", json=payload)
        assert response.status_code == 201

    response = client.get("/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total_evaluations": 3,
        "passed_evaluations": 1,
        "failed_evaluations": 2,
        "pass_rate_percent": 33.33,
        "average_latency_ms": 950.0,
    }