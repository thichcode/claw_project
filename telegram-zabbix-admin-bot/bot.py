import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

ZABBIX_URL = os.getenv("ZABBIX_URL", "").rstrip("/")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN", "").strip()
ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "").strip()


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 Zabbix Admin Bot sẵn sàng.\n\n"
        "Lệnh:\n"
        "/problems [N] - Top N problems đang mở (mặc định 10)\n"
        "/hosts [N] - Top N hosts có issues (mặc định 10)\n"
        "/host <host> - Xem nhanh trạng thái host\n"
        "/ack <eventid> <message> - Ack problem\n"
        "/disable <host> - Disable host\n"
        "/enable <host> - Enable host\n"
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


async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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

        _zabbix_api("host.update", {"hostid": hostid, "status": 1})
        await update.message.reply_text(f"🛑 Đã disable host ({query}) [hostid={hostid}]")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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

        _zabbix_api("host.update", {"hostid": hostid, "status": 0})
        await update.message.reply_text(f"✅ Đã enable host ({query}) [hostid={hostid}]")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


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
    app.add_handler(CommandHandler("disable", disable))
    app.add_handler(CommandHandler("enable", enable))

    print("Zabbix admin bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
