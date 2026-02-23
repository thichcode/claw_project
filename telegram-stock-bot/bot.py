import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

DEFAULT_WATCHLIST = ["FPT", "CTG", "HPG", "VCB", "TCB", "MBB", "SSI", "VND", "MWG", "PNJ"]
CHAT_STORE = Path(__file__).parent / "chat_ids.json"


def _get_watchlist() -> list[str]:
    raw = os.getenv("WATCHLIST", "").strip()
    if not raw:
        return DEFAULT_WATCHLIST
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def _parse_report_time(raw: str) -> time:
    try:
        hh, mm = raw.split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception:
        return time(hour=22, minute=0)


def _load_chat_ids() -> set[int]:
    if not CHAT_STORE.exists():
        return set()
    try:
        data = json.loads(CHAT_STORE.read_text(encoding="utf-8"))
        return set(int(x) for x in data.get("chat_ids", []))
    except Exception:
        return set()


def _save_chat_ids(chat_ids: set[int]):
    payload = {"chat_ids": sorted(chat_ids)}
    CHAT_STORE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _trade_plan(last: float, ma20: float, atr14: float) -> dict:
    entry_low = min(last * 0.995, ma20 * 1.005)
    entry_high = max(last * 1.005, ma20 * 1.015)
    entry_mid = (entry_low + entry_high) / 2

    # Stop-loss: bảo thủ, tối đa theo ATR hoặc 4% dưới entry_mid
    sl_by_atr = entry_mid - 1.2 * atr14
    sl_by_pct = entry_mid * 0.96
    sl = min(sl_by_atr, sl_by_pct)

    risk = max(entry_mid - sl, entry_mid * 0.01)
    tp1 = entry_mid + 1.6 * risk
    tp2 = entry_mid + 2.5 * risk

    return {
        "entry_low": float(entry_low),
        "entry_high": float(entry_high),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
    }


def _fetch_score(symbol: str) -> dict | None:
    ticker = f"{symbol}.VN"
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 80:
            return None

        close = df["Close"].dropna()
        vol = df["Volume"].fillna(0)
        high = df["High"].dropna()
        low = df["Low"].dropna()

        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        last = close.iloc[-1]

        prev5 = close.iloc[-6] if len(close) >= 6 else close.iloc[0]
        ret5 = (last / prev5 - 1.0) * 100

        vol20 = vol.rolling(20).mean().iloc[-1]
        vol_last = vol.iloc[-1]
        vol_ratio = float(vol_last / vol20) if vol20 and not np.isnan(vol20) else 1.0

        rsi14 = _rsi(close, 14).iloc[-1]
        macd_line, macd_signal, macd_hist = _macd(close)
        macd_bull = bool(macd_line.iloc[-1] > macd_signal.iloc[-1] and macd_hist.iloc[-1] > 0)

        atr14 = _atr(high, low, close, 14).iloc[-1]
        if np.isnan(atr14) or atr14 <= 0:
            atr14 = last * 0.02

        # Weighted score
        trend_score = 1.0 if ma20 > ma50 else 0.0
        momentum_score = max(min(ret5 / 5.0, 2.0), -2.0)
        liquidity_score = max(min((vol_ratio - 1.0), 2.0), -1.0)

        # RSI score: ưu tiên vùng 45-65 (vừa tăng vừa chưa quá nóng)
        if 45 <= rsi14 <= 65:
            rsi_score = 1.0
        elif 35 <= rsi14 < 45 or 65 < rsi14 <= 72:
            rsi_score = 0.5
        else:
            rsi_score = -0.2

        macd_score = 1.0 if macd_bull else 0.0

        score = (
            40
            + trend_score * 18
            + momentum_score * 14
            + liquidity_score * 12
            + rsi_score * 8
            + macd_score * 8
        )

        plan = _trade_plan(float(last), float(ma20), float(atr14))

        return {
            "symbol": symbol,
            "price": float(last),
            "ret5": float(ret5),
            "vol_ratio": float(vol_ratio),
            "score": float(score),
            "trend_up": bool(ma20 > ma50),
            "rsi14": float(rsi14),
            "macd_bull": macd_bull,
            "plan": plan,
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
        macd = "✅" if p["macd_bull"] else "⚠️"
        plan = p["plan"]

        lines.append(
            f"{i}) {p['symbol']} | Giá: {p['price']:.2f} | 5d: {p['ret5']:+.2f}% | KL: x{p['vol_ratio']:.2f} | Trend: {trend} | RSI14: {p['rsi14']:.1f} | MACD: {macd} | Score: {p['score']:.1f}"
        )
        lines.append(
            f"   • Vùng mua: {plan['entry_low']:.2f} - {plan['entry_high']:.2f} | Cắt lỗ: {plan['sl']:.2f} | TP1: {plan['tp1']:.2f} | TP2: {plan['tp2']:.2f}"
        )

    lines += [
        "",
        "Quản trị rủi ro: chia lệnh 3 phần, không mua đuổi khi gap-up mạnh.",
        "⚠️ Bot tham khảo, không phải khuyến nghị đầu tư chắc chắn thắng.",
    ]
    return "\n".join(lines)


async def _register_chat(chat_id: int):
    chat_ids = _load_chat_ids()
    if chat_id not in chat_ids:
        chat_ids.add(chat_id)
        _save_chat_ids(chat_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _register_chat(chat_id)

    await update.message.reply_text(
        "Xin chào, mình là bot phân tích cổ phiếu VN.\n"
        "Lệnh:\n"
        "/top3 - Lấy Top 3 mã ưu tiên cho phiên kế tiếp\n"
        "/watchlist - Xem danh sách mã đang quét\n"
        "/reporttime - Xem giờ gửi báo cáo tự động"
    )


async def top3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _register_chat(chat_id)

    await update.message.reply_text("Đang phân tích nhanh, chờ mình 3-8 giây...")
    msg = render_top3()
    await update.message.reply_text(msg)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wl = ", ".join(_get_watchlist())
    await update.message.reply_text(f"WATCHLIST hiện tại:\n{wl}")


async def reporttime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_name = os.getenv("BOT_TIMEZONE", "Asia/Saigon")
    report_time = os.getenv("DAILY_REPORT_TIME", "22:00")
    await update.message.reply_text(f"Báo cáo tự động: mỗi ngày lúc {report_time} ({tz_name})")


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    msg = render_top3()
    chat_ids = _load_chat_ids()
    if not chat_ids:
        return

    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception:
            continue


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong file .env")

    tz_name = os.getenv("BOT_TIMEZONE", "Asia/Saigon")
    tz = ZoneInfo(tz_name)
    report_time = _parse_report_time(os.getenv("DAILY_REPORT_TIME", "22:00")).replace(tzinfo=tz)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top3", top3))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("reporttime", reporttime))

    app.job_queue.run_daily(daily_report_job, time=report_time, name="daily_top3", data=None)

    print(f"Bot is running... Daily report at {report_time.strftime('%H:%M')} ({tz_name})")
    app.run_polling()


if __name__ == "__main__":
    main()
