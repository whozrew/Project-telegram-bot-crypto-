"""
Halol Crypto AI Bot - Signal tizimi
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Tuple, Any
from dataclasses import dataclass

from config import (
    HALAL_COINS, MIN_CONFIDENCE_FOR_ALERT, MIN_SCORE_FOR_STRONG_SIGNAL,
    SIGNAL_EMOJI, SIGNAL_NAMES, RISK_NAMES, TREND_EMOJI, TREND_NAMES
)
from scanner import market_cache

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    symbol: str
    price: float
    signal_type: str          # KUCHLI_SOTIB_OLISH | SOTIB_OLISH | KUTISH | SOTISH | KUCHLI_SOTISH
    confidence: int           # 0-100%
    score: float              # Raw score
    trend: str                # bullish | bearish | neutral
    risk_level: str           # past | o'rta | yuqori
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    reasons: List[str] = None
    change_24h: float = 0.0
    volume: float = 0.0

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []


# ──────────────────────────────────────────────
# TEXNIK INDIKATORLAR
# ──────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def calc_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def calc_macd(close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = calc_ema(close, 12)
    ema26 = calc_ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = calc_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def calc_bollinger_bands(close: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + 2 * std
    lower = middle - 2 * std
    return upper, middle, lower


def calc_support_resistance(df: pd.DataFrame, lookback: int = 30) -> Tuple[float, float]:
    """Oddiy qo'llab-quvvatlash va qarshilik darajalari"""
    recent = df.tail(lookback)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    return support, resistance


def calc_volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    """Joriy hajm / O'rtacha hajm nisbati"""
    if len(df) < period + 1:
        return 1.0
    avg_vol = df["volume"].iloc[-(period + 1):-1].mean()
    cur_vol = df["volume"].iloc[-1]
    if avg_vol <= 0:
        return 1.0
    return float(cur_vol / avg_vol)


# ──────────────────────────────────────────────
# SIGNAL SCORING ENGINE
# ──────────────────────────────────────────────

