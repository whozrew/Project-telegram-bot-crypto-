"""
bot.py - HALOL CRYPTO AI BOT V3.5
Asosiy Telegram bot — barcha handler va menyular
Faqat halol spot savdo — futures/leveraj/short YO'Q
"""

import asyncio
import logging
import io
from typing import Optional, List

import aiohttp
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN, SIGNALS, RISK_LEVELS,
    HALAL_COINS, LOG_LEVEL, SCAN_INTERVAL,
    ALERT_THRESHOLD, RVOL_THRESHOLDS
)
from database import (
    init_database, upsert_user, get_user,
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    get_settings, update_setting, get_alert_history
)
from signals import SignalResult, compute_market_health
from scanner import (
    analyze_coin, scan_all_coins, find_strong_signals,
    get_coin_rankings, update_watchlist_signals,
    continuous_scanner
)
from ai_helper import (
    search_knowledge, AI_MENU_SECTIONS, get_section_topics,
    get_topic_content, get_all_topics
)
from utils import (
    format_price, format_pct, format_volume,
    get_symbol_base, normalize_symbol, setup_logging
)

logger = logging.getLogger(__name__)

# ============================================================
# XABAR FORMATLASH
# ============================================================

def format_signal_message(signal: SignalResult, detailed: bool = False) -> str:
    """Signal xabarini HTML formatda shakllantirish."""
    sig_cfg = SIGNALS.get(signal.signal_type, SIGNALS["WAIT"])
    risk_cfg = RISK_LEVELS.get(signal.risk_level, RISK_LEVELS["HIGH"])
    base = get_symbol_base(signal.symbol)

    # RVOL belgisi
    rvol = signal.rvol
    if rvol >= RVOL_THRESHOLDS["EXCEPTIONAL"]:
        rvol_badge = f"🚀 {rvol:.2f}x"
    elif rvol >= RVOL_THRESHOLDS["STRONG"]:
        rvol_badge = f"🔥 {rvol:.2f}x"
    elif rvol >= RVOL_THRESHOLDS["NORMAL_LOW"]:
        rvol_badge = f"✅ {rvol:.2f}x"
    else:
        rvol_badge = f"⚠️ {rvol:.2f}x"

    # Trend belgisi
    trend_badges = {
        "BULLISH": "📈 Bullish",
        "BEARISH": "📉 Bearish",
        "SIDEWAYS": "↔️ Yandeq",
    }
    trend_badge = trend_badges.get(signal.trend, "↔️ Yandeq")

    # O'zgarish belgisi
    chg = signal.change_24h
    chg_str = f"{'🟢' if chg >= 0 else '🔴'} {format_pct(chg)}"

    msg = (
        f"{sig_cfg['emoji']} <b>{sig_cfg['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 <b>{base}/USDT</b>  |  {chg_str}\n"
        f"💵 Narx: <code>${format_price(signal.price)}</code>\n"
        f"📊 Ishonch: <b>{signal.confidence}/100</b>  |  "
        f"🎯 Kirish Sifati: <b>{signal.entry_quality}/100</b>\n"
        f"📉 Trend: {trend_badge}  |  🔁 RVOL: {rvol_badge}\n"
        f"⚠️ Xavf: {risk_cfg['emoji']} {risk_cfg['name']}\n"
    )

    # Buy/Strong Buy uchun Risk Boshqaruvi
    if signal.signal_type in ("BUY", "STRONG_BUY") and signal.stop_loss > 0:
        msg += (
            f"\n<b>📐 Risk Boshqaruvi:</b>\n"
            f"  🟢 Kirish:    <code>${format_price(signal.price)}</code>\n"
            f"  🛑 Stop Loss: <code>${format_price(signal.stop_loss)}</code>\n"
            f"  🎯 TP1:       <code>${format_price(signal.tp1)}</code>\n"
            f"  🎯 TP2:       <code>${format_price(signal.tp2)}</code>\n"
            f"  🎯 TP3:       <code>${format_price(signal.tp3)}</code>\n"
            f"  ⚖️ R:R:       <b>1:{signal.risk_reward}</b>\n"
        )

    # Batafsil ko'rsatish
    if detailed:
        ind = signal.indicators
        struct = signal.structure

        msg += f"\n<b>📊 Indikatorlar:</b>\n"
        msg += f"  RSI: <b>{ind.get('rsi', 0):.1f}</b>  "
        msg += f"ADX: <b>{ind.get('adx', 0):.1f}</b>  "
        msg += f"ATR: <b>${format_price(ind.get('atr', 0))}</b>\n"

        msg += (
            f"  EMA20: <code>${format_price(ind.get('ema20', 0))}</code>  "
            f"EMA50: <code>${format_price(ind.get('ema50', 0))}</code>  "
            f"EMA200: <code>${format_price(ind.get('ema200', 0))}</code>\n"
        )

        macd_hist = ind.get("macd_hist", 0)
        macd_icon = "🟢" if macd_hist > 0 else "🔴"
        msg += f"  MACD Hist: {macd_icon} <b>{macd_hist:.6f}</b>\n"

        msg += f"\n<b>🏗️ Bozor Tuzilmasi:</b>\n"
        msg += f"  Support: <code>${format_price(struct.get('support', 0))}</code>  "
        msg += f"Resistance: <code>${format_price(struct.get('resistance', 0))}</code>\n"

        flags = []
        if struct.get("order_block_bull"):    flags.append("🟦 Bull OB")
        if struct.get("fvg_bull"):            flags.append("📐 FVG")
        if struct.get("bos_bullish"):         flags.append("💥 BOS")
        if struct.get("choch_bullish"):       flags.append("🔄 CHoCH")
        if struct.get("liquidity_sweep_bull"):flags.append("💧 Likvidlik")
        if struct.get("breakout_detected") and struct.get("retest_confirmed"):
            flags.append("✅ Breakout+Retest")
        elif struct.get("breakout_detected"):
            flags.append("💥 Breakout")
        if struct.get("higher_highs"):        flags.append("📈 HH")
        if struct.get("higher_lows"):         flags.append("📈 HL")

        if flags:
            msg += "  " + "  ".join(flags) + "\n"

        # Asoslar
        if signal.reasoning:
            msg += f"\n<b>🔍 Nega bu signal?</b>\n"
            for reason in signal.reasoning[:6]:
                msg += f"  {reason}\n"

    msg += f"\n⏱ <i>Vaqt oralig'i: {signal.timeframe.upper()}</i>"
    return msg


