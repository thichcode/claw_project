#!/usr/bin/env python3
"""
RCA Multi-Agent Complete (Zabbix + UptimeRobot + LLM + Teams + SDP)
- Smart input parsing (LLM + regex fallback)
- Zabbix item enrichment with metric analysis
- Event time extraction & ±10 min time window
- SDP integration
- Async processing with caching
"""
 
import os, json, time, hashlib, sqlite3, asyncio, re, argparse
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import requests
import urllib3
 
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 
# ===== CONFIG LOADER =====
def _load_config() -> dict:
    """Load config from config.json, fallback to environment variables."""
    config_file = os.getenv("RCA_CONFIG_FILE", "config.json")
   
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {config_file}: {e}. Using environment variables.")
   
    return {
        "llm": {
            "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            "api_key": os.getenv("LLM_API_KEY", "ollama"),
            "model": os.getenv("LLM_MODEL", "mistral"),
            "timeout": float(os.getenv("LLM_TIMEOUT", "120"))
        },
        "zabbix": {
            "url": os.getenv("ZABBIX_URL", ""),
            "token": os.getenv("ZABBIX_TOKEN", ""),
            "timeout": float(os.getenv("ZBX_TIMEOUT", "30"))
        },
        "uptimerobot": {
            "api_key": os.getenv("UPTIMEROBOT_API_KEY", ""),
            "timeout": float(os.getenv("UR_TIMEOUT", "30"))
        },
        "teams": {
            "webhook_url": os.getenv("TEAMS_WEBHOOK_URL", ""),
            "timeout": float(os.getenv("TEAMS_TIMEOUT", "10"))
        },
        "sdp": {
            "url": os.getenv("SDP_URL", ""),
            "technician_key": os.getenv("SDP_TECHNICIAN_KEY", ""),
            "request_id": os.getenv("SDP_REQUEST_ID", "")
        },
        "concurrency": {
            "llm": int(os.getenv("LLM_CONCURRENCY", "1")),
            "zabbix": int(os.getenv("ZBX_CONCURRENCY", "5")),
            "uptimerobot": int(os.getenv("UR_CONCURRENCY", "3"))
        },
        "http": {
            "timeout": float(os.getenv("HTTP_TIMEOUT", "30"))
        },
        "cache": {
            "db_path": os.getenv("RCA_CACHE_DB", "rca_cache.db"),
            "ttl_zabbix": int(os.getenv("TTL_ZBX", "120")),
            "ttl_uptimerobot": int(os.getenv("TTL_UR", "120")),
            "ttl_llm": int(os.getenv("TTL_LLM", "86400"))
        }
    }
 
_CONFIG = _load_config()
 
# ===== CONFIG =====
LLM_BASE = _CONFIG["llm"]["base_url"]
LLM_KEY = _CONFIG["llm"]["api_key"]
LLM_MODEL = _CONFIG["llm"]["model"]
LLM_TIMEOUT = _CONFIG["llm"].get("timeout", 120)
 
ZABBIX_URL = _CONFIG["zabbix"]["url"]
ZABBIX_TOKEN = _CONFIG["zabbix"]["token"]
ZBX_TIMEOUT = _CONFIG["zabbix"].get("timeout", 30)
 
UPTIMEROBOT_KEY = _CONFIG["uptimerobot"]["api_key"]
UR_TIMEOUT = _CONFIG["uptimerobot"].get("timeout", 30)
 
TEAMS_WEBHOOK = _CONFIG["teams"]["webhook_url"]
TEAMS_TIMEOUT = _CONFIG["teams"].get("timeout", 10)
 
SDP_URL = _CONFIG["sdp"]["url"]
SDP_TECHNICIAN_KEY = _CONFIG["sdp"]["technician_key"]
SDP_REQUEST_ID = _CONFIG["sdp"]["request_id"]
 
SEM_LLM = asyncio.Semaphore(_CONFIG["concurrency"]["llm"])
SEM_ZBX = asyncio.Semaphore(_CONFIG["concurrency"]["zabbix"])
SEM_UR = asyncio.Semaphore(_CONFIG["concurrency"]["uptimerobot"])
 
HTTP_TIMEOUT = _CONFIG["http"]["timeout"]
CACHE_DB = _CONFIG["cache"]["db_path"]
TTL_ZBX_DEFAULT = _CONFIG["cache"]["ttl_zabbix"]
TTL_UR_DEFAULT = _CONFIG["cache"]["ttl_uptimerobot"]
TTL_LLM_DEFAULT = _CONFIG["cache"]["ttl_llm"]
 
