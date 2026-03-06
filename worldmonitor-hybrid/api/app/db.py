import os
import re
import sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # allow sqlite-only dev mode without psycopg2 installed
    psycopg2 = None
    RealDictCursor = None


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wm:wm@localhost:5432/worldmonitor")
IS_SQLITE = DATABASE_URL.startswith("sqlite:///")
SQLITE_PATH = DATABASE_URL.replace("sqlite:///", "", 1) if IS_SQLITE else None


def _normalize_sql(sql: str):
    if not IS_SQLITE:
        return sql
    s = sql
    s = s.replace("%s", "?")
    s = re.sub(r"::\s*jsonb", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
    return s


def _bootstrap_sqlite(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT DEFAULT 'operator',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS services (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          environment TEXT DEFAULT 'prod',
          owner TEXT,
          source_key TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS locations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          level TEXT NOT NULL CHECK(level IN ('site','region','zone')),
          parent_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS service_locations (
          service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
          location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
          is_primary INTEGER DEFAULT 0,
          PRIMARY KEY(service_id, location_id)
        );

        CREATE TABLE IF NOT EXISTS alert_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          fingerprint TEXT,
          service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
          location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
          severity TEXT DEFAULT 'warning',
          title TEXT NOT NULL,
          payload TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'open',
          acked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
          acked_note TEXT,
          acked_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS incidents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          severity TEXT DEFAULT 'medium',
          service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
          location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
          status TEXT NOT NULL DEFAULT 'open',
          assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
          resolved_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS incident_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          payload TEXT NOT NULL DEFAULT '{}',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          action TEXT NOT NULL,
          resource_type TEXT,
          resource_id TEXT,
          details TEXT NOT NULL DEFAULT '{}',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS service_dependencies (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          from_service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
          to_service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
          dependency_type TEXT NOT NULL DEFAULT 'runtime_call',
          criticality TEXT NOT NULL DEFAULT 'medium',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(from_service_id, to_service_id)
        );

        CREATE TABLE IF NOT EXISTS incident_hypotheses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          hypothesis TEXT NOT NULL,
          confidence REAL NOT NULL,
          rank INTEGER NOT NULL,
          evidence TEXT NOT NULL DEFAULT '{}',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS incident_timeline (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          event_time TEXT NOT NULL,
          event_type TEXT NOT NULL,
          title TEXT NOT NULL,
          details TEXT NOT NULL DEFAULT '{}',
          source TEXT,
          actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        );
        """
    )

    # lightweight forward-compat for existing sqlite files
    for ddl in (
        "ALTER TABLE services ADD COLUMN source_key TEXT",
        "ALTER TABLE alert_events ADD COLUMN location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL",
        "ALTER TABLE incidents ADD COLUMN location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            pass


def get_conn():
    if IS_SQLITE:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        _bootstrap_sqlite(conn)
        return conn
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is required for PostgreSQL DATABASE_URL")
    return psycopg2.connect(DATABASE_URL)


def query_all(sql: str, params=None):
    sql = _normalize_sql(sql)
    with get_conn() as conn:
        if IS_SQLITE:
            cur = conn.execute(sql, params or ())
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql: str, params=None):
    sql = _normalize_sql(sql)
    with get_conn() as conn:
        if IS_SQLITE:
            cur = conn.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def execute(sql: str, params=None):
    sql = _normalize_sql(sql)
    with get_conn() as conn:
        if IS_SQLITE:
            cur = conn.execute(sql, params or ())
            row = None
            if cur.description:
                fetched = cur.fetchone()
                row = dict(fetched) if fetched else None
            conn.commit()
            return row
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if cur.description:
                return cur.fetchone()
            return None