def analyze_coin(symbol: str) -> Optional[SignalResult]:
    """
    Bir coin uchun to'liq texnik tahlil va signal hisoblash.
    """
    df = market_cache.get_klines(symbol)
    ticker = market_cache.get_ticker(symbol)
    price = market_cache.get_price(symbol)

    if df is None or len(df) < 50:
        return None
    if not price or price <= 0:
        price = ticker.get("price", 0) if ticker else 0
    if price <= 0:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Indikatorlarni hisoblash
    rsi = calc_rsi(close)
    ema20 = calc_ema(close, 20)
    ema50 = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)
    macd_line, signal_line, histogram = calc_macd(close)
    atr = calc_atr(high, low, close)
    bb_upper, bb_mid, bb_lower = calc_bollinger_bands(close)
    support, resistance = calc_support_resistance(df)
    vol_ratio = calc_volume_ratio(df)

    # Oxirgi qiymatlar
    rsi_val = float(rsi.iloc[-1]) if not rsi.empty else 50
    ema20_val = float(ema20.iloc[-1])
    ema50_val = float(ema50.iloc[-1])
    ema200_val = float(ema200.iloc[-1])
    macd_val = float(macd_line.iloc[-1])
    signal_val = float(signal_line.iloc[-1])
    hist_val = float(histogram.iloc[-1])
    hist_prev = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0
    atr_val = float(atr.iloc[-1])
    bb_upper_val = float(bb_upper.iloc[-1])
    bb_lower_val = float(bb_lower.iloc[-1])
    bb_mid_val = float(bb_mid.iloc[-1])

    # ────────────────────────────────
    # SCORING TIZIMI
    # ────────────────────────────────
    score = 0.0
    reasons_buy = []
    reasons_sell = []
    reasons_neutral = []

    # 1. RSI tahlili (max ±4)
    if rsi_val < 30:
        score += 4
        reasons_buy.append("RSI haddan tashqari pastda — tiklash kutilmoqda")
    elif rsi_val < 40:
        score += 2
        reasons_buy.append("RSI past zonada — xaridorlar faollashishi mumkin")
    elif rsi_val < 50:
        score += 1
        reasons_buy.append("RSI neytral pastda")
    elif rsi_val > 70:
        score -= 4
        reasons_sell.append("RSI haddan tashqari yuqori — sotish bosimi kuchli")
    elif rsi_val > 60:
        score -= 2
        reasons_sell.append("RSI yuqori zonada — ehtiyot bo'ling")
    elif rsi_val > 55:
        score -= 1

    # 2. EMA tahlili (max +6)
    # EMA 20 > EMA 50 (qisqa muddatli bullish)
    if ema20_val > ema50_val:
        score += 2
        reasons_buy.append("Qisqa muddatli trend o'sish yo'nalishida")
    else:
        score -= 2
        reasons_sell.append("Qisqa muddatli trend tushish yo'nalishida")

    # EMA 50 > EMA 200 (uzoq muddatli bullish)
    if ema50_val > ema200_val:
        score += 2
        reasons_buy.append("Uzoq muddatli trend bullish — oltin kesishish")
    else:
        score -= 2
        reasons_sell.append("Uzoq muddatli trend bearish")

    # Narx EMA 20 ustida
    if price > ema20_val:
        score += 1
        reasons_buy.append("Narx qisqa muddatli o'rtacha ustida")
    else:
        score -= 1

    # Narx EMA 200 ustida
    if price > ema200_val:
        score += 1
        reasons_buy.append("Narx uzoq muddatli o'rtacha ustida — kuchli signal")
    else:
        score -= 1

    # 3. EMA kesishish (max +3)
    ema20_prev = float(ema20.iloc[-2]) if len(ema20) >= 2 else ema20_val
    ema50_prev = float(ema50.iloc[-2]) if len(ema50) >= 2 else ema50_val
    if ema20_prev <= ema50_prev and ema20_val > ema50_val:
        score += 3
        reasons_buy.append("EMA kesishish aniqlandi — kuchli sotib olish signali")
    elif ema20_prev >= ema50_prev and ema20_val < ema50_val:
        score -= 3
        reasons_sell.append("EMA teskari kesishish — sotish signali")

    # 4. MACD tahlili (max ±3)
    if macd_val > signal_val:
        score += 2
        reasons_buy.append("MACD ijobiy — momentum o'sishda")
    else:
        score -= 2

    if hist_val > 0 and hist_val > hist_prev:
        score += 1
        reasons_buy.append("MACD histogram kuchaymoqda")
    elif hist_val < 0 and hist_val < hist_prev:
        score -= 1
        reasons_sell.append("MACD histogram kuchsizlanmoqda")

    # 5. Hajm tahlili (max +3)
    if vol_ratio > 2.5:
        score += 3
        reasons_buy.append("Savdo hajmi keskin oshgan — kuchli tasdiqlash")
    elif vol_ratio > 1.5:
        score += 2
        reasons_buy.append("Savdo hajmi o'rtachadan yuqori")
    elif vol_ratio > 1.2:
        score += 1
    elif vol_ratio < 0.5:
        reasons_neutral.append("Savdo hajmi past — kichik harakatlar bo'lishi mumkin")

    # 6. Breakout aniqlash (max +2)
    prev_high = float(df["high"].iloc[-20:-1].max())
    if price > prev_high * 0.99:
        score += 2
        reasons_buy.append("Narx qarshilik darajasini yengib o'tdi — breakout!")
    elif price < float(df["low"].iloc[-20:-1].min()) * 1.01:
        score -= 2
        reasons_sell.append("Narx qo'llab-quvvatlash darajasini sindirdi")

    # 7. Bollinger Bands (max ±2)
    if price <= bb_lower_val:
        score += 2
        reasons_buy.append("Narx quyi Bollinger chizig'ida — qaytish signali")
    elif price >= bb_upper_val:
        score -= 2
        reasons_sell.append("Narx yuqori Bollinger chizig'ida — to'yinish")

    # 8. 24h o'zgarish (max ±1)
    change_24h = ticker.get("change_pct", 0) if ticker else 0
    if change_24h > 5:
        score += 1
        reasons_buy.append(f"24 soatda {change_24h:.1f}% o'sish qayd etildi")
    elif change_24h < -5:
        score -= 1
        reasons_sell.append(f"24 soatda {abs(change_24h):.1f}% tushish qayd etildi")

    # ────────────────────────────────
    # SIGNAL TURI ANIQLASH
    # ────────────────────────────────
    max_score = 20.0
    norm_score = max(-max_score, min(max_score, score))

    if score >= 85:
        signal = SIGNAL_ENTRY

    elif score >= 70:
        signal = SIGNAL_WATCH

    elif score >= 50:
        signal = SIGNAL_WAIT

    else:
        signal = SIGNAL_NO_ENTRY

    # Trend
    if ema20_val > ema50_val > ema200_val and price > ema20_val:
        trend = "bullish"
    elif ema20_val < ema50_val < ema200_val and price < ema20_val:
        trend = "bearish"
    else:
        trend = "neutral"

    # ────────────────────────────────
    # KIRISH / CHIQISH DARAJALARI
    # ────────────────────────────────
    atr_mult = 1.5
    if signal_type in ("KUCHLI_SOTIB_OLISH", "SOTIB_OLISH"):
        entry_low = round(price * 0.99, 6)
        entry_high = round(price * 1.01, 6)
        stop_loss = round(price - atr_val * atr_mult, 6)
        take_profit_1 = round(price + atr_val * 2, 6)
        take_profit_2 = round(price + atr_val * 3.5, 6)
    elif signal_type in ("KUCHLI_SOTISH", "SOTISH"):
        entry_low = round(price * 0.99, 6)
        entry_high = round(price * 1.01, 6)
        stop_loss = round(price + atr_val * atr_mult, 6)
        take_profit_1 = round(price - atr_val * 2, 6)
        take_profit_2 = round(price - atr_val * 3.5, 6)
    else:
        entry_low = entry_high = stop_loss = take_profit_1 = take_profit_2 = 0.0

    return SignalResult(
        symbol=symbol,
        price=price,
        signal_type=signal_type,
        confidence=confidence,
        score=score,
        trend=trend,
        risk_level=risk_level,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        support=support,
        resistance=resistance,
        reasons=reasons,
        change_24h=change_24h,
        volume=ticker.get("quote_volume", 0) if ticker else 0,
    )