# ===== SQLite Cache =====
def _db_init():
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL, ts INTEGER NOT NULL)")
    conn.commit()
    conn.close()
 
_db_init()
 
def _cache_key(prefix: str, payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prefix + '|' + data).encode('utf-8')).hexdigest()
 
def cache_get(key: str, ttl: int) -> Optional[Any]:
    now = int(time.time())
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("SELECT v, ts FROM cache WHERE k=?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    v_str, ts = row
    if now - ts > ttl:
        return None
    try:
        return json.loads(v_str)
    except:
        return None
 
def cache_set(key: str, val: Any):
    now = int(time.time())
    v_str = json.dumps(val, ensure_ascii=False)
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("REPLACE INTO cache(k, v, ts) VALUES(?,?,?)", (key, v_str, now))
    conn.commit()
    conn.close()
 
# ===== Time Extraction =====
def _parse_event_time(description_text: str) -> Optional[int]:
    if not description_text:
        return None
   
    match = re.search(r'(\d{2}):(\d{2}):(\d{2})/(\d{4})\.(\d{2})\.(\d{2})', description_text)
    if match:
        try:
            hour, minute, second, year, month, day = map(int, match.groups())
            dt = datetime(year, month, day, hour, minute, second)
            return int(dt.timestamp())
        except ValueError:
            pass
   
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})', description_text)
    if match:
        try:
            year, month, day, hour, minute, second = map(int, match.groups())
            dt = datetime(year, month, day, hour, minute, second)
            return int(dt.timestamp())
        except ValueError:
            pass
   
    return None
 
def _get_time_window(event_time_epoch: int, window_minutes: int = 10) -> dict:
    window_seconds = window_minutes * 60
    start_time = event_time_epoch - window_seconds
    end_time = event_time_epoch + window_seconds
   
    return {
        "start": start_time,
        "end": end_time,
        "start_readable": datetime.fromtimestamp(start_time).isoformat(),
        "end_readable": datetime.fromtimestamp(end_time).isoformat()
    }
 