def format_market_health(health: dict) -> str:
    """Bozor holati xabarini shakllantirish."""
    score = health.get("score", 50)
    if score >= 70:
        bar = "🟩🟩🟩🟩🟩"
    elif score >= 55:
        bar = "🟩🟩🟩🟩⬜"
    elif score >= 40:
        bar = "🟩🟩🟩⬜⬜"
    elif score >= 25:
        bar = "🟨🟨⬜⬜⬜"
    else:
        bar = "🟥⬜⬜⬜⬜"

    bull = health.get("bull_count", 0)
    bear = health.get("bear_count", 0)
    total = health.get("total", 1)

    return (
        f"📊 <b>Bozor Holati</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌡 Ball: <b>{score}/100</b>  {bar}\n\n"
        f"📈 Trend:      {health.get('trend', 'Noaniq')}\n"
        f"⚡ Momentum:   {health.get('momentum', 'O\'rta')}\n"
        f"📦 Hajm:       {health.get('volume', 'O\'rta')}\n"
        f"🌊 Volatillik: {health.get('volatility', 'O\'rta')}\n\n"
        f"🐂 Buqali: <b>{bull}</b>  🐻 Ayiqli: <b>{bear}</b>  "
        f"Jami: <b>{total}</b>\n"
    )


# ============================================================
# INLINE KLAVIATURALAR
# ============================================================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Signal",          callback_data="menu_signal"),
            InlineKeyboardButton("📈 Coin Tahlili",    callback_data="menu_analysis"),
        ],
        [
            InlineKeyboardButton("⭐ Watchlist",        callback_data="menu_watchlist"),
            InlineKeyboardButton("🚨 Kuchli Signallar", callback_data="menu_strong"),
        ],
        [
            InlineKeyboardButton("📚 AI Yordamchi",    callback_data="menu_ai"),
            InlineKeyboardButton("📊 Bozor Holati",    callback_data="menu_market"),
        ],
        [
            InlineKeyboardButton("🏆 Imkoniyatlar",    callback_data="menu_opps"),
            InlineKeyboardButton("📈 Reyting",          callback_data="menu_ranking"),
        ],
        [
            InlineKeyboardButton("⚙️ Sozlamalar",       callback_data="menu_settings"),
            InlineKeyboardButton("ℹ️ Yordam",            callback_data="menu_help"),
        ],
    ])


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")]
    ])


def ai_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Kripto Asoslari",   callback_data="ai_basics")],
        [InlineKeyboardButton("📈 Texnik Tahlil",     callback_data="ai_technical")],
        [InlineKeyboardButton("💰 Spot Savdo",        callback_data="ai_spot_trading")],
        [InlineKeyboardButton("🕌 Halol Kripto",      callback_data="ai_halal_crypto")],
        [InlineKeyboardButton("⚠️ Risk Boshqaruvi",  callback_data="ai_risk_management")],
        [InlineKeyboardButton("🏦 Smart Money",       callback_data="ai_smart_money")],
        [InlineKeyboardButton("🔍 Savol Berish",      callback_data="ai_search")],
        [InlineKeyboardButton("🏠 Asosiy Menyu",      callback_data="menu_main")],
    ])


def ai_section_keyboard(section_key: str) -> InlineKeyboardMarkup:
    topics = get_section_topics(section_key)
    buttons = []
    for t in topics:
        buttons.append([InlineKeyboardButton(t["title"], callback_data=f"ai_topic_{t['key']}")])
    buttons.append([InlineKeyboardButton("◀️ AI Menyu", callback_data="menu_ai")])
    return InlineKeyboardMarkup(buttons)


