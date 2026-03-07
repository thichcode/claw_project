import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from .db import execute, query_all, query_one


JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")

app = FastAPI(title="WorldMonitor API", version="0.1.0")

ALLOWED_SEVERITIES = {"critical", "high", "medium", "warning", "low", "error", "disaster", "p1", "p2", "p3", "info", "ok"}
ALLOWED_ALERT_STATUSES = {"open", "acked"}


def normalize_severity(value: Optional[str], default: str = "warning") -> str:
    normalized = str(value or default).strip().lower()
    if normalized not in ALLOWED_SEVERITIES:
        allowed = ", ".join(sorted(ALLOWED_SEVERITIES))
        raise ValueError(f"Invalid severity '{value}'. Allowed values: {allowed}")
    return normalized


def normalize_alert_status(value: Optional[str], default: str = "open") -> str:
    normalized = str(value or default).strip().lower()
    if normalized not in ALLOWED_ALERT_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_ALERT_STATUSES))
        raise ValueError(f"Invalid alert status '{value}'. Allowed values: {allowed}")
    return normalized


class LoginRequest(BaseModel):
    username: str
    password: str


class AckRequest(BaseModel):
    ack_note: Optional[str] = None


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    severity: str = "medium"
    service_id: Optional[int] = None
    location_code: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str):
        return normalize_severity(value, default="medium")


class IncidentAssign(BaseModel):
    assignee_id: int


class IncidentAck(BaseModel):
    ack_note: Optional[str] = None


class IncidentComment(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("comment must not be blank")
        return normalized


class IngestEvent(BaseModel):
    source: Optional[str] = None
    fingerprint: Optional[str] = None
    service_name: Optional[str] = None
    severity: Optional[str] = "warning"
    status: Optional[str] = "open"
    title: Optional[str] = "Incoming alert"
    location_code: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    payload: dict = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: Optional[str]):
        return normalize_severity(value, default="warning")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]):
        return normalize_alert_status(value, default="open")


class TopologyNode(BaseModel):
    service_id: int
    name: str
    environment: str = "prod"
    health: str = "unknown"
    meta: Optional[str] = None
    open_alerts: int = 0
    open_incidents: int = 0


class TopologyEdge(BaseModel):
    from_service_id: int
    to_service_id: int
    relation: str = "depends_on"
    criticality: str = "medium"


class TopologyKPI(BaseModel):
    affected_services: int = 0
    critical_edges: int = 0
    blast_radius: str = "Low"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sign_token(user_id: int, username: str):
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def auth_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return {"id": int(payload["sub"]), "username": payload["username"]}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "time": now_iso()}


@app.get("/readyz")
def readyz():
    try:
        row = query_one("SELECT 1 as ok")
        return {"status": "ready", "db": bool(row and row["ok"] == 1)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"not ready: {e}")


@app.post("/auth/login")
def login(body: LoginRequest):
    user = query_one(
        "SELECT id, username, password_hash FROM users WHERE username = %s",
        (body.username,),
    )
    if not user or user["password_hash"] != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = sign_token(user["id"], user["username"])
    return {"access_token": token, "token_type": "bearer"}


def pick_first(data: dict, *keys):
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return None


def normalize_source_severity(value: Optional[str], source: str, default: str = "warning") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return normalize_severity(default, default=default)

    # numeric severities (e.g. Zabbix priority 0..5)
    if raw.isdigit():
        num = int(raw)
        if source == "zabbix":
            if num >= 4:
                return "critical"
            if num == 3:
                return "high"
            if num == 2:
                return "medium"
            if num == 1:
                return "warning"
            return "info"

    aliases = {
        "disaster": "critical",
        "average": "medium",
        "warn": "warning",
        "information": "info",
        "not classified": "info",
        "ok": "ok",
        "resolved": "info",
        "up": "info",
        "down": "critical",
    }
    mapped = aliases.get(raw, raw)
    return normalize_severity(mapped, default=default)


def normalize_event_state(value: Optional[str], default: str = "open") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return normalize_alert_status(default, default=default)

    if raw in {"0", "ok", "up", "resolved", "recovered", "false", "close", "closed"}:
        return "acked"
    if raw in {"1", "problem", "down", "alert", "open", "true", "firing"}:
        return "open"
    return normalize_alert_status(default, default=default)


