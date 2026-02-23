# Telegram Stock Bot (VN) - V2

Bot Telegram trả về **Top 3 mã ưu tiên cho phiên kế tiếp** với bộ lọc:
- Xu hướng: MA20 > MA50
- Momentum 5 ngày
- Thanh khoản so với trung bình 20 ngày
- RSI(14)
- MACD (line > signal và histogram dương)

V2 bổ sung:
1. **Market filter VN-Index** (BULLISH/CAUTION)
2. **Intraday alert** khi giá vào vùng mua
3. **Quản lý vốn** theo rủi ro %/lệnh (gợi ý số lượng cp)

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
- `DEFAULT_CAPITAL_VND=100000000`
- `RISK_PER_TRADE_PCT=1.0`
- `INTRADAY_ALERT_ENABLED=true`
- `INTRADAY_CHECK_MINUTES=10`

## 3) Chạy bot
```bash
python bot.py
```

## 4) Lệnh sử dụng
- `/start`
- `/top3` — Top 3 + vùng mua/SL/TP + khối lượng gợi ý
- `/watchlist`
- `/reporttime`
- `/risk <von_vnd> <risk_pct>` (ví dụ: `/risk 100000000 1`)
- `/myrisk`

## 5) Tự động
- **Báo cáo hằng ngày**: lúc `DAILY_REPORT_TIME`
- **Intraday alerts**: check mỗi `INTRADAY_CHECK_MINUTES` phút trong giờ giao dịch
- Chat nào đã dùng `/start` hoặc `/top3` sẽ được nhận báo cáo/alert

## 6) File dữ liệu bot
- `chat_ids.json`: lưu chat nhận tin
- `risk_profiles.json`: lưu cấu hình vốn/rủi ro theo chat
- `alerts_state.json`: tránh spam cùng mã nhiều lần trong 1 ngày

---

## Lưu ý
- Dữ liệu lấy từ Yahoo Finance (`.VN` và `^VNINDEX`)
- Đây là bot tham khảo, không đảm bảo lợi nhuận
- Nên tự kiểm tra thêm KQKD, định giá, tin tức trước khi vào lệnh
