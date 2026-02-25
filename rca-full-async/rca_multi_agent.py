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
        return {"count": 0, "latest": None, "min": None, "max": None, "avg": None, "delta": None}
    mn = min(points)
    mx = max(points)
    avg = sum(points) / len(points)
    latest = points[-1]
    return {
        "count": len(points),
        "latest": latest,
        "min": mn,
        "max": mx,
        "avg": avg,
        "delta": mx - mn,
    }


async def zabbix_enrich_from_hostname_eventid(hostname: str, eventid: str) -> Dict[str, Any]:
    """Best-effort enrichment for CPU/mem/disk/net/process/log(+k8s/docker/mysql keys if present)."""
    if not (hostname and eventid and ZABBIX_URL and ZABBIX_TOKEN):
        return {"hostname": hostname, "eventid": eventid, "metrics": [], "note": "missing inputs or zabbix creds"}

    hostid = await zabbix_hostid_from_hostname(hostname)
    event_clock = await zabbix_event_clock(eventid)
    if not hostid or not event_clock:
        return {"hostname": hostname, "eventid": eventid, "metrics": [], "note": "hostid/event_clock not found"}

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
    metric_rows.sort(key=lambda x: (x.get("summary", {}).get("delta") or 0), reverse=True)

    return {
        "hostname": hostname,
        "eventid": eventid,
        "event_clock": event_clock,
        "window": {"from": time_from, "till": time_till},
        "metrics": metric_rows[:ENRICH_TOP_N_ITEMS],
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
    prompt = "You are Collector Agent. Normalize incidents + enrichment signals and produce compact timeline. Return JSON with timeline[] and key_entities[] and top_signals[]."
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
        "Return JSON with keys: root_cause, confidence, impact, evidence, immediate_actions[], preventive_actions[], "
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


def resolve_request_id(cli_id: Optional[str], payload: Optional[Dict[str, Any]]) -> str:
    if cli_id:
        return str(cli_id)
    p = payload or {}
    if p.get("request_id"):
        return str(p["request_id"])
    req = p.get("request") or {}
    if isinstance(req, dict) and req.get("id"):
        return str(req["id"])
    sdp = p.get("sdp") or {}
    if isinstance(sdp, dict) and sdp.get("request_id"):
        return str(sdp["request_id"])
    return str(SDP_REQUEST_ID or "")


async def run_sdp_flow(request_id: str, decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (SDP_URL and SDP_TECHNICIAN_KEY and request_id):
        return None

    solution = build_itsm_5w1h_markdown(decision)
    worklog = (
        "RCA multi-agent completed (ITSM 5W1H). "
        "Executed flow: update solution -> create one task -> close task -> add worklog -> close ticket."
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


def render_report(decision: Dict[str, Any], groups_count: int, enrichment_count: int, sdp_done: bool, request_id: str) -> str:
    confidence = decision.get("confidence", "n/a")
    root_cause = decision.get("root_cause", "N/A")
    impact = decision.get("impact", "N/A")
    return (
        f"🚨 RCA Multi-Agent Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"- Correlated groups: {groups_count}\n"
        f"- Enriched host/event pairs: {enrichment_count}\n"
        f"- Root cause: {root_cause}\n"
        f"- Confidence: {confidence}\n"
        f"- Impact: {impact}\n"
        f"- ServiceDesk Plus: {'done' if sdp_done else 'skipped'}"
        + (f" (request_id={request_id})" if sdp_done else "")
    )


def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main(cli_request_id: Optional[str], input_payload: Optional[Dict[str, Any]]):
    z_task = asyncio.create_task(fetch_zabbix_problems())
    u_task = asyncio.create_task(fetch_uptimerobot_monitors())
    zbx, upr = await asyncio.gather(z_task, u_task)

    groups = correlate(zbx, upr)

    # Enrichment from hostname + eventid (best effort)
    pairs = []
    seen = set()

    # allow direct input mode: only hostname + eventid provided
    ip = input_payload or {}
    in_hostname = ip.get("hostname") or (ip.get("host") or {}).get("name")
    in_eventid = ip.get("eventid") or (ip.get("event") or {}).get("id")
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

    async def enrich_one(hostname: str, eventid: str) -> Dict[str, Any]:
        async with sem:
            return await zabbix_enrich_from_hostname_eventid(hostname, eventid)

    enrichments = await asyncio.gather(*(enrich_one(h, e) for h, e in pairs)) if pairs else []

    # Multi-agent orchestration
    collected = await collector_agent(groups, enrichments)
    corr_out = await correlation_agent(groups, collected)

    hypotheses = await hypothesis_agent(corr_out)
    verifier = await verifier_agent(corr_out, hypotheses)

    decision = await decision_agent(collected, corr_out, hypotheses, verifier)

    request_id = resolve_request_id(cli_request_id, input_payload)
    sdp_result = await run_sdp_flow(request_id, decision)
    sdp_done = sdp_result is not None

    report = render_report(decision, len(groups), len(enrichments), sdp_done, request_id)
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
