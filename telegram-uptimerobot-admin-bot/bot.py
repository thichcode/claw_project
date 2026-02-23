import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
UPTIMEROBOT_API_KEY = os.getenv("UPTIMEROBOT_API_KEY", "").strip()
ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "").strip()
CONFIRM_TIMEOUT_SEC = int(os.getenv("CONFIRM_TIMEOUT_SEC", "60"))
DEFAULT_INTERVAL_SEC = int(os.getenv("DEFAULT_INTERVAL_SEC", "300"))

API_URL = "https://api.uptimerobot.com/v2"

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


def _ur_call(path: str, data: dict) -> dict:
    if not UPTIMEROBOT_API_KEY:
        raise RuntimeError("Thiếu UPTIMEROBOT_API_KEY trong .env")

    payload = {
        "api_key": UPTIMEROBOT_API_KEY,
        "format": "json",
    }
    payload.update(data)

    resp = requests.post(f"{API_URL}/{path}", data=payload, timeout=30)
    resp.raise_for_status()
    out = resp.json()

    if out.get("stat") != "ok":
        raise RuntimeError(f"UptimeRobot error: {out}")

    return out


def _monitor_status_text(s: int | str) -> str:
    m = {
        0: "PAUSED",
        1: "NOT_CHECKED_YET",
        2: "UP",
        8: "SEEMS_DOWN",
        9: "DOWN",
    }
    try:
        return m.get(int(s), f"UNKNOWN({s})")
    except Exception:
        return f"UNKNOWN({s})"


def _find_monitor(monitor_id: str) -> dict | None:
    out = _ur_call("getMonitors", {"monitors": monitor_id, "logs": 0, "response_times": 0, "alert_contacts": 0})
    rows = out.get("monitors", [])
    return rows[0] if rows else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        "🤖 UptimeRobot Admin Bot ready\n\n"
        "Commands:\n"
        "/hosts [N] - list monitors\n"
        "/host <monitor_id> - monitor details\n"
        "/createhost <name> <url> [interval_sec] - create monitor\n"
        "/updatehost <monitor_id> name=<...> url=<...> interval=<sec> - update monitor\n"
        "/pausehost <monitor_id> - pause monitor (/confirm)\n"
        "/starthost <monitor_id> - resume monitor (/confirm)\n"
        "/maintain <monitor_id> <minutes> - pause then auto-resume (/confirm)\n"
        "/confirm - confirm pending action\n"
        "/cancel - cancel pending action\n"
        "/ping - health check\n\n"
        f"Your Telegram user id: {u.id}"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


