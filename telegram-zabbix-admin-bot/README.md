# Telegram Zabbix Admin Bot

Bot Telegram để quản trị Zabbix nhanh từ chat.

## Tính năng
- `/problems [N]` — xem top N problem đang mở
- `/hosts [N]` — xem danh sách host
- `/host <keyword>` — tra cứu host
- `/ack <eventid> <message>` — acknowledge event
- `/disable <host>` — yêu cầu disable host (cần `/confirm`)
- `/enable <host>` — yêu cầu enable host (cần `/confirm`)
- `/mainton <host> [minutes]` — bật maintenance cho host (cần `/confirm`)
- `/maintoff <host>` — tắt maintenance cho host (cần `/confirm`)
- `/confirm` — xác nhận thao tác nguy hiểm đang chờ
- `/cancel` — hủy thao tác đang chờ

## 1) Chuẩn bị Zabbix API token
Trên Zabbix (v6+):
1. Vào **Administration → API tokens**
2. Tạo token có quyền phù hợp (host/event read + action update nếu cần ack/enable/disable)

## 2) Cài đặt bot
```bash
cd telegram-zabbix-admin-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Sửa `.env`:
- `TELEGRAM_BOT_TOKEN=...`
- `ZABBIX_URL=https://your-zabbix-domain`
- `ZABBIX_API_TOKEN=...`
- `ADMIN_USER_IDS=123456789` (khuyên nên set để khóa quyền)
- `CONFIRM_TIMEOUT_SEC=60` (timeout xác nhận lệnh nguy hiểm)

## 3) Chạy
```bash
python bot.py
```

## Security notes
- Nên đặt `ADMIN_USER_IDS` để chỉ cho user Telegram được phép admin.
- Token Zabbix nên tạo riêng cho bot, tối thiểu quyền cần thiết.
- Bot này là bản nền nhanh, có thể nâng cấp thêm confirm-step cho lệnh nguy hiểm (`/disable`, `/enable`).
