"""Orchestrator data models."""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Literal
from datetime import datetime


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    id: str
    title: str
    description: str
    tool_name: str | None = None
    action_type: Literal["reason", "tool_call", "respond"] = "reason"
    expected_output: str | None = None
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: str | None = None


class Task(BaseModel):
    id: str
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    final_output: Any = None


class ToolResult(BaseModel):
    ok: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    is_complete: bool
    confidence: float = 0.0
    reasoning: str
    missing_items: list[str] = Field(default_factory=list)
    next_action: str | None = None