async def parse_ingest_payload(request: Request) -> dict:
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if isinstance(payload, dict):
            return payload
        return {"payload": payload}

    raw_body = (await request.body()).decode("utf-8", errors="ignore").strip()
    if not raw_body:
        return {}

    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(raw_body, keep_blank_values=False)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    # Last resort: try JSON even if content-type is wrong
    try:
        payload = json.loads(raw_body)
        if isinstance(payload, dict):
            return payload
        return {"payload": payload}
    except Exception:
        return {"payload": {"raw": raw_body}}


def event_from_zabbix_payload(payload: dict) -> IngestEvent:
    state = normalize_event_state(
        pick_first(payload, "event_status", "status", "value", "event_value", "trigger_value"),
        default="open",
    )
    severity = normalize_source_severity(
        pick_first(payload, "severity", "event_severity", "trigger_severity", "priority"),
        source="zabbix",
        default="warning",
    )
    title = (
        pick_first(payload, "title", "subject", "alert_subject", "trigger_name", "name", "message")
        or "Zabbix alert"
    )
    service_name = pick_first(payload, "service_name", "host", "host_name", "hostname") or "zabbix-host"
    fingerprint = pick_first(payload, "fingerprint", "event_id", "eventid", "problem_id", "triggerid")

    return IngestEvent(
        source="zabbix",
        fingerprint=str(fingerprint) if fingerprint is not None else None,
        service_name=str(service_name),
        severity=severity,
        status=state,
        title=str(title),
        location_code=pick_first(payload, "location_code", "location", "site", "dc", "datacenter"),
        region=pick_first(payload, "region"),
        zone=pick_first(payload, "zone"),
        payload=payload,
    )


def event_from_uptimerobot_payload(payload: dict) -> IngestEvent:
    alert_type_raw = pick_first(payload, "alert_type", "alertType", "status")
    state = normalize_event_state(alert_type_raw, default="open")

    severity_hint = pick_first(payload, "severity")
    if severity_hint is not None:
        severity = normalize_source_severity(severity_hint, source="uptimerobot", default="warning")
    else:
        severity = "critical" if state == "open" else "info"

    monitor_name = (
        pick_first(payload, "service_name", "friendly_name", "monitor_friendly_name", "monitor_name")
        or "uptimerobot-monitor"
    )
    monitor_url = pick_first(payload, "monitor_url", "url", "monitorURL")
    if not pick_first(payload, "service_name") and monitor_url:
        try:
            monitor_name = urlparse(str(monitor_url)).hostname or monitor_name
        except Exception:
            pass

    fingerprint = pick_first(payload, "fingerprint", "alert_id", "id")
    if fingerprint is None:
        monitor_id = pick_first(payload, "monitor_id", "monitorID")
        if monitor_id is not None:
            fingerprint = f"uptimerobot:{monitor_id}:{alert_type_raw or state}"

    title = pick_first(payload, "title")
    if not title:
        title = (
            f"UptimeRobot: {monitor_name} DOWN"
            if state == "open"
            else f"UptimeRobot: {monitor_name} RECOVERED"
        )

    return IngestEvent(
        source="uptimerobot",
        fingerprint=str(fingerprint) if fingerprint is not None else None,
        service_name=str(monitor_name),
        severity=severity,
        status=state,
        title=str(title),
        location_code=pick_first(payload, "location_code", "location"),
        region=pick_first(payload, "region"),
        zone=pick_first(payload, "zone"),
        payload=payload,
    )


