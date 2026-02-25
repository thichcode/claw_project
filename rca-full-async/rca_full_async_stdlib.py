#!/usr/bin/env python3
"""
RCA Full Async (stdlib-only):
- asyncio + threads (no extra deps)
- SQLite TTL cache
- batching with controlled concurrency
- event time extraction + correlation by ±10 minute window
- sources: Zabbix + UptimeRobot
- output: Microsoft Teams webhook
"""

import os
import json
import time
import sqlite3
import hashlib
import asyncio
import urllib.request
import urllib.parse
import argparse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# =========================
# Config (ENV)
# =========================
ZABBIX_URL = os.getenv("ZABBIX_URL", "").rstrip("/")
ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN", "")
UPTIMEROBOT_API_KEY = os.getenv("UPTIMEROBOT_API_KEY", "")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

# OpenAI-compatible LLM endpoint (optional)
LLM_URL = os.getenv("LLM_URL", "https://api.openai.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ServiceDesk Plus (v14720+) optional integration
SDP_URL = os.getenv("SDP_URL", "").rstrip("/")
SDP_TECHNICIAN_KEY = os.getenv("SDP_TECHNICIAN_KEY", "")
SDP_REQUEST_ID = os.getenv("SDP_REQUEST_ID", "")  # fallback only
SDP_TASK_TITLE = os.getenv("SDP_TASK_TITLE", "RCA investigation")
SDP_TASK_OWNER = os.getenv("SDP_TASK_OWNER", "")
SDP_RESOLUTION_PREFIX = os.getenv("SDP_RESOLUTION_PREFIX", "[AUTO RCA]")
SDP_CLOSE_STATUS = os.getenv("SDP_CLOSE_STATUS", "Closed")

LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "30"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))

# batching
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "8"))

# correlation window (±10 minutes default)
TIME_WINDOW_MINUTES = int(os.getenv("TIME_WINDOW_MINUTES", "10"))
TIME_WINDOW_SEC = TIME_WINDOW_MINUTES * 60

# cache TTL
TTL_ZABBIX_SEC = int(os.getenv("TTL_ZABBIX_SEC", "90"))
TTL_UPTIME_SEC = int(os.getenv("TTL_UPTIME_SEC", "180"))
TTL_LLM_SEC = int(os.getenv("TTL_LLM_SEC", "600"))
CACHE_DB = os.getenv("CACHE_DB", "rca_cache.db")


