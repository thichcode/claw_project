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

# key = "<chat_id>:<user_id>"
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
    if not ADMIN_USER_IDS:
        return True
    return user_id in ADMIN_USER_IDS


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
    url = f"{SDP_BASE_URL}{path}"
    resp = requests.get(url, headers=_sdp_headers(), params=params or {}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("response_status"):
        rs = data.get("response_status", [])
        if isinstance(rs, list) and rs and int(rs[0].get("status_code", 2000)) >= 4000:
            raise RuntimeError(f"SDP API error: {rs}")
    return data


def _sdp_post(path: str, input_data: dict) -> dict:
    if not SDP_BASE_URL:
        raise RuntimeError("Thiếu SDP_BASE_URL trong .env")
    url = f"{SDP_BASE_URL}{path}"
    payload = {"input_data": json.dumps(input_data, ensure_ascii=False)}
    resp = requests.post(url, headers=_sdp_headers(), data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("response_status"):
        rs = data.get("response_status", [])
        if isinstance(rs, list) and rs and int(rs[0].get("status_code", 2000)) >= 4000:
            raise RuntimeError(f"SDP API error: {rs}")
    return data


def _extract_list(data: dict, key: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    if key in data and isinstance(data[key], list):
        return data[key]
    resp = data.get("response", {}) if isinstance(data.get("response"), dict) else {}
    if key in resp and isinstance(resp[key], list):
        return resp[key]
    return []


def _extract_one(data: dict, key: str) -> dict | None:
    if not isinstance(data, dict):
        return None
    if key in data and isinstance(data[key], dict):
        return data[key]
    resp = data.get("response", {}) if isinstance(data.get("response"), dict) else {}
    if key in resp and isinstance(resp[key], dict):
        return resp[key]
    return None


def _extract_requests(data: dict) -> list[dict]:
    return _extract_list(data, "requests")


def _extract_request(data: dict) -> dict | None:
    return _extract_one(data, "request")


def _fmt_dt(ms_or_ts) -> str:
    try:
        s = str(ms_or_ts)
        iv = int(s)
        if iv > 10_000_000_000:
            iv //= 1000
        return datetime.fromtimestamp(iv).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ms_or_ts)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 ServiceDesk Plus Admin Bot ready.\n\n"
        "Commands:\n"
        "/requests [N] - list open requests\n"
        "/request <id> - request details\n"
        "/assign <id> <technician_name> - assign request\n"
        "/setstatus <id> <status_name> - update status\n"
        "/setpriority <id> <priority_name> - update priority\n"
        "/setgroup <id> <support_group_name> - update support group\n"
        "/addnote <id> <note text> - add note\n"
        "/technicians [N] - list technicians\n"
        "/statuses - list status names\n"
        "/priorities - list priority names\n"
        "/sgroups [N] - list support groups\n"
        "/sgcreate <name> [| description] - create support group (/confirm)\n"
        "/sgupdate <group_id> <new_name> [| description] - update support group (/confirm)\n"
        "/close <id> - close request (requires /confirm)\n"
        "/confirm - confirm pending dangerous action\n"
        "/cancel - cancel pending action\n"
        "/ping - health check\n\n"
        f"Your Telegram user id: {u.id}"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


async def requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))

    try:
        list_info = {"row_count": limit, "start_index": 1, "sort_field": "created_time", "sort_order": "desc"}
        input_data = {
            "list_info": list_info,
            "fields_required": ["id", "subject", "status", "priority", "requester", "technician", "group", "created_time"],
        }
        data = _sdp_get("/api/v3/requests", params={"input_data": json.dumps(input_data, ensure_ascii=False)})
        reqs = _extract_requests(data)

        if not reqs:
            await update.message.reply_text("No requests found.")
            return

        lines = [f"📋 Requests (top {limit})", ""]
        for i, r in enumerate(reqs, 1):
            rid = r.get("id", "?")
            subj = r.get("subject", "(no subject)")
            st = (r.get("status") or {}).get("name", "?") if isinstance(r.get("status"), dict) else str(r.get("status", "?"))
            pr = (r.get("priority") or {}).get("name", "?") if isinstance(r.get("priority"), dict) else str(r.get("priority", "?"))
            tech = (r.get("technician") or {}).get("name", "-") if isinstance(r.get("technician"), dict) else "-"
            grp = (r.get("group") or {}).get("name", "-") if isinstance(r.get("group"), dict) else "-"
            lines.append(f"{i}) #{rid} | {st} | {pr} | {tech} | grp:{grp}\n   {subj}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /request <id>")
        return

    rid = context.args[0]
    try:
        data = _sdp_get(f"/api/v3/requests/{rid}")
        r = _extract_request(data)
        if not r:
            await update.message.reply_text("Request not found.")
            return

        st = (r.get("status") or {}).get("name", "?") if isinstance(r.get("status"), dict) else str(r.get("status", "?"))
        pr = (r.get("priority") or {}).get("name", "?") if isinstance(r.get("priority"), dict) else str(r.get("priority", "?"))
        tech = (r.get("technician") or {}).get("name", "-") if isinstance(r.get("technician"), dict) else "-"
        reqr = (r.get("requester") or {}).get("name", "-") if isinstance(r.get("requester"), dict) else "-"
        grp = (r.get("group") or {}).get("name", "-") if isinstance(r.get("group"), dict) else "-"
        created = _fmt_dt((r.get("created_time") or {}).get("value") if isinstance(r.get("created_time"), dict) else r.get("created_time"))

        msg = (
            f"🧾 Request #{rid}\n"
            f"Subject: {r.get('subject', '(no subject)')}\n"
            f"Status: {st}\n"
            f"Priority: {pr}\n"
            f"Support Group: {grp}\n"
            f"Requester: {reqr}\n"
            f"Technician: {tech}\n"
            f"Created: {created}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /assign <id> <technician_name>")
        return

    rid = context.args[0]
    tech_name = " ".join(context.args[1:]).strip()

    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"technician": {"name": tech_name}}})
        await update.message.reply_text(f"✅ Assigned request #{rid} -> {tech_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setstatus <id> <status_name>")
        return

    rid = context.args[0]
    status_name = " ".join(context.args[1:]).strip()

    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"status": {"name": status_name}}})
        await update.message.reply_text(f"✅ Updated status for #{rid} -> {status_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setpriority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setpriority <id> <priority_name>")
        return

    rid = context.args[0]
    priority_name = " ".join(context.args[1:]).strip()

    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"priority": {"name": priority_name}}})
        await update.message.reply_text(f"✅ Updated priority for #{rid} -> {priority_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroup <id> <support_group_name>")
        return

    rid = context.args[0]
    group_name = " ".join(context.args[1:]).strip()

    try:
        _sdp_post(f"/api/v3/requests/{rid}", {"request": {"group": {"name": group_name}}})
        await update.message.reply_text(f"✅ Updated support group for #{rid} -> {group_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def addnote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /addnote <id> <note text>")
        return

    rid = context.args[0]
    note_text = " ".join(context.args[1:]).strip()

    try:
        _sdp_post(f"/api/v3/requests/{rid}/notes", {"note": {"description": note_text, "show_to_requester": False}})
        await update.message.reply_text(f"✅ Added note to request #{rid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def technicians(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 100))

    try:
        input_data = {"list_info": {"row_count": limit, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
        data = _sdp_get("/api/v3/technicians", params={"input_data": json.dumps(input_data, ensure_ascii=False)})
        rows = _extract_list(data, "technicians")
        if not rows:
            await update.message.reply_text("No technicians found.")
            return

        lines = [f"👨‍💻 Technicians (top {limit})", ""]
        for i, t in enumerate(rows, 1):
            tid = t.get("id", "?")
            name = t.get("name") or t.get("first_name", "(unknown)")
            email = t.get("email_id", "-")
            lines.append(f"{i}) #{tid} | {name} | {email}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def statuses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    try:
        data = _sdp_get("/api/v3/request_statuses")
        rows = _extract_list(data, "request_statuses") or _extract_list(data, "statuses")
        if not rows:
            await update.message.reply_text("No statuses found.")
            return

        lines = ["📌 Statuses", ""]
        for i, s in enumerate(rows, 1):
            sid = s.get("id", "?")
            name = s.get("name", "?")
            lines.append(f"{i}) #{sid} | {name}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def priorities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    try:
        data = _sdp_get("/api/v3/priorities")
        rows = _extract_list(data, "priorities")
        if not rows:
            await update.message.reply_text("No priorities found.")
            return

        lines = ["⚡ Priorities", ""]
        for i, p in enumerate(rows, 1):
            pid = p.get("id", "?")
            name = p.get("name", "?")
            lines.append(f"{i}) #{pid} | {name}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def sgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    limit = DEFAULT_LIMIT
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 100))

    try:
        input_data = {"list_info": {"row_count": limit, "start_index": 1, "sort_field": "name", "sort_order": "asc"}}
        data = _sdp_get("/api/v3/support_groups", params={"input_data": json.dumps(input_data, ensure_ascii=False)})
        rows = _extract_list(data, "support_groups")
        if not rows:
            await update.message.reply_text("No support groups found.")
            return

        lines = [f"👥 Support Groups (top {limit})", ""]
        for i, g in enumerate(rows, 1):
            gid = g.get("id", "?")
            name = g.get("name", "?")
            lines.append(f"{i}) #{gid} | {name}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def sgcreate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /sgcreate <name> [| description]")
        return

    raw = " ".join(context.args)
    parts = [x.strip() for x in raw.split("|", 1)]
    name = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    if not name:
        await update.message.reply_text("Support group name cannot be empty.")
        return

    _set_pending(chat_id, user_id, "sgcreate", {"name": name, "description": desc})
    await update.message.reply_text(
        f"⚠️ Confirm create support group: {name}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def sgupdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /sgupdate <group_id> <new_name> [| description]")
        return

    gid = context.args[0]
    raw = " ".join(context.args[1:])
    parts = [x.strip() for x in raw.split("|", 1)]
    name = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    if not name:
        await update.message.reply_text("New support group name cannot be empty.")
        return

    _set_pending(chat_id, user_id, "sgupdate", {"id": gid, "name": name, "description": desc})
    await update.message.reply_text(
        f"⚠️ Confirm update support group #{gid} -> {name}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def close_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /close <id>")
        return

    rid = context.args[0]
    _set_pending(chat_id, user_id, "close", {"id": rid})
    await update.message.reply_text(f"⚠️ Confirm close request #{rid}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel")


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _allowed(user_id):
        await update.message.reply_text("⛔ Not authorized.")
        return

    x = _get_pending(chat_id, user_id)
    if not x:
        await update.message.reply_text("No pending action or it expired.")
        return

    try:
        action = x.get("action")
        payload = x.get("payload", {})
        if action == "close":
            rid = payload.get("id")
            _sdp_post(f"/api/v3/requests/{rid}/close", {"request": {"closure_info": {"requester_ack_resolution": True}}})
            await update.message.reply_text(f"✅ Closed request #{rid}")
        elif action == "sgcreate":
            _sdp_post("/api/v3/support_groups", {"support_group": {"name": payload.get("name"), "description": payload.get("description", "")}})
            await update.message.reply_text(f"✅ Created support group: {payload.get('name')}")
        elif action == "sgupdate":
            gid = payload.get("id")
            _sdp_post(
                f"/api/v3/support_groups/{gid}",
                {"support_group": {"name": payload.get("name"), "description": payload.get("description", "")}},
            )
            await update.message.reply_text(f"✅ Updated support group #{gid} -> {payload.get('name')}")
        else:
            await update.message.reply_text("Unknown pending action.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        _clear_pending(chat_id, user_id)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    x = _get_pending(chat_id, user_id)
    if not x:
        await update.message.reply_text("No pending action.")
        return
    _clear_pending(chat_id, user_id)
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
