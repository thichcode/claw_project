#!/usr/bin/env python3
"""
RCA Multi-Agent (stdlib-only)
- Async orchestration similar to OpenClaw style (role-based agents)
- Zabbix + UptimeRobot ingestion
- Multi-agent reasoning pipeline
- ServiceDesk Plus (v14720+) ITSM 5W1H update + single task + worklog + close ticket
"""

import os
import json
import asyncio
import urllib.request
import urllib.parse
import argparse
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ===== Core config =====
ZABBIX_URL = os.getenv("ZABBIX_URL", "").rstrip("/")
ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN", "")
UPTIMEROBOT_API_KEY = os.getenv("UPTIMEROBOT_API_KEY", "")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

LLM_URL = os.getenv("LLM_URL", "https://api.openai.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "30"))
TIME_WINDOW_MINUTES = int(os.getenv("TIME_WINDOW_MINUTES", "10"))
TIME_WINDOW_SEC = TIME_WINDOW_MINUTES * 60
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))
ENRICH_TOP_N_ITEMS = int(os.getenv("ENRICH_TOP_N_ITEMS", "5"))
ENRICH_LOOKBACK_MINUTES = int(os.getenv("ENRICH_LOOKBACK_MINUTES", "20"))
ENRICH_ITEM_KEY_HINTS = [
    s.strip() for s in os.getenv(
        "ENRICH_ITEM_KEY_HINTS",
        "system.cpu,vm.memory,vfs.fs,net.if,proc.num,log,kubelet,docker,mysql",
    ).split(",") if s.strip()
]

# ===== ServiceDesk Plus =====
SDP_URL = os.getenv("SDP_URL", "").rstrip("/")
SDP_TECHNICIAN_KEY = os.getenv("SDP_TECHNICIAN_KEY", "")
SDP_REQUEST_ID = os.getenv("SDP_REQUEST_ID", "")
SDP_TASK_TITLE = os.getenv("SDP_TASK_TITLE", "RCA investigation")
SDP_TASK_OWNER = os.getenv("SDP_TASK_OWNER", "")
SDP_CLOSE_STATUS = os.getenv("SDP_CLOSE_STATUS", "Closed")

# ===== KB matching =====
KB_JSON_PATH = os.getenv("KB_JSON_PATH", "")
KB_MATCH_MIN_SCORE = float(os.getenv("KB_MATCH_MIN_SCORE", "0.2"))


# ---------------- HTTP helpers ----------------
def http_json_request(method: str, url: str, payload: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def http_post_form(url: str, form: Dict[str, Any]) -> Dict[str, Any]:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


async def to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def zabbix_rpc(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "auth": ZABBIX_TOKEN,
        "id": 1,
    }
    return http_json_request("POST", f"{ZABBIX_URL}/api_jsonrpc.php", payload)


# ---------------- Data fetch ----------------
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
            "selectHosts": ["host", "name", "hostid"],
        },
        "auth": ZABBIX_TOKEN,
        "id": 1,
    }
    data = await to_thread(http_json_request, "POST", f"{ZABBIX_URL}/api_jsonrpc.php", payload)
    return data.get("result", [])


async def fetch_uptimerobot_monitors() -> List[Dict[str, Any]]:
    if not UPTIMEROBOT_API_KEY:
        return []
    form = {
        "api_key": UPTIMEROBOT_API_KEY,
        "format": "json",
        "logs": 1,
    }
    data = await to_thread(http_post_form, "https://api.uptimerobot.com/v2/getMonitors", form)
    return data.get("monitors", [])