# ===== JSON Helpers =====
async def _post_json(url: str, *, json_body: Optional[dict] = None, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: float = HTTP_TIMEOUT) -> dict:
    def _do_post():
        resp = requests.post(url, json=json_body, data=data, headers=headers, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp.json()
    return await asyncio.to_thread(_do_post)
 
def _sanitize_json_output(content: str) -> str:
    content = content.replace("```json", "").replace("```", "").strip()
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        content = json_match.group(0)
    return content
 
def _fix_json_string(content: str) -> str:
    result = []
    in_string = False
    escape_next = False
   
    for i, char in enumerate(content):
        if escape_next:
            result.append(char)
            escape_next = False
            continue
       
        if char == '\\':
            result.append(char)
            escape_next = True
            continue
       
        if char == '"' and (i == 0 or content[i-1] != '\\'):
            in_string = not in_string
            result.append(char)
            continue
       
        if in_string:
            if char == '\n':
                result.append('\\n')
                continue
            elif char == '\r':
                result.append('\\r')
                continue
            elif char == '\t':
                result.append('\\t')
                continue
       
        result.append(char)
   
    return ''.join(result)
 
# ===== PROMPTS =====
PROMPT_INPUT_EXTRACTOR = (
    "You are Input Extractor.\n"
    "Goal: Extract structured data from unstructured input text.\n"
    "\n"
    "Instructions:\n"
    "- Extract: hostname, eventid, ip, service, trigger, severity, description.\n"
    "- Handle various formats:\n"
    "  * 'hostname:eventid' → {hostname, eventid}\n"
    "  * 'hostname 1308284088' → {hostname, eventid}\n"
    "  * 'SSH service down on host1' → {hostname, service, trigger}\n"
    "  * Full text with embedded data → extract all fields\n"
    "- If a field is missing, set null (do NOT invent).\n"
    "- Output strictly JSON: {hostname, eventid, ip, service, trigger, severity, description}.\n"
    "\n"
    "Return only JSON. No prose."
)
 
PROMPT_PARSER = (
    "You are Event Parser & Normalizer.\n"
    "Goal: Parse one monitoring event (Zabbix or UptimeRobot) and output IncidentContext JSON.\n"
    "\n"
    "Instructions:\n"
    "- Extract: service/app, system/group, env, host, ip, domain, trigger, severity, last_check_epoch, monitor_source.\n"
    "- If a field is missing, set null (do NOT invent).\n"
    "- Derive 'is_web' if subject/description contains web/http/url/web.test.\n"
    "- Keep original text in 'raw.description'.\n"
    "- Output strictly IncidentContext JSON schema.\n"
    "\n"
    "Return only JSON. No prose."
)
 
PROMPT_EVIDENCE_ENRICHED = (
    "You are Evidence Synthesizer with deep metric analysis.\n"
    "Goal: Analyze Zabbix metrics (CPU, Memory, Disk, Network) + events + problems to identify patterns.\n"
    "\n"
    "Instructions:\n"
    "- Examine metric trends (↑ increasing, ↓ decreasing, → stable)\n"
    "- Identify anomalies: sudden spikes, drops, or sustained high values\n"
    "- Correlate metrics with events/problems timeline\n"
    "- Look for cascading failures (e.g., high CPU → high memory → service down)\n"
    "- Output Evidence JSON with: timeline, metric_analysis, anomalies, root_indicators, observations.\n"
    "\n"
    "Return only JSON."
)
 
PROMPT_HYPOTHESIS = (
    "You are Hypothesis & Scoring.\n"
    "Given Evidence JSON produce: { 'hypotheses':[...], 'best':'H1', 'confidence':0.xx } (0..1).\n"
    "Be conservative if data missing. Return only JSON."
)
 
PROMPT_RCA = (
    "You are RCA Writer & Formatter.\n"
    "Input: incident + evidence + hypotheses.\n"
    "Output JSON: { 'rca': {...}, 'summary_markdown': '...' }\n"
    "If confidence < 0.5, phrase as Likely causes and list missing data. Provide actionable steps for L1.\n"
    "\n"
    "IMPORTANT: Return ONLY valid JSON. Ensure:\n"
    "- All newlines in string values are escaped as \\n\n"
    "- All quotes are properly escaped\n"
    "- No trailing commas\n"
    "- No comments\n"
    "Return only JSON."
)
 
# ===== LLM Agent =====
async def call_llm(system_prompt: str, user_input: Any, ttl: int = TTL_LLM_DEFAULT) -> Any:
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)}
        ]
    }
    key = _cache_key("LLM", {"sp": system_prompt, "u": user_input, "model": LLM_MODEL})
    cached = cache_get(key, ttl)
    if cached is not None:
        print(f"✓ LLM cache hit")
        return cached
 
    async with SEM_LLM:
        try:
            print(f"📡 Calling LLM ({LLM_MODEL}) with {LLM_TIMEOUT}s timeout...")
            res = await _post_json(
                f"{LLM_BASE}/v1/chat/completions",
                json_body=payload,
                headers={
                    "Authorization": f"Bearer {LLM_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=LLM_TIMEOUT
            )
        except requests.exceptions.Timeout:
            print(f"⏱️  LLM timeout after {LLM_TIMEOUT}s.")
            return {"_error": f"LLM timeout after {LLM_TIMEOUT}s", "raw": ""}
        except Exception as e:
            print(f"❌ LLM error: {e}")
            return {"_error": str(e), "raw": ""}
   
    content = res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    content = _sanitize_json_output(content)
   
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        try:
            content_fixed = _fix_json_string(content)
            data = json.loads(content_fixed)
        except json.JSONDecodeError as e2:
            print(f"❌ JSON parse error: {e2}")
            data = {"_error": f"LLM JSON parse failed: {e2}", "raw": content[:1000]}
   
    cache_set(key, data)
    return data
 
# ===== Input Parser =====
async def extract_input_with_llm(raw_input: str) -> Dict[str, Any]:
    if not raw_input:
        return {}
   
    print(f"🔍 Extracting input data with LLM...")
   
    result = await call_llm(PROMPT_INPUT_EXTRACTOR, {
        "raw_input": raw_input,
        "input_type": "text"
    })
   
    if result.get("_error"):
        print(f"  ⚠️  LLM extraction error: {result.get('_error')}")
        return {}
   
    print(f"  ✓ Extracted: hostname={result.get('hostname')}, eventid={result.get('eventid')}")
    return result
# ===== SDP Ticket ID Extraction (ĐẶT TRƯỚC) =====
def extract_sdp_ticket_id(url: str) -> Optional[str]:
    """Extract SDP ticket ID from URL."""
    if not url:
        return None
   
    match = re.search(r'woID=(\d+)', url)
    if match:
        return match.group(1)
   
    match = re.search(r'/requests/(\d+)', url)
    if match:
        return match.group(1)
   
    match = re.search(r'/workorder/(\d+)', url)
    if match:
        return match.group(1)
   
    return None
 
# ===== Input Parser =====
async def extract_input_with_llm(raw_input: str) -> Dict[str, Any]:
    if not raw_input:
        return {}
   
    print(f"🔍 Extracting input data with LLM...")
   
    result = await call_llm(PROMPT_INPUT_EXTRACTOR, {
        "raw_input": raw_input,
        "input_type": "text"
    })
   
    if result.get("_error"):
        print(f"  ⚠️  LLM extraction error: {result.get('_error')}")
        return {}
   
    print(f"  ✓ Extracted: hostname={result.get('hostname')}, eventid={result.get('eventid')}")
    return result
 
def extract_input_with_regex(raw_input: str) -> Dict[str, Any]:
    """Enhanced regex extraction with SDP ticket ID support."""
    if not raw_input:
        return {}
   
    extracted = {
        "hostname": None,
        "eventid": None,
        "ip": None,
        "service": None,
        "trigger": None,
        "severity": None,
        "sdp_ticket_id": None,
        "description": raw_input
    }
   
    # Extract SDP ticket ID from URL FIRST
    url_match = re.search(r'https?://[^\s]+|"\s*:\s*"[^"]*WorkOrder[^"]*"', raw_input)
    if url_match:
        url = url_match.group(0).strip('"').strip()
        sdp_id = extract_sdp_ticket_id(url)
        if sdp_id:
            extracted["sdp_ticket_id"] = sdp_id
            print(f"  ✓ Extracted SDP ticket ID from URL: {sdp_id}")
 
    match = re.search(r'(\w+[-\w]*)\s*[:|\s]\s*(\d{8,})', raw_input)
    if match:
        extracted["hostname"] = match.group(1)
        extracted["eventid"] = match.group(2)
        return extracted
   
    hostname_match = re.search(r'(?:host|server|node)[\s:=]+([a-zA-Z0-9_-]+)', raw_input, re.IGNORECASE)
    eventid_match = re.search(r'(?:eventid|event_id|event)[\s:=]+(\d{8,})', raw_input, re.IGNORECASE)
   
    if hostname_match:
        extracted["hostname"] = hostname_match.group(1)
    if eventid_match:
        extracted["eventid"] = eventid_match.group(1)
   
    ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', raw_input)
    if ip_match:
        extracted["ip"] = ip_match.group(0)
   
    service_match = re.search(r'(?:service|app|application)[\s:=]+([a-zA-Z0-9_-]+)', raw_input, re.IGNORECASE)
    if service_match:
        extracted["service"] = service_match.group(1)
   
    severity_match = re.search(r'(?:severity|level)[\s:=]+(critical|high|medium|low|info)', raw_input, re.IGNORECASE)
    if severity_match:
        extracted["severity"] = severity_match.group(1)
   
    trigger_match = re.search(r'(?:trigger|issue|problem|alert)[\s:=]+([^,\n]+)', raw_input, re.IGNORECASE)
    if trigger_match:
        extracted["trigger"] = trigger_match.group(1).strip()
   
    return extracted
 
async def parse_input_smart(raw_input: str, use_llm: bool = True) -> Dict[str, Any]:
    """Smart input parser with SDP ticket ID support."""
    if not raw_input or not isinstance(raw_input, str):
        return {}
   
    print(f"\n📥 Parsing input: {raw_input[:100]}...")
   
    if use_llm and LLM_KEY:
        try:
            result = await extract_input_with_llm(raw_input)
            if result and not result.get("_error"):
                return result
        except Exception as e:
            print(f"  ⚠️  LLM parsing failed: {e}, falling back to regex")
   
    print(f"  📋 Using regex extraction...")
    result = extract_input_with_regex(raw_input)
   
    # IMPORTANT: Keep sdp_ticket_id even if None
    return {k: v for k, v in result.items() if v is not None or k == "sdp_ticket_id"}
def extract_input_with_regex(raw_input: str) -> Dict[str, Any]:
    if not raw_input:
        return {}
   
    extracted = {
        "hostname": None,
        "eventid": None,
        "ip": None,
        "service": None,
        "trigger": None,
        "severity": None,
        "sdp_ticket_id": None,
        "description": raw_input
    }
    # Extract SDP ticket ID from URL
    url_match = re.search(r'https?://[^\s]+|"\s*:\s*"[^"]*WorkOrder[^"]*"', raw_input)
    if url_match:
        url = url_match.group(0).strip('"').strip()
        sdp_id = extract_sdp_ticket_id(url)
        if sdp_id:
            extracted["sdp_ticket_id"] = sdp_id
 
    match = re.search(r'(\w+[-\w]*)\s*[:|\s]\s*(\d{8,})', raw_input)
    if match:
        extracted["hostname"] = match.group(1)
        extracted["eventid"] = match.group(2)
        return extracted
   
    hostname_match = re.search(r'(?:host|server|node)[\s:=]+([a-zA-Z0-9_-]+)', raw_input, re.IGNORECASE)
    eventid_match = re.search(r'(?:eventid|event_id|event)[\s:=]+(\d{8,})', raw_input, re.IGNORECASE)
   
    if hostname_match:
        extracted["hostname"] = hostname_match.group(1)
    if eventid_match:
        extracted["eventid"] = eventid_match.group(1)
   
    ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', raw_input)
    if ip_match:
        extracted["ip"] = ip_match.group(0)
   
    service_match = re.search(r'(?:service|app|application)[\s:=]+([a-zA-Z0-9_-]+)', raw_input, re.IGNORECASE)
    if service_match:
        extracted["service"] = service_match.group(1)
   
    severity_match = re.search(r'(?:severity|level)[\s:=]+(critical|high|medium|low|info)', raw_input, re.IGNORECASE)
    if severity_match:
        extracted["severity"] = severity_match.group(1)
   
    trigger_match = re.search(r'(?:trigger|issue|problem|alert)[\s:=]+([^,\n]+)', raw_input, re.IGNORECASE)
    if trigger_match:
        extracted["trigger"] = trigger_match.group(1).strip()
   
    return extracted
 
 
async def normalize_event_input(event: Dict[str, Any]) -> Dict[str, Any]:
    print("\n=== NORMALIZING INPUT ===\n")
   
    # Extract SDP ticket ID from URL if present
    sdp_ticket_id = None
    if event.get("url"):
        sdp_ticket_id = extract_sdp_ticket_id(event.get("url"))
        if sdp_ticket_id:
            print(f"✓ Extracted SDP ticket ID: {sdp_ticket_id}")
   
    if event.get("id"):
        sdp_ticket_id = event.get("id")
        print(f"✓ Using SDP ticket ID from 'id' field: {sdp_ticket_id}")
   
    if event.get("hostname") and event.get("eventid"):
        print("✓ Input is already structured (hostname + eventid)")
        return {
            "host": event.get("hostname"),
            "eventid": event.get("eventid"),
            "ip": event.get("ip"),
            "service": event.get("service"),
            "trigger": event.get("trigger"),
            "severity": event.get("severity"),
            "description": event.get("description"),
            "sdp_ticket_id": sdp_ticket_id  # ← THÊM DÒNG NÀY
        }
   
    if event.get("subject") or event.get("description_text"):
        print("✓ Input is full event object, parsing with LLM...")
       
        combined_text = f"{event.get('subject', '')} {event.get('description_text', '')}"
       
        parsed = await parse_input_smart(combined_text, use_llm=True)
       
        incident = {
            "host": parsed.get("hostname") or event.get("host"),
            "eventid": parsed.get("eventid") or event.get("eventid"),
            "ip": parsed.get("ip") or event.get("ip"),
            "service": parsed.get("service"),
            "trigger": parsed.get("trigger") or event.get("trigger"),
            "severity": parsed.get("severity") or event.get("severity"),
            "description": event.get("description_text") or parsed.get("description"),
            "sdp_ticket_id": sdp_ticket_id or parsed.get("sdp_ticket_id"),  # ← THÊM DÒNG NÀY
            "raw_event": event
        }
       
        return incident
   
    # ... rest remains the same
   
    if isinstance(event, str):
        print("✓ Input is raw text, parsing with LLM...")
        parsed = await parse_input_smart(event, use_llm=True)
        return parsed
   
    if event.get("raw_input"):
        print("✓ Input has raw_input field, parsing...")
        parsed = await parse_input_smart(event.get("raw_input"), use_llm=True)
        return parsed
   
    print("⚠️  Unknown input format")
    return event
 
# ===== Zabbix API =====
async def zbx_api(method: str, params: dict, ttl: int = TTL_ZBX_DEFAULT) -> Any:
    key = _cache_key("ZBX", {"method": method, "params": params})
    cached = cache_get(key, ttl)
    if cached is not None:
        return cached
 
    async with SEM_ZBX:
        res = await _post_json(
            f"{ZABBIX_URL}/api_jsonrpc.php",
            json_body={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "auth": ZABBIX_TOKEN,
                "id": 1,
            },
            headers={"Content-Type": "application/json"},
            timeout=ZBX_TIMEOUT
        )
    if "result" in res:
        cache_set(key, res["result"])
        return res["result"]
    else:
        cache_set(key, {"_error": res})
        return {"_error": res}
 
async def zbx_get_event_clock(eventid: str) -> Optional[int]:
    if not eventid:
        return None
   
    events = await zbx_api("event.get", {
        "eventids": [str(eventid)],
        "output": ["eventid", "clock"],
        "limit": 1
    })
   
    if events:
        return int(events[0].get("clock", 0))
    return None
 
async def zbx_enrich_items(hostid: str, time_window: Optional[dict] = None, max_items: int = 15) -> Dict[str, Any]:
    if not time_window:
        print(f"    ⚠️  No time window, skipping enrichment")
        return {"items": [], "metrics": {}}
   
    start_time = time_window.get("start")
    end_time = time_window.get("end")
   
    print(f"  🔍 Enriching items for hostid={hostid}...")
   
    items = await zbx_api("item.get", {
        "hostids": [hostid],
        "output": ["itemid", "name", "key_", "value_type", "units", "lastvalue"],
        "search": {"key_": ["cpu", "memory", "disk", "net", "service", "ping", "uptime"]},
        "searchByAny": True,
        "sortfield": "name",
        "limit": max_items
    })
   
    if not items:
        print(f"    ⚠️  No items found")
        return {"items": [], "metrics": {}}
   
    print(f"    ✓ Found {len(items)} items")
   
    sem = asyncio.Semaphore(_CONFIG["concurrency"]["zabbix"])
   
    async def fetch_item_history(item: dict) -> Optional[Dict[str, Any]]:
        async with sem:
            itemid = item.get("itemid")
            value_type = int(item.get("value_type", 0))
           
            if value_type not in (0, 3):
                return None
           
            history = await zbx_api("history.get", {
                "itemids": [itemid],
                "time_from": start_time,
                "time_till": end_time,
                "output": "extend",
                "sortfield": "clock",
                "limit": 100
            })
           
            if not history:
                return None
           
            values = []
            for h in history:
                try:
                    val = float(h.get("value", 0))
                    ts = int(h.get("clock", 0))
                    values.append({"ts": ts, "value": val})
                except (ValueError, TypeError):
                    pass
           
            if not values:
                return None
           
            nums = [v["value"] for v in values]
            stats = {
                "count": len(nums),
                "min": min(nums),
                "max": max(nums),
                "avg": sum(nums) / len(nums),
                "latest": nums[-1],
                "delta": max(nums) - min(nums),
                "trend": "↑" if nums[-1] > nums[0] else "↓" if nums[-1] < nums[0] else "→"
            }
           
            return {
                "itemid": itemid,
                "name": item.get("name"),
                "key": item.get("key_"),
                "units": item.get("units", ""),
                "lastvalue": item.get("lastvalue"),
                "stats": stats,
                "history": values
            }
   
    enriched_items = []
    results = await asyncio.gather(*(fetch_item_history(i) for i in items), return_exceptions=False)
    enriched_items = [r for r in results if r is not None]
   
    enriched_items.sort(key=lambda x: x.get("stats", {}).get("delta", 0), reverse=True)
   
    print(f"    ✓ Enriched {len(enriched_items)} items with history")
   
    metrics_summary = {}
    for item in enriched_items:
        key = item.get("key", "unknown")
        stats = item.get("stats", {})
        metrics_summary[key] = {
            "name": item.get("name"),
            "units": item.get("units"),
            "latest": stats.get("latest"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "avg": stats.get("avg"),
            "delta": stats.get("delta"),
            "trend": stats.get("trend")
        }
   
    return {
        "items": enriched_items,
        "metrics": metrics_summary
    }
 
async def collect_zabbix_evidence(incident: dict, time_window: Optional[dict] = None) -> Dict[str, Any]:
    if not (ZABBIX_URL and ZABBIX_TOKEN):
        return {}
   
    hostname = incident.get("host")
    eventid = incident.get("eventid")
    ip = incident.get("ip")
   
    if not (hostname or eventid or ip):
        print("  ⚠️  No hostname, eventid, or IP provided")
        return {}
   
    print("📊 Collecting Zabbix evidence...")
   
    try:
        hosts = None
       
        # ✅ Try search by hostname first
        if hostname:
            print(f"  🔍 Searching by hostname: {hostname}")
            hosts = await zbx_api("host.get", {
                "filter": {"host": [hostname]},
                "output": ["hostid", "host", "name", "status"],
                "limit": 1
            })
            if hosts:
                print(f"  ✓ Found by hostname")
       
        # ✅ Fallback: search by IP if hostname not found
        if not hosts and ip:
            print(f"  🔍 Searching by IP: {ip}")
            hosts = await zbx_api("host.get", {
                "filter": {"ip": [ip]},
                "output": ["hostid", "host", "name", "status"],
                "limit": 1
            })
            if hosts:
                print(f"  ✓ Found by IP")
       
        # ✅ Fallback: search by eventid if still not found
        if not hosts and eventid:
            print(f"  🔍 Searching by eventid: {eventid}")
            events = await zbx_api("event.get", {
                "eventids": [str(eventid)],
                "output": ["eventid", "objectid"],
                "limit": 1
            })
            if not events:
                print("  ⚠️  Event not found")
                return {}
           
            trigger_id = events[0].get("objectid")
            triggers = await zbx_api("trigger.get", {
                "triggerids": [str(trigger_id)],
                "output": ["triggerid"],
                "selectHosts": ["hostid", "host", "name", "status"],
                "limit": 1
            })
           
            if not triggers or not triggers[0].get("hosts"):
                print("  ⚠️  Host not found from trigger")
                return {}
           
            hosts = triggers[0].get("hosts")
            if hosts:
                print(f"  ✓ Found by eventid → trigger → host")
       
        if not hosts:
            print("  ⚠️  Host not found by any method (hostname, IP, or eventid)")
            return {}
       
        hostid = hosts[0]["hostid"]
        hostname = hosts[0].get("host") or hosts[0].get("name")
        print(f"  ✓ Host: {hostname} (hostid={hostid})")
       
        if not time_window and eventid:
            event_clock = await zbx_get_event_clock(eventid)
            if event_clock:
                time_window = _get_time_window(event_clock, window_minutes=10)
                print(f"  ✓ Event clock: {event_clock}")
                print(f"  ✓ Time window: {time_window['start_readable']} to {time_window['end_readable']}")
       
        problems_task = asyncio.create_task(zbx_api("problem.get", {
            "hostids": [hostid],
            "output": "extend",
            "selectTags": "extend",
            "limit": 100
        }))
       
        events_task = asyncio.create_task(zbx_api("event.get", {
            "hostids": [hostid],
            "time_from": time_window.get("start") if time_window else int(time.time()) - 3600,
            "time_till": time_window.get("end") if time_window else int(time.time()),
            "output": "extend",
            "sortfield": "clock",
            "limit": 100
        })) if time_window else None
       
        maintenance_task = asyncio.create_task(zbx_api("maintenance.get", {
            "hostids": [hostid],
            "output": "extend",
            "limit": 10
        }))
       
        enrichment_task = asyncio.create_task(zbx_enrich_items(hostid, time_window, max_items=15))
       
        problems = await problems_task
        events = await events_task if events_task else []
        maintenance = await maintenance_task
        enrichment = await enrichment_task
       
        print(f"  ✓ Problems: {len(problems)}, Events: {len(events)}, Maintenance: {len(maintenance)}")
       
        return {
            "host": {
                "hostid": hostid,
                "hostname": hostname,
                "status": hosts[0].get("status")
            },
            "problems": problems,
            "events": events,
            "maintenance": maintenance,
            "enrichment": enrichment,
            "time_window": time_window
        }
   
    except Exception as e:
        print(f"  ❌ Zabbix error: {e}")
        return {}
 
# ===== SDP Integration =====
async def sdp_update_solution(request_id: str, text: str) -> Dict[str, Any]:
    if not SDP_URL or not SDP_TECHNICIAN_KEY:
        print("⚠️  SDP not configured, skipping")
        return {}
   
    try:
        return await _post_json(
            f"{SDP_URL}/api/v3/requests/{request_id}",
            json_body={"request": {"resolution": {"content": text}}},
            headers={"TECHNICIAN_KEY": SDP_TECHNICIAN_KEY},
            timeout=HTTP_TIMEOUT
        )
    except Exception as e:
        print(f"⚠️  SDP error: {e}")
        return {}
 
# ===== Main Orchestration =====
async def run_full_rca(event: Dict[str, Any]) -> dict:
    print("\n=== RCA PIPELINE ===\n")
   
    incident = await normalize_event_input(event)
   
    # ✅ FIX: Use local variable instead of global
    sdp_request_id = incident.get("sdp_ticket_id") or SDP_REQUEST_ID
   
    if sdp_request_id and sdp_request_id != SDP_REQUEST_ID:
        print(f"✓ Using SDP_REQUEST_ID from input: {sdp_request_id}")
    elif not sdp_request_id:
        print(f"⚠️  No SDP request ID found")
   
    if not incident.get("host") and not incident.get("eventid"):
        print("⚠️  Could not extract hostname/eventid, trying full LLM parse...")
        incident = await call_llm(PROMPT_PARSER, event)
   
    description_text = incident.get("description") or event.get("description_text", "")
    event_time_epoch = _parse_event_time(description_text)
   
    if event_time_epoch:
        incident["event_time_epoch"] = event_time_epoch
        incident["time_window"] = _get_time_window(event_time_epoch, window_minutes=10)
        print(f"Event time (epoch): {event_time_epoch}")
        print(f"Time window: {incident['time_window']['start_readable']} to {incident['time_window']['end_readable']}")
   
    zbx_raw = await collect_zabbix_evidence(incident, incident.get("time_window"))
   
    evidence = await call_llm(PROMPT_EVIDENCE_ENRICHED, {
        "incident": incident,
        "zabbix_evidence": zbx_raw,
        "time_window": incident.get("time_window")
    })
   
    hypotheses = await call_llm(PROMPT_HYPOTHESIS, evidence)
   
    rca = await call_llm(PROMPT_RCA, {
        "incident": incident,
        "evidence": evidence,
        "hypotheses": hypotheses
    })
   
    print("✓ RCA complete\n")
   
    # ✅ FIX: Use local variable sdp_request_id
    if SDP_URL and SDP_TECHNICIAN_KEY and sdp_request_id:
        print("📤 Updating SDP...")
        print(f"  📤 Using request ID: {sdp_request_id}")
        rca_text = rca.get("summary_markdown", json.dumps(rca, indent=2))
        await sdp_update_solution(sdp_request_id, rca_text)
        print("✓ SDP updated\n")
   
    return rca
 
# ===== Main =====
if __name__ == "__main__":
    test_input_1 = "hostname:1308284088"
   
    test_input_2 = "hostname 1308284088"
   
    test_input_3 = "SSH service down on host hostname (10.243.87.211) eventid 1308284088 severity high"
   
    test_input_4 = {
        "id": "4562797",
        "subject": " hostname hostname:10.243.87.211 SSH service is Down (0) eventid:1308284088",
        "description_text": "Trigger: hostname:10.243.87.211 SSH service is Down (0)\nTrigger status: PROBLEM\nTrigger severity: High\nMonitorFrom:zabbix_fci_ldz\nItem values:\n1. SSH service status (hostname|10.243.87.211|net.tcp.service[ssh,,22]): Down (0)\n2. [ Zabbix ] System information (hostname:system.uname): Linux data-elk 6.8.0-60-generic\n---\nEmail sent from zmonitor.domain\nLast check: 14:55:35/2026.02.25",
        "url": "[MASKED]/WorkOrder.do?woMode=viewWO&woID=4562797"
    }
   
    test_input_5 =   {
    "id": "4565849",
    "subject": " hostname hostname:10.243.16.60 Available memory on server 1.43 GB less than 5 % TotalMEM eventid:1312158100",
    "description_text": "Trigger: hostname:10.243.16.60 Available memory on server 1.43 GB less than 5 % TotalMEM \nTrigger status: PROBLEM \nTrigger severity: Average \nMonitorFrom:zabbix_fci_ldz \nItem values: \n1. [ RAM ] Available memory (%) (hostname|10.243.16.60|vm.memory.size[pavailable]): 4.34 % \n2. [ RAM ] Available memory (hostname:vm.memory.size[available]): 1.78 GB \n--- \nEmail sent from zmonitor.domain \nLast check: 15:49:03/2026.02.26",
    "url": "https://spd_url/WorkOrder.do?woMode=viewWO&woID=4565849"
    }
   
    parser = argparse.ArgumentParser(description="RCA Multi-Agent Complete")
    parser.add_argument("--request-id", help="SDP request id")
    parser.add_argument("--demo", type=int, choices=[1,2,3,4,5], help="Run demo (1-5)")
    parser.add_argument("--input", help="Raw input text")
    args = parser.parse_args()
   
    if args.request_id:
        os.environ["SDP_REQUEST_ID"] = args.request_id
   
    async def _main():
        test_cases = {
            1: test_input_1,
            2: test_input_2,
            3: test_input_3,
            4: test_input_4,
            5: test_input_5
        }
       
        if args.input:
            print(f"\n🎯 Running with custom input: {args.input}\n")
            result = await run_full_rca({"raw_input": args.input})
        elif args.demo:
            print(f"\n🎯 Running demo case {args.demo}\n")
            result = await run_full_rca(test_cases[args.demo])
        else:
            print(f"\n🎯 Running demo case 4 (full event)\n")
            result = await run_full_rca(test_input_4)
       
        print(json.dumps(result, ensure_ascii=False, indent=2))
   
    asyncio.run(_main())