async def hosts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    limit = 20
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))

    try:
        out = _ur_call("getMonitors", {"logs": 0, "response_times": 0, "alert_contacts": 0})
        rows = out.get("monitors", [])[:limit]
        if not rows:
            await update.message.reply_text("No monitors found.")
            return

        lines = [f"🌐 Monitors (top {len(rows)})", ""]
        for i, m in enumerate(rows, 1):
            mid = m.get("id", "?")
            name = m.get("friendly_name", "?")
            url = m.get("url", "-")
            status = _monitor_status_text(m.get("status"))
            interval = m.get("interval", "?")
            lines.append(f"{i}) #{mid} | {status} | {name} | every {interval}s\n   {url}")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def host(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /host <monitor_id>")
        return

    monitor_id = context.args[0]
    try:
        m = _find_monitor(monitor_id)
        if not m:
            await update.message.reply_text("Monitor not found.")
            return

        created = datetime.fromtimestamp(int(m.get("create_datetime", 0))).strftime("%Y-%m-%d %H:%M:%S") if str(m.get("create_datetime", "0")).isdigit() else "-"
        msg = (
            f"🔎 Monitor #{m.get('id')}\n"
            f"Name: {m.get('friendly_name')}\n"
            f"URL: {m.get('url')}\n"
            f"Type: {m.get('type')}\n"
            f"Status: {_monitor_status_text(m.get('status'))}\n"
            f"Interval: {m.get('interval')}s\n"
            f"Created: {created}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def createhost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /createhost <name> <url> [interval_sec]")
        return

    name = context.args[0]
    url = context.args[1]
    interval = DEFAULT_INTERVAL_SEC
    if len(context.args) >= 3 and context.args[2].isdigit():
        interval = max(60, min(int(context.args[2]), 3600))

    try:
        out = _ur_call(
            "newMonitor",
            {
                "friendly_name": name,
                "url": url,
                "type": 1,
                "interval": interval,
            },
        )
        monitor = out.get("monitor", {})
        await update.message.reply_text(f"✅ Created monitor #{monitor.get('id')} | {name} | {url} | every {interval}s")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def updatehost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /updatehost <monitor_id> name=<...> url=<...> interval=<sec>")
        return

    monitor_id = context.args[0]
    fields = {}
    for token in context.args[1:]:
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        fields[k.strip().lower()] = v.strip()

    data = {"id": monitor_id}
    if "name" in fields:
        data["friendly_name"] = fields["name"]
    if "url" in fields:
        data["url"] = fields["url"]
    if "interval" in fields and fields["interval"].isdigit():
        data["interval"] = max(60, min(int(fields["interval"]), 3600))

    if len(data) == 1:
        await update.message.reply_text("Không có field hợp lệ để update. Dùng name= url= interval=")
        return

    try:
        _ur_call("editMonitor", data)
        await update.message.reply_text(f"✅ Updated monitor #{monitor_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def pausehost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /pausehost <monitor_id>")
        return

    monitor_id = context.args[0]
    _set_pending(update.effective_chat.id, update.effective_user.id, "pause", {"monitor_id": monitor_id})
    await update.message.reply_text(
        f"⚠️ Confirm pause monitor #{monitor_id}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def starthost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /starthost <monitor_id>")
        return

    monitor_id = context.args[0]
    _set_pending(update.effective_chat.id, update.effective_user.id, "start", {"monitor_id": monitor_id})
    await update.message.reply_text(
        f"⚠️ Confirm start/resume monitor #{monitor_id}\nUse /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def maintain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text("Usage: /maintain <monitor_id> <minutes>")
        return

    monitor_id = context.args[0]
    minutes = max(1, min(int(context.args[1]), 1440))

    _set_pending(
        update.effective_chat.id,
        update.effective_user.id,
        "maintain",
        {"monitor_id": monitor_id, "minutes": minutes, "chat_id": update.effective_chat.id},
    )
    await update.message.reply_text(
        f"⚠️ Confirm maintenance for monitor #{monitor_id} during {minutes} minute(s)\n"
        f"Action: pause now, auto-resume later.\n"
        f"Use /confirm within {CONFIRM_TIMEOUT_SEC}s or /cancel"
    )


async def _resume_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    monitor_id = data.get("monitor_id")
    chat_id = data.get("chat_id")

    try:
        _ur_call("editMonitor", {"id": monitor_id, "status": 1})
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Auto-resumed monitor #{monitor_id} after maintenance window")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed to auto-resume monitor #{monitor_id}: {e}")


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized")
        return

    x = _get_pending(update.effective_chat.id, update.effective_user.id)
    if not x:
        await update.message.reply_text("No pending action or it expired.")
        return

    try:
        action = x.get("action")
        payload = x.get("payload", {})
        monitor_id = payload.get("monitor_id")

        if action == "pause":
            _ur_call("editMonitor", {"id": monitor_id, "status": 0})
            await update.message.reply_text(f"⏸️ Paused monitor #{monitor_id}")

        elif action == "start":
            _ur_call("editMonitor", {"id": monitor_id, "status": 1})
            await update.message.reply_text(f"▶️ Started monitor #{monitor_id}")

        elif action == "maintain":
            minutes = int(payload.get("minutes", 30))
            chat_id = payload.get("chat_id", update.effective_chat.id)

            _ur_call("editMonitor", {"id": monitor_id, "status": 0})
            context.job_queue.run_once(
                _resume_monitor_job,
                when=minutes * 60,
                data={"monitor_id": monitor_id, "chat_id": chat_id},
                name=f"resume_{monitor_id}_{int(time.time())}",
            )
            await update.message.reply_text(
                f"🛠️ Monitor #{monitor_id} paused for maintenance ({minutes} minute(s)). Auto-resume scheduled."
            )

        else:
            await update.message.reply_text("Unknown pending action")

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
    app.add_handler(CommandHandler("hosts", hosts))
    app.add_handler(CommandHandler("host", host))
    app.add_handler(CommandHandler("createhost", createhost))
    app.add_handler(CommandHandler("updatehost", updatehost))
    app.add_handler(CommandHandler("pausehost", pausehost))
    app.add_handler(CommandHandler("starthost", starthost))
    app.add_handler(CommandHandler("maintain", maintain))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("cancel", cancel))

    print("UptimeRobot admin bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
