# Telegram Stock Bot (VN)

Bot Telegram trả về **Top 3 mã ưu tiên cho phiên kế tiếp** với bộ lọc:
- Xu hướng: MA20 > MA50
- Momentum 5 ngày
- Thanh khoản so với trung bình 20 ngày
- RSI(14)
- MACD (line > signal và histogram dương)

Ngoài ra bot tự sinh kế hoạch giao dịch:
- Vùng mua
- Cắt lỗ (SL)
- Chốt lời TP1 / TP2

---

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
- `BOT_TIMEZONE=Asia/Saigon`
- `DAILY_REPORT_TIME=22:00`

## 3) Chạy bot
```bash
python bot.py
```

## 4) Lệnh sử dụng
- `/start`
- `/top3`
- `/watchlist`
- `/reporttime`

## 5) Gửi tự động mỗi tối
- Bot sẽ tự gửi báo cáo lúc `DAILY_REPORT_TIME` (mặc định 22:00)
- Bot gửi vào các chat đã từng dùng `/start` hoặc `/top3`
- Danh sách chat lưu tại `chat_ids.json`

---

## Lưu ý
- Dữ liệu lấy từ Yahoo Finance (`.VN` suffix)
- Đây là bot tham khảo, không đảm bảo lợi nhuận
- Nên tự kiểm tra thêm KQKD, định giá, và tin tức trước khi vào lệnh