# ──────────────────────────────────────────────
# BARCHA COINLARNI SKANERLASH
# ──────────────────────────────────────────────

def scan_all_halal_coins() -> List[SignalResult]:
    """Barcha halol coinlarni skanerlash va natijalarni qaytarish"""
    results = []
    for sym in HALAL_COINS:
        try:
            result = analyze_coin(sym)
            if result:
                results.append(result)
        except Exception as e:
            logger.error(f"Signal xatosi {sym}: {e}")
    return results


def get_top_opportunities(n: int = 10) -> List[SignalResult]:
    """Eng yaxshi imkoniyatlarni qaytarish"""
    results = scan_all_halal_coins()
    # Faqat sotib olish signallari, ishonchlilik tartibida
    buy_signals = [
        r for r in results
        if r.signal_type in ("KUCHLI_SOTIB_OLISH", "SOTIB_OLISH")
        and r.confidence >= 55
    ]
    buy_signals.sort(key=lambda x: (x.confidence, x.score), reverse=True)
    return buy_signals[:n]


def get_strong_signals(min_confidence: int = None) -> List[SignalResult]:
    """Kuchli signallarni qaytarish"""
    if min_confidence is None:
        min_confidence = MIN_CONFIDENCE_FOR_ALERT
    results = scan_all_halal_coins()
    strong = [
        r for r in results
        if r.signal_type in ("KUCHLI_SOTIB_OLISH", "KUCHLI_SOTISH")
        and r.confidence >= min_confidence
    ]
    strong.sort(key=lambda x: x.confidence, reverse=True)
    return strong


# ──────────────────────────────────────────────
# XABAR FORMATLASH
# ──────────────────────────────────────────────

def format_price(price: float) -> str:
    """Narxni chiroyli formatlash"""
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    elif price >= 0.01:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def format_watchlist_signal(result: SignalResult) -> str:
    """Watchlist uchun signal xabari"""
    emoji = SIGNAL_EMOJI.get(result.signal_type, "🟡")
    trend_em = TREND_EMOJI.get(result.trend, "➡️")
    trend_name = TREND_NAMES.get(result.trend, "Neytral")
    signal_name = SIGNAL_NAMES.get(result.signal_type, result.signal_type)
    risk_name = RISK_NAMES.get(result.risk_level, result.risk_level)

    chg_str = ""
    if result.change_24h != 0:
        chg_emoji = "📈" if result.change_24h > 0 else "📉"
        chg_str = f"\n{chg_emoji} 24s: {result.change_24h:+.2f}%"

    reasons_str = "\n".join(f"• {r}" for r in result.reasons) if result.reasons else "• Tahlil mavjud"

    text = (
        f"🪙 *{result.symbol}*{chg_str}\n"
        f"💲 Narx: *{format_price(result.price)}*\n"
        f"📊 Signal: *{emoji} {signal_name}*\n"
        f"{trend_em} Trend: *{trend_name}*\n"
        f"⚠️ Risk: *{risk_name}*\n"
        f"🎯 Ishonchlilik: *{result.confidence}%*\n\n"
        f"💡 Sabab:\n{reasons_str}"
    )
    return text


