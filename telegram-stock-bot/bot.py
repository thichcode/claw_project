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
RISK_STORE = Path(__file__).parent / "risk_profiles.json"
ALERT_STATE_STORE = Path(__file__).parent / "alerts_state.json"


# ---------- Config helpers ----------
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


def _safe_float(v: str, fallback: float) -> float:
    try:
        return float(v)
    except Exception:
        return fallback


# ---------- JSON stores ----------
def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_chat_ids() -> set[int]:
    data = _load_json(CHAT_STORE, {"chat_ids": []})
    return set(int(x) for x in data.get("chat_ids", []))


def _save_chat_ids(chat_ids: set[int]):
    _save_json(CHAT_STORE, {"chat_ids": sorted(chat_ids)})


def _load_risk_profiles() -> dict:
    return _load_json(RISK_STORE, {"profiles": {}})


def _save_risk_profiles(data: dict):
    _save_json(RISK_STORE, data)


def _get_risk_profile(chat_id: int) -> dict:
    data = _load_risk_profiles()
    prof = data.get("profiles", {}).get(str(chat_id), {})
    capital = prof.get("capital_vnd", _safe_float(os.getenv("DEFAULT_CAPITAL_VND", "100000000"), 100_000_000))
    risk_pct = prof.get("risk_pct", _safe_float(os.getenv("RISK_PER_TRADE_PCT", "1.0"), 1.0))
    return {"capital_vnd": float(capital), "risk_pct": float(risk_pct)}


def _set_risk_profile(chat_id: int, capital_vnd: float, risk_pct: float):
    data = _load_risk_profiles()
    profiles = data.setdefault("profiles", {})
    profiles[str(chat_id)] = {"capital_vnd": float(capital_vnd), "risk_pct": float(risk_pct)}
    _save_risk_profiles(data)


def _load_alert_state() -> dict:
    return _load_json(ALERT_STATE_STORE, {"last_alert_day": {}, "sent": {}})


def _save_alert_state(data: dict):
    _save_json(ALERT_STATE_STORE, data)


# ---------- Indicators ----------
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


# ---------- Market filter ----------
def _market_regime() -> dict:
    """
    Filter by VN-Index trend. bullish when MA20 > MA50 and price > MA20.
    """
    try:
        df = yf.download("^VNINDEX", period="8mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 60:
            return {"ok": True, "label": "NEUTRAL (không đủ dữ liệu VN-Index)", "score": 0}

        close = df["Close"].dropna()
        last = float(close.iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])

        bullish = ma20 > ma50 and last > ma20
        label = "BULLISH" if bullish else "CAUTION"
        score = 1 if bullish else -1
        return {"ok": bullish, "label": label, "score": score, "last": last, "ma20": ma20, "ma50": ma50}
    except Exception:
        return {"ok": True, "label": "NEUTRAL (lỗi dữ liệu VN-Index)", "score": 0}


# ---------- Strategy core ----------
def _trade_plan(last: float, ma20: float, atr14: float) -> dict:
    entry_low = min(last * 0.995, ma20 * 1.005)
    entry_high = max(last * 1.005, ma20 * 1.015)
    entry_mid = (entry_low + entry_high) / 2

    sl_by_atr = entry_mid - 1.2 * atr14
    sl_by_pct = entry_mid * 0.96
    sl = min(sl_by_atr, sl_by_pct)

    risk = max(entry_mid - sl, entry_mid * 0.01)
    tp1 = entry_mid + 1.6 * risk
    tp2 = entry_mid + 2.5 * risk

    return {
        "entry_low": float(entry_low),
        "entry_high": float(entry_high),
        "entry_mid": float(entry_mid),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
    }


