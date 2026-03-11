from __future__ import annotations

from pydantic import BaseModel, Field


class TaskStep(BaseModel):
    step_index: int
    title: str
    tool_name: str
    tool_input: dict = Field(default_factory=dict)
    status: str = "pending"
    output: dict | None = None
    error: str | None = None


class TaskPlan(BaseModel):
    steps: list[TaskStep]


class TaskExecutionResult(BaseModel):
    task_id: str
    status: str
    steps: list[TaskStep]
    summary: str