def format_strong_alert(result: SignalResult) -> str:
    """Kuchli signal alert xabari"""
    emoji = SIGNAL_EMOJI.get(result.signal_type, "🟢")
    signal_name = SIGNAL_NAMES.get(result.signal_type, result.signal_type)
    risk_name = RISK_NAMES.get(result.risk_level, result.risk_level)

    reasons_str = "\n".join(f"• {r}" for r in result.reasons) if result.reasons else ""

    entry_str = ""
    if result.entry_low and result.entry_high:
        entry_str = (
            f"\n🎯 Kirish:\n"
            f"`{format_price(result.entry_low)}` – `{format_price(result.entry_high)}`"
        )

    sl_str = ""
    if result.stop_loss:
        sl_str = f"\n\n🛑 Stop Loss:\n`{format_price(result.stop_loss)}`"

    tp_str = ""
    if result.take_profit_1:
        tp_str = f"\n\n🎯 Take Profit:\n`{format_price(result.take_profit_1)}`"
        if result.take_profit_2:
            tp_str += f"\n`{format_price(result.take_profit_2)}`"

    text = (
        f"🚨 *MUHIM SIGNAL*\n\n"
        f"🪙 *{result.symbol}*\n"
        f"💲 Narx: *{format_price(result.price)}*\n"
        f"📊 Signal: *{emoji} {signal_name}*"
        f"{entry_str}"
        f"{sl_str}"
        f"{tp_str}\n\n"
        f"📈 Ishonchlilik: *{result.confidence}%*\n"
        f"⚠️ Risk: *{risk_name}*\n\n"
        f"💡 Tahlil:\n{reasons_str}\n\n"
        f"⚠️ _Bu ta'lim maqsadida. Moliyaviy maslahat emas._"
    )
    return text


def format_coin_detail(result: SignalResult) -> str:
    """Coin batafsil ma'lumoti"""
    emoji = SIGNAL_EMOJI.get(result.signal_type, "🟡")
    signal_name = SIGNAL_NAMES.get(result.signal_type, result.signal_type)
    trend_em = TREND_EMOJI.get(result.trend, "➡️")
    trend_name = TREND_NAMES.get(result.trend, "Neytral")
    risk_name = RISK_NAMES.get(result.risk_level, result.risk_level)

    chg_str = f"{result.change_24h:+.2f}%" if result.change_24h != 0 else "0%"
    vol_str = f"${result.volume:,.0f}" if result.volume else "Ma'lumot yo'q"
    reasons_str = "\n".join(f"• {r}" for r in result.reasons) if result.reasons else "• Tahlil mavjud"

    text = (
        f"📊 *{result.symbol} Tahlili*\n\n"
        f"💲 Narx: *{format_price(result.price)}*\n"
        f"📈 24s o'zgarish: *{chg_str}*\n"
        f"💹 Hajm: *{vol_str}*\n\n"
        f"📊 Signal: *{emoji} {signal_name}*\n"
        f"{trend_em} Trend: *{trend_name}*\n"
        f"⚠️ Risk: *{risk_name}*\n"
        f"🎯 Ishonchlilik: *{result.confidence}%*\n\n"
    )

    if result.signal_type in ("KUCHLI_SOTIB_OLISH", "SOTIB_OLISH"):
        text += (
            f"🎯 Kirish zonasi:\n"
            f"  `{format_price(result.entry_low)}` – `{format_price(result.entry_high)}`\n"
            f"🛑 Stop Loss: `{format_price(result.stop_loss)}`\n"
            f"✅ Maqsad 1: `{format_price(result.take_profit_1)}`\n"
            f"✅ Maqsad 2: `{format_price(result.take_profit_2)}`\n\n"
        )

    if result.support and result.resistance:
        text += (
            f"📉 Qo'llab-quvvatlash: `{format_price(result.support)}`\n"
            f"📈 Qarshilik: `{format_price(result.resistance)}`\n\n"
        )

    text += f"💡 Sabab:\n{reasons_str}\n\n"
    text += "⚠️ _Bu ta'lim maqsadida. Moliyaviy maslahat emas._"
    return text
