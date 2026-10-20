from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    test_case_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    status: Literal["pass", "fail"]
    latency_ms: int = Field(ge=0)
    review_required: bool = False


class EvaluationResult(EvaluationInput):
    evaluation_id: int


class EvaluationSummary(BaseModel):
    total_evaluations: int = Field(ge=0)
    passed_evaluations: int = Field(ge=0)
    failed_evaluations: int = Field(ge=0)
    pass_rate_percent: float | None = Field(ge=0, le=100)
    average_latency_ms: float | None = Field(ge=0)