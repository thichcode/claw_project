import sqlite3
from pathlib import Path

from .config import settings


def get_conn() -> sqlite3.Connection:
    db_path = Path(settings.app_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            request_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0,
            approved_by TEXT,
            executed INTEGER NOT NULL DEFAULT 0,
            execution_result_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            executed_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Lightweight migrations for existing MVP databases.
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(approvals)").fetchall()}
    if "executed" not in existing_cols:
        cur.execute("ALTER TABLE approvals ADD COLUMN executed INTEGER NOT NULL DEFAULT 0")
    if "execution_result_json" not in existing_cols:
        cur.execute("ALTER TABLE approvals ADD COLUMN execution_result_json TEXT")
    if "executed_at" not in existing_cols:
        cur.execute("ALTER TABLE approvals ADD COLUMN executed_at TEXT")

    conn.commit()
    conn.close()
