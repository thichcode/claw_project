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
def http_post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


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


# =========================
# Main
# =========================
async def main():
    try:
        z_task = asyncio.create_task(fetch_zabbix_problems())
        u_task = asyncio.create_task(fetch_uptimerobot_monitors())
        zabbix_problems, uptime_monitors = await asyncio.gather(z_task, u_task)

        corr_groups = correlate(zabbix_problems, uptime_monitors)
        summaries = await process_groups_batched(corr_groups)
        rca_md = await generate_rca(corr_groups, summaries)

        report = (
            f"🚨 RCA Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"- Lookback: {LOOKBACK_MINUTES}m\n"
            f"- Correlation window: ±{TIME_WINDOW_MINUTES}m\n"
            f"- Zabbix problems fetched: {len(zabbix_problems)}\n"
            f"- Uptime monitors fetched: {len(uptime_monitors)}\n"
            f"- Correlated groups: {len(corr_groups)}\n\n"
            f"{rca_md}"
        )

        await send_teams(report)
        print("[OK] RCA complete.")
    finally:
        await asyncio.to_thread(CACHE.cleanup)
        CACHE.close()


if __name__ == "__main__":
    asyncio.run(main())
