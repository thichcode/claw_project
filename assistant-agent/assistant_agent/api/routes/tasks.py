"""Task routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
import uuid

from assistant_agent.orchestrator import TaskManager, Planner, Executor, Verifier, Task
from assistant_agent.tools import ToolRegistry

router = APIRouter()

# Global task storage (in-memory for MVP)
TASKS: dict[str, Task] = {}

# Initialize components
tool_registry = ToolRegistry()
planner = Planner()
executor = Executor(tool_registry)
verifier = Verifier()
task_manager = TaskManager(planner, executor, verifier)


class CreateTaskRequest(BaseModel):
    goal: str


class TaskResponse(BaseModel):
    id: str
    goal: str
    status: str
    steps: list[dict[str, Any]]
    final_output: Any = None


@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest) -> TaskResponse:
    """Create a new task with a plan."""
    task = await task_manager.create_task(request.goal)
    TASKS[task.id] = task
    return TaskResponse(
        id=task.id,
        goal=task.goal,
        status=task.status.value,
        steps=[step.model_dump() for step in task.steps],
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """Get task by ID."""
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id,
        goal=task.goal,
        status=task.status.value,
        steps=[step.model_dump() for step in task.steps],
        final_output=task.final_output,
    )


@router.post("/tasks/{task_id}/run", response_model=TaskResponse)
async def run_task(task_id: str) -> TaskResponse:
    """Execute and verify a task."""
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task = await task_manager.run_task(task)
    TASKS[task.id] = task

    return TaskResponse(
        id=task.id,
        goal=task.goal,
        status=task.status.value,
        steps=[step.model_dump() for step in task.steps],
        final_output=task.final_output,
    )