def resolve_location(event: IngestEvent):
    loc_code = (event.location_code or event.zone or event.region or "global").strip().lower().replace(" ", "-")
    if not loc_code:
        return None

    level = "site"
    if event.zone:
        level = "zone"
    elif event.region:
        level = "region"

    found = query_one("SELECT id FROM locations WHERE code = %s", (loc_code,))
    if found:
        return found["id"]

    created = execute(
        """
        INSERT INTO locations(code, name, level)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (loc_code, (event.location_code or event.zone or event.region or "Global").strip(), level),
    )
    return created["id"] if created else None


def resolve_service(source: str, event: IngestEvent):
    svc_name = (event.service_name or "unknown-service").strip() or "unknown-service"
    source_key = f"{source}:{svc_name.lower()}"

    # Avoid duplicate services when upstream sources send inconsistent casing
    # (e.g. "API-Gateway" vs "api-gateway").
    existing = query_one("SELECT id FROM services WHERE LOWER(name) = LOWER(%s) LIMIT 1", (svc_name,))
    if existing:
        execute("UPDATE services SET source_key = COALESCE(source_key, %s) WHERE id = %s", (source_key, existing["id"]))
        return existing["id"]

    created = execute(
        """
        INSERT INTO services(name, environment, owner, source_key)
        VALUES (%s, 'prod', 'unknown', %s)
        RETURNING id
        """,
        (svc_name, source_key),
    )
    return created["id"] if created else None


def save_ingest(source: str, event: IngestEvent):
    service_id = resolve_service(source, event)
    location_id = resolve_location(event)

    if service_id and location_id:
        execute(
            """
            INSERT INTO service_locations(service_id, location_id, is_primary)
            VALUES (%s, %s, %s)
            ON CONFLICT (service_id, location_id) DO NOTHING
            """,
            (service_id, location_id, True),
        )

    row = execute(
        """
        INSERT INTO alert_events(source, fingerprint, service_id, location_id, severity, title, payload, status, acked_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, CASE WHEN %s = 'acked' THEN NOW() ELSE NULL END)
        RETURNING id, source, severity, title, status, created_at
        """,
        (
            source,
            event.fingerprint or f"{source}-{datetime.now().timestamp()}",
            service_id,
            location_id,
            event.severity,
            event.title,
            json.dumps(event.payload),
            event.status or "open",
            event.status or "open",
        ),
    )
    return row


def severity_to_rank(sev: Optional[str]):
    key = str(sev or "").lower()
    if key in ("critical", "disaster", "p1"):
        return 3
    if key in ("high", "error", "p2"):
        return 2
    if key in ("warning", "medium", "warn", "p3"):
        return 1
    return 0


def rank_to_health(rank: int):
    if rank >= 2:
        return "critical"
    if rank == 1:
        return "warning"
    return "healthy"


def derive_health(open_alerts: int, open_incidents: int, alert_rank: int = 0, incident_rank: int = 0):
    base = max(int(alert_rank or 0), int(incident_rank or 0))
    if base > 0:
        return rank_to_health(base)
    if open_incidents > 0:
        return "critical"
    if open_alerts > 0:
        return "warning"
    return "healthy"


def compute_blast_radius(affected_services: int):
    if affected_services >= 10:
        return "High"
    if affected_services >= 4:
        return "Medium"
    return "Low"


def normalize_optional_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def normalize_env(value: Optional[str], default: str = "prod") -> str:
    normalized = str(value or "").strip().lower()
    return normalized or default


@app.post("/ingest/zabbix")
async def ingest_zabbix(request: Request):
    payload = await parse_ingest_payload(request)
    try:
        try:
            event = IngestEvent.model_validate(payload)
            event.source = "zabbix"
        except ValidationError:
            event = event_from_zabbix_payload(payload)
        return {"ok": True, "event": save_ingest("zabbix", event)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/ingest/alertmanager")
async def ingest_alertmanager(request: Request):
    payload = await parse_ingest_payload(request)
    try:
        event = IngestEvent.model_validate(payload)
        event.source = "alertmanager"
        return {"ok": True, "event": save_ingest("alertmanager", event)}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/ingest/uptimerobot")
async def ingest_uptimerobot(request: Request):
    payload = await parse_ingest_payload(request)
    try:
        try:
            event = IngestEvent.model_validate(payload)
            event.source = "uptimerobot"
        except ValidationError:
            event = event_from_uptimerobot_payload(payload)
        return {"ok": True, "event": save_ingest("uptimerobot", event)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/alerts")
def list_alerts(status: Optional[str] = None, location_code: Optional[str] = None, _: dict = Depends(auth_user)):
    filters = []
    params = []

    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status:
            try:
                normalized_status = normalize_alert_status(normalized_status)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            filters.append("a.status = %s")
            params.append(normalized_status)

    normalized_location_code = normalize_optional_code(location_code)
    if normalized_location_code:
        filters.append("LOWER(COALESCE(l.code, '')) = %s")
        params.append(normalized_location_code)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    return query_all(
        f"""
        SELECT a.id, a.source, a.severity, a.title, a.status, a.created_at, s.name as service_name, l.code as location_code
        FROM alert_events a
        LEFT JOIN services s ON s.id = a.service_id
        LEFT JOIN locations l ON l.id = a.location_id
        {where_clause}
        ORDER BY a.created_at DESC
        LIMIT 200
        """,
        tuple(params),
    )


@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, body: AckRequest, user=Depends(auth_user)):
    alert = query_one("SELECT id, status, acked_at FROM alert_events WHERE id = %s", (alert_id,))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    current_status = str(alert.get("status") or "").lower()
    if current_status == "acked":
        return alert
    if current_status != "open":
        raise HTTPException(status_code=409, detail="Alert is not in open state")

    row = execute(
        """
        UPDATE alert_events
        SET status = 'acked', acked_by = %s, acked_note = %s, acked_at = NOW(), updated_at = NOW()
        WHERE id = %s AND status = 'open'
        RETURNING id, status, acked_at
        """,
        (user["id"], body.ack_note, alert_id),
    )
    if not row:
        raise HTTPException(status_code=409, detail="Alert is not in open state")
    return row


@app.post("/incidents")
def create_incident(body: IncidentCreate, user=Depends(auth_user)):
    if body.service_id is not None:
        service = query_one("SELECT id FROM services WHERE id = %s", (body.service_id,))
        if not service:
            raise HTTPException(status_code=422, detail="Invalid service_id")

    location_id = None
    if body.location_code:
        lc = body.location_code.strip().lower().replace(" ", "-")
        row_loc = query_one("SELECT id FROM locations WHERE code = %s", (lc,))
        if row_loc:
            location_id = row_loc["id"]
        else:
            created = execute(
                "INSERT INTO locations(code, name, level) VALUES (%s, %s, 'site') RETURNING id",
                (lc, body.location_code.strip()),
            )
            location_id = created["id"] if created else None

    row = execute(
        """
        INSERT INTO incidents(title, severity, service_id, location_id, status, created_by)
        VALUES (%s, %s, %s, %s, 'open', %s)
        RETURNING id, title, severity, status, created_at
        """,
        (body.title, body.severity, body.service_id, location_id, user["id"]),
    )
    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'created', %s, %s::jsonb)
        """,
        (row["id"], user["id"], '{"message":"incident created"}'),
    )
    return row


