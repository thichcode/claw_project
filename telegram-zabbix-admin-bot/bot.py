import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

ZABBIX_URL = os.getenv("ZABBIX_URL", "").rstrip("/")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN", "").strip()
ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "").strip()
CONFIRM_TIMEOUT_SEC = int(os.getenv("CONFIRM_TIMEOUT_SEC", "60"))

# In-memory pending confirmations:
# key: "<chat_id>:<user_id>" -> {"action": "enable|disable|maint_on|maint_off", ... , "expire_at": epoch}
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


def _is_allowed(user_id: int) -> bool:
    # If ADMIN_USER_IDS is empty, allow all (quick start). Recommend setting this in production.
    if not ADMIN_USER_IDS:
        return True
    return user_id in ADMIN_USER_IDS


def _zabbix_api(method: str, params: dict):
    if not ZABBIX_URL or not ZABBIX_API_TOKEN:
        raise RuntimeError("Thiếu ZABBIX_URL hoặc ZABBIX_API_TOKEN trong .env")

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }
    headers = {
        "Content-Type": "application/json-rpc",
        "Authorization": f"Bearer {ZABBIX_API_TOKEN}",
    }
    resp = requests.post(f"{ZABBIX_URL}/api_jsonrpc.php", json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"Zabbix API error {err.get('code')}: {err.get('data') or err.get('message')}")
    return data.get("result")


def _fmt_ts(ts: str | int) -> str:
    try:
        t = int(ts)
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _pending_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _set_pending(chat_id: int, user_id: int, action: str, hostid: str, query: str):
    PENDING_ACTIONS[_pending_key(chat_id, user_id)] = {
        "action": action,
        "hostid": hostid,
        "query": query,
        "expire_at": time.time() + max(10, CONFIRM_TIMEOUT_SEC),
    }


def _get_pending(chat_id: int, user_id: int) -> dict | None:
    k = _pending_key(chat_id, user_id)
    x = PENDING_ACTIONS.get(k)
    if not x:
        return None
    if time.time() > float(x.get("expire_at", 0)):
        PENDING_ACTIONS.pop(k, None)
        return None
    return x