# =========================
# SQLite TTL Cache
# =========================
class TTLCache:
    def __init__(self, db_path: str = CACHE_DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL,
                exp INTEGER NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_exp ON cache(exp)")
        self.conn.commit()

    @staticmethod
    def make_key(prefix: str, payload: Any) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    def get(self, key: str) -> Optional[Any]:
        now = int(time.time())
        row = self.conn.execute("SELECT v, exp FROM cache WHERE k = ?", (key,)).fetchone()
        if not row:
            return None
        v, exp = row
        if exp < now:
            self.conn.execute("DELETE FROM cache WHERE k = ?", (key,))
            self.conn.commit()
            return None
        return json.loads(v)

    def set(self, key: str, value: Any, ttl_sec: int):
        exp = int(time.time()) + ttl_sec
        self.conn.execute(
            """
            INSERT INTO cache(k, v, exp) VALUES (?, ?, ?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v, exp=excluded.exp
            """,
            (key, json.dumps(value, ensure_ascii=False), exp),
        )
        self.conn.commit()

    def cleanup(self):
        self.conn.execute("DELETE FROM cache WHERE exp < ?", (int(time.time()),))
        self.conn.commit()

    def close(self):
        self.conn.close()


CACHE = TTLCache()


# =========================
# HTTP helpers (blocking)
# =========================
def http_json_request(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def http_post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return http_json_request("POST", url, payload, headers)


def http_put_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return http_json_request("PUT", url, payload, headers)


def http_post_form(url: str, form: Dict[str, Any]) -> Dict[str, Any]:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


async def cached_call(prefix: str, cache_payload: Any, ttl_sec: int, async_fn):
    key = CACHE.make_key(prefix, cache_payload)
    hit = await asyncio.to_thread(CACHE.get, key)
    if hit is not None:
        return hit
    val = await async_fn()
    await asyncio.to_thread(CACHE.set, key, val, ttl_sec)
    return val


# =========================
# Data sources
# =========================
async def fetch_zabbix_problems() -> List[Dict[str, Any]]:
    if not (ZABBIX_URL and ZABBIX_TOKEN):
        return []

    payload = {
        "jsonrpc": "2.0",
        "method": "problem.get",
        "params": {
            "recent": True,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            "limit": 100,
            "selectTags": "extend",
        },
        "auth": ZABBIX_TOKEN,
        "id": 1,
    }

    async def _run():
        data = await asyncio.to_thread(http_post_json, f"{ZABBIX_URL}/api_jsonrpc.php", payload)
        return data.get("result", [])

    return await cached_call(
        "zabbix_problems",
        {"url": ZABBIX_URL, "lookback": LOOKBACK_MINUTES},
        TTL_ZABBIX_SEC,
        _run,
    )


async def fetch_uptimerobot_monitors() -> List[Dict[str, Any]]:
    if not UPTIMEROBOT_API_KEY:
        return []

    form = {
        "api_key": UPTIMEROBOT_API_KEY,
        "format": "json",
        "logs": 1,
        "response_times": 0,
    }

    async def _run():
        data = await asyncio.to_thread(http_post_form, "https://api.uptimerobot.com/v2/getMonitors", form)
        return data.get("monitors", [])

    return await cached_call(
        "uptimerobot_monitors",
        {"has_logs": 1, "lookback": LOOKBACK_MINUTES},
        TTL_UPTIME_SEC,
        _run,
    )


# =========================
# Time parsing & correlation
# =========================
def parse_ts(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 10_000_000_000:  # ms
            ts //= 1000
        return ts

    s = str(value).strip()
    if not s:
        return None

    if s.isdigit():
        ts = int(s)
        if ts > 10_000_000_000:
            ts //= 1000
        return ts

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def zabbix_event_ts(ev: Dict[str, Any]) -> Optional[int]:
    return parse_ts(ev.get("clock")) or parse_ts(ev.get("event_time")) or parse_ts(ev.get("timestamp"))


def uptime_log_ts(log: Dict[str, Any]) -> Optional[int]:
    return parse_ts(log.get("datetime")) or parse_ts(log.get("created_at")) or parse_ts(log.get("time"))


def within_window(ts_a: int, ts_b: int, sec: int = TIME_WINDOW_SEC) -> bool:
    return abs(ts_a - ts_b) <= sec


def normalize_uptime_events(monitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for m in monitors:
        for lg in (m.get("logs") or []):
            ts = uptime_log_ts(lg)
            if not ts:
                continue
            events.append(
                {
                    "ts": ts,
                    "monitor": m.get("friendly_name"),
                    "url": m.get("url"),
                    "status": m.get("status"),
                    "log": lg,
                }
            )
    return events


def correlate(zabbix_problems: List[Dict[str, Any]], uptime_monitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=LOOKBACK_MINUTES)

    uptime_events = normalize_uptime_events(uptime_monitors)

    groups: List[Dict[str, Any]] = []
    for z in zabbix_problems:
        zts = zabbix_event_ts(z)
        if not zts:
            continue

        zdt = datetime.fromtimestamp(zts, tz=timezone.utc)
        if zdt < since:
            continue

        matched = [u for u in uptime_events if within_window(zts, u["ts"], TIME_WINDOW_SEC)]

        groups.append(
            {
                "zabbix_event": {
                    "eventid": z.get("eventid"),
                    "name": z.get("name"),
                    "severity": z.get("severity"),
                    "tags": z.get("tags", []),
                    "clock": z.get("clock"),
                },
                "zabbix_ts": zts,
                "matched_uptimerobot": matched,
                "window_sec": TIME_WINDOW_SEC,
            }
        )

    return groups


# =========================
# Batch processing
# =========================
def chunks(items: List[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def summarize_group(group: Dict[str, Any]) -> Dict[str, Any]:
    """Optional per-group mini summary (lightweight, no LLM)."""
    z = group["zabbix_event"]
    return {
        "eventid": z.get("eventid"),
        "title": z.get("name"),
        "severity": z.get("severity"),
        "match_count": len(group.get("matched_uptimerobot", [])),
        "time": group.get("zabbix_ts"),
    }


async def process_groups_batched(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def guarded(g: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            return await summarize_group(g)

    out: List[Dict[str, Any]] = []
    for batch in chunks(groups, BATCH_SIZE):
        res = await asyncio.gather(*(guarded(g) for g in batch), return_exceptions=False)
        out.extend(res)
    return out


# =========================
# LLM + Teams
# =========================
async def generate_rca(correlation_groups: List[Dict[str, Any]], summaries: List[Dict[str, Any]]) -> str:
    payload_for_key = {
        "groups": summaries,
        "window": TIME_WINDOW_MINUTES,
        "lookback": LOOKBACK_MINUTES,
    }

    async def _run_llm():
        if not LLM_API_KEY:
            return (
                "### Probable Root Cause\n"
                "Có dấu hiệu sự cố hạ tầng/network hoặc dependency gây đồng thời cảnh báo từ nhiều nguồn.\n\n"
                "### Impact\n"
                f"- Số sự kiện đã correlate: {len(correlation_groups)}\n"
                "- Ảnh hưởng dịch vụ phụ thuộc các monitor bị match.\n\n"
                "### Immediate Actions\n"
                "1) Kiểm tra network path + DNS + LB\n"
                "2) Soát deploy/config gần thời điểm sự cố\n"
                "3) Đối chiếu app logs theo event time\n"
            )

        llm_payload = {
            "model": LLM_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an SRE assistant. Return concise markdown with sections: "
                        "Probable Root Cause, Impact, Evidence, Immediate Actions, Preventive Actions."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "lookback_minutes": LOOKBACK_MINUTES,
                            "window_minutes": TIME_WINDOW_MINUTES,
                            "summaries": summaries,
                            "correlation_groups": correlation_groups,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
        data = await asyncio.to_thread(http_post_json, LLM_URL, llm_payload, headers)
        return data["choices"][0]["message"]["content"]

    return await cached_call("llm_rca", payload_for_key, TTL_LLM_SEC, _run_llm)


async def send_teams(message_text: str):
    if not TEAMS_WEBHOOK_URL:
        print("[WARN] Missing TEAMS_WEBHOOK_URL. Skip sending.")
        return
    await asyncio.to_thread(http_post_json, TEAMS_WEBHOOK_URL, {"text": message_text})


def sdp_headers() -> Dict[str, str]:
    # SDP v14720 (on-prem) commonly accepts TECHNICIAN_KEY header
    return {"TECHNICIAN_KEY": SDP_TECHNICIAN_KEY}


def sdp_request_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}"


def sdp_tasks_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}/tasks"


def sdp_worklog_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}/worklogs"


async def sdp_update_solution(request_id: str, solution_text: str) -> Dict[str, Any]:
    payload = {
        "request": {
            "resolution": {"content": f"{SDP_RESOLUTION_PREFIX}\n\n{solution_text}"}
        }
    }
    return await asyncio.to_thread(http_put_json, sdp_request_url(request_id), payload, sdp_headers())


async def sdp_add_single_task(request_id: str, task_title: str) -> Dict[str, Any]:
    task_payload: Dict[str, Any] = {
        "task": {
            "title": task_title,
            "description": "Auto-created RCA execution task",
        }
    }
    if SDP_TASK_OWNER:
        task_payload["task"]["owner"] = {"name": SDP_TASK_OWNER}

    return await asyncio.to_thread(http_post_json, sdp_tasks_url(request_id), task_payload, sdp_headers())


async def sdp_close_task(request_id: str, task_id: str) -> Dict[str, Any]:
    payload = {"task": {"status": {"name": "Completed"}}}
    return await asyncio.to_thread(
        http_put_json,
        f"{sdp_tasks_url(request_id)}/{task_id}",
        payload,
        sdp_headers(),
    )


async def sdp_add_worklog(request_id: str, worklog_text: str) -> Dict[str, Any]:
    payload = {
        "worklog": {
            "description": worklog_text,
            "time_spent": "0:15",
        }
    }
    return await asyncio.to_thread(http_post_json, sdp_worklog_url(request_id), payload, sdp_headers())


async def sdp_close_ticket(request_id: str) -> Dict[str, Any]:
    payload = {"request": {"status": {"name": SDP_CLOSE_STATUS}}}
    return await asyncio.to_thread(http_put_json, sdp_request_url(request_id), payload, sdp_headers())


def _extract_id(resp: Dict[str, Any], *keys: str) -> Optional[str]:
    cur: Any = resp
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    if cur is None:
        return None
    return str(cur)


def _read_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_request_id(cli_request_id: Optional[str], input_payload: Optional[Dict[str, Any]]) -> str:
    """
    Priority:
    1) --request-id CLI
    2) input payload fields (request_id, request.id, sdp.request_id, input.request_id)
    3) SDP_REQUEST_ID env (fallback)
    """
    if cli_request_id:
        return str(cli_request_id)

    p = input_payload or {}

    direct = p.get("request_id")
    if direct:
        return str(direct)

    req_obj = p.get("request") or {}
    if isinstance(req_obj, dict) and req_obj.get("id"):
        return str(req_obj.get("id"))

    sdp_obj = p.get("sdp") or {}
    if isinstance(sdp_obj, dict) and sdp_obj.get("request_id"):
        return str(sdp_obj.get("request_id"))

    in_obj = p.get("input") or {}
    if isinstance(in_obj, dict) and in_obj.get("request_id"):
        return str(in_obj.get("request_id"))

    return str(SDP_REQUEST_ID or "")


async def run_servicedesk_plus_flow(rca_text: str, request_id: str) -> Optional[Dict[str, Any]]:
    """
    v14720 flow requested:
    1) update solution
    2) add exactly 1 task
    3) close that task
    4) add worklog
    5) close ticket
    """
    if not (SDP_URL and SDP_TECHNICIAN_KEY and request_id):
        return None

    out: Dict[str, Any] = {}

    out["update_solution"] = await sdp_update_solution(request_id, rca_text)

    created_task = await sdp_add_single_task(request_id, SDP_TASK_TITLE)
    out["create_task"] = created_task

    task_id = (
        _extract_id(created_task, "task", "id")
        or _extract_id(created_task, "response", "task", "id")
        or _extract_id(created_task, "response", "id")
    )

    if task_id:
        out["close_task"] = await sdp_close_task(request_id, task_id)
    else:
        out["close_task"] = {"warning": "Task created but task_id not found in response; skip close_task."}

    out["worklog"] = await sdp_add_worklog(
        request_id,
        "RCA automation completed: solution updated, single task handled, ticket ready to close.",
    )

    out["close_ticket"] = await sdp_close_ticket(request_id)

    return out


# =========================
# Main
# =========================
async def main(cli_request_id: Optional[str] = None, input_payload: Optional[Dict[str, Any]] = None):
    try:
        z_task = asyncio.create_task(fetch_zabbix_problems())
        u_task = asyncio.create_task(fetch_uptimerobot_monitors())
        zabbix_problems, uptime_monitors = await asyncio.gather(z_task, u_task)

        corr_groups = correlate(zabbix_problems, uptime_monitors)
        summaries = await process_groups_batched(corr_groups)
        rca_md = await generate_rca(corr_groups, summaries)

        request_id = resolve_request_id(cli_request_id, input_payload)
        sdp_result = await run_servicedesk_plus_flow(rca_md, request_id)

        sdp_line = "- ServiceDesk Plus: skipped (missing SDP env/request_id)"
        if sdp_result is not None:
            sdp_line = f"- ServiceDesk Plus: done (request_id={request_id})"

        report = (
            f"🚨 RCA Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"- Lookback: {LOOKBACK_MINUTES}m\n"
            f"- Correlation window: ±{TIME_WINDOW_MINUTES}m\n"
            f"- Zabbix problems fetched: {len(zabbix_problems)}\n"
            f"- Uptime monitors fetched: {len(uptime_monitors)}\n"
            f"- Correlated groups: {len(corr_groups)}\n"
            f"{sdp_line}\n\n"
            f"{rca_md}"
        )

        await send_teams(report)
        print("[OK] RCA complete.")
        if sdp_result is not None:
            print("[OK] ServiceDesk Plus flow complete.")
    finally:
        await asyncio.to_thread(CACHE.cleanup)
        CACHE.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RCA Full Async stdlib pipeline")
    parser.add_argument("--request-id", help="ServiceDesk Plus request ID (overrides input/env)")
    parser.add_argument("--input-json", help="Path to input JSON payload (used to extract request_id)")
    args = parser.parse_args()

    payload = None
    if args.input_json:
        payload = _read_json_file(args.input_json)

    asyncio.run(main(cli_request_id=args.request_id, input_payload=payload))
