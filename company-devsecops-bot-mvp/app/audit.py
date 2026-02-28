import json

from .db import get_conn


def write_audit(actor: str, action: str, details: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_logs(actor, action, details) VALUES (?, ?, ?)",
        (actor, action, json.dumps(details, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
