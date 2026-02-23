# Telegram ServiceDesk Plus Admin Bot (On-prem v14720)

Bot Telegram để quản trị nhanh ManageEngine ServiceDesk Plus on-prem qua API.

## Tính năng hiện có
- `/requests [N]` — list ticket gần nhất
- `/request <id>` — xem chi tiết ticket
- `/assign <id> <technician_name>`
- `/setstatus <id> <status_name>`
- `/setpriority <id> <priority_name>`
- `/setgroup <id> <support_group_name>`
- `/addnote <id> <note text>`
- `/close <id>` + `/confirm` (2 bước)

### Danh mục tra cứu nhanh
- `/technicians [N]` — danh sách technician
- `/statuses` — danh sách status
- `/priorities` — danh sách priority
- `/sgroups [N]` — danh sách support group

### Quản lý support group
- `/sgcreate <name> [| description]` + `/confirm`
- `/sgupdate <group_id> <new_name> [| description]` + `/confirm`
- `/cancel`

## Cài đặt
```bash
cd telegram-sdp-admin-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Sửa `.env`:
- `TELEGRAM_BOT_TOKEN=...`
- `SDP_BASE_URL=https://sdp.your-domain`
- `SDP_API_KEY=...`
- `ADMIN_USER_IDS=123456789` (khuyên dùng)
- `DEFAULT_LIMIT=10`
- `CONFIRM_TIMEOUT_SEC=60`

## Chạy bot
```bash
python bot.py
```

## Lưu ý tương thích API
- Bot dùng endpoint `/api/v3/...` cho SDP on-prem.
- Một số build có khác biệt payload/field nhỏ.
- Nếu lệnh nào lỗi do schema API của instance bạn, gửi lỗi đó mình patch đúng bản 14720 của bạn.

## Security
- Bắt buộc set `ADMIN_USER_IDS` trong production.
- Dùng API key riêng cho bot, phân quyền tối thiểu.
- Lệnh đóng ticket + create/update support group đã có xác nhận 2 bước.
