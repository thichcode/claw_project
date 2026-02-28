import httpx

from ..config import settings


async def trigger_pipeline(project_id: str, branch: str) -> dict:
    if not settings.gitlab_base_url or not settings.gitlab_token:
        return {"ok": False, "message": "GitLab is not configured"}

    # MVP note: replace endpoint with project trigger token flow if needed.
    url = f"{settings.gitlab_base_url}/api/v4/projects/{project_id}/pipelines"
    headers = {"PRIVATE-TOKEN": settings.gitlab_token}
    data = {"ref": branch}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, data=data)
        if r.status_code >= 300:
            return {"ok": False, "message": f"GitLab error {r.status_code}: {r.text[:300]}"}
        return {"ok": True, "message": "Pipeline triggered", "data": r.json()}
