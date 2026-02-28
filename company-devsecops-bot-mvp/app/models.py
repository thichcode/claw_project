from pydantic import BaseModel


class ChatRequest(BaseModel):
    user: str
    message: str


class ActionResponse(BaseModel):
    ok: bool
    message: str
    request_id: str | None = None


class ApproveRequest(BaseModel):
    request_id: str
    approver: str


class ScanRequest(BaseModel):
    project_id: str
    branch: str = "main"


class DeployRequest(BaseModel):
    service: str
    env: str
    image_tag: str
    requested_by: str
