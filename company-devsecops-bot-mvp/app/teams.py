from fastapi import APIRouter, Request

from .command_handler import handle_approve, handle_chat, handle_deploy, handle_scan
from .config import settings
from .models import DeployRequest, ScanRequest

router = APIRouter()


def _help_text() -> str:
    return (
        "Commands:\n"
        "- help\n"
        "- scan <project_id> [branch]\n"
        "- deploy <service> <env> <image_tag>\n"
        "- approve <request_id>"
    )


@router.post("/messages")
async def teams_messages(req: Request):
    if not settings.ms_teams_bot_enabled:
        return {"type": "message", "text": "Teams bot is disabled"}

    body = await req.json()
    text = (body.get("text") or "").strip()
    from_user = (
        body.get("from", {}).get("id")
        or body.get("from", {}).get("aadObjectId")
        or body.get("from", {}).get("name")
        or "teams-user"
    )

    if not text:
        return {"type": "message", "text": _help_text()}

    parts = text.split()
    cmd = parts[0].lower()

    if cmd in {"help", "/help"}:
        return {"type": "message", "text": _help_text()}

    if cmd == "scan" and len(parts) >= 2:
        branch = parts[2] if len(parts) >= 3 else "main"
        res = await handle_scan(from_user, ScanRequest(project_id=parts[1], branch=branch))
        return {"type": "message", "text": res.message}

    if cmd == "deploy" and len(parts) >= 4:
        res = await handle_deploy(
            DeployRequest(
                service=parts[1],
                env=parts[2],
                image_tag=parts[3],
                requested_by=from_user,
            )
        )
        msg = res.message
        if res.request_id:
            msg += f" | request_id={res.request_id}"
        return {"type": "message", "text": msg}

    if cmd == "approve" and len(parts) >= 2:
        res = await handle_approve(parts[1], from_user)
        return {"type": "message", "text": res.message}

    res = await handle_chat(from_user, text)
    return {"type": "message", "text": res.message}
