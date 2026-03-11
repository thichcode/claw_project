import json

from fastapi import APIRouter

from .models import (
    ActionResponse,
    ApproveRequest,
    ChatRequest,
    DeployRequest,
    ScanRequest,
    TaskCreateRequest,
)
from .command_handler import handle_approve, handle_chat, handle_deploy, handle_scan
from .orchestrator.task_manager import create_task_from_goal, run_task
from .store import get_request, get_task, list_recent_approvals, list_recent_audit, list_task_steps

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True, "service": "devsecops-bot-mvp"}


@router.post("/chat", response_model=ActionResponse)
async def chat(req: ChatRequest):
    return await handle_chat(req.user, req.message)


@router.post("/scan", response_model=ActionResponse)
async def scan(req: ScanRequest):
    return await handle_scan("system", req)


@router.post("/deploy", response_model=ActionResponse)
async def deploy(req: DeployRequest):
    return await handle_deploy(req)


@router.post("/approve", response_model=ActionResponse)
async def approve(req: ApproveRequest):
    return await handle_approve(req.request_id, req.approver)


@router.post("/tasks", response_model=ActionResponse)
async def create_task(req: TaskCreateRequest):
    task_id = await create_task_from_goal(req.goal, req.requested_by)
    return ActionResponse(ok=True, message="Task created", request_id=task_id)


@router.post("/tasks/{task_id}/run", response_model=ActionResponse)
async def run_created_task(task_id: str):
    res = await run_task(task_id)
    return ActionResponse(ok=res["ok"], message=res["message"], request_id=task_id)


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"ok": False, "message": "Task not found"}

    steps = list_task_steps(task_id)
    return {
        "ok": True,
        "task": {
            "task_id": task["task_id"],
            "goal": task["goal"],
            "requested_by": task["requested_by"],
            "status": task["status"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "steps": steps,
        },
    }


@router.get("/approvals/{request_id}")
def approval_detail(request_id: str):
    row = get_request(request_id)
    if not row:
        return {"ok": False, "message": "Request not found"}

    return {
        "ok": True,
        "request": {
            "request_id": row["request_id"],
            "action_type": row["action_type"],
            "payload": json.loads(row["payload_json"]),
            "requested_by": row["requested_by"],
            "approved": bool(row["approved"]),
            "approved_by": row["approved_by"],
            "executed": bool(row["executed"]),
            "execution_result": json.loads(row["execution_result_json"]) if row["execution_result_json"] else None,
            "created_at": row["created_at"],
            "approved_at": row["approved_at"],
            "executed_at": row["executed_at"],
        },
    }


@router.get("/approvals")
def approvals(
    limit: int = 50,
    approved: bool | None = None,
    executed: bool | None = None,
    requested_by: str | None = None,
    action_type: str | None = None,
):
    limit = max(1, min(limit, 500))
    rows = list_recent_approvals(
        limit=limit,
        approved=approved,
        executed=executed,
        requested_by=requested_by,
        action_type=action_type,
    )
    items = []
    for row in rows:
        items.append(
            {
                "request_id": row["request_id"],
                "action_type": row["action_type"],
                "payload": json.loads(row["payload_json"]),
                "requested_by": row["requested_by"],
                "approved": bool(row["approved"]),
                "approved_by": row["approved_by"],
                "executed": bool(row["executed"]),
                "created_at": row["created_at"],
                "approved_at": row["approved_at"],
                "executed_at": row["executed_at"],
            }
        )
    return {"ok": True, "count": len(items), "items": items}


@router.get("/audit")
def audit(limit: int = 100, actor: str | None = None, action: str | None = None):
    limit = max(1, min(limit, 1000))
    rows = list_recent_audit(limit=limit, actor=actor, action=action)
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "actor": row["actor"],
                "action": row["action"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
        )
    return {"ok": True, "count": len(items), "items": items}
