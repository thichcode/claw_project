# Imou -> Telegram Alert MVP

MVP theo dõi camera Imou qua RTSP để cảnh báo Telegram:
- Person detection (mặc định dùng YOLOv8n)
- Fire/Smoke detection (cần custom model, optional)
- Chống spam bằng consecutive frames + cooldown
- Gửi snapshot kèm timestamp

## 1) Setup

```bash
cd imou-telegram-alert-mvp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## 2) Cấu hình `.env`

Bắt buộc:
- `RTSP_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Khuyến nghị:
- `CONSECUTIVE_FRAMES=3`
- `ALERT_COOLDOWN_SECONDS=60`
- `FRAME_SKIP=2`

> Lưu ý: YOLO mặc định **không có class fire/smoke**. Nếu muốn phát hiện cháy/khói, bạn cần set `FIRE_SMOKE_MODEL` tới model custom đã train class `fire/smoke`.

## 3) Chạy

```bash
python main.py
```

Khi phát hiện sự kiện đủ điều kiện, bot sẽ gửi ảnh snapshot lên Telegram.

## 4) Test nhanh

- Test person: đứng trước camera
- Test fire/smoke: chỉ test bằng video mô phỏng an toàn, không test nguy hiểm thực tế

## 5) Next steps

- Multi-camera config (nhiều luồng RTSP)
- Alert severity (critical cho fire/smoke)
- Retry queue khi Telegram lỗi mạng
- Dashboard mini xem lịch sử alert