def watchlist_keyboard(symbols: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, sym in enumerate(symbols):
        base = get_symbol_base(sym)
        row.append(InlineKeyboardButton(f"📊 {base}", callback_data=f"analyze_{sym}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("➕ Qo'shish",  callback_data="watchlist_add"),
        InlineKeyboardButton("➖ O'chirish", callback_data="watchlist_remove"),
    ])
    buttons.append([InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def coin_select_keyboard(coins: List[str], prefix: str = "analyze",
                          cols: int = 3) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, sym in enumerate(coins[:30]):
        base = get_symbol_base(sym)
        row.append(InlineKeyboardButton(base, callback_data=f"{prefix}_{sym}"))
        if len(row) == cols:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def ranking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Eng Kuchli Ishonch", callback_data="rank_confidence")],
        [InlineKeyboardButton("🔥 Eng Yuqori RVOL",   callback_data="rank_rvol")],
        [InlineKeyboardButton("⚖️ Eng Yaxshi R:R",    callback_data="rank_rr")],
        [InlineKeyboardButton("🎯 Kirish Sifati",      callback_data="rank_quality")],
        [InlineKeyboardButton("🏠 Asosiy Menyu",       callback_data="menu_main")],
    ])


def settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    alert_icon = "🔔" if settings.get("notify_strong") else "🔕"
    chart_icon = "📊" if settings.get("show_chart") else "📉"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{alert_icon} Ogohlantirishlar",
                              callback_data="settings_alerts")],
        [InlineKeyboardButton(f"{chart_icon} Grafiklar",
                              callback_data="settings_charts")],
        [InlineKeyboardButton("📊 Chegara (threshold)",
                              callback_data="settings_threshold")],
        [InlineKeyboardButton("🏠 Asosiy Menyu",
                              callback_data="menu_main")],
    ])


# ============================================================
# /START KOMANDASI
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(
        user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )

    welcome = (
        f"🕌 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"<b>HALOL CRYPTO AI BOT V3.5</b> ga xush kelibsiz!\n\n"
        f"Bu bot faqat <b>halol spot savdo</b> uchun mo'ljallangan:\n"
        f"✅ Spot savdo signallari\n"
        f"✅ Texnik tahlil (RSI, EMA, MACD, ADX...)\n"
        f"✅ Smart Money tahlili (OB, FVG, BOS, CHoCH)\n"
        f"✅ Risk boshqaruvi (SL, TP1, TP2, TP3)\n"
        f"✅ Ko'p vaqt oralig'i tahlili\n"
        f"✅ Likvidlik va breakout aniqlash\n\n"
        f"❌ <b>FUTURES, LEVERAJ, SHORT</b> — HECH QACHON\n\n"
        f"Quyidagi menyudan boshlang:"
    )
    await update.message.reply_text(
        welcome, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )


# ============================================================
# /MENU KOMANDASI
# ============================================================

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 <b>Asosiy Menyu</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )


