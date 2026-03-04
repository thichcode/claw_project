import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .db import execute, query_all, query_one


JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")

app = FastAPI(title="WorldMonitor API", version="0.1.0")


class LoginRequest(BaseModel):
    username: str
    password: str


class AckRequest(BaseModel):
    ack_note: Optional[str] = None


class IncidentCreate(BaseModel):
    title: str
    severity: str = "medium"
    service_id: Optional[int] = None


class IncidentAssign(BaseModel):
    assignee_id: int


class IncidentAck(BaseModel):
    ack_note: Optional[str] = None


class IncidentComment(BaseModel):
    comment: str


class IngestEvent(BaseModel):
    source: Optional[str] = None
    fingerprint: Optional[str] = None
    service_name: Optional[str] = None
    severity: Optional[str] = "warning"
    title: Optional[str] = "Incoming alert"
    payload: dict = Field(default_factory=dict)


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


def save_ingest(source: str, event: IngestEvent):
    service = query_one(
        "SELECT id FROM services WHERE name = %s LIMIT 1", (event.service_name or "unknown",)
    )
    service_id = service["id"] if service else None

    row = execute(
        """
        INSERT INTO alert_events(source, fingerprint, service_id, severity, title, payload, status)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'open')
        RETURNING id, source, severity, title, status, created_at
        """,
        (
            source,
            event.fingerprint or f"{source}-{datetime.now().timestamp()}",
            service_id,
            event.severity,
            event.title,
            json.dumps(event.payload),
        ),
    )
    return row


@app.post("/ingest/zabbix")
def ingest_zabbix(body: IngestEvent):
    return {"ok": True, "event": save_ingest("zabbix", body)}


@app.post("/ingest/alertmanager")
def ingest_alertmanager(body: IngestEvent):
    return {"ok": True, "event": save_ingest("alertmanager", body)}


@app.post("/ingest/uptimerobot")
def ingest_uptimerobot(body: IngestEvent):
    return {"ok": True, "event": save_ingest("uptimerobot", body)}


@app.get("/alerts")
def list_alerts(status: Optional[str] = None, _: dict = Depends(auth_user)):
    if status:
        return query_all(
            """
            SELECT a.id, a.source, a.severity, a.title, a.status, a.created_at, s.name as service_name
            FROM alert_events a
            LEFT JOIN services s ON s.id = a.service_id
            WHERE a.status = %s
            ORDER BY a.created_at DESC
            """,
            (status,),
        )
    return query_all(
        """
        SELECT a.id, a.source, a.severity, a.title, a.status, a.created_at, s.name as service_name
        FROM alert_events a
        LEFT JOIN services s ON s.id = a.service_id
        ORDER BY a.created_at DESC
        LIMIT 200
        """
    )


@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, body: AckRequest, user=Depends(auth_user)):
    row = execute(
        """
        UPDATE alert_events
        SET status = 'acked', acked_by = %s, acked_note = %s, acked_at = NOW(), updated_at = NOW()
        WHERE id = %s
        RETURNING id, status, acked_at
        """,
        (user["id"], body.ack_note, alert_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return row


@app.post("/incidents")
def create_incident(body: IncidentCreate, user=Depends(auth_user)):
    row = execute(
        """
        INSERT INTO incidents(title, severity, service_id, status, created_by)
        VALUES (%s, %s, %s, 'open', %s)
        RETURNING id, title, severity, status, created_at
        """,
        (body.title, body.severity, body.service_id, user["id"]),
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
def list_incidents(_: dict = Depends(auth_user)):
    return query_all(
        """
        SELECT i.id, i.title, i.severity, i.status, i.assignee_id, i.created_at, s.name as service_name
        FROM incidents i
        LEFT JOIN services s ON s.id = i.service_id
        ORDER BY i.created_at DESC
        LIMIT 200
        """
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
    row = execute(
        """
        UPDATE incidents SET status = 'acked', updated_at = NOW()
        WHERE id = %s
        RETURNING id, status, updated_at
        """,
        (incident_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
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
    row = execute(
        """
        UPDATE incidents SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
        WHERE id = %s
        RETURNING id, status, resolved_at
        """,
        (incident_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    execute(
        """
        INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
        VALUES (%s, 'resolved', %s, %s::jsonb)
        """,
        (incident_id, user["id"], '{"message":"incident resolved"}'),
    )
    return row


@app.get("/summary")
def summary(_: dict = Depends(auth_user)):
    data = {
        "open_alerts": query_one("SELECT COUNT(*)::int as c FROM alert_events WHERE status = 'open'")["c"],
        "acked_alerts": query_one("SELECT COUNT(*)::int as c FROM alert_events WHERE status = 'acked'")["c"],
        "open_incidents": query_one("SELECT COUNT(*)::int as c FROM incidents WHERE status = 'open'")["c"],
        "resolved_incidents": query_one("SELECT COUNT(*)::int as c FROM incidents WHERE status = 'resolved'")["c"],
    }
    return data
