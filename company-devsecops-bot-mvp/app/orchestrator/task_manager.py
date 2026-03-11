from __future__ import annotations

from .executor import execute_step
from .planner import create_plan
from .state_machine import can_transition
from .verifier import verify_completion
from ..store import (
    append_task_step,
    create_task,
    get_task,
    list_task_steps,
    update_task_status,
    update_task_step,
)


async def create_task_from_goal(goal: str, requested_by: str) -> str:
    task_id = create_task(goal=goal, requested_by=requested_by)
    plan = create_plan(goal)
    for step in plan.steps:
        append_task_step(task_id, step.model_dump())
    return task_id


async def run_task(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        return {"ok": False, "message": "Task not found"}

    current = task["status"]
    if not can_transition(current, "running") and current != "running":
        return {"ok": False, "message": f"Task cannot run from status '{current}'"}

    update_task_status(task_id, "running")
    steps = list_task_steps(task_id)
    context = {"goal": task["goal"], "task_id": task_id}

    for row in steps:
        if row["status"] == "completed":
            continue
        step_model = {
            "step_index": row["step_index"],
            "title": row["title"],
            "tool_name": row["tool_name"],
            "tool_input": row["tool_input"],
            "status": row["status"],
            "output": row["output"],
            "error": row["error"],
        }
        from .models import TaskStep

        step = TaskStep(**step_model)
        result = await execute_step(step, context)
        update_task_step(task_id, result.step_index, result.model_dump())
        if result.status == "failed":
            update_task_status(task_id, "failed")
            return {"ok": False, "message": result.error or "Step failed"}

    refreshed = list_task_steps(task_id)
    ok, summary = verify_completion([dict(x) for x in refreshed])
    update_task_status(task_id, "completed" if ok else "failed")
    return {"ok": ok, "message": summary}