# ============================================================
# CALLBACK QUERY HANDLER
# ============================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    user = query.from_user
    upsert_user(user.id, username=user.username or "",
                first_name=user.first_name or "")

    # ---- ASOSIY MENYU ----
    if data == "menu_main":
        await query.edit_message_text(
            "📋 <b>Asosiy Menyu</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )

    # ---- SIGNAL MENYUSI ----
    elif data == "menu_signal":
        watchlist = get_watchlist(user.id)
        await query.edit_message_text(
            "📊 <b>Signal</b>\n\nQaysi tanga tahlilini ko'rmoqchisiz?",
            parse_mode=ParseMode.HTML,
            reply_markup=coin_select_keyboard(watchlist, "analyze")
        )

    # ---- COIN TAHLILI ----
    elif data == "menu_analysis":
        await query.edit_message_text(
            "📈 <b>Coin Tahlili</b>\n\nTanga tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=coin_select_keyboard(HALAL_COINS[:24], "analyze")
        )

    # ---- TANGA TAHLILI (analyze_XXXUSDT) ----
    elif data.startswith("analyze_"):
        symbol = data.replace("analyze_", "")
        await _show_coin_analysis(query, context, symbol)

    # ---- WATCHLIST ----
    elif data == "menu_watchlist":
        watchlist = get_watchlist(user.id)
        base_names = [get_symbol_base(s) for s in watchlist]
        wl_text = "  |  ".join(base_names) if base_names else "Bo'sh"
        await query.edit_message_text(
            f"⭐ <b>Mening Watchlistim</b>\n\n"
            f"<code>{wl_text}</code>\n\n"
            f"Tahlil uchun tanga tanlang yoki boshqaring:",
            parse_mode=ParseMode.HTML,
            reply_markup=watchlist_keyboard(watchlist)
        )

    elif data == "watchlist_add":
        await query.edit_message_text(
            "➕ <b>Watchlistga Qo'shish</b>\n\n"
            "Tanga belgisini yuboring (masalan: BTC, ETH, SOL):",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )
        context.user_data["awaiting"] = "watchlist_add"

    elif data == "watchlist_remove":
        watchlist = get_watchlist(user.id)
        buttons = []
        row = []
        for sym in watchlist:
            base = get_symbol_base(sym)
            row.append(InlineKeyboardButton(
                f"❌ {base}", callback_data=f"wl_remove_{sym}"
            ))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="menu_watchlist")])
        await query.edit_message_text(
            "➖ <b>Watchlistdan O'chirish</b>\n\nQaysi tangani o'chirish?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("wl_remove_"):
        symbol = data.replace("wl_remove_", "")
        success = remove_from_watchlist(user.id, symbol)
        base = get_symbol_base(symbol)
        msg = f"✅ <b>{base}</b> watchlistdan o'chirildi." if success else "❌ Xato yuz berdi."
        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )

    # ---- KUCHLI SIGNALLAR ----
    elif data == "menu_strong":
        await query.edit_message_text(
            "🚨 <b>Kuchli Signallar Skanerlanmoqda...</b>\n\n"
            "⏳ Iltimos kuting (20-60 soniya)...",
            parse_mode=ParseMode.HTML
        )
        await _show_strong_signals(query, context)

    # ---- BOZOR HOLATI ----
    elif data == "menu_market":
        await query.edit_message_text(
            "📊 <b>Bozor Holati Hisoblanmoqda...</b>\n\n⏳ Kuting...",
            parse_mode=ParseMode.HTML
        )
        await _show_market_health(query, context)

    # ---- TOP IMKONIYATLAR ----
    elif data == "menu_opps":
        await query.edit_message_text(
            "🏆 <b>Eng Kuchli Imkoniyatlar Skanerlanmoqda...</b>\n\n⏳ Kuting...",
            parse_mode=ParseMode.HTML
        )
        await _show_top_opportunities(query, context)

    # ---- REYTING ----
    elif data == "menu_ranking":
        await query.edit_message_text(
            "📈 <b>Reyting</b>\n\nQaysi mezon bo'yicha?",
            parse_mode=ParseMode.HTML,
            reply_markup=ranking_keyboard()
        )

    elif data.startswith("rank_"):
        rank_type = data.replace("rank_", "")
        await query.edit_message_text(
            "📊 <b>Reyting hisoblanmoqda...</b>\n\n⏳ Kuting...",
            parse_mode=ParseMode.HTML
        )
        await _show_ranking(query, context, rank_type)

    # ---- AI YORDAMCHI ----
    elif data == "menu_ai":
        await query.edit_message_text(
            "🤖 <b>AI Yordamchi</b>\n\n"
            "Kripto savdo va tahlil bo'yicha batafsil ma'lumot.\n"
            "Mavzu tanlang yoki savol bering:",
            parse_mode=ParseMode.HTML,
            reply_markup=ai_menu_keyboard()
        )

    elif data.startswith("ai_") and not data.startswith("ai_topic_"):
        section_key = data.replace("ai_", "")
        if section_key == "search":
            await query.edit_message_text(
                "🔍 <b>Savol Berish</b>\n\n"
                "Quyidagi mavzulardan birini yozing:\n\n"
                "<code>rsi  macd  ema  adx  atr\n"
                "bollinger  volume  support  resistance\n"
                "orderblock  fvg  bos  choch\n"
                "candlestick  trend  breakout\n"
                "liquidity  spot  halol  risk\n"
                "position  portfolio  bullmarket  bearmarket</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            context.user_data["awaiting"] = "ai_search"
        elif section_key in AI_MENU_SECTIONS:
            section = AI_MENU_SECTIONS[section_key]
            await query.edit_message_text(
                f"{section['emoji']} <b>{section['title']}</b>\n\nMavzu tanlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=ai_section_keyboard(section_key)
            )

    elif data.startswith("ai_topic_"):
        topic_key = data.replace("ai_topic_", "")
        content = get_topic_content(topic_key)
        if content:
            await query.edit_message_text(
                content,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Orqaga", callback_data="menu_ai")]
                ])
            )

    # ---- SOZLAMALAR ----
    elif data == "menu_settings":
        settings = get_settings(user.id)
        msg = (
            f"⚙️ <b>Sozlamalar</b>\n\n"
            f"🔔 Kuchli signal ogohlantirish: "
            f"{'✅ Yoqilgan' if settings.get('notify_strong') else '❌ O\'chirilgan'}\n"
            f"📊 Grafik ko'rsatish: "
            f"{'✅ Ha' if settings.get('show_chart') else '❌ Yo\'q'}\n"
            f"🎯 Signal chegarasi: <b>{settings.get('alert_threshold', 70)}/100</b>\n"
        )
        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=settings_keyboard(settings)
        )

    elif data == "settings_alerts":
        settings = get_settings(user.id)
        current = settings.get("notify_strong", 1)
        new_val = 0 if current else 1
        update_setting(user.id, "notify_strong", new_val)
        status = "Yoqildi ✅" if new_val else "O'chirildi ❌"
        await query.answer(f"Ogohlantirishlar: {status}")
        settings["notify_strong"] = new_val
        msg = (
            f"⚙️ <b>Sozlamalar</b>\n\n"
            f"🔔 Kuchli signal ogohlantirish: "
            f"{'✅ Yoqilgan' if settings.get('notify_strong') else '❌ O\'chirilgan'}\n"
            f"📊 Grafik ko'rsatish: "
            f"{'✅ Ha' if settings.get('show_chart') else '❌ Yo\'q'}\n"
            f"🎯 Signal chegarasi: <b>{settings.get('alert_threshold', 70)}/100</b>\n"
        )
        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=settings_keyboard(settings)
        )

    elif data == "settings_charts":
        settings = get_settings(user.id)
        current = settings.get("show_chart", 1)
        new_val = 0 if current else 1
        update_setting(user.id, "show_chart", new_val)
        status = "Yoqildi ✅" if new_val else "O'chirildi ❌"
        await query.answer(f"Grafiklar: {status}")
        settings["show_chart"] = new_val
        msg = (
            f"⚙️ <b>Sozlamalar</b>\n\n"
            f"🔔 Kuchli signal ogohlantirish: "
            f"{'✅ Yoqilgan' if settings.get('notify_strong') else '❌ O\'chirilgan'}\n"
            f"📊 Grafik ko'rsatish: "
            f"{'✅ Ha' if settings.get('show_chart') else '❌ Yo\'q'}\n"
            f"🎯 Signal chegarasi: <b>{settings.get('alert_threshold', 70)}/100</b>\n"
        )
        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=settings_keyboard(settings)
        )

    elif data == "settings_threshold":
        await query.edit_message_text(
            "🎯 <b>Signal Chegarasini O'zgartirish</b>\n\n"
            "Ogohlantirish yuborish uchun minimal ishonch ballini yuboring.\n"
            "Masalan: <code>65</code> yoki <code>80</code>\n\n"
            "Tavsiya: 60-80",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )
        context.user_data["awaiting"] = "threshold_input"

    # ---- YORDAM ----
    elif data == "menu_help":
        help_text = (
            "ℹ️ <b>Yordam — HALOL CRYPTO AI BOT V3.5</b>\n\n"
            "<b>🤖 Bot nima qiladi?</b>\n"
            "Halol spot savdo uchun texnik tahlil va signal beradi.\n\n"
            "<b>📊 Signal turlari:</b>\n"
            "🔥 KUCHLI SOTIB OLISH (80-100)\n"
            "🟢 SOTIB OLISH (60-79)\n"
            "🟡 KUTISH (40-59)\n"
            "🔵 FOYDA OLISH (bearish)\n"
            "🟠 XAVF OSHDI (yuqori xavf)\n\n"
            "<b>🕌 Halol tamoyillar:</b>\n"
            "✅ Faqat spot savdo\n"
            "✅ Faqat long pozitsiyalar\n"
            "❌ Futures/leveraj/short — yo'q\n\n"
            "<b>📐 Indikatorlar:</b>\n"
            "RSI, EMA20/50/200, MACD, ADX, ATR,\n"
            "Bollinger Bands, Volume, RVOL\n\n"
            "<b>🏦 Smart Money:</b>\n"
            "Order Blocks, FVG, BOS, CHoCH,\n"
            "Liquidity Sweeps, Breakout+Retest\n\n"
            "<b>⏱ Vaqt oraliqlar:</b>\n"
            "15m, 1h, 4h, 1d (ko'p vaqt tahlili)\n\n"
            "<b>📞 Komandalar:</b>\n"
            "/start — Botni ishga tushirish\n"
            "/menu — Asosiy menyuni ko'rsatish\n"
            "/signal [tanga] — Tezkor signal\n"
            "/watchlist — Kuzatuv ro'yxati\n"
            "/market — Bozor holati"
        )
        await query.edit_message_text(
            help_text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# TAHLIL SAHIFASI
# ============================================================

async def _show_coin_analysis(query, context, symbol: str):
    """Tanga tahlilini ko'rsatish."""
    base = get_symbol_base(symbol)
    await query.edit_message_text(
        f"🔍 <b>{base}/USDT</b> tahlil qilinmoqda...\n\n⏳ Kuting (5-15 soniya)...",
        parse_mode=ParseMode.HTML
    )

    try:
        async with aiohttp.ClientSession() as session:
            signal = await analyze_coin(session, symbol, "1h", full_mtf=True)

        if not signal:
            await query.edit_message_text(
                f"❌ <b>{base}/USDT</b> uchun ma'lumot olishda xato.\n"
                "Bir ozdan so'ng qayta urinib ko'ring.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            return

        msg = format_signal_message(signal, detailed=True)
        user_settings = get_settings(query.from_user.id)

        # Grafik yuborish
        if user_settings.get("show_chart", 1):
            try:
                from charts import generate_chart
                from scanner import analyze_coin as ac
                from signals import parse_klines
                from utils import fetch_klines

                async with aiohttp.ClientSession() as session:
                    raw = await fetch_klines(session, symbol, "1h", 120)
                    ohlcv = parse_klines(raw)

                if ohlcv:
                    chart_bytes = generate_chart(ohlcv, signal)
                    if chart_bytes:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=io.BytesIO(chart_bytes),
                            caption=f"📊 {base}/USDT — 1H Grafik",
                        )
            except Exception as e:
                logger.warning(f"Grafik yuborish xatosi: {e}")

        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Yangilash",
                                         callback_data=f"analyze_{symbol}"),
                    InlineKeyboardButton("⭐ Watchlist",
                                         callback_data=f"wl_add_{symbol}"),
                ],
                [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")]
            ])
        )

    except Exception as e:
        logger.error(f"Tahlil ko'rsatish xatosi {symbol}: {e}")
        await query.edit_message_text(
            f"❌ Xato yuz berdi: {str(e)[:100]}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# KUCHLI SIGNALLAR
# ============================================================

async def _show_strong_signals(query, context):
    try:
        async with aiohttp.ClientSession() as session:
            signals = await find_strong_signals(session, ALERT_THRESHOLD)

        if not signals:
            await query.edit_message_text(
                "🚨 <b>Kuchli Signallar</b>\n\n"
                "Hozirda yetarli ishonchli signal topilmadi.\n"
                f"Chegara: {ALERT_THRESHOLD}/100\n\n"
                "Keyinroq qayta urinib ko'ring.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            return

        msg = f"🚨 <b>Kuchli Signallar</b> ({len(signals)} ta)\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        for s in signals[:10]:
            sig_cfg = SIGNALS.get(s.signal_type, {})
            base = get_symbol_base(s.symbol)
            chg = f"{'🟢' if s.change_24h >= 0 else '🔴'} {format_pct(s.change_24h)}"
            msg += (
                f"{sig_cfg.get('emoji','📊')} <b>{base}/USDT</b>  {chg}\n"
                f"   💵 ${format_price(s.price)}  |  "
                f"📊 {s.confidence}%  |  🔁 {s.rvol:.2f}x\n\n"
            )

        buttons = []
        row = []
        for s in signals[:6]:
            base = get_symbol_base(s.symbol)
            row.append(InlineKeyboardButton(f"📊 {base}",
                                             callback_data=f"analyze_{s.symbol}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")])

        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Kuchli signallar xatosi: {e}")
        await query.edit_message_text(
            f"❌ Xato: {str(e)[:100]}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# BOZOR HOLATI
# ============================================================

async def _show_market_health(query, context):
    try:
        async with aiohttp.ClientSession() as session:
            all_signals = await scan_all_coins(session, HALAL_COINS[:40])

        health = compute_market_health(all_signals)
        msg = format_market_health(health)

        # Top 5 bullish
        top_bull = sorted(
            [s for s in all_signals if s.trend == "BULLISH"],
            key=lambda x: x.confidence, reverse=True
        )[:5]

        if top_bull:
            msg += "\n<b>🏆 Top Bullish Tangalar:</b>\n"
            for i, s in enumerate(top_bull, 1):
                base = get_symbol_base(s.symbol)
                msg += f"  {i}. <b>{base}</b> — {s.confidence}%\n"

        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Bozor holati xatosi: {e}")
        await query.edit_message_text(
            f"❌ Xato: {str(e)[:100]}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# TOP IMKONIYATLAR
# ============================================================

async def _show_top_opportunities(query, context):
    try:
        async with aiohttp.ClientSession() as session:
            signals = await find_strong_signals(session, 60)

        if not signals:
            await query.edit_message_text(
                "🏆 <b>Eng Kuchli Imkoniyatlar</b>\n\n"
                "Hozirda kuchli imkoniyat topilmadi.\n"
                "Bozor hozir noaniq — sabr qiling.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            return

        top10 = signals[:10]
        msg = f"🏆 <b>Eng Kuchli Imkoniyatlar</b> (Top {len(top10)})\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, s in enumerate(top10, 1):
            sig_cfg = SIGNALS.get(s.signal_type, {})
            base = get_symbol_base(s.symbol)
            chg = format_pct(s.change_24h)
            msg += (
                f"{i}. {sig_cfg.get('emoji','📊')} <b>{base}/USDT</b>\n"
                f"   📊 Ishonch: <b>{s.confidence}%</b>  "
                f"🎯 Sifat: <b>{s.entry_quality}/100</b>\n"
                f"   📈 {s.trend}  |  🔁 RVOL: {s.rvol:.2f}x  |  {chg}\n"
                f"   ⚖️ R:R: 1:{s.risk_reward}\n\n"
            )

        buttons = []
        row = []
        for s in top10[:9]:
            base = get_symbol_base(s.symbol)
            row.append(InlineKeyboardButton(f"📊 {base}",
                                             callback_data=f"analyze_{s.symbol}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")])

        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Top imkoniyatlar xatosi: {e}")
        await query.edit_message_text(
            f"❌ Xato: {str(e)[:100]}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# REYTING
# ============================================================

async def _show_ranking(query, context, rank_type: str):
    try:
        async with aiohttp.ClientSession() as session:
            rankings = await get_coin_rankings(session, 20)

        rank_map = {
            "confidence": ("by_confidence", "🏆 Eng Kuchli Ishonch Reytingi"),
            "rvol":       ("by_rvol",        "🔥 Eng Yuqori RVOL Reytingi"),
            "rr":         ("by_rr",          "⚖️ Eng Yaxshi Risk/Reward"),
            "quality":    ("by_quality",     "🎯 Kirish Sifati Reytingi"),
        }

        key, title = rank_map.get(rank_type, ("by_confidence", "🏆 Reyting"))
        ranked = rankings.get(key, [])[:10]

        msg = f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, s in enumerate(ranked):
            base = get_symbol_base(s.symbol)
            medal = medals[i] if i < len(medals) else f"{i+1}."
            sig_cfg = SIGNALS.get(s.signal_type, {})

            if rank_type == "rvol":
                metric = f"RVOL: {s.rvol:.2f}x"
            elif rank_type == "rr":
                metric = f"R:R: 1:{s.risk_reward}"
            elif rank_type == "quality":
                metric = f"Sifat: {s.entry_quality}/100"
            else:
                metric = f"Ishonch: {s.confidence}%"

            msg += (
                f"{medal} <b>{base}</b>  {sig_cfg.get('emoji', '')} "
                f"{metric}  📈{s.trend[:4]}\n"
            )

        await query.edit_message_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=ranking_keyboard()
        )

    except Exception as e:
        logger.error(f"Reyting xatosi: {e}")
        await query.edit_message_text(
            f"❌ Xato: {str(e)[:100]}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )


# ============================================================
# MATN XABARLARI HANDLER
# ============================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    upsert_user(user.id)

    awaiting = context.user_data.get("awaiting")

    # ---- WATCHLIST QO'SHISH ----
    if awaiting == "watchlist_add":
        context.user_data.pop("awaiting", None)
        symbol = normalize_symbol(text.upper())
        if symbol not in [s.upper() for s in HALAL_COINS]:
            await update.message.reply_text(
                f"❌ <b>{text.upper()}</b> qo'llab-quvvatlanmaydi.\n\n"
                "Faqat halol tangalar qo'shish mumkin.\n"
                "Mavjud tangalar: /halal_coins",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            return
        success = add_to_watchlist(user.id, symbol)
        if success:
            await update.message.reply_text(
                f"✅ <b>{get_symbol_base(symbol)}</b> watchlistga qo'shildi!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Qo'shib bo'lmadi. Watchlist to'la yoki tanga allaqachon mavjud.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
        return

    # ---- AI IZLASH ----
    if awaiting == "ai_search":
        context.user_data.pop("awaiting", None)
        result = search_knowledge(text.lower())
        if result:
            await update.message.reply_text(
                result["content"],
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 AI Menyu", callback_data="menu_ai")],
                    [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")],
                ])
            )
        else:
            topics = "  ".join(get_all_topics())
            await update.message.reply_text(
                f"🔍 '<b>{text}</b>' topilmadi.\n\n"
                f"Mavjud mavzular:\n<code>{topics}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Qayta Izlash", callback_data="ai_search")],
                    [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")],
                ])
            )
        return

    # ---- CHEGARA O'ZGARTIRISH ----
    if awaiting == "threshold_input":
        context.user_data.pop("awaiting", None)
        try:
            val = int(text)
            if 40 <= val <= 95:
                update_setting(user.id, "alert_threshold", val)
                await update.message.reply_text(
                    f"✅ Signal chegarasi <b>{val}</b> ga o'zgartirildi.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ 40-95 oralig'ida qiymat kiriting.",
                    reply_markup=back_to_main_keyboard()
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Raqam kiriting (masalan: 70)",
                reply_markup=back_to_main_keyboard()
            )
        return

    # ---- TEZKOR TANGA IZLASH ----
    sym_try = normalize_symbol(text)
    if sym_try in [s.upper() for s in HALAL_COINS]:
        await update.message.reply_text(
            f"🔍 <b>{get_symbol_base(sym_try)}</b> tahlil qilinmoqda...",
            parse_mode=ParseMode.HTML
        )
        try:
            async with aiohttp.ClientSession() as session:
                signal = await analyze_coin(session, sym_try, "1h", full_mtf=True)
            if signal:
                msg = format_signal_message(signal, detailed=True)
                await update.message.reply_text(
                    msg, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="menu_main")]
                    ])
                )
            else:
                await update.message.reply_text("❌ Ma'lumot olishda xato.")
        except Exception as e:
            await update.message.reply_text(f"❌ Xato: {str(e)[:100]}")
        return

    # ---- STANDART JAVOB ----
    await update.message.reply_text(
        "📋 Menyudan foydalaning:",
        reply_markup=main_menu_keyboard()
    )


