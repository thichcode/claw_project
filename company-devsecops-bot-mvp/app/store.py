import json
import uuid

from .db import get_conn


def _payload_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def create_approval(action_type: str, payload: dict, requested_by: str) -> str:
    request_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO approvals(request_id, action_type, payload_json, requested_by) VALUES (?, ?, ?, ?)",
        (request_id, action_type, _payload_json(payload), requested_by),
    )
    conn.commit()
    conn.close()
    return request_id


def find_recent_pending_request(action_type: str, payload: dict, requested_by: str, within_minutes: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM approvals
        WHERE action_type = ?
          AND payload_json = ?
          AND requested_by = ?
          AND approved = 0
          AND created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (action_type, _payload_json(payload), requested_by, f"-{within_minutes} minutes"),
    )
    row = cur.fetchone()
    conn.close()
    return row


def approve_request(request_id: str, approver: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE approvals
        SET approved = 1, approved_by = ?, approved_at = CURRENT_TIMESTAMP
        WHERE request_id = ?
        """,
        (approver, request_id),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def mark_executed(request_id: str, result: dict) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE approvals
        SET executed = 1,
            execution_result_json = ?,
            executed_at = CURRENT_TIMESTAMP
        WHERE request_id = ? AND executed = 0
        """,
        (json.dumps(result, ensure_ascii=False), request_id),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_request(request_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,))
    row = cur.fetchone()
    conn.close()
    return row


def list_recent_approvals(
    limit: int = 50,
    approved: bool | None = None,
    executed: bool | None = None,
    requested_by: str | None = None,
    action_type: str | None = None,
):
    conn = get_conn()
    cur = conn.cursor()

    where = []
    params = []
    if approved is not None:
        where.append("approved = ?")
        params.append(1 if approved else 0)
    if executed is not None:
        where.append("executed = ?")
        params.append(1 if executed else 0)
    if requested_by:
        where.append("requested_by = ?")
        params.append(requested_by)
    if action_type:
        where.append("action_type = ?")
        params.append(action_type)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT request_id, action_type, payload_json, requested_by, approved, approved_by,
               executed, execution_result_json, created_at, approved_at, executed_at
        FROM approvals
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
    """
    params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def list_recent_audit(
    limit: int = 100,
    actor: str | None = None,
    action: str | None = None,
):
    conn = get_conn()
    cur = conn.cursor()

    where = []
    params = []
    if actor:
        where.append("actor = ?")
        params.append(actor)
    if action:
        where.append("action = ?")
        params.append(action)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id, actor, action, details, created_at
        FROM audit_logs
        {where_sql}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows
