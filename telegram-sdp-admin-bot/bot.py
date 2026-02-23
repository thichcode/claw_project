import json
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SDP_BASE_URL = os.getenv("SDP_BASE_URL", "").rstrip("/")
SDP_API_KEY = os.getenv("SDP_API_KEY", "").strip()
ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "").strip()
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "10"))
CONFIRM_TIMEOUT_SEC = int(os.getenv("CONFIRM_TIMEOUT_SEC", "60"))

PENDING_ACTIONS: dict[str, dict] = {}


def _parse_admin_ids() -> set[int]:
    if not ADMIN_USER_IDS_RAW:
        return set()
    out = set()
    for x in ADMIN_USER_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit() or (x.startswith("-") and x[1:].isdigit()):
            out.add(int(x))
    return out


ADMIN_USER_IDS = _parse_admin_ids()


def _allowed(user_id: int) -> bool:
    return True if not ADMIN_USER_IDS else user_id in ADMIN_USER_IDS


def _pending_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _set_pending(chat_id: int, user_id: int, action: str, payload: dict):
    PENDING_ACTIONS[_pending_key(chat_id, user_id)] = {
        "action": action,
        "payload": payload,
        "expire_at": time.time() + max(10, CONFIRM_TIMEOUT_SEC),
    }


def _get_pending(chat_id: int, user_id: int) -> dict | None:
    key = _pending_key(chat_id, user_id)
    x = PENDING_ACTIONS.get(key)
    if not x:
        return None
    if time.time() > float(x.get("expire_at", 0)):
        PENDING_ACTIONS.pop(key, None)
        return None
    return x


def _clear_pending(chat_id: int, user_id: int):
    PENDING_ACTIONS.pop(_pending_key(chat_id, user_id), None)


def _sdp_headers() -> dict:
    if not SDP_API_KEY:
        raise RuntimeError("Thiếu SDP_API_KEY trong .env")
    return {
        "authtoken": SDP_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _sdp_get(path: str, params: dict | None = None) -> dict:
    if not SDP_BASE_URL:
        raise RuntimeError("Thiếu SDP_BASE_URL trong .env")
    resp = requests.get(f"{SDP_BASE_URL}{path}", headers=_sdp_headers(), params=params or {}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rs = data.get("response_status") if isinstance(data, dict) else None
    if isinstance(rs, list) and rs and int(rs[0].get("status_code", 2000)) >= 4000:
        raise RuntimeError(f"SDP API error: {rs}")
    return data


def _sdp_post(path: str, input_data: dict) -> dict:
    if not SDP_BASE_URL:
        raise RuntimeError("Thiếu SDP_BASE_URL trong .env")
    payload = {"input_data": json.dumps(input_data, ensure_ascii=False)}
    resp = requests.post(f"{SDP_BASE_URL}{path}", headers=_sdp_headers(), data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rs = data.get("response_status") if isinstance(data, dict) else None
    if isinstance(rs, list) and rs and int(rs[0].get("status_code", 2000)) >= 4000:
        raise RuntimeError(f"SDP API error: {rs}")
    return data


def _extract_list(data: dict, key: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    if isinstance(data.get(key), list):
        return data[key]
    resp = data.get("response") if isinstance(data.get("response"), dict) else {}
    if isinstance(resp.get(key), list):
        return resp[key]
    return []


def _extract_one(data: dict, key: str) -> dict | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get(key), dict):
        return data[key]
    resp = data.get("response") if isinstance(data.get("response"), dict) else {}
    if isinstance(resp.get(key), dict):
        return resp[key]
    return None


def _fmt_dt(ms_or_ts) -> str:
    try:
        iv = int(str(ms_or_ts))
        if iv > 10_000_000_000:
            iv //= 1000
        return datetime.fromtimestamp(iv).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ms_or_ts)


def _get_request_site_id(request_obj: dict) -> str | None:
    site = request_obj.get("site")
    if isinstance(site, dict):
        sid = site.get("id")
        return str(sid) if sid is not None else None
    return None


def _find_support_group_by_name_and_site(group_name: str, site_id: str | None) -> dict | None:
    input_data = {"list_info": {"row_count": 200, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
    data = _sdp_get("/api/v3/support_groups", params={"input_data": json.dumps(input_data, ensure_ascii=False)})
    rows = _extract_list(data, "support_groups")
    for g in rows:
        name = (g.get("name") or "").strip().lower()
        site = g.get("site") if isinstance(g.get("site"), dict) else {}
        g_site_id = str(site.get("id")) if site.get("id") is not None else None
        if name == group_name.strip().lower():
            if site_id is None or g_site_id == str(site_id):
                return g
    return None


def _get_all_technicians(limit: int = 500) -> list[dict]:
    input_data = {"list_info": {"row_count": limit, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
    return _extract_list(_sdp_get("/api/v3/technicians", params={"input_data": json.dumps(input_data, ensure_ascii=False)}), "technicians")


def _resolve_techaccounts(identifiers: list[str]) -> tuple[list[dict], list[str]]:
    """
    Resolve technician accounts by login_name first, then name.
    Returns: (technician_refs_for_payload, unresolved_identifiers)
    """
    techs = _get_all_technicians()
    by_login = {}
    by_name = {}
    for t in techs:
        login = str(t.get("login_name") or "").strip().lower()
        name = str(t.get("name") or t.get("first_name") or "").strip().lower()
        if login:
            by_login[login] = t
        if name:
            by_name[name] = t

    resolved = []
    missing = []
    seen_ids = set()
    for raw in identifiers:
        k = raw.strip().lower()
        if not k:
            continue
        t = by_login.get(k) or by_name.get(k)
        if not t:
            missing.append(raw)
            continue
        tid = t.get("id")
        if tid is None or str(tid) in seen_ids:
            continue
        seen_ids.add(str(tid))
        resolved.append({"id": str(tid), "name": t.get("name") or t.get("first_name") or raw})

    return resolved, missing


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 SDP Admin Bot (multi-site ready)\n\n"
        "Core:\n"
        "/requests [N], /request <id>, /assign <id> <tech>, /setstatus <id> <status>, /setpriority <id> <priority>\n"
        "/setgroup <id> <support_group_name> (auto-validate by request site)\n"
        "/addnote <id> <text>, /close <id> (/confirm)\n\n"
        "Lookup:\n"
        "/sites [N], /technicians [N], /statuses, /priorities, /sgroups [N] [site_id]\n\n"
        "Support Group admin (site-aware):\n"
        "/sgcreate <site_id> <name> | <techaccount1,techaccount2> [| description] (/confirm)\n"
        "/sgupdate <group_id> <site_id> <new_name> | <techaccount1,techaccount2> [| description] (/confirm)\n"
        "/confirm, /cancel, /ping\n\n"
        f"Your Telegram user id: {u.id}"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


async def requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))
    try:
        input_data = {
            "list_info": {"row_count": limit, "start_index": 1, "sort_field": "created_time", "sort_order": "desc"},
            "fields_required": ["id", "subject", "status", "priority", "requester", "technician", "group", "site", "created_time"],
        }
        data = _sdp_get("/api/v3/requests", params={"input_data": json.dumps(input_data, ensure_ascii=False)})
        reqs = _extract_list(data, "requests")
        if not reqs:
            await update.message.reply_text("No requests found.")
            return
        lines = [f"📋 Requests (top {limit})", ""]
        for i, r in enumerate(reqs, 1):
            rid = r.get("id", "?")
            st = (r.get("status") or {}).get("name", "?") if isinstance(r.get("status"), dict) else str(r.get("status", "?"))
            pr = (r.get("priority") or {}).get("name", "?") if isinstance(r.get("priority"), dict) else str(r.get("priority", "?"))
            grp = (r.get("group") or {}).get("name", "-") if isinstance(r.get("group"), dict) else "-"
            site = (r.get("site") or {}).get("name", "-") if isinstance(r.get("site"), dict) else "-"
            lines.append(f"{i}) #{rid} | {st} | {pr} | grp:{grp} | site:{site}\n   {r.get('subject', '(no subject)')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /request <id>")
        return
    rid = context.args[0]
    try:
        r = _extract_one(_sdp_get(f"/api/v3/requests/{rid}"), "request")
        if not r:
            await update.message.reply_text("Request not found.")
            return
        site = (r.get("site") or {}).get("name", "-") if isinstance(r.get("site"), dict) else "-"
        site_id = (r.get("site") or {}).get("id", "-") if isinstance(r.get("site"), dict) else "-"
        msg = (
            f"🧾 Request #{rid}\n"
            f"Subject: {r.get('subject', '(no subject)')}\n"
            f"Status: {(r.get('status') or {}).get('name', '?') if isinstance(r.get('status'), dict) else r.get('status', '?')}\n"
            f"Priority: {(r.get('priority') or {}).get('name', '?') if isinstance(r.get('priority'), dict) else r.get('priority', '?')}\n"
            f"Support Group: {(r.get('group') or {}).get('name', '-') if isinstance(r.get('group'), dict) else '-'}\n"
            f"Site: {site} (id={site_id})\n"
            f"Technician: {(r.get('technician') or {}).get('name', '-') if isinstance(r.get('technician'), dict) else '-'}\n"
            f"Created: {_fmt_dt((r.get('created_time') or {}).get('value') if isinstance(r.get('created_time'), dict) else r.get('created_time'))}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /assign <id> <technician_name>")
        return
    rid, tech_name = context.args[0], " ".join(context.args[1:]).strip()
    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"technician": {"name": tech_name}}})
        await update.message.reply_text(f"✅ Assigned request #{rid} -> {tech_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setstatus <id> <status_name>")
        return
    rid, name = context.args[0], " ".join(context.args[1:]).strip()
    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"status": {"name": name}}})
        await update.message.reply_text(f"✅ Updated status for #{rid} -> {name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setpriority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setpriority <id> <priority_name>")
        return
    rid, name = context.args[0], " ".join(context.args[1:]).strip()
    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"priority": {"name": name}}})
        await update.message.reply_text(f"✅ Updated priority for #{rid} -> {name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroup <request_id> <support_group_name>")
        return

    rid = context.args[0]
    group_name = " ".join(context.args[1:]).strip()
    try:
        req = _extract_one(_sdp_get(f"/api/v3/requests/{rid}"), "request")
        if not req:
            await update.message.reply_text("Request not found.")
            return

        site_id = _get_request_site_id(req)
        sg = _find_support_group_by_name_and_site(group_name, site_id)
        if not sg:
            await update.message.reply_text(
                f"Không tìm thấy group '{group_name}' thuộc site của request (site_id={site_id}).\n"
                "Dùng /sgroups 50 <site_id> để xem đúng danh sách."
            )
            return

        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"group": {"id": sg.get('id'), "name": sg.get('name')}}})
        await update.message.reply_text(f"✅ Updated support group for #{rid} -> {sg.get('name')} (id={sg.get('id')})")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def addnote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /addnote <id> <note text>")
        return
    rid, note_text = context.args[0], " ".join(context.args[1:]).strip()
    try:
        _sdp_post(f"/api/v3/requests/{rid}/notes", {"note": {"description": note_text, "show_to_requester": False}})
        await update.message.reply_text(f"✅ Added note to request #{rid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 200))
    try:
        input_data = {"list_info": {"row_count": limit, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
        rows = _extract_list(_sdp_get("/api/v3/sites", params={"input_data": json.dumps(input_data, ensure_ascii=False)}), "sites")
        if not rows:
            await update.message.reply_text("No sites found.")
            return
        lines = [f"🏢 Sites (top {limit})", ""]
        for i, s in enumerate(rows, 1):
            lines.append(f"{i}) site_id={s.get('id')} | {s.get('name', '?')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def technicians(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 100))
    try:
        input_data = {"list_info": {"row_count": limit, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
        rows = _extract_list(_sdp_get("/api/v3/technicians", params={"input_data": json.dumps(input_data, ensure_ascii=False)}), "technicians")
        if not rows:
            await update.message.reply_text("No technicians found.")
            return
        lines = [f"👨‍💻 Technicians (top {limit})", ""]
        for i, t in enumerate(rows, 1):
            login = t.get("login_name", "-")
            lines.append(
                f"{i}) #{t.get('id', '?')} | {t.get('name') or t.get('first_name', '(unknown)')} | login:{login} | {t.get('email_id', '-')}"
            )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def statuses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    try:
        rows = _extract_list(_sdp_get("/api/v3/request_statuses"), "request_statuses") or _extract_list(_sdp_get("/api/v3/request_statuses"), "statuses")
        if not rows:
            await update.message.reply_text("No statuses found.")
            return
        lines = ["📌 Statuses", ""]
        for i, s in enumerate(rows, 1):
            lines.append(f"{i}) #{s.get('id', '?')} | {s.get('name', '?')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def priorities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    try:
        rows = _extract_list(_sdp_get("/api/v3/priorities"), "priorities")
        if not rows:
            await update.message.reply_text("No priorities found.")
            return
        lines = ["⚡ Priorities", ""]
        for i, p in enumerate(rows, 1):
            lines.append(f"{i}) #{p.get('id', '?')} | {p.get('name', '?')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def sgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    limit = DEFAULT_LIMIT
    site_id = None
    args = context.args or []
    if len(args) >= 1 and args[0].isdigit():
        limit = max(1, min(int(args[0]), 100))
        if len(args) >= 2 and args[1].isdigit():
            site_id = args[1]
    elif len(args) >= 1 and args[0].isdigit() is False and len(args) == 1:
        site_id = args[0] if args[0].isdigit() else None

    try:
        input_data = {"list_info": {"row_count": 200, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
        rows = _extract_list(_sdp_get("/api/v3/support_groups", params={"input_data": json.dumps(input_data, ensure_ascii=False)}), "support_groups")
        if site_id:
            rows = [g for g in rows if isinstance(g.get("site"), dict) and str(g["site"].get("id")) == str(site_id)]
        rows = rows[:limit]
        if not rows:
            await update.message.reply_text("No support groups found.")
            return

        title = f"👥 Support Groups (top {len(rows)})"
        if site_id:
            title += f" | site_id={site_id}"
        lines = [title, ""]
        for i, g in enumerate(rows, 1):
            site = g.get("site") if isinstance(g.get("site"), dict) else {}
            lines.append(f"{i}) #{g.get('id', '?')} | {g.get('name', '?')} | site_id={site.get('id', '-')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def sgcreate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /sgcreate <site_id> <name> | <techaccount1,techaccount2> [| description]")
        return

    site_id = context.args[0]
    raw = " ".join(context.args[1:])
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        await update.message.reply_text("Thiếu techaccount. Ví dụ: /sgcreate 2 NOC Team | thuongdv2,anhnv")
        return

    name = parts[0]
    tech_csv = parts[1]
    desc = parts[2] if len(parts) > 2 else ""

    if not name:
        await update.message.reply_text("Support group name cannot be empty.")
        return

    tech_keys = [x.strip() for x in tech_csv.split(",") if x.strip()]
    if not tech_keys:
        await update.message.reply_text("Phải có ít nhất 1 techaccount.")
        return

    try:
        tech_refs, missing = _resolve_techaccounts(tech_keys)
    except Exception as e:
        await update.message.reply_text(f"❌ Error khi resolve technician: {e}")
        return

    if missing:
        await update.message.reply_text(f"Không tìm thấy techaccount: {', '.join(missing)}")
        return
    if not tech_refs:
        await update.message.reply_text("Không resolve được technician hợp lệ.")
        return

    _set_pending(
        update.effective_chat.id,
        update.effective_user.id,
        "sgcreate",
        {"site_id": site_id, "name": name, "description": desc, "technicians": tech_refs},
    )
    await update.message.reply_text(
        f"⚠️ Confirm create support group '{name}' on site_id={site_id} with {len(tech_refs)} technician(s)\n"
        f"Use /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def sgupdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 3 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text("Usage: /sgupdate <group_id> <site_id> <new_name> | <techaccount1,techaccount2> [| description]")
        return

    gid, site_id = context.args[0], context.args[1]
    raw = " ".join(context.args[2:])
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        await update.message.reply_text("Thiếu techaccount. Ví dụ: /sgupdate 12 2 NOC Team | thuongdv2")
        return

    name = parts[0]
    tech_csv = parts[1]
    desc = parts[2] if len(parts) > 2 else ""
    if not name:
        await update.message.reply_text("New support group name cannot be empty.")
        return

    tech_keys = [x.strip() for x in tech_csv.split(",") if x.strip()]
    if not tech_keys:
        await update.message.reply_text("Phải có ít nhất 1 techaccount.")
        return

    try:
        tech_refs, missing = _resolve_techaccounts(tech_keys)
    except Exception as e:
        await update.message.reply_text(f"❌ Error khi resolve technician: {e}")
        return

    if missing:
        await update.message.reply_text(f"Không tìm thấy techaccount: {', '.join(missing)}")
        return
    if not tech_refs:
        await update.message.reply_text("Không resolve được technician hợp lệ.")
        return

    _set_pending(
        update.effective_chat.id,
        update.effective_user.id,
        "sgupdate",
        {"id": gid, "site_id": site_id, "name": name, "description": desc, "technicians": tech_refs},
    )
    await update.message.reply_text(
        f"⚠️ Confirm update support group #{gid} on site_id={site_id} -> {name} with {len(tech_refs)} technician(s)\n"
        f"Use /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def close_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /close <id>")
        return
    rid = context.args[0]
    _set_pending(update.effective_chat.id, update.effective_user.id, "close", {"id": rid})
    await update.message.reply_text(f"⚠️ Confirm close request #{rid}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel")


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    x = _get_pending(update.effective_chat.id, update.effective_user.id)
    if not x:
        await update.message.reply_text("No pending action or it expired.")
        return

    try:
        action, payload = x.get("action"), x.get("payload", {})
        if action == "close":
            rid = payload.get("id")
            _sdp_post(f"/api/v3/requests/{rid}/close", {"request": {"closure_info": {"requester_ack_resolution": True}}})
            await update.message.reply_text(f"✅ Closed request #{rid}")
        elif action == "sgcreate":
            _sdp_post(
                "/api/v3/support_groups",
                {
                    "support_group": {
                        "name": payload.get("name"),
                        "description": payload.get("description", ""),
                        "site": {"id": payload.get("site_id")},
                        "technicians": payload.get("technicians", []),
                    }
                },
            )
            await update.message.reply_text(
                f"✅ Created support group '{payload.get('name')}' on site_id={payload.get('site_id')} with {len(payload.get('technicians', []))} technician(s)"
            )
        elif action == "sgupdate":
            _sdp_post(
                f"/api/v3/support_groups/{payload.get('id')}",
                {
                    "support_group": {
                        "name": payload.get("name"),
                        "description": payload.get("description", ""),
                        "site": {"id": payload.get("site_id")},
                        "technicians": payload.get("technicians", []),
                    }
                },
            )
            await update.message.reply_text(
                f"✅ Updated support group #{payload.get('id')} -> {payload.get('name')} (site_id={payload.get('site_id')}) with {len(payload.get('technicians', []))} technician(s)"
            )
        else:
            await update.message.reply_text("Unknown pending action.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        _clear_pending(update.effective_chat.id, update.effective_user.id)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    x = _get_pending(update.effective_chat.id, update.effective_user.id)
    if not x:
        await update.message.reply_text("No pending action.")
        return
    _clear_pending(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text("Cancelled pending action.")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("requests", requests_list))
    app.add_handler(CommandHandler("request", request_detail))
    app.add_handler(CommandHandler("assign", assign))
    app.add_handler(CommandHandler("setstatus", setstatus))
    app.add_handler(CommandHandler("setpriority", setpriority))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("addnote", addnote))
    app.add_handler(CommandHandler("sites", sites))
    app.add_handler(CommandHandler("technicians", technicians))
    app.add_handler(CommandHandler("statuses", statuses))
    app.add_handler(CommandHandler("priorities", priorities))
    app.add_handler(CommandHandler("sgroups", sgroups))
    app.add_handler(CommandHandler("sgcreate", sgcreate))
    app.add_handler(CommandHandler("sgupdate", sgupdate))
    app.add_handler(CommandHandler("close", close_req))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("cancel", cancel))

    print("ServiceDesk Plus admin bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
