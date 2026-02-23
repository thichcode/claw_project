# Telegram ServiceDesk Plus Admin Bot (On-prem v14720)

Bot Telegram để quản trị nhanh ManageEngine ServiceDesk Plus on-prem qua API (multi-site ready).

## Tính năng hiện có
- `/requests [N]` — list ticket gần nhất
- `/request <id>` — xem chi tiết ticket (kèm site)
- `/assign <id> <technician_name>`
- `/setstatus <id> <status_name>`
- `/setpriority <id> <priority_name>`
- `/setgroup <id> <support_group_name>` (validate theo site của request)
- `/addnote <id> <note text>`
- `/close <id>` + `/confirm` (2 bước)

## Lookup
- `/sites [N]` — list site + site_id
- `/technicians [N]` (hiển thị cả `login_name` để dùng cho sgcreate/sgupdate)
- `/statuses`
- `/priorities`
- `/sgroups [N] [site_id]` — list support groups, có filter theo site

## Quản lý support group (site-aware, bắt buộc có technician)
- `/sgcreate <site_id> <name> | <techaccount1,techaccount2> [| description]` + `/confirm`
- `/sgupdate <group_id> <site_id> <new_name> | <techaccount1,techaccount2> [| description]` + `/confirm`
- `/cancel`

Ví dụ:
- `/sgcreate 2 NOC Team | thuongdv2,anhnv | Team trực NOC`
- `/sgupdate 15 2 NOC Team L2 | thuongdv2`

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
- Nếu lệnh nào lỗi do schema API instance của bạn, gửi lỗi mình patch theo đúng build.

## Security
- Bắt buộc set `ADMIN_USER_IDS` trong production.
- Dùng API key riêng cho bot, phân quyền tối thiểu.
- Lệnh đóng ticket + create/update support group có xác nhận 2 bước.