def _clear_pending(chat_id: int, user_id: int):
    PENDING_ACTIONS.pop(_pending_key(chat_id, user_id), None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 Zabbix Admin Bot sẵn sàng.\n\n"
        "Lệnh:\n"
        "/problems [N] - Top N problems đang mở (mặc định 10)\n"
        "/hosts [N] - Top N hosts (mặc định 10)\n"
        "/host <host> - Xem nhanh trạng thái host\n"
        "/ack <eventid> <message> - Ack problem\n"
        "/groups [N] - List host groups (để lấy groupid)\n"
        "/templates [N] - List templates (để lấy templateid)\n"
        "/disable <host> - Yêu cầu disable host (cần /confirm)\n"
        "/enable <host> - Yêu cầu enable host (cần /confirm)\n"
        "/mainton <host> [minutes] - Bật maintenance (cần /confirm)\n"
        "/maintoff <host> - Tắt maintenance (cần /confirm)\n"
        "/confirm - Xác nhận thao tác đang chờ\n"
        "/cancel - Hủy thao tác đang chờ\n"
        "/ping - test bot\n\n"
        f"Your Telegram user id: {u.id}"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


async def problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))

    try:
        result = _zabbix_api(
            "problem.get",
            {
                "output": ["eventid", "name", "severity", "clock", "objectid"],
                "selectHosts": ["host", "name", "status"],
                "sortfield": ["eventid"],
                "sortorder": "DESC",
                "recent": True,
                "limit": limit,
            },
        )

        if not result:
            await update.message.reply_text("✅ Không có problem đang mở.")
            return

        lines = [f"🚨 Open Problems (top {limit})", ""]
        for i, p in enumerate(result, 1):
            host_name = "unknown"
            if p.get("hosts"):
                host_name = p["hosts"][0].get("name") or p["hosts"][0].get("host", "unknown")
            lines.append(
                f"{i}) #{p.get('eventid')} | Sev:{p.get('severity')} | {host_name}\n"
                f"   {p.get('name')}\n"
                f"   { _fmt_ts(p.get('clock')) }"
            )

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def hosts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))

    try:
        result = _zabbix_api(
            "host.get",
            {
                "output": ["hostid", "host", "name", "status"],
                "selectInterfaces": ["ip", "dns", "available"],
                "selectItems": ["lastvalue", "lastclock", "name", "state"],
                "limit": limit,
            },
        )

        if not result:
            await update.message.reply_text("Không lấy được danh sách host.")
            return

        lines = [f"🖥 Hosts (top {limit})", ""]
        for i, h in enumerate(result, 1):
            st = "ENABLED" if str(h.get("status", "0")) == "0" else "DISABLED"
            ip = "-"
            if h.get("interfaces"):
                ip = h["interfaces"][0].get("ip") or h["interfaces"][0].get("dns") or "-"
            lines.append(f"{i}) {h.get('name')} ({h.get('host')}) | {st} | {ip}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def host(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Cú pháp: /host <host>")
        return

    q = " ".join(context.args)
    try:
        result = _zabbix_api(
            "host.get",
            {
                "output": ["hostid", "host", "name", "status"],
                "search": {"host": q, "name": q},
                "searchByAny": True,
                "selectInterfaces": ["ip", "dns", "available"],
                "limit": 5,
            },
        )
        if not result:
            await update.message.reply_text("Không tìm thấy host.")
            return

        lines = [f"🔎 Kết quả host: {q}", ""]
        for h in result:
            st = "ENABLED" if str(h.get("status", "0")) == "0" else "DISABLED"
            ip = "-"
            av = "?"
            if h.get("interfaces"):
                i0 = h["interfaces"][0]
                ip = i0.get("ip") or i0.get("dns") or "-"
                av = i0.get("available", "?")
            lines.append(f"- {h.get('name')} ({h.get('host')})\n  hostid: {h.get('hostid')} | {st} | ip: {ip} | available: {av}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def ack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /ack <eventid> <message>")
        return

    eventid = context.args[0]
    message = " ".join(context.args[1:]).strip()

    if not eventid.isdigit():
        await update.message.reply_text("eventid không hợp lệ.")
        return

    try:
        _zabbix_api(
            "event.acknowledge",
            {
                "eventids": [eventid],
                "action": 6,
                "message": message,
            },
        )
        await update.message.reply_text(f"✅ Đã ack event #{eventid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    limit = 30
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 200))

    try:
        result = _zabbix_api(
            "hostgroup.get",
            {
                "output": ["groupid", "name"],
                "sortfield": "name",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

        if not result:
            await update.message.reply_text("Không có group nào.")
            return

        lines = [f"📁 Host Groups (top {limit})", ""]
        for i, g in enumerate(result, 1):
            lines.append(f"{i}) groupid={g.get('groupid')} | {g.get('name')}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    limit = 30
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 200))

    try:
        result = _zabbix_api(
            "template.get",
            {
                "output": ["templateid", "host", "name"],
                "sortfield": "name",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

        if not result:
            await update.message.reply_text("Không có template nào.")
            return

        lines = [f"🧩 Templates (top {limit})", ""]
        for i, t in enumerate(result, 1):
            tname = t.get("name") or t.get("host")
            lines.append(f"{i}) templateid={t.get('templateid')} | {tname}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


def _find_hostid_by_query(query: str) -> str | None:
    result = _zabbix_api(
        "host.get",
        {
            "output": ["hostid", "host", "name", "status"],
            "search": {"host": query, "name": query},
            "searchByAny": True,
            "limit": 1,
        },
    )
    if not result:
        return None
    return str(result[0].get("hostid"))


def _find_maintenance_by_name(name: str) -> dict | None:
    result = _zabbix_api(
        "maintenance.get",
        {
            "output": ["maintenanceid", "name", "active_since", "active_till", "status"],
            "selectHosts": ["hostid", "host", "name"],
            "search": {"name": name},
            "searchByAny": True,
            "limit": 1,
        },
    )
    if not result:
        return None
    return result[0]


def _find_or_create_maintenance_for_host(hostid: str, host_query: str, duration_min: int) -> tuple[str, str, bool]:
    """
    Returns: (maintenanceid, maintenance_name, created_new)
    """
    maint_name = f"TG-Maint-{host_query}-{hostid}"
    existing = _find_maintenance_by_name(maint_name)
    now = int(time.time())
    till = now + max(5, duration_min) * 60

    if existing:
        maintenanceid = str(existing.get("maintenanceid"))
        _zabbix_api(
            "maintenance.update",
            {
                "maintenanceid": maintenanceid,
                "active_since": now,
                "active_till": till,
                "hostids": [hostid],
            },
        )
        return maintenanceid, maint_name, False

    result = _zabbix_api(
        "maintenance.create",
        {
            "name": maint_name,
            "maintenance_type": 0,
            "active_since": now,
            "active_till": till,
            "hostids": [hostid],
            "timeperiods": [
                {
                    "timeperiod_type": 0,
                    "period": max(300, duration_min * 60),
                }
            ],
        },
    )
    mids = result.get("maintenanceids", []) if isinstance(result, dict) else []
    if not mids:
        raise RuntimeError("Không tạo được maintenance")
    return str(mids[0]), maint_name, True


async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Cú pháp: /disable <host>")
        return

    query = " ".join(context.args)
    try:
        hostid = _find_hostid_by_query(query)
        if not hostid:
            await update.message.reply_text("Không tìm thấy host.")
            return

        _set_pending(chat_id, user_id, "disable", hostid, query)
        await update.message.reply_text(
            f"⚠️ Xác nhận disable host '{query}' [hostid={hostid}]\n"
            f"Gõ /confirm trong {CONFIRM_TIMEOUT_SEC}s để thực thi, hoặc /cancel để hủy."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Cú pháp: /enable <host>")
        return

    query = " ".join(context.args)
    try:
        hostid = _find_hostid_by_query(query)
        if not hostid:
            await update.message.reply_text("Không tìm thấy host.")
            return

        _set_pending(chat_id, user_id, "enable", hostid, query)
        await update.message.reply_text(
            f"⚠️ Xác nhận enable host '{query}' [hostid={hostid}]\n"
            f"Gõ /confirm trong {CONFIRM_TIMEOUT_SEC}s để thực thi, hoặc /cancel để hủy."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def mainton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Cú pháp: /mainton <host> [duration_min]\nVí dụ: /mainton web-01 60")
        return

    duration_min = 60
    if context.args and context.args[-1].isdigit():
        duration_min = max(5, min(int(context.args[-1]), 1440))
        host_query = " ".join(context.args[:-1]).strip()
    else:
        host_query = " ".join(context.args).strip()

    if not host_query:
        await update.message.reply_text("Thiếu host. Ví dụ: /mainton web-01 60")
        return

    try:
        hostid = _find_hostid_by_query(host_query)
        if not hostid:
            await update.message.reply_text("Không tìm thấy host.")
            return

        _set_pending(chat_id, user_id, "maint_on", hostid, f"{host_query}|{duration_min}")
        await update.message.reply_text(
            f"⚠️ Xác nhận bật maintenance cho '{host_query}' trong {duration_min} phút [hostid={hostid}]\n"
            f"Gõ /confirm trong {CONFIRM_TIMEOUT_SEC}s để thực thi, hoặc /cancel để hủy."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def maintoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Cú pháp: /maintoff <host>")
        return

    host_query = " ".join(context.args).strip()
    try:
        hostid = _find_hostid_by_query(host_query)
        if not hostid:
            await update.message.reply_text("Không tìm thấy host.")
            return

        _set_pending(chat_id, user_id, "maint_off", hostid, host_query)
        await update.message.reply_text(
            f"⚠️ Xác nhận tắt maintenance cho '{host_query}' [hostid={hostid}]\n"
            f"Gõ /confirm trong {CONFIRM_TIMEOUT_SEC}s để thực thi, hoặc /cancel để hủy."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    pending = _get_pending(chat_id, user_id)
    if not pending:
        await update.message.reply_text("Không có thao tác nào đang chờ xác nhận, hoặc đã hết hạn.")
        return

    action = pending["action"]
    hostid = pending["hostid"]
    query = pending["query"]

    try:
        if action == "disable":
            _zabbix_api("host.update", {"hostid": hostid, "status": 1})
            await update.message.reply_text(f"🛑 Đã disable host ({query}) [hostid={hostid}]")
        elif action == "enable":
            _zabbix_api("host.update", {"hostid": hostid, "status": 0})
            await update.message.reply_text(f"✅ Đã enable host ({query}) [hostid={hostid}]")
        elif action == "maint_on":
            host_query, dmin_raw = (query.split("|", 1) + ["60"])[:2]
            duration_min = int(dmin_raw) if dmin_raw.isdigit() else 60
            maintenanceid, mname, created_new = _find_or_create_maintenance_for_host(hostid, host_query, duration_min)
            verb = "Tạo mới" if created_new else "Cập nhật"
            await update.message.reply_text(
                f"🛠 {verb} maintenance thành công\n"
                f"Host: {host_query} [hostid={hostid}]\n"
                f"Maintenance: {mname} [id={maintenanceid}]\n"
                f"Duration: {duration_min} phút"
            )
        elif action == "maint_off":
            host_query = query
            mname = f"TG-Maint-{host_query}-{hostid}"
            maint = _find_maintenance_by_name(mname)
            if not maint:
                await update.message.reply_text(f"Không thấy maintenance '{mname}' để tắt.")
            else:
                _zabbix_api("maintenance.delete", [str(maint.get("maintenanceid"))])
                await update.message.reply_text(
                    f"✅ Đã tắt maintenance\nHost: {host_query} [hostid={hostid}]\nMaintenance: {mname}"
                )
        else:
            await update.message.reply_text("Thao tác chờ không hợp lệ.")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")
    finally:
        _clear_pending(chat_id, user_id)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    pending = _get_pending(chat_id, user_id)
    if not pending:
        await update.message.reply_text("Không có thao tác nào để hủy.")
        return

    _clear_pending(chat_id, user_id)
    await update.message.reply_text("Đã hủy thao tác đang chờ.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("problems", problems))
    app.add_handler(CommandHandler("hosts", hosts))
    app.add_handler(CommandHandler("host", host))
    app.add_handler(CommandHandler("ack", ack))
    app.add_handler(CommandHandler("groups", groups))
    app.add_handler(CommandHandler("templates", templates))
    app.add_handler(CommandHandler("disable", disable))
    app.add_handler(CommandHandler("enable", enable))
    app.add_handler(CommandHandler("mainton", mainton))
    app.add_handler(CommandHandler("maintoff", maintoff))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("cancel", cancel))

    print("Zabbix admin bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