@app.get("/incidents")
def list_incidents(location_code: Optional[str] = None, _: dict = Depends(auth_user)):
    filters = []
    params = []

    normalized_location_code = normalize_optional_code(location_code)
    if normalized_location_code:
        filters.append("LOWER(COALESCE(l.code, '')) = %s")
        params.append(normalized_location_code)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    return query_all(
        f"""
        SELECT i.id, i.title, i.severity, i.status, i.assignee_id, i.created_at, s.name as service_name, l.code as location_code
        FROM incidents i
        LEFT JOIN services s ON s.id = i.service_id
        LEFT JOIN locations l ON l.id = i.location_id
        {where_clause}
        ORDER BY i.created_at DESC
        LIMIT 200
        """,
        tuple(params),
    )


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: int, _: dict = Depends(auth_user)):
    incident = query_one("SELECT * FROM incidents WHERE id = %s", (incident_id,))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    events = query_all(
        "SELECT id, event_type, actor_id, payload, created_at FROM incident_events WHERE incident_id = %s ORDER BY created_at ASC",
        (incident_id,),
    )
    return {"incident": incident, "events": events}


@app.post("/incidents/{incident_id}/ack")
def ack_incident(incident_id: int, body: IncidentAck, user=Depends(auth_user)):
    incident = query_one("SELECT id, status, updated_at FROM incidents WHERE id = %s", (incident_id,))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    current_status = str(incident.get("status") or "").lower()
    if current_status == "resolved":
        raise HTTPException(status_code=409, detail="Resolved incident cannot be acknowledged")

    if current_status == "acked":
        return incident

    row = execute(
        """
        UPDATE incidents SET status = 'acked', updated_at = NOW()
        WHERE id = %s AND status = 'open'
        RETURNING id, status, updated_at
        """,
        (incident_id,),
    )
    if not row:
        raise HTTPException(status_code=409, detail="Incident is not in open state")

    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'acked', %s, %s::jsonb)
        """,
        (incident_id, user["id"], json.dumps({"ack_note": body.ack_note or "acknowledged"})),
    )
    return row


@app.post("/incidents/{incident_id}/assign")
def assign_incident(incident_id: int, body: IncidentAssign, user=Depends(auth_user)):
    row = execute(
        """
        UPDATE incidents SET assignee_id = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id, assignee_id, status
        """,
        (body.assignee_id, incident_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'assigned', %s, %s::jsonb)
        """,
        (incident_id, user["id"], f'{{"assignee_id": {body.assignee_id}}}'),
    )
    return row