# ============================================================
# KOMANDALAR
# ============================================================

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        symbol = normalize_symbol(args[0].upper())
        await update.message.reply_text(f"🔍 {get_symbol_base(symbol)} tahlil qilinmoqda...")
        try:
            async with aiohttp.ClientSession() as session:
                signal = await analyze_coin(session, symbol, "1h", full_mtf=True)
            if signal:
                await update.message.reply_text(
                    format_signal_message(signal, detailed=True),
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_main_keyboard()
                )
            else:
                await update.message.reply_text("❌ Ma'lumot topilmadi.")
        except Exception as e:
            await update.message.reply_text(f"❌ Xato: {e}")
    else:
        watchlist = get_watchlist(update.effective_user.id)
        await update.message.reply_text(
            "📊 Qaysi tanga?",
            reply_markup=coin_select_keyboard(watchlist, "analyze")
        )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    watchlist = get_watchlist(uid)
    base_names = [get_symbol_base(s) for s in watchlist]
    await update.message.reply_text(
        f"⭐ <b>Watchlist:</b> {', '.join(base_names) or 'Bo\'sh'}",
        parse_mode=ParseMode.HTML,
        reply_markup=watchlist_keyboard(watchlist)
    )


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Bozor holati hisoblanmoqda...")
    try:
        async with aiohttp.ClientSession() as session:
            signals = await scan_all_coins(session, HALAL_COINS[:40])
        health = compute_market_health(signals)
        await update.message.reply_text(
            format_market_health(health),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")


# ============================================================
# WL_ADD CALLBACK
# ============================================================

async def handle_wl_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("wl_add_"):
        symbol = query.data.replace("wl_add_", "")
        success = add_to_watchlist(query.from_user.id, symbol)
        base = get_symbol_base(symbol)
        if success:
            await query.answer(f"✅ {base} watchlistga qo'shildi!", show_alert=True)
        else:
            await query.answer(f"⚠️ {base} allaqachon mavjud yoki limit to'ldi.", show_alert=True)


# ============================================================
# BOTNI ISHGA TUSHIRISH
# ============================================================

async def post_init(application: Application):
    """Bot ishga tushgandan keyin chaqiriladigan funksiya."""
    await application.bot.set_my_commands([
        BotCommand("start",     "Botni ishga tushirish"),
        BotCommand("menu",      "Asosiy menyuni ko'rsatish"),
        BotCommand("signal",    "Tezkor signal olish"),
        BotCommand("watchlist", "Kuzatuv ro'yxatim"),
        BotCommand("market",    "Bozor holati"),
    ])
    logger.info("✅ Bot komandalar ro'yxati o'rnatildi")


def run_bot():
    """Asosiy kirish nuqtasi."""
    setup_logging(LOG_LEVEL)

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    # Ma'lumotlar bazasini ishga tushirish
    init_database()

    # Botni sozlash
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handler'larni qo'shish
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("menu",      cmd_menu))
    app.add_handler(CommandHandler("signal",    cmd_signal))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("market",    cmd_market))

    # wl_add callback (analyze dan keyin)
    app.add_handler(CallbackQueryHandler(handle_wl_add_callback, pattern="^wl_add_"))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Fon skaneri — job queue orqali
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            _scanner_job,
            interval=SCAN_INTERVAL,
            first=30,
            name="market_scanner",
        )

    logger.info("🚀 HALOL CRYPTO AI BOT V3.5 ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


async def _scanner_job(context: ContextTypes.DEFAULT_TYPE):
    """Job queue dan chaqiriladigan skaner."""
    try:
        async with aiohttp.ClientSession() as session:
            strong_signals = await find_strong_signals(session, ALERT_THRESHOLD)

        if not strong_signals:
            return

        users = get_all_active_users()
        from database import get_watchlist as gw, check_alert_cooldown, record_alert

        for user in users:
            uid = user["user_id"]
            if not user.get("alerts_on"):
                continue
            settings = get_settings(uid)
            if not settings.get("notify_strong"):
                continue

            user_wl = gw(uid)
            threshold = settings.get("alert_threshold", ALERT_THRESHOLD)

            for signal in strong_signals:
                if signal.symbol not in user_wl:
                    continue
                if signal.confidence < threshold:
                    continue
                if check_alert_cooldown(uid, signal.symbol, 3600):
                    continue

                try:
                    msg = format_signal_message(signal, detailed=False)
                    msg = "🚨 <b>YANGI SIGNAL!</b>\n\n" + msg
                    await context.bot.send_message(
                        chat_id=uid, text=msg, parse_mode=ParseMode.HTML
                    )
                    record_alert(uid, signal.symbol, signal.signal_type,
                                 signal.confidence, signal.price)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"Ogohlantirish xatosi {uid}: {e}")

    except Exception as e:
        logger.error(f"Scanner job xatosi: {e}")


if __name__ == "__main__":
    run_bot()
