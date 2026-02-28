# Company DevSecOps Bot MVP (OpenClaw-like, internal-only)

MVP bot nền tảng nội bộ cho DevSecOps use-cases (không dùng OpenClaw runtime), ưu tiên private-first:
- Model router: Ollama local mặc định, Azure OpenAI `gpt-5-mini` cho tác vụ nhạy cảm hơn.
- Tích hợp GitLab API trigger pipeline.
- Deploy flow có approval 2 bước (MVP).
- Audit log + approval log lưu SQLite.

## 1) Setup

```bash
cd company-devsecops-bot-mvp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Chỉnh `.env`:
- `GITLAB_BASE_URL`
- `GITLAB_TOKEN`
- Azure/Ollama config theo hạ tầng công ty

## 2) Run local

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Health:
- `GET http://localhost:8080/api/health`

## 3) API nhanh

### Chat route test
`POST /api/chat`
```json
{
  "user": "mrthuong",
  "message": "review security policy for production deploy"
}
```

### Trigger scan/pipeline
`POST /api/scan`
```json
{
  "project_id": "123",
  "branch": "main"
}
```

### Request deploy (approval required)
`POST /api/deploy`
```json
{
  "service": "payment-api",
  "env": "prod",
  "image_tag": "v1.4.2",
  "requested_by": "mrthuong"
}
```

### Approve deploy request
`POST /api/approve`
```json
{
  "request_id": "<uuid-from-deploy-response>",
  "approver": "sec-lead"
}
```

### Get approval detail
`GET /api/approvals/<request_id>`

### List approvals
`GET /api/approvals?limit=50`

Filter examples:
- `GET /api/approvals?approved=true&executed=false`
- `GET /api/approvals?requested_by=ops&action_type=deploy`

### List audit logs
`GET /api/audit?limit=100`

Filter examples:
- `GET /api/audit?action=deploy_requested`
- `GET /api/audit?actor=sec-lead&action=approved_and_executed`

## 4) GitLab CI template

Đã có `.gitlab-ci.yml` MVP với stages:
- lint
- test (placeholder)
- security (Trivy FS)
- build image

## 5) Microsoft Teams connector (MVP)

Endpoint: `POST /teams/messages`

Command hỗ trợ qua Teams text:
- `help`
- `scan <project_id> [branch]`
- `deploy <service> <env> <image_tag>`
- `approve <request_id>`

Ví dụ:
- `scan 123 main`
- `deploy payment-api prod v1.4.2`
- `approve 7d4b9a9c-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

Lưu ý: connector này là MVP parser theo payload text; ở bản production nên dùng đầy đủ Bot Framework auth/validation + AAD role mapping.

### AuthZ MVP (config qua `.env`)

- `AUTHZ_SCAN_ALLOW` (mặc định `*`)
- `AUTHZ_DEPLOY_ALLOW` (mặc định `ops,sec-lead`)
- `AUTHZ_APPROVE_ALLOW` (mặc định `sec-lead`)
- `AUTHZ_PROD_APPROVERS` (mặc định `sec-lead`)

Giá trị có thể là user ID hoặc name, cách nhau bằng dấu phẩy.

### Deploy approval behavior

- `/deploy ...` tạo request chờ duyệt (có idempotency chống gửi trùng trong 10 phút cho cùng payload/user).
- `/approve <request_id>` sẽ **approve + execute** action deploy (MVP).

## 6) Next steps (v1.1)

1. K8s thật: thay `app/tools/k8s_tool.py` bằng Kubernetes Python client + namespace RBAC cho EKS/AKS.
2. Bot Framework auth verification + Teams adaptive cards.
3. OPA/Kyverno policy decision trước deploy.
4. SBOM + Cosign + verify ở admission.
5. Thêm Postgres + Redis cho production.
