import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

DEFAULT_WATCHLIST = ["FPT", "CTG", "HPG", "VCB", "TCB", "MBB", "SSI", "VND", "MWG", "PNJ"]


def _get_watchlist() -> list[str]:
    raw = os.getenv("WATCHLIST", "").strip()
    if not raw:
        return DEFAULT_WATCHLIST
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def _fetch_score(symbol: str) -> dict | None:
    """
    Score logic (simple + fast):
    - Trend 20 > 50 MA
    - Momentum 5d return
    - Liquidity vs 20d avg volume
    """
    ticker = f"{symbol}.VN"
    try:
        df = yf.download(ticker, period="4mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 60:
            return None

        close = df["Close"].dropna()
        vol = df["Volume"].fillna(0)

        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]

        last = close.iloc[-1]
        prev5 = close.iloc[-6] if len(close) >= 6 else close.iloc[0]
        ret5 = (last / prev5 - 1.0) * 100

        vol20 = vol.rolling(20).mean().iloc[-1]
        vol_last = vol.iloc[-1]
        vol_ratio = float(vol_last / vol20) if vol20 and not np.isnan(vol20) else 1.0

        # Weighted score
        trend_score = 1.0 if ma20 > ma50 else 0.0
        momentum_score = max(min(ret5 / 5.0, 2.0), -2.0)  # clamp
        liquidity_score = max(min((vol_ratio - 1.0), 2.0), -1.0)

        score = 50 + trend_score * 20 + momentum_score * 15 + liquidity_score * 15

        return {
            "symbol": symbol,
            "price": float(last),
            "ret5": float(ret5),
            "vol_ratio": float(vol_ratio),
            "score": float(score),
            "trend_up": bool(ma20 > ma50),
        }
    except Exception:
        return None


def pick_top3() -> list[dict]:
    candidates = []
    for s in _get_watchlist():
        row = _fetch_score(s)
        if row:
            candidates.append(row)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:3]


def render_top3() -> str:
    picks = pick_top3()
    if not picks:
        return "Không lấy được dữ liệu. Kiểm tra mạng hoặc danh sách mã (WATCHLIST)."

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 Top 3 mã ưu tiên (auto) - {now}", ""]

    for i, p in enumerate(picks, 1):
        trend = "✅" if p["trend_up"] else "⚠️"
        lines.append(
            f"{i}) {p['symbol']} | Giá: {p['price']:.2f} | 5d: {p['ret5']:+.2f}% | KL: x{p['vol_ratio']:.2f} | Trend: {trend} | Score: {p['score']:.1f}"
        )

    lines += [
        "",
        "Quản trị rủi ro gợi ý: cắt lỗ 3-5%, không mua đuổi, chia lệnh theo 3 phần.",
        "⚠️ Đây là bot tham khảo, không phải khuyến nghị đầu tư chắc chắn thắng.",
    ]
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Xin chào, mình là bot phân tích cổ phiếu VN.\n"
        "Lệnh:\n"
        "/top3 - Lấy Top 3 mã ưu tiên cho phiên kế tiếp\n"
        "/watchlist - Xem danh sách mã đang quét"
    )


async def top3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Đang phân tích nhanh, chờ mình 2-5 giây...")
    msg = render_top3()
    await update.message.reply_text(msg)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wl = ", ".join(_get_watchlist())
    await update.message.reply_text(f"WATCHLIST hiện tại:\n{wl}")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong file .env")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top3", top3))
    app.add_handler(CommandHandler("watchlist", watchlist))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