@app.post("/incidents/{incident_id}/comment")
def comment_incident(incident_id: int, body: IncidentComment, user=Depends(auth_user)):
    incident = query_one("SELECT id FROM incidents WHERE id = %s", (incident_id,))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'commented', %s, %s::jsonb)
        """,
        (incident_id, user["id"], json.dumps({"comment": body.comment})),
    )
    return {"ok": True}


@app.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, user=Depends(auth_user)):
    incident = query_one("SELECT id, status, resolved_at FROM incidents WHERE id = %s", (incident_id,))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    current_status = str(incident.get("status") or "").lower()
    if current_status == "resolved":
        return incident
    if current_status not in {"open", "acked"}:
        raise HTTPException(status_code=409, detail="Incident cannot be resolved from current state")

    row = execute(
        """
        UPDATE incidents SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
        WHERE id = %s AND status IN ('open', 'acked')
        RETURNING id, status, resolved_at
        """,
        (incident_id,),
    )
    if not row:
        raise HTTPException(status_code=409, detail="Incident cannot be resolved from current state")

    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'resolved', %s, %s::jsonb)
        """,
        (incident_id, user["id"], '{"message":"incident resolved"}'),
    )
    return row


@app.get("/topology")
def topology(env: Optional[str] = "prod", location_code: Optional[str] = None, _: dict = Depends(auth_user)):
    env_value = normalize_env(env, default="prod")
    normalized_location_code = normalize_optional_code(location_code)

    try:
        if normalized_location_code:
            nodes = query_all(
                """
                SELECT
                    s.id as service_id,
                    s.name,
                    s.environment,
                    s.owner,
                    l.code as location_code,
                    COALESCE(a.open_alerts, 0) as open_alerts,
                    COALESCE(a.alert_rank, 0) as alert_rank,
                    COALESCE(i.open_incidents, 0) as open_incidents,
                    COALESCE(i.incident_rank, 0) as incident_rank
                FROM services s
                LEFT JOIN service_locations sl ON sl.service_id = s.id
                LEFT JOIN locations l ON l.id = sl.location_id
                LEFT JOIN (
                    SELECT service_id, COUNT(*) as open_alerts,
                    MAX(CASE
                        WHEN LOWER(COALESCE(severity, '')) IN ('critical','disaster','p1') THEN 3
                        WHEN LOWER(COALESCE(severity, '')) IN ('high','error','p2') THEN 2
                        WHEN LOWER(COALESCE(severity, '')) IN ('warning','medium','warn','p3') THEN 1
                        ELSE 0 END) as alert_rank
                    FROM alert_events WHERE status = 'open' GROUP BY service_id
                ) a ON a.service_id = s.id
                LEFT JOIN (
                    SELECT service_id, COUNT(*) as open_incidents,
                    MAX(CASE
                        WHEN LOWER(COALESCE(severity, '')) IN ('critical','disaster','p1') THEN 3
                        WHEN LOWER(COALESCE(severity, '')) IN ('high','error','p2') THEN 2
                        WHEN LOWER(COALESCE(severity, '')) IN ('warning','medium','warn','p3') THEN 1
                        ELSE 2 END) as incident_rank
                    FROM incidents WHERE status IN ('open', 'acked') GROUP BY service_id
                ) i ON i.service_id = s.id
                WHERE s.environment = %s AND LOWER(COALESCE(l.code, '')) = %s
                ORDER BY s.name ASC
                """,
                (env_value, normalized_location_code),
            )
        else:
            nodes = query_all(
                """
                SELECT
                    s.id as service_id,
                    s.name,
                    s.environment,
                    s.owner,
                    COALESCE(a.open_alerts, 0) as open_alerts,
                    COALESCE(a.alert_rank, 0) as alert_rank,
                    COALESCE(i.open_incidents, 0) as open_incidents,
                    COALESCE(i.incident_rank, 0) as incident_rank
                FROM services s
                LEFT JOIN (
                    SELECT service_id, COUNT(*) as open_alerts,
                    MAX(CASE
                        WHEN LOWER(COALESCE(severity, '')) IN ('critical','disaster','p1') THEN 3
                        WHEN LOWER(COALESCE(severity, '')) IN ('high','error','p2') THEN 2
                        WHEN LOWER(COALESCE(severity, '')) IN ('warning','medium','warn','p3') THEN 1
                        ELSE 0 END) as alert_rank
                    FROM alert_events WHERE status = 'open' GROUP BY service_id
                ) a ON a.service_id = s.id
                LEFT JOIN (
                    SELECT service_id, COUNT(*) as open_incidents,
                    MAX(CASE
                        WHEN LOWER(COALESCE(severity, '')) IN ('critical','disaster','p1') THEN 3
                        WHEN LOWER(COALESCE(severity, '')) IN ('high','error','p2') THEN 2
                        WHEN LOWER(COALESCE(severity, '')) IN ('warning','medium','warn','p3') THEN 1
                        ELSE 2 END) as incident_rank
                    FROM incidents WHERE status IN ('open', 'acked') GROUP BY service_id
                ) i ON i.service_id = s.id
                WHERE s.environment = %s
                ORDER BY s.name ASC
                """,
                (env_value,),
            )
    except Exception:
        nodes = []

    try:
        edges = query_all(
            """
            SELECT from_service_id, to_service_id, dependency_type, criticality
            FROM service_dependencies
            ORDER BY id ASC
            """
        )
    except Exception:
        edges = []

    base_nodes = [
        TopologyNode(
            service_id=n["service_id"],
            name=n["name"],
            environment=n.get("environment") or "prod",
            health=derive_health(
                n.get("open_alerts", 0),
                n.get("open_incidents", 0),
                n.get("alert_rank", 0),
                n.get("incident_rank", 0),
            ),
            meta=(
                f"owner: {n.get('owner') or 'unknown'}"
                + (f" | location: {n.get('location_code')}" if n.get("location_code") else "")
            ),
            open_alerts=n.get("open_alerts", 0),
            open_incidents=n.get("open_incidents", 0),
        ).model_dump()
        for n in nodes
    ]

    normalized_edges = [
        TopologyEdge(
            from_service_id=e["from_service_id"],
            to_service_id=e["to_service_id"],
            relation=e.get("dependency_type") or "depends_on",
            criticality=e.get("criticality") or "medium",
        ).model_dump()
        for e in edges
    ]

    node_map = {n["service_id"]: dict(n) for n in base_nodes}
    impacted_by = {n["service_id"]: set() for n in base_nodes}

    criticality_weight = {"critical": 2, "high": 2, "medium": 1, "low": 1}
    propagate_relations = {"runtime_call", "data_store", "cache_layer", "traffic_route", "depends_on"}

    for _ in range(4):
        changed = False
        for e in normalized_edges:
            from_id = e["from_service_id"]
            to_id = e["to_service_id"]
            if from_id not in node_map or to_id not in node_map:
                continue

            relation = str(e.get("relation") or "depends_on").lower()
            if relation not in propagate_relations:
                continue

            dep_rank = severity_to_rank(node_map[to_id]["health"])
            svc_rank = severity_to_rank(node_map[from_id]["health"])
            edge_w = criticality_weight.get(str(e.get("criticality") or "medium").lower(), 1)

            target_rank = svc_rank
            if dep_rank >= 2:
                target_rank = max(target_rank, 2 if edge_w >= 2 else 1)
            elif dep_rank == 1:
                target_rank = max(target_rank, 1)

            if target_rank > svc_rank:
                node_map[from_id]["health"] = rank_to_health(target_rank)
                impacted_by[from_id].add(node_map[to_id]["name"])
                changed = True

        if not changed:
            break

    normalized_nodes = []
    for sid, n in node_map.items():
        deps = sorted(list(impacted_by.get(sid, set())))
        if deps:
            n["meta"] = f"{n.get('meta', '')} | impacted by: {', '.join(deps[:2])}{'...' if len(deps) > 2 else ''}"
        normalized_nodes.append(n)

    normalized_nodes.sort(key=lambda x: x.get("name", ""))

    affected_services = len([n for n in normalized_nodes if n["health"] != "healthy"])
    critical_edges = len([e for e in normalized_edges if e["criticality"] in ("high", "critical")])
    return {
        "generated_at": now_iso(),
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "kpi": TopologyKPI(
            affected_services=affected_services,
            critical_edges=critical_edges,
            blast_radius=compute_blast_radius(affected_services),
        ).model_dump(),
    }


