# Telegram UptimeRobot Admin Bot

Bot Telegram để admin UptimeRobot: create/update/maintain/start/pause host monitor.

## Tính năng
- `/hosts [N]` — list monitors
- `/host <monitor_id>` — monitor details
- `/createhost <name> <url> [interval_sec]` — tạo monitor HTTP(s)
- `/updatehost <monitor_id> name=<...> url=<...> interval=<sec>` — cập nhật monitor
- `/pausehost <monitor_id>` + `/confirm`
- `/starthost <monitor_id>` + `/confirm`
- `/maintain <monitor_id> <minutes>` + `/confirm` (pause ngay, tự resume)
- `/cancel`

## Cài đặt
```bash
cd telegram-uptimerobot-admin-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Sửa `.env`:
- `TELEGRAM_BOT_TOKEN=...`
- `UPTIMEROBOT_API_KEY=...`
- `ADMIN_USER_IDS=123456789` (khuyên dùng)
- `CONFIRM_TIMEOUT_SEC=60`
- `DEFAULT_INTERVAL_SEC=300`

## Chạy
```bash
python bot.py
```

## Lưu ý
- Bot gọi API v2: `https://api.uptimerobot.com/v2/...`
- `maintain` dùng cơ chế pause + job queue auto-resume.
- Nếu process bot bị restart trong maintenance window, job auto-resume có thể mất. Khi đó dùng `/starthost <id>` để resume tay.