def _position_size(plan: dict, capital_vnd: float, risk_pct: float) -> dict:
    risk_budget = capital_vnd * (risk_pct / 100.0)
    per_share_risk = max(plan["entry_mid"] - plan["sl"], plan["entry_mid"] * 0.005)
    qty = max(int(risk_budget // per_share_risk), 0)

    lot_qty = (qty // 100) * 100
    if lot_qty == 0 and qty > 0:
        lot_qty = 100

    est_value = lot_qty * plan["entry_mid"]
    if est_value > capital_vnd and plan["entry_mid"] > 0:
        lot_qty = int(capital_vnd // plan["entry_mid"])
        lot_qty = (lot_qty // 100) * 100
        est_value = lot_qty * plan["entry_mid"]

    return {
        "risk_budget": float(risk_budget),
        "qty": int(max(lot_qty, 0)),
        "est_value": float(max(est_value, 0)),
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

        trend_score = 1.0 if ma20 > ma50 else 0.0
        momentum_score = max(min(ret5 / 5.0, 2.0), -2.0)
        liquidity_score = max(min((vol_ratio - 1.0), 2.0), -1.0)

        if 45 <= rsi14 <= 65:
            rsi_score = 1.0
        elif 35 <= rsi14 < 45 or 65 < rsi14 <= 72:
            rsi_score = 0.5
        else:
            rsi_score = -0.2

        macd_score = 1.0 if macd_bull else 0.0

        score = 40 + trend_score * 18 + momentum_score * 14 + liquidity_score * 12 + rsi_score * 8 + macd_score * 8

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


def render_top3(chat_id: int | None = None) -> str:
    market = _market_regime()
    picks = pick_top3()
    if not picks:
        return "Không lấy được dữ liệu. Kiểm tra mạng hoặc WATCHLIST."

    risk_prof = _get_risk_profile(chat_id) if chat_id is not None else {
        "capital_vnd": _safe_float(os.getenv("DEFAULT_CAPITAL_VND", "100000000"), 100_000_000),
        "risk_pct": _safe_float(os.getenv("RISK_PER_TRADE_PCT", "1.0"), 1.0),
    }

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 Top 3 mã ưu tiên (V2) - {now}"]
    lines.append(f"🌐 Market filter (VN-Index): {market.get('label')}" + (" ✅" if market.get("ok") else " ⚠️"))
    lines.append("")

    for i, p in enumerate(picks, 1):
        trend = "✅" if p["trend_up"] else "⚠️"
        macd = "✅" if p["macd_bull"] else "⚠️"
        plan = p["plan"]
        pos = _position_size(plan, risk_prof["capital_vnd"], risk_prof["risk_pct"])

        lines.append(
            f"{i}) {p['symbol']} | Giá: {p['price']:.2f} | 5d: {p['ret5']:+.2f}% | KL: x{p['vol_ratio']:.2f} | Trend: {trend} | RSI14: {p['rsi14']:.1f} | MACD: {macd} | Score: {p['score']:.1f}"
        )
        lines.append(
            f"   • Vùng mua: {plan['entry_low']:.2f}-{plan['entry_high']:.2f} | SL: {plan['sl']:.2f} | TP1: {plan['tp1']:.2f} | TP2: {plan['tp2']:.2f}"
        )
        lines.append(
            f"   • Gợi ý khối lượng: ~{pos['qty']} cp (risk {risk_prof['risk_pct']:.2f}% ~ {pos['risk_budget']:,.0f} VND) | Giá trị ước tính: {pos['est_value']:,.0f} VND"
        )

    lines += [
        "",
        "Quản trị rủi ro: chia lệnh 3 phần, không mua đuổi khi gap-up mạnh.",
        "⚠️ Bot tham khảo, không phải khuyến nghị đầu tư chắc chắn thắng.",
    ]
    return "\n".join(lines)


# ---------- Intraday alerts ----------
def _fetch_intraday_snapshot(symbol: str) -> dict | None:
    """
    Pull recent 15m candles for intraday price/volume confirmation.
    """
    ticker = f"{symbol}.VN"
    try:
        df = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 20:
            return None

        close = df["Close"].dropna()
        vol = df["Volume"].fillna(0)
        if close.empty or vol.empty:
            return None

        last_price = float(close.iloc[-1])
        last_vol = float(vol.iloc[-1])

        # Compare with recent intraday baseline (exclude last candle)
        recent_base = vol.iloc[-17:-1] if len(vol) >= 17 else vol.iloc[:-1]
        base = float(recent_base.mean()) if len(recent_base) > 0 else 0.0
        vol_ratio = (last_vol / base) if base > 0 else 0.0

        return {
            "last_price": last_price,
            "last_vol": last_vol,
            "vol_ratio": float(vol_ratio),
        }
    except Exception:
        return None


def _is_market_time(now: datetime) -> bool:
    # Vietnam market sessions: ~09:15-11:30 and 13:00-14:45, Mon-Fri
    if now.weekday() >= 5:
        return False

    hm = now.hour * 60 + now.minute
    morning = 9 * 60 + 15 <= hm <= 11 * 60 + 30
    afternoon = 13 * 60 <= hm <= 14 * 60 + 45
    return morning or afternoon


def _today_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


async def intraday_alert_job(context: ContextTypes.DEFAULT_TYPE):
    enabled = os.getenv("INTRADAY_ALERT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    min_vol_ratio = _safe_float(os.getenv("INTRADAY_VOLUME_MULTIPLIER", "1.3"), 1.3)
    min_last_vol = _safe_float(os.getenv("INTRADAY_MIN_LAST_VOLUME", "50000"), 50_000)

    tz_name = os.getenv("BOT_TIMEZONE", "Asia/Saigon")
    now = datetime.now(ZoneInfo(tz_name))
    if not _is_market_time(now):
        return

    market = _market_regime()
    if not market.get("ok"):
        return

    picks = pick_top3()
    if not picks:
        return

    state = _load_alert_state()
    day_key = _today_key(now)
    sent = state.setdefault("sent", {})
    today_sent = set(sent.get(day_key, []))

    to_alert = []
    for p in picks:
        if p["symbol"] in today_sent:
            continue

        snapshot = _fetch_intraday_snapshot(p["symbol"])
        if not snapshot:
            continue

        plan = p["plan"]
        in_buy_zone = plan["entry_low"] <= snapshot["last_price"] <= plan["entry_high"]
        vol_ok = snapshot["vol_ratio"] >= min_vol_ratio and snapshot["last_vol"] >= min_last_vol

        if in_buy_zone and vol_ok:
            p2 = dict(p)
            p2["intraday_price"] = snapshot["last_price"]
            p2["intraday_vol_ratio"] = snapshot["vol_ratio"]
            p2["intraday_last_vol"] = snapshot["last_vol"]
            to_alert.append(p2)

    if not to_alert:
        return

    chat_ids = _load_chat_ids()
    if not chat_ids:
        return

    for p in to_alert:
        for chat_id in chat_ids:
            try:
                msg = (
                    f"🚨 Intraday alert: {p['symbol']} vào vùng mua + volume xác nhận\n"
                    f"Giá hiện tại: {p['intraday_price']:.2f}\n"
                    f"Volume 15m: {p['intraday_last_vol']:,.0f} (x{p['intraday_vol_ratio']:.2f} so với nền gần nhất)\n"
                    f"Vùng mua: {p['plan']['entry_low']:.2f}-{p['plan']['entry_high']:.2f}\n"
                    f"SL: {p['plan']['sl']:.2f} | TP1: {p['plan']['tp1']:.2f} | TP2: {p['plan']['tp2']:.2f}"
                )
                await context.bot.send_message(chat_id=chat_id, text=msg)
            except Exception:
                continue

        today_sent.add(p["symbol"])

    sent[day_key] = sorted(today_sent)
    state["sent"] = sent
    _save_alert_state(state)


# ---------- Commands ----------
async def _register_chat(chat_id: int):
    chat_ids = _load_chat_ids()
    if chat_id not in chat_ids:
        chat_ids.add(chat_id)
        _save_chat_ids(chat_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _register_chat(chat_id)

    await update.message.reply_text(
        "Xin chào, mình là bot phân tích cổ phiếu VN (V2.1).\n"
        "Lệnh:\n"
        "/top3 - Top 3 mã ưu tiên + vùng mua/SL/TP + khối lượng\n"
        "/watchlist - Xem danh sách mã đang quét\n"
        "/reporttime - Xem giờ gửi báo cáo tự động\n"
        "/risk <von_vnd> <risk_pct> - Cài quản lý vốn, vd: /risk 100000000 1\n"
        "/myrisk - Xem cấu hình vốn/rủi ro hiện tại"
    )


async def top3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _register_chat(chat_id)

    await update.message.reply_text("Đang phân tích nhanh V2, chờ mình 3-8 giây...")
    msg = render_top3(chat_id=chat_id)
    await update.message.reply_text(msg)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wl = ", ".join(_get_watchlist())
    await update.message.reply_text(f"WATCHLIST hiện tại:\n{wl}")


async def reporttime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_name = os.getenv("BOT_TIMEZONE", "Asia/Saigon")
    report_time = os.getenv("DAILY_REPORT_TIME", "22:00")
    interval = os.getenv("INTRADAY_CHECK_MINUTES", "10")
    vol_mul = os.getenv("INTRADAY_VOLUME_MULTIPLIER", "1.3")
    min_last_vol = os.getenv("INTRADAY_MIN_LAST_VOLUME", "50000")
    await update.message.reply_text(
        f"Báo cáo tự động: mỗi ngày lúc {report_time} ({tz_name})\n"
        f"Intraday check: mỗi {interval} phút trong giờ giao dịch\n"
        f"Volume filter: >= x{vol_mul} và vol nến 15m >= {min_last_vol}"
    )


async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /risk <von_vnd> <risk_pct>\nVí dụ: /risk 100000000 1")
        return

    try:
        capital = float(context.args[0])
        risk_pct = float(context.args[1])
        if capital <= 0 or not (0.1 <= risk_pct <= 5.0):
            raise ValueError
    except Exception:
        await update.message.reply_text("Giá trị không hợp lệ. risk_pct nên trong khoảng 0.1 - 5.0")
        return

    _set_risk_profile(chat_id, capital, risk_pct)
    await update.message.reply_text(
        f"Đã lưu quản lý vốn:\n- Vốn: {capital:,.0f} VND\n- Rủi ro/lệnh: {risk_pct:.2f}%"
    )


async def myrisk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prof = _get_risk_profile(chat_id)
    await update.message.reply_text(
        f"Risk profile hiện tại:\n- Vốn: {prof['capital_vnd']:,.0f} VND\n- Rủi ro/lệnh: {prof['risk_pct']:.2f}%"
    )


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    chat_ids = _load_chat_ids()
    if not chat_ids:
        return

    for chat_id in chat_ids:
        try:
            msg = render_top3(chat_id=chat_id)
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
    interval_min = int(_safe_float(os.getenv("INTRADAY_CHECK_MINUTES", "10"), 10))
    interval_min = max(3, interval_min)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top3", top3))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("reporttime", reporttime))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("myrisk", myrisk))

    app.job_queue.run_daily(daily_report_job, time=report_time, name="daily_top3")
    app.job_queue.run_repeating(intraday_alert_job, interval=interval_min * 60, first=20, name="intraday_alerts")

    print(
        f"Bot V2 running... Daily report at {report_time.strftime('%H:%M')} ({tz_name}); "
        f"Intraday check every {interval_min} minutes"
    )
    app.run_polling()


if __name__ == "__main__":
    main()