# ---------------- Time + correlate ----------------
def parse_ts(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        t = int(v)
        return t // 1000 if t > 10_000_000_000 else t
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        t = int(s)
        return t // 1000 if t > 10_000_000_000 else t
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def within_window(a: int, b: int) -> bool:
    return abs(a - b) <= TIME_WINDOW_SEC


def correlate(zbx: List[Dict[str, Any]], upr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=LOOKBACK_MINUTES)

    up_events: List[Dict[str, Any]] = []
    for m in upr:
        for lg in (m.get("logs") or []):
            ts = parse_ts(lg.get("datetime") or lg.get("time") or lg.get("created_at"))
            if not ts:
                continue
            up_events.append({
                "ts": ts,
                "monitor": m.get("friendly_name"),
                "url": m.get("url"),
                "status": m.get("status"),
                "log": lg,
            })

    groups: List[Dict[str, Any]] = []
    for z in zbx:
        zts = parse_ts(z.get("clock") or z.get("event_time") or z.get("timestamp"))
        if not zts:
            continue
        if datetime.fromtimestamp(zts, tz=timezone.utc) < since:
            continue
        matched = [e for e in up_events if within_window(zts, e["ts"])]
        hosts = z.get("hosts") or []
        host0 = hosts[0] if hosts else {}
        hostname = host0.get("host") or host0.get("name")
        groups.append({
            "zabbix": {
                "eventid": z.get("eventid"),
                "name": z.get("name"),
                "severity": z.get("severity"),
                "tags": z.get("tags", []),
                "clock": z.get("clock"),
                "hostname": hostname,
                "hostid": host0.get("hostid"),
            },
            "zabbix_ts": zts,
            "matched_uptime": matched,
            "window_min": TIME_WINDOW_MINUTES,
        })
    return groups


# ---------------- Zabbix enrichment (hostname + eventid) ----------------
async def zabbix_hostid_from_hostname(hostname: str) -> Optional[str]:
    if not (ZABBIX_URL and ZABBIX_TOKEN and hostname):
        return None
    data = await to_thread(zabbix_rpc, "host.get", {"filter": {"host": [hostname]}, "output": ["hostid", "host", "name"], "limit": 1})
    result = data.get("result", [])
    if result:
        return str(result[0].get("hostid"))
    return None


async def zabbix_event_clock(eventid: str) -> Optional[int]:
    if not (ZABBIX_URL and ZABBIX_TOKEN and eventid):
        return None
    data = await to_thread(zabbix_rpc, "event.get", {"eventids": [str(eventid)], "output": ["eventid", "clock"], "limit": 1})
    result = data.get("result", [])
    if not result:
        return None
    return parse_ts(result[0].get("clock"))


async def zabbix_item_candidates(hostid: str) -> List[Dict[str, Any]]:
    data = await to_thread(
        zabbix_rpc,
        "item.get",
        {
            "hostids": [hostid],
            "output": ["itemid", "name", "key_", "value_type", "units"],
            "search": {"key_": ENRICH_ITEM_KEY_HINTS},
            "searchByAny": True,
            "sortfield": "name",
            "limit": 200,
        },
    )
    return data.get("result", [])


async def zabbix_item_history(itemid: str, value_type: int, time_from: int, time_till: int) -> List[Dict[str, Any]]:
    history_type = value_type if value_type in (0, 3) else 0
    data = await to_thread(
        zabbix_rpc,
        "history.get",
        {
            "history": history_type,
            "itemids": [str(itemid)],
            "time_from": int(time_from),
            "time_till": int(time_till),
            "output": "extend",
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": 200,
        },
    )
    return data.get("result", [])


def summarize_series(points: List[float]) -> Dict[str, Any]:
    if not points:
        return {
            "count": 0,
            "latest": None,
            "first": None,
            "min": None,
            "max": None,
            "avg": None,
            "delta": None,
            "change": None,
            "trend": "unknown",
            "volatility": None,
            "anomaly_score": 0.0,
        }

    mn = min(points)
    mx = max(points)
    avg = sum(points) / len(points)
    latest = points[-1]
    first = points[0]
    delta = mx - mn
    change = latest - first

    trend = "stable"
    if change > 0:
        trend = "up"
    elif change < 0:
        trend = "down"

    volatility = (delta / abs(avg)) if avg not in (0, None) else (delta if delta is not None else 0)
    change_ratio = (abs(change) / abs(first)) if first not in (0, None) else abs(change)

    # Simple anomaly score in [0,1] from movement + volatility
    movement = min(1.0, float(change_ratio) if isinstance(change_ratio, (int, float)) else 0.0)
    vol = min(1.0, float(volatility) if isinstance(volatility, (int, float)) else 0.0)
    anomaly_score = round((movement * 0.6 + vol * 0.4), 4)

    return {
        "count": len(points),
        "latest": latest,
        "first": first,
        "min": mn,
        "max": mx,
        "avg": avg,
        "delta": delta,
        "change": change,
        "trend": trend,
        "volatility": volatility,
        "anomaly_score": anomaly_score,
    }


async def zabbix_enrich_from_hostname_eventid(
    hostname: str,
    eventid: str,
    explicit_window: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Best-effort enrichment for CPU/mem/disk/net/process/log(+k8s/docker/mysql keys if present)."""
    if not (hostname and eventid and ZABBIX_URL and ZABBIX_TOKEN):
        return {"hostname": hostname, "eventid": eventid, "metrics": [], "note": "missing inputs or zabbix creds"}

    hostid = await zabbix_hostid_from_hostname(hostname)
    event_clock = await zabbix_event_clock(eventid)
    if not hostid:
        return {"hostname": hostname, "eventid": eventid, "metrics": [], "note": "hostid not found"}

    if explicit_window and explicit_window.get("from") and explicit_window.get("till"):
        time_from = int(explicit_window["from"])
        time_till = int(explicit_window["till"])
        if not event_clock:
            event_clock = (time_from + time_till) // 2
    else:
        if not event_clock:
            return {"hostname": hostname, "eventid": eventid, "metrics": [], "note": "event_clock not found"}
        time_till = event_clock + TIME_WINDOW_SEC
        time_from = event_clock - (ENRICH_LOOKBACK_MINUTES * 60)

    items = await zabbix_item_candidates(hostid)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def one_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with sem:
            vt = int(it.get("value_type", 0) or 0)
            if vt not in (0, 3):
                return None
            hist = await zabbix_item_history(str(it.get("itemid")), vt, time_from, time_till)
            vals: List[float] = []
            for h in hist:
                try:
                    vals.append(float(h.get("value")))
                except Exception:
                    pass
            s = summarize_series(vals)
            if s["count"] == 0:
                return None
            return {
                "itemid": it.get("itemid"),
                "name": it.get("name"),
                "key": it.get("key_"),
                "units": it.get("units"),
                "summary": s,
            }

    metric_rows = [m for m in await asyncio.gather(*(one_item(i) for i in items)) if m is not None]
    metric_rows.sort(key=lambda x: (x.get("summary", {}).get("anomaly_score") or 0), reverse=True)

    top_metrics = metric_rows[:ENRICH_TOP_N_ITEMS]
    anomalies = []
    for m in top_metrics:
        s = m.get("summary") or {}
        if (s.get("anomaly_score") or 0) >= 0.35:
            anomalies.append({
                "key": m.get("key"),
                "name": m.get("name"),
                "trend": s.get("trend"),
                "anomaly_score": s.get("anomaly_score"),
                "latest": s.get("latest"),
                "avg": s.get("avg"),
                "delta": s.get("delta"),
            })

    host_anomaly_score = 0.0
    if top_metrics:
        scores = [(x.get("summary", {}).get("anomaly_score") or 0.0) for x in top_metrics]
        host_anomaly_score = round(sum(scores) / len(scores), 4)

    return {
        "hostname": hostname,
        "eventid": eventid,
        "event_clock": event_clock,
        "window": {"from": time_from, "till": time_till},
        "host_anomaly_score": host_anomaly_score,
        "anomalies": anomalies,
        "metrics": top_metrics,
    }


# ---------------- LLM agents ----------------
async def llm_json(system_prompt: str, user_payload: Dict[str, Any]) -> Dict[str, Any]:
    if not LLM_API_KEY:
        return {"fallback": True, "note": "LLM disabled"}

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    data = await to_thread(http_json_request, "POST", LLM_URL, payload, headers)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        return json.loads(content)
    except Exception:
        return {"raw": content}


async def collector_agent(groups: List[Dict[str, Any]], enrichments: List[Dict[str, Any]]) -> Dict[str, Any]:
    prompt = (
        "You are Collector Agent. Normalize incidents + enrichment signals and produce compact timeline. "
        "Use trend/anomaly fields from enrichment (trend, anomaly_score, host_anomaly_score, anomalies[]) "
        "to rank top signals. Return JSON with timeline[], key_entities[], top_signals[], anomaly_summary[]."
    )
    return await llm_json(prompt, {"groups": groups, "enrichments": enrichments})


async def correlation_agent(groups: List[Dict[str, Any]], collected: Dict[str, Any]) -> Dict[str, Any]:
    prompt = "You are Correlation Agent. Group incidents by probable shared cause. Return JSON with clusters[]."
    return await llm_json(prompt, {"groups": groups, "collected": collected})


async def hypothesis_agent(correlation_out: Dict[str, Any]) -> Dict[str, Any]:
    prompt = "You are Hypothesis Agent. Produce top 3 root-cause hypotheses with confidence (0-1), evidence, and missing_data. Return JSON hypotheses[]."
    return await llm_json(prompt, {"correlation": correlation_out})


async def verifier_agent(correlation_out: Dict[str, Any], hypotheses: Dict[str, Any]) -> Dict[str, Any]:
    prompt = "You are Verifier Agent. Challenge each hypothesis and score robustness. Return JSON verdicts[]."
    return await llm_json(prompt, {"correlation": correlation_out, "hypotheses": hypotheses})


async def decision_agent(collected: Dict[str, Any], correlation_out: Dict[str, Any], hypotheses: Dict[str, Any], verdicts: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        "You are Decision Agent. Select final RCA with confidence and actions. "
        "Be conservative: if evidence is weak or incomplete, return probable/likely causes and explicit missing_data[]. "
        "Return JSON with keys: root_cause, confidence, impact, evidence, immediate_actions[], preventive_actions[], missing_data[], "
        "and itsm_5w1h={who,what,when,where,why,how}."
    )
    return await llm_json(prompt, {
        "collected": collected,
        "correlation": correlation_out,
        "hypotheses": hypotheses,
        "verifier": verdicts,
    })


# ---------------- SDP (ITSM 5W1H flow) ----------------
def sdp_headers() -> Dict[str, str]:
    return {"TECHNICIAN_KEY": SDP_TECHNICIAN_KEY}


def sdp_request_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}"


def sdp_tasks_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}/tasks"


def sdp_worklog_url(request_id: str) -> str:
    return f"{SDP_URL}/api/v3/requests/{request_id}/worklogs"


def build_itsm_5w1h_markdown(decision: Dict[str, Any]) -> str:
    w = decision.get("itsm_5w1h") or {}
    immediate = decision.get("immediate_actions") or []
    preventive = decision.get("preventive_actions") or []
    evidence = decision.get("evidence") or []

    def line(v: Any, default: str = "N/A") -> str:
        if isinstance(v, list):
            return "; ".join(str(x) for x in v) if v else default
        return str(v) if v not in (None, "") else default

    return (
        "## ITSM RCA (5W1H)\n"
        f"- **Who**: {line(w.get('who'))}\n"
        f"- **What**: {line(w.get('what') or decision.get('root_cause'))}\n"
        f"- **When**: {line(w.get('when'))}\n"
        f"- **Where**: {line(w.get('where'))}\n"
        f"- **Why**: {line(w.get('why'))}\n"
        f"- **How**: {line(w.get('how'))}\n\n"
        f"### Impact\n{line(decision.get('impact'))}\n\n"
        f"### Evidence\n{line(evidence)}\n\n"
        f"### Immediate Actions\n{line(immediate)}\n\n"
        f"### Preventive Actions\n{line(preventive)}\n"
    )


async def sdp_update_solution(request_id: str, text: str) -> Dict[str, Any]:
    payload = {"request": {"resolution": {"content": text}}}
    return await to_thread(http_json_request, "PUT", sdp_request_url(request_id), payload, sdp_headers())


async def sdp_add_single_task(request_id: str, title: str) -> Dict[str, Any]:
    task = {"title": title, "description": "RCA task generated by multi-agent pipeline"}
    if SDP_TASK_OWNER:
        task["owner"] = {"name": SDP_TASK_OWNER}
    payload = {"task": task}
    return await to_thread(http_json_request, "POST", sdp_tasks_url(request_id), payload, sdp_headers())


async def sdp_close_task(request_id: str, task_id: str) -> Dict[str, Any]:
    payload = {"task": {"status": {"name": "Completed"}}}
    return await to_thread(http_json_request, "PUT", f"{sdp_tasks_url(request_id)}/{task_id}", payload, sdp_headers())


async def sdp_add_worklog(request_id: str, text: str) -> Dict[str, Any]:
    payload = {"worklog": {"description": text, "time_spent": "0:20"}}
    return await to_thread(http_json_request, "POST", sdp_worklog_url(request_id), payload, sdp_headers())


async def sdp_close_ticket(request_id: str) -> Dict[str, Any]:
    payload = {"request": {"status": {"name": SDP_CLOSE_STATUS}}}
    return await to_thread(http_json_request, "PUT", sdp_request_url(request_id), payload, sdp_headers())


def extract_task_id(resp: Dict[str, Any]) -> Optional[str]:
    paths = [
        ("task", "id"),
        ("response", "task", "id"),
        ("response", "id"),
    ]
    for path in paths:
        cur: Any = resp
        ok = True
        for p in path:
            if not isinstance(cur, dict):
                ok = False
                break
            cur = cur.get(p)
        if ok and cur:
            return str(cur)
    return None


def extract_sdp_ticket_id(text: Any) -> Optional[str]:
    s = str(text or "")
    if not s:
        return None

    patterns = [
        r"woID=(\d+)",
        r"/requests/(\d+)",
        r"/workorder/(\d+)",
        r"\brequest[_\s-]?id[\s:=]+(\d+)\b",
        r"\bid[\s:=]+(\d{5,})\b",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def parse_hostname_eventid_from_text(text: Any) -> Dict[str, Optional[str]]:
    s = str(text or "")
    out: Dict[str, Optional[str]] = {"hostname": None, "eventid": None}
    if not s:
        return out

    m = re.search(r"([a-zA-Z0-9_.-]+)\s*[:|\s]\s*(\d{8,})", s)
    if m:
        out["hostname"] = m.group(1)
        out["eventid"] = m.group(2)
        return out

    # support: hostname:10.243.16.60 ... eventid:1312158100
    hm_ip = re.search(r"hostname\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3}|[a-zA-Z0-9_.-]+)", s, flags=re.IGNORECASE)
    if hm_ip:
        out["hostname"] = hm_ip.group(1)

    hm = re.search(r"(?:host|hostname|server|node)[\s:=]+([a-zA-Z0-9_.-]+)", s, flags=re.IGNORECASE)
    em = re.search(r"(?:eventid|event_id|event)[\s:=]+(\d{8,})", s, flags=re.IGNORECASE)
    if hm and not out.get("hostname"):
        out["hostname"] = hm.group(1)
    if em:
        out["eventid"] = em.group(1)
    return out


def parse_event_time_epoch(text: Any) -> Optional[int]:
    s = str(text or "")
    if not s:
        return None

    # Format: Last check: 15:49:03/2026.02.26
    m = re.search(r"(\d{2}):(\d{2}):(\d{2})\/(\d{4})\.(\d{2})\.(\d{2})", s)
    if m:
        hh, mm, ss, yyyy, mon, dd = map(int, m.groups())
        try:
            dt = datetime(yyyy, mon, dd, hh, mm, ss, tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            pass

    # Format: 2026-02-26 15:49:03
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", s)
    if m:
        yyyy, mon, dd, hh, mm, ss = map(int, m.groups())
        try:
            dt = datetime(yyyy, mon, dd, hh, mm, ss, tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            pass

    return None


def build_time_window(event_epoch: int, window_minutes: int = TIME_WINDOW_MINUTES) -> Dict[str, Any]:
    delta = window_minutes * 60
    t_from = int(event_epoch) - delta
    t_till = int(event_epoch) + delta
    return {
        "from": t_from,
        "till": t_till,
        "window_min": window_minutes,
    }


def normalize_input_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    p = payload or {}
    out = dict(p)

    host_val = out.get("host")
    if isinstance(host_val, dict):
        host_from_host = host_val.get("name") or host_val.get("host")
    else:
        host_from_host = host_val

    event_val = out.get("event")
    if isinstance(event_val, dict):
        event_from_event = event_val.get("id")
    else:
        event_from_event = event_val

    hostname = out.get("hostname") or host_from_host
    eventid = out.get("eventid") or event_from_event

    if not hostname or not eventid:
        raw_candidates = [
            out.get("raw_input"),
            out.get("subject"),
            out.get("description_text"),
            out.get("description"),
        ]
        parsed = {"hostname": None, "eventid": None}
        for rc in raw_candidates:
            parsed = parse_hostname_eventid_from_text(rc)
            if parsed.get("hostname") or parsed.get("eventid"):
                break
        hostname = hostname or parsed.get("hostname")
        eventid = eventid or parsed.get("eventid")

    if hostname:
        out["hostname"] = str(hostname)
    if eventid:
        out["eventid"] = str(eventid)

    # optional: keep explicit sdp_ticket_id and map into request_id
    sdp_ticket_id = out.get("sdp_ticket_id")
    if not sdp_ticket_id:
        if out.get("id") and str(out.get("id")).isdigit():
            sdp_ticket_id = str(out.get("id"))
        else:
            sdp_ticket_id = (
                extract_sdp_ticket_id(out.get("url"))
                or extract_sdp_ticket_id(out.get("raw_input"))
                or extract_sdp_ticket_id(out.get("subject"))
                or extract_sdp_ticket_id(out.get("description_text"))
                or extract_sdp_ticket_id(out.get("description"))
            )
    if sdp_ticket_id:
        out["sdp_ticket_id"] = str(sdp_ticket_id)

    rid = out.get("request_id") or out.get("sdp_ticket_id")
    if rid:
        out["request_id"] = str(rid)

    # derive event time + explicit time window for enrichment (if present in text)
    evt_epoch = (
        out.get("event_time_epoch")
        or parse_event_time_epoch(out.get("description_text"))
        or parse_event_time_epoch(out.get("description"))
        or parse_event_time_epoch(out.get("raw_input"))
    )
    if evt_epoch:
        out["event_time_epoch"] = int(evt_epoch)
        out["time_window"] = build_time_window(int(evt_epoch), TIME_WINDOW_MINUTES)

    return out


def resolve_request_id(cli_id: Optional[str], payload: Optional[Dict[str, Any]]) -> str:
    if cli_id:
        return str(cli_id)
    p = normalize_input_payload(payload)
    if p.get("request_id"):
        return str(p["request_id"])
    req = p.get("request") or {}
    if isinstance(req, dict) and req.get("id"):
        return str(req["id"])
    sdp = p.get("sdp") or {}
    if isinstance(sdp, dict) and sdp.get("request_id"):
        return str(sdp["request_id"])
    return str(SDP_REQUEST_ID or "")


async def run_sdp_flow(request_id: str, decision: Dict[str, Any], kb_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not (SDP_URL and SDP_TECHNICIAN_KEY and request_id):
        return None

    solution = build_itsm_5w1h_markdown(decision)
    if kb_id:
        solution = f"{solution}\n\n### Related Knowledge Base\n- KB ID: {kb_id}\n"

    kb_note = f" Matched KB ID: {kb_id}." if kb_id else ""
    worklog = (
        "RCA multi-agent completed (ITSM 5W1H). "
        "Executed flow: update solution -> create one task -> close task -> add worklog -> close ticket."
        + kb_note
    )

    out: Dict[str, Any] = {}
    out["update_solution"] = await sdp_update_solution(request_id, solution)
    created = await sdp_add_single_task(request_id, SDP_TASK_TITLE)
    out["create_task"] = created

    task_id = extract_task_id(created)
    if task_id:
        out["close_task"] = await sdp_close_task(request_id, task_id)
    else:
        out["close_task"] = {"warning": "task_id not found; skip close_task"}

    out["worklog"] = await sdp_add_worklog(request_id, worklog)
    out["close_ticket"] = await sdp_close_ticket(request_id)
    return out


# ---------------- Output ----------------
async def send_teams(text: str):
    if not TEAMS_WEBHOOK_URL:
        return
    await to_thread(http_json_request, "POST", TEAMS_WEBHOOK_URL, {"text": text})


def render_report(
    decision: Dict[str, Any],
    groups_count: int,
    enrichment_count: int,
    sdp_done: bool,
    request_id: str,
    kb_id: Optional[str],
    enrichments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    confidence = decision.get("confidence_calibrated", decision.get("confidence", "n/a"))
    confidence_raw = decision.get("confidence_raw", "n/a")
    root_cause = str(decision.get("root_cause", "N/A"))
    impact = str(decision.get("impact", "N/A"))
    evidence = decision.get("evidence") or []
    immediate = decision.get("immediate_actions") or []
    preventive = decision.get("preventive_actions") or []
    missing = decision.get("missing_data") or []
    kb_line = kb_id or "N/A"
    kb_score = decision.get("kb_match_score", "n/a")

    top_host_line = "N/A"
    top_anomaly_keys: List[str] = []
    if enrichments:
        ranked = sorted(
            [e for e in enrichments if isinstance(e, dict)],
            key=lambda x: (x.get("host_anomaly_score") or 0),
            reverse=True,
        )
        if ranked:
            top = ranked[0]
            top_host_line = f"{top.get('hostname') or 'unknown'} ({top.get('host_anomaly_score', 0)})"
            for a in (top.get("anomalies") or [])[:3]:
                if isinstance(a, dict):
                    key = a.get("key") or a.get("name") or "unknown"
                    score = a.get("anomaly_score", "n/a")
                    trend = a.get("trend", "n/a")
                    top_anomaly_keys.append(f"{key} (score={score}, trend={trend})")

    resolution = "Automated remediation flow executed (SDP update/task/worklog/closure)." if sdp_done else "Investigation completed; remediation pending ticket workflow execution."
    contributing = "Correlated cross-source signals and anomaly trends were used to identify probable factors."

    lessons = []
    if top_anomaly_keys:
        lessons.append("High-variance metric keys should be prioritized in first-response triage.")
    lessons.append("Use correlation window + host anomaly score to reduce false positives.")
    lessons.append("Attach KB and missing-data checklist to speed up L1/L2 handoff.")

    actionable = []
    actionable.extend([str(x) for x in immediate if str(x).strip()])
    actionable.extend([str(x) for x in preventive if str(x).strip()])
    for m in missing:
        actionable.append(f"Collect: {m}")
    if not actionable:
        actionable = ["Review host metrics/logs around incident time and confirm probable root cause."]

    rca_obj = {
        "root_cause": root_cause,
        "contributing_factors": contributing,
        "impact": impact,
        "resolution": resolution,
        "lessons_learned": "\n".join([f"{i+1}. {x}" for i, x in enumerate(lessons)]),
        "actionable_steps_for_L1": "\n".join([f"{i+1}. {x}" for i, x in enumerate(actionable[:8])]),
        "metadata": {
            "confidence_calibrated": confidence,
            "confidence_raw": confidence_raw,
            "guardrail_mode": bool(decision.get("guardrail_mode")),
            "kb_id": kb_line,
            "kb_match_score": kb_score,
            "top_anomalous_host": top_host_line,
            "top_anomaly_keys": top_anomaly_keys,
            "correlated_groups": groups_count,
            "enriched_pairs": enrichment_count,
            "sdp_done": sdp_done,
            "request_id": request_id if sdp_done else None,
        },
    }

    md_lines = [
        "**Root Cause Analysis Summary**",
        "",
        f"- **Root Cause:** {root_cause}",
        f"- **Impact:** {impact}",
        f"- **Resolution:** {resolution}",
        f"- **Confidence (calibrated/raw):** {confidence} / {confidence_raw}",
        f"- **Top Anomalous Host:** {top_host_line}",
        f"- **KB Matched ID:** {kb_line} (score={kb_score})",
    ]
    if top_anomaly_keys:
        md_lines.append("- **Top Anomaly Keys:**")
        for i, k in enumerate(top_anomaly_keys, 1):
            md_lines.append(f"  {i}. {k}")
    if evidence:
        md_lines.append("- **Evidence:**")
        ev = evidence if isinstance(evidence, list) else [evidence]
        for i, e in enumerate(ev[:5], 1):
            md_lines.append(f"  {i}. {e}")
    md_lines.append("- **Actionable Steps for L1:**")
    for i, a in enumerate(actionable[:8], 1):
        md_lines.append(f"  {i}. {a}")

    report_obj = {
        "rca": rca_obj,
        "summary_markdown": "\n".join(md_lines),
    }
    return json.dumps(report_obj, ensure_ascii=False, indent=2)


def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_kb_entries(path: str) -> List[Dict[str, Any]]:
    if not path:
        return []
    try:
        raw = read_json(path)
    except Exception:
        return []

    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if not isinstance(raw, dict):
        return []

    for key in ("kbs", "kb", "items", "articles", "data", "knowledge_base"):
        val = raw.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]

    return []


def _normalize_text(s: Any) -> str:
    return " ".join(str(s or "").lower().split())


def _token_set(s: Any) -> set:
    text = _normalize_text(s)
    return {t for t in text.replace("\n", " ").split(" ") if len(t) >= 3}


def _weighted_token_overlap(sol_tokens: set, kb: Dict[str, Any]) -> float:
    # BM25-lite: weighted field overlap (not full BM25, but better than flat Jaccard)
    fields = [
        ("title", 2.5),
        ("root_cause", 2.5),
        ("solution", 2.2),
        ("problem", 1.8),
        ("summary", 1.4),
        ("description", 1.0),
        ("content", 0.8),
    ]
    score = 0.0
    max_score = 0.0
    for key, w in fields:
        kb_tokens = _token_set(kb.get(key))
        if not kb_tokens:
            continue
        overlap = len(sol_tokens & kb_tokens)
        union = len(sol_tokens | kb_tokens)
        s = overlap / max(1, union)
        score += s * w
        max_score += w
    return (score / max_score) if max_score > 0 else 0.0


def pick_best_kb_match(solution_text: str, kb_entries: List[Dict[str, Any]], min_score: float = KB_MATCH_MIN_SCORE) -> Dict[str, Any]:
    sol_tokens = _token_set(solution_text)
    if not sol_tokens:
        return {"id": None, "score": 0.0}

    best_id: Optional[str] = None
    best_score = 0.0

    for kb in kb_entries:
        kb_id = kb.get("id") or kb.get("kb_id") or kb.get("article_id") or kb.get("knowledge_id")
        if not kb_id:
            continue
        score = _weighted_token_overlap(sol_tokens, kb)
        if score > best_score:
            best_score = score
            best_id = str(kb_id)

    if best_score < min_score:
        return {"id": None, "score": round(best_score, 4)}
    return {"id": best_id, "score": round(best_score, 4)}


def pick_best_kb_id(solution_text: str, kb_entries: List[Dict[str, Any]], min_score: float = KB_MATCH_MIN_SCORE) -> Optional[str]:
    return pick_best_kb_match(solution_text, kb_entries, min_score).get("id")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def calibrate_confidence(decision: Dict[str, Any], groups: List[Dict[str, Any]], enrichments: List[Dict[str, Any]]) -> Dict[str, float]:
    llm_conf = _safe_float(decision.get("confidence"), 0.5)
    llm_conf = max(0.0, min(1.0, llm_conf))

    anomaly = 0.0
    if enrichments:
        anomaly = max((_safe_float(e.get("host_anomaly_score"), 0.0) for e in enrichments if isinstance(e, dict)), default=0.0)
        anomaly = max(0.0, min(1.0, anomaly))

    matched = 0
    for g in groups:
        if (g.get("matched_uptime") or []):
            matched += 1
    corr_density = (matched / max(1, len(groups))) if groups else 0.0

    completeness_signals = [
        1.0 if groups else 0.0,
        1.0 if enrichments else 0.0,
        1.0 if decision.get("evidence") else 0.0,
        1.0 if decision.get("root_cause") else 0.0,
        1.0 if decision.get("itsm_5w1h") else 0.0,
    ]
    completeness = sum(completeness_signals) / len(completeness_signals)

    calibrated = (llm_conf * 0.4) + (anomaly * 0.25) + (corr_density * 0.2) + (completeness * 0.15)
    calibrated = max(0.0, min(1.0, calibrated))

    return {
        "llm_conf": round(llm_conf, 4),
        "anomaly": round(anomaly, 4),
        "corr_density": round(corr_density, 4),
        "completeness": round(completeness, 4),
        "calibrated": round(calibrated, 4),
    }


def apply_guardrail(decision: Dict[str, Any], conf_meta: Dict[str, float]) -> Dict[str, Any]:
    calibrated = conf_meta.get("calibrated", 0.0)
    completeness = conf_meta.get("completeness", 0.0)
    guardrail_on = calibrated < 0.45 or completeness < 0.35

    out = dict(decision)
    out["confidence_raw"] = conf_meta.get("llm_conf")
    out["confidence"] = conf_meta.get("calibrated")
    out["confidence_calibrated"] = conf_meta.get("calibrated")
    out["guardrail_mode"] = guardrail_on

    if guardrail_on:
        rc = str(out.get("root_cause") or "Insufficient evidence for definitive root cause")
        if not rc.lower().startswith("likely"):
            out["root_cause"] = f"Likely: {rc}"

        missing = out.get("missing_data")
        if not isinstance(missing, list):
            missing = []
        needed = [
            "Additional host metrics around incident window",
            "Application/service logs correlated with alert time",
            "Verification from on-call/operator confirmation",
        ]
        for n in needed:
            if n not in missing:
                missing.append(n)
        out["missing_data"] = missing

        immediate = out.get("immediate_actions")
        if not isinstance(immediate, list):
            immediate = [str(immediate)] if immediate else []
        extra = "Collect missing data above before final root-cause closure."
        if extra not in immediate:
            immediate.append(extra)
        out["immediate_actions"] = immediate

    return out


async def main(cli_request_id: Optional[str], input_payload: Optional[Dict[str, Any]]):
    normalized_input = normalize_input_payload(input_payload)

    z_task = asyncio.create_task(fetch_zabbix_problems())
    u_task = asyncio.create_task(fetch_uptimerobot_monitors())
    zbx, upr = await asyncio.gather(z_task, u_task)

    groups = correlate(zbx, upr)

    # Enrichment from hostname + eventid (best effort)
    pairs = []
    seen = set()

    # allow direct input mode: hostname/eventid can come from structured JSON or raw text/url parsing
    in_hostname = normalized_input.get("hostname")
    in_eventid = normalized_input.get("eventid")
    if in_hostname and in_eventid and (str(in_hostname), str(in_eventid)) not in seen:
        seen.add((str(in_hostname), str(in_eventid)))
        pairs.append((str(in_hostname), str(in_eventid)))
    for g in groups:
        z = g.get("zabbix") or {}
        h = z.get("hostname")
        e = z.get("eventid")
        if h and e and (h, str(e)) not in seen:
            seen.add((h, str(e)))
            pairs.append((h, str(e)))

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    explicit_window = normalized_input.get("time_window") if isinstance(normalized_input.get("time_window"), dict) else None

    async def enrich_one(hostname: str, eventid: str) -> Dict[str, Any]:
        async with sem:
            return await zabbix_enrich_from_hostname_eventid(hostname, eventid, explicit_window)

    enrichments = await asyncio.gather(*(enrich_one(h, e) for h, e in pairs)) if pairs else []

    # Multi-agent orchestration
    collected = await collector_agent(groups, enrichments)
    corr_out = await correlation_agent(groups, collected)

    hypotheses = await hypothesis_agent(corr_out)
    verifier = await verifier_agent(corr_out, hypotheses)

    decision_raw = await decision_agent(collected, corr_out, hypotheses, verifier)

    # Confidence calibration + guardrail (anti overconfident RCA when data is weak)
    conf_meta = calibrate_confidence(decision_raw, groups, enrichments)
    decision = apply_guardrail(decision_raw, conf_meta)

    # KB matching: compare generated solution text vs KB JSON entries to pick best KB id
    solution_text = build_itsm_5w1h_markdown(decision)
    kb_path = str(normalized_input.get("kb_json") or normalized_input.get("kb_path") or KB_JSON_PATH or "").strip()
    kb_entries = load_kb_entries(kb_path) if kb_path else []
    kb_match = pick_best_kb_match(solution_text, kb_entries)
    matched_kb_id = kb_match.get("id")
    decision["kb_match_score"] = kb_match.get("score")

    request_id = resolve_request_id(cli_request_id, normalized_input)
    sdp_result = await run_sdp_flow(request_id, decision, matched_kb_id)
    sdp_done = sdp_result is not None

    report = render_report(decision, len(groups), len(enrichments), sdp_done, request_id, matched_kb_id, enrichments)
    await send_teams(report)

    print("[OK] Multi-agent RCA complete")
    if sdp_done:
        print("[OK] SDP ITSM 5W1H flow complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RCA Multi-Agent + SDP ITSM 5W1H")
    parser.add_argument("--request-id", help="ServiceDesk Plus request id")
    parser.add_argument("--input-json", help="Input JSON containing request id")
    args = parser.parse_args()

    payload = read_json(args.input_json) if args.input_json else None
    asyncio.run(main(args.request_id, payload))