@app.get("/incidents/{incident_id}/rca")
def incident_rca(incident_id: int, _: dict = Depends(auth_user)):
    incident = query_one(
        """
        SELECT i.id, i.title, i.severity, i.status, i.service_id, i.created_at, s.name as service_name
        FROM incidents i
        LEFT JOIN services s ON s.id = i.service_id
        WHERE i.id = %s
        """,
        (incident_id,),
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    try:
        hypotheses = query_all(
            """
            SELECT id, hypothesis, confidence, rank, evidence, created_at
            FROM incident_hypotheses
            WHERE incident_id = %s
            ORDER BY rank ASC
            """,
            (incident_id,),
        )
    except Exception:
        hypotheses = []

    try:
        timeline = query_all(
            """
            SELECT event_time as ts, event_type, title, source, details as payload
            FROM incident_timeline
            WHERE incident_id = %s
            ORDER BY event_time ASC
            """,
            (incident_id,),
        )
    except Exception:
        timeline = []

    impacted = []
    if incident.get("service_id"):
        try:
            impacted = query_all(
                """
                SELECT s.id as service_id, s.name, sd.criticality
                FROM service_dependencies sd
                JOIN services s ON s.id = sd.from_service_id
                WHERE sd.to_service_id = %s
                """,
                (incident["service_id"],),
            )
        except Exception:
            impacted = []

    return {
        "incident": incident,
        "summary": f"RCA for incident {incident_id}",
        "confidence": float(hypotheses[0]["confidence"]) if hypotheses else 0.0,
        "hypotheses": hypotheses,
        "timeline": timeline,
        "impacted_services": impacted,
        "generated_at": now_iso(),
    }


@app.post("/demo/reset")
def demo_reset(user=Depends(auth_user)):
    # demo-only bulk reset to make presets clearly visible
    execute(
        """
        UPDATE alert_events
        SET status='acked', acked_by=%s, acked_note='demo reset', acked_at=NOW(), updated_at=NOW()
        WHERE status='open'
        """,
        (user["id"],),
    )
    execute(
        """
        UPDATE incidents
        SET status='resolved', resolved_at=NOW(), updated_at=NOW()
        WHERE status IN ('open','acked')
        """
    )
    return {"ok": True}


@app.get("/locations")
def list_locations(_: dict = Depends(auth_user)):
    return query_all(
        """
        SELECT l.id, l.code, l.name, l.level, l.parent_id,
               COUNT(DISTINCT sl.service_id) as services
        FROM locations l
        LEFT JOIN service_locations sl ON sl.location_id = l.id
        GROUP BY l.id, l.code, l.name, l.level, l.parent_id
        ORDER BY l.level, l.code
        """
    )


@app.get("/summary")
def summary(_: dict = Depends(auth_user)):
    total_services = query_one("SELECT COUNT(*) as c FROM services")["c"]
    services_with_location = query_one(
        "SELECT COUNT(DISTINCT service_id) as c FROM service_locations"
    )["c"]
    data = {
        "open_alerts": query_one("SELECT COUNT(*) as c FROM alert_events WHERE status = 'open'")["c"],
        "acked_alerts": query_one("SELECT COUNT(*) as c FROM alert_events WHERE status = 'acked'")["c"],
        "open_incidents": query_one("SELECT COUNT(*) as c FROM incidents WHERE status = 'open'")["c"],
        "resolved_incidents": query_one("SELECT COUNT(*) as c FROM incidents WHERE status = 'resolved'")["c"],
        "total_services": total_services,
        "services_with_location": services_with_location,
        "location_coverage": round((services_with_location / total_services), 3) if total_services else 0,
    }
    return data
