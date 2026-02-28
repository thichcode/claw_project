import json

from .agents.router import route_model
from .audit import write_audit
from .models import ActionResponse, DeployRequest, ScanRequest
from .policy import can_approve, can_approve_prod, can_deploy, can_deploy_env, can_scan, requires_approval
from .store import approve_request, create_approval, find_recent_pending_request, get_request, mark_executed
from .tools.gitlab_tool import trigger_pipeline
from .tools.k8s_tool import deploy_service
from .tools.security_tool import scan_summary


async def handle_chat(user: str, message: str) -> ActionResponse:
    model = route_model(message)
    write_audit(user, "chat", {"message": message, "routed_model": model})
    return ActionResponse(ok=True, message=f"Routed to {model}")


async def handle_scan(user: str, req: ScanRequest) -> ActionResponse:
    if not can_scan(user):
        return ActionResponse(ok=False, message="Not authorized to run scan")

    gl = await trigger_pipeline(req.project_id, req.branch)
    sec = await scan_summary(req.project_id, req.branch)
    write_audit(user, "scan", {"project_id": req.project_id, "branch": req.branch, "gitlab": gl, "security": sec})
    if gl.get("ok"):
        return ActionResponse(ok=True, message=f"Scan started. {sec['message']}")
    return ActionResponse(ok=False, message=f"Scan request failed: {gl.get('message')}")


async def handle_deploy(req: DeployRequest) -> ActionResponse:
    if not can_deploy(req.requested_by):
        return ActionResponse(ok=False, message="Not authorized to request deploy")

    if not can_deploy_env(req.env):
        return ActionResponse(ok=False, message=f"Env '{req.env}' is not in allowlist")

    payload = req.model_dump()

    # Idempotency: reuse identical pending deploy request within 10 minutes.
    recent = find_recent_pending_request("deploy", payload, req.requested_by, within_minutes=10)
    if recent:
        rid = recent["request_id"]
        return ActionResponse(ok=True, message="Deploy already pending approval", request_id=rid)

    if requires_approval("deploy"):
        request_id = create_approval("deploy", payload, req.requested_by)
        write_audit(req.requested_by, "deploy_requested", payload | {"request_id": request_id})
        return ActionResponse(ok=True, message="Deploy requires approval", request_id=request_id)

    res = await deploy_service(req.service, req.env, req.image_tag)
    write_audit(req.requested_by, "deploy_executed", payload | {"result": res})
    return ActionResponse(ok=res["ok"], message=res["message"])


async def handle_approve(request_id: str, approver: str) -> ActionResponse:
    if not can_approve(approver):
        return ActionResponse(ok=False, message="Not authorized to approve")

    row = get_request(request_id)
    if not row:
        return ActionResponse(ok=False, message="Request not found")

    payload = json.loads(row["payload_json"])

    # Optional tighter control for prod approvals.
    if payload.get("env", "").lower() == "prod" and not can_approve_prod(approver):
        return ActionResponse(ok=False, message="Only prod approvers can approve production deploy")

    if int(row["approved"]) == 0 and not approve_request(request_id, approver):
        return ActionResponse(ok=False, message="Approve failed")

    if int(row["executed"]) == 1:
        return ActionResponse(ok=True, message="Already approved and executed")

    if row["action_type"] == "deploy":
        res = await deploy_service(payload["service"], payload["env"], payload["image_tag"])
        mark_executed(request_id, res)
        write_audit(approver, "approved_and_executed", {"request_id": request_id, "payload": payload, "result": res})
        return ActionResponse(ok=res.get("ok", True), message=f"Approved + executed: {res.get('message', 'done')}")

    write_audit(approver, "approved", {"request_id": request_id})
    return ActionResponse(ok=True, message="Approved")
