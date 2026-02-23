# Telegram Stock Bot (VN)

Bot Telegram trả về **Top 3 mã ưu tiên cho phiên kế tiếp** dựa trên scoring nhanh:
- Xu hướng MA20 > MA50
- Momentum 5 ngày
- Thanh khoản hiện tại so với trung bình 20 ngày

## 1) Tạo bot Telegram
1. Mở Telegram, chat với **@BotFather**
2. Gõ `/newbot`
3. Lấy token bot

## 2) Cài đặt
```bash
cd telegram-stock-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Mở `.env`, điền:
- `TELEGRAM_BOT_TOKEN=...`
- `WATCHLIST=FPT,CTG,HPG,...` (tuỳ chỉnh)

## 3) Chạy bot
```bash
python bot.py
```

## 4) Lệnh sử dụng
- `/start`
- `/top3`
- `/watchlist`

## Lưu ý
- Dữ liệu lấy từ Yahoo Finance (`.VN` suffix).
- Đây là bot tham khảo, không đảm bảo lợi nhuận.
- Nên tự thêm bộ lọc cơ bản (KQKD, định giá, tin tức) trước khi vào lệnh.
