"""
Halol Crypto AI Bot — Asosiy fayl
"""
import asyncio
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

import config
from config import (
    TELEGRAM_BOT_TOKEN, HALAL_COINS, HARAM_COINS, MEME_COINS,
    SIGNAL_EMOJI, SIGNAL_NAMES, TREND_EMOJI, TREND_NAMES,
    ALERT_COOLDOWN_MINUTES, MIN_CONFIDENCE_FOR_ALERT,
)
from database import (
    init_database, get_or_create_user, get_or_create_group,
    get_user_watchlist, add_to_watchlist, remove_from_watchlist,
    clear_watchlist, can_send_alert, record_alert, cleanup_old_alerts,
    get_all_active_users, get_all_active_groups, update_user_alert_setting,
    save_signal,
)
from scanner import binance, market_scanner, market_cache
from signals import (
    analyze_coin, get_top_opportunities, get_strong_signals,
    scan_all_halal_coins, format_price, format_watchlist_signal,
    format_strong_alert, format_coin_detail,
)
from charts import generate_signal_chart
from utils import (
    safe_send_message, build_main_menu, build_back_button,
    build_coin_keyboard, build_watchlist_menu, build_settings_menu,
    setup_logging, WELCOME_TEXT, HELP_TEXT,
)

logger = logging.getLogger(__name__)

# Foydalanuvchi vaqtinchalik holati (coin tanlash uchun)
user_state: dict = {}


# ──────────────────────────────────────────────
# STARTLASH
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        await get_or_create_group(chat.id, chat.title)
        await update.message.reply_text(
            "✅ Halol Crypto AI Bot guruhga ulandi!\n"
            "Kuchli signallar bu guruhga yuboriladi.",
            parse_mode="Markdown"
        )
        return

    await get_or_create_user(
        chat_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 BOSHLASH", callback_data="main_menu")
    ]])
    await update.message.reply_text(
        WELCOME_TEXT, parse_mode="Markdown", reply_markup=keyboard
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyuni ko'rsatish"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "📱 *Halol Crypto AI*\n\nQuyidagi bo'limlardan birini tanlang:",
            parse_mode="Markdown",
            reply_markup=build_main_menu()
        )
    else:
        await update.message.reply_text(
            "📱 *Halol Crypto AI*\n\nQuyidagi bo'limlardan birini tanlang:",
            parse_mode="Markdown",
            reply_markup=build_main_menu()
        )


# ──────────────────────────────────────────────
# SIGNAL
# ──────────────────────────────────────────────

async def handle_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Signal tahlil qilinmoqda...", parse_mode="Markdown")

    # Foydalanuvchi watchlistidan birinchi coinni tanlash
    chat_id = update.effective_user.id
    watchlist = await get_user_watchlist(chat_id)

    if not watchlist:
        watchlist = ["BTC", "ETH", "BNB"]

    results = []
    for sym in watchlist[:5]:
        r = analyze_coin(sym)
        if r:
            results.append(r)

    if not results:
        await query.edit_message_text(
            "❌ Ma'lumotlar hali yuklanmagan. Biroz kuting...",
            reply_markup=build_back_button()
        )
        return

    # Eng yaxshi signalni ko'rsatish
    results.sort(key=lambda x: abs(x.score), reverse=True)
    best = results[0]

    text = f"📡 *Mening Coinlarim Signallari*\n\n"

    for r in results[:5]:
        text += format_watchlist_signal(r) + "\n\n" + "─" * 30 + "\n\n"

    text += "⚠️ _Ta'lim maqsadida. Moliyaviy maslahat emas._"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="signal")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])

    # Kuchli signal bo'lsa grafik ham qo'shish
    chart = None
    if best.signal_type in ("KUCHLI_SOTIB_OLISH", "KUCHLI_SOTISH") and best.confidence >= 70:
        chart = await generate_signal_chart(best)

    if chart:
        await query.message.delete()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=chart,
            caption=text[:1024],
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buyruq: /signal"""
    chat_id = update.effective_user.id
    watchlist = await get_user_watchlist(chat_id)
    if not watchlist:
        watchlist = ["BTC", "ETH", "SOL"]

    await update.message.reply_text("⏳ Signal tahlil qilinmoqda...", parse_mode="Markdown")

    results = []
    for sym in watchlist[:5]:
        r = analyze_coin(sym)
        if r:
            results.append(r)

    if not results:
        await update.message.reply_text("❌ Ma'lumotlar yuklanmagan. Keyinroq urinib ko'ring.")
        return

    text = "📡 *Signal Natijalar*\n\n"
    for r in results:
        text += format_watchlist_signal(r) + "\n\n─────────────\n\n"
    text += "⚠️ _Ta'lim maqsadida._"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=build_back_button())


# ──────────────────────────────────────────────
# BOZOR
# ──────────────────────────────────────────────

async def handle_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Bozor tahlil qilinmoqda...", parse_mode="Markdown")

    sentiment = market_scanner.get_market_sentiment()
    trend = sentiment["trend"]
    trend_em = TREND_EMOJI.get(trend, "➡️")
    trend_name = TREND_NAMES.get(trend, "Neytral")
    pos = sentiment["positive_pct"]
    neg = sentiment["negative_pct"]

    if trend == "bullish":
        market_desc = "Bozor umumiy ko'tarilish tendensiyasida. Xaridorlar ustunlik qilmoqda."
        sentiment_em = "🟢"
    elif trend == "bearish":
        market_desc = "Bozor umumiy tushish tendensiyasida. Sotuvchilar ustunlik qilmoqda."
        sentiment_em = "🔴"
    else:
        market_desc = "Bozor neytral holatda. Kuchli yo'nalish yo'q."
        sentiment_em = "🟡"

    # Top 5 imkoniyat
    top_opps = get_top_opportunities(5)
    opps_text = ""
    for i, r in enumerate(top_opps, 1):
        em = SIGNAL_EMOJI.get(r.signal_type, "🟡")
        opps_text += f"{i}. {em} *{r.symbol}* — {format_price(r.price)} ({r.confidence}%)\n"

    text = (
        f"📈 *Bozor Holati*\n\n"
        f"{sentiment_em} Kayfiyat: *{trend_name}*\n"
        f"{trend_em} Yo'nalish: *{trend_name}*\n\n"
        f"📊 Statistika:\n"
        f"• Ko'tarilgan: *{pos}%*\n"
        f"• Tushgan: *{neg}%*\n"
        f"• Tahlil qilingan: *{sentiment['total_coins']} ta coin*\n\n"
        f"ℹ️ {market_desc}\n\n"
        f"📊 *Top Imkoniyatlar:*\n{opps_text if opps_text else 'Hozircha mavjud emas'}\n\n"
        f"⚠️ _Ta'lim maqsadida._"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="market")],
        [InlineKeyboardButton("📊 To'liq imkoniyatlar", callback_data="top_opps")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sentiment = market_scanner.get_market_sentiment()
    trend = sentiment["trend"]
    trend_em = TREND_EMOJI.get(trend, "➡️")
    trend_name = TREND_NAMES.get(trend, "Neytral")

    text = (
        f"📈 *Bozor Holati*\n\n"
        f"{trend_em} Umumiy trend: *{trend_name}*\n"
        f"📊 Ko'tarilgan: *{sentiment['positive_pct']}%*\n"
        f"📉 Tushgan: *{sentiment['negative_pct']}%*\n"
        f"🪙 Tahlil: *{sentiment['total_coins']} ta coin*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────────────────────────
# O'SAYOTGAN COINLAR
# ──────────────────────────────────────────────

async def handle_rising(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ O'sayotgan coinlar aniqlanmoqda...", parse_mode="Markdown")

    gainers = market_scanner.get_top_gainers(10)

    if not gainers:
        await query.edit_message_text(
            "❌ Ma'lumotlar yuklanmagan. Biroz kuting...",
            reply_markup=build_back_button()
        )
        return

    text = "🚀 *O'sayotgan Coinlar (Top 10)*\n\n"
    for i, t in enumerate(gainers, 1):
        sym = t["symbol"]
        price = t["price"]
        chg = t["change_pct"]
        vol = t.get("quote_volume", 0)
        em = "📈" if chg > 0 else "📉"
        text += (
            f"{i}. *{sym}* {em}\n"
            f"   💲 {format_price(price)}  |  {chg:+.2f}%\n"
            f"   💹 Vol: ${vol/1e6:.1f}M\n\n"
        )

    text += "⚠️ _Ta'lim maqsadida._"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="rising")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_rising(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gainers = market_scanner.get_top_gainers(5)
    text = "🚀 *O'sayotgan Coinlar*\n\n"
    for i, t in enumerate(gainers, 1):
        text += f"{i}. *{t['symbol']}* — {t['change_pct']:+.2f}%\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────────────────────────
# TOP IMKONIYATLAR
# ──────────────────────────────────────────────

async def handle_top_opps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Top imkoniyatlar aniqlanmoqda...", parse_mode="Markdown")

    opps = get_top_opportunities(10)

    if not opps:
        await query.edit_message_text(
            "ℹ️ Hozircha kuchli imkoniyatlar aniqlanmadi.\n"
            "Bozor tekshirilmoqda, biroz kuting...",
            reply_markup=build_back_button()
        )
        return

    text = "📊 *Top Imkoniyatlar*\n\n"
    for i, r in enumerate(opps, 1):
        em = SIGNAL_EMOJI.get(r.signal_type, "🟡")
        sig_name = SIGNAL_NAMES.get(r.signal_type, r.signal_type)
        chg_str = f"{r.change_24h:+.2f}%" if r.change_24h else ""
        text += (
            f"{i}. {em} *{r.symbol}*\n"
            f"   💲 {format_price(r.price)}  {chg_str}\n"
            f"   📊 {sig_name}  |  🎯 {r.confidence}%\n\n"
        )

    text += "⚠️ _Ta'lim maqsadida._"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="top_opps")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opps = get_top_opportunities(5)
    text = "📊 *Top Imkoniyatlar*\n\n"
    for i, r in enumerate(opps, 1):
        em = SIGNAL_EMOJI.get(r.signal_type, "🟡")
        text += f"{i}. {em} *{r.symbol}* — {format_price(r.price)} ({r.confidence}%)\n"
    if not opps:
        text += "Hozircha kuchli imkoniyatlar yo'q."
    await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────────────────────────
# HALOL / HARAM / MEME COINLAR
# ──────────────────────────────────────────────

async def handle_halal_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coins_list = ", ".join(HALAL_COINS[:30])
    text = (
        f"✅ *Halol Coinlar*\n\n"
        f"Quyidagi coinlar halol mezonlarga mos keladi:\n\n"
        f"`{coins_list}` va boshqalar\n\n"
        f"Jami: *{len(HALAL_COINS)} ta halol coin* kuzatilmoqda\n\n"
        f"*Halollik mezonlari:*\n"
        f"• Spekulyativ meme coin emas\n"
        f"• Qimor (gambling) bilan bog'liq emas\n"
        f"• Kattalar kontenti bilan bog'liq emas\n"
        f"• Ishonchli texnologik loyiha\n"
        f"• Sof iqtisodiy maqsad\n\n"
        f"⚠️ _Halollik masalasida olim bilan maslahatlashing._"
    )
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_back_button())


async def handle_haram_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = "❌ *Haram yoki Shubhali Coinlar*\n\n"
    text += "Bu coinlar tahlildan chiqarib tashlangan:\n\n"
    for sym, reason in list(HARAM_COINS.items())[:10]:
        text += f"• *{sym}* — {reason}\n"
    text += (
        f"\n*Nima uchun chiqarilgan?*\n"
        f"• Riba (foiz) elementlari\n"
        f"• Qimor va lotereya\n"
        f"• Ishdan chiqqan loyihalar\n"
        f"• Aldash va firibgarlik xavfi\n\n"
        f"⚠️ _Halollik masalasida olim bilan maslahatlashing._"
    )
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_back_button())


async def handle_meme_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = "⚠️ *Meme Coinlar*\n\n"
    text += "Bu coinlar tahlildan chiqarilgan:\n\n"
    for sym, reason in list(MEME_COINS.items())[:10]:
        text += f"• *{sym}* — {reason}\n"
    text += (
        f"\n*Nima uchun chiqarilgan?*\n"
        f"• Iqtisodiy asosi yo'q\n"
        f"• Yuqori spekulyativ xavf\n"
        f"• Ko'pincha heyp va manipulyatsiya\n"
        f"• Ko'p investorlar zarar ko'rgan\n\n"
        f"⚠️ _Meme coinlar juda xavfli. Ehtiyot bo'ling._"
    )
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_back_button())


# ──────────────────────────────────────────────
# WATCHLIST
# ──────────────────────────────────────────────

async def handle_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    wl = await get_user_watchlist(chat_id)

    if not wl:
        text = (
            "⭐ *Mening Coinlarim*\n\n"
            "Siz hali hech qanday coin tanlamadingiz.\n"
            "Coin tanlash uchun tugmani bosing."
        )
    else:
        coins_str = "  ".join(f"`{c}`" for c in wl)
        text = (
            f"⭐ *Mening Coinlarim* ({len(wl)} ta)\n\n"
            f"{coins_str}\n\n"
            f"Bu coinlar har 10 daqiqada yangilanadi."
        )

    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_watchlist_menu())


async def handle_edit_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    wl = await get_user_watchlist(chat_id)

    page = user_state.get(chat_id, {}).get("page", 0)
    kb = build_coin_keyboard(HALAL_COINS, wl, page)
    await query.edit_message_text(
        "🪙 *Coinlarni tanlang*\n\n✅ — tanlangan | ◻️ — tanlanmagan",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def handle_toggle_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    symbol = query.data.replace("toggle_", "")
    wl = await get_user_watchlist(chat_id)

    if symbol in wl:
        await remove_from_watchlist(chat_id, symbol)
        await query.answer(f"❌ {symbol} o'chirildi", show_alert=False)
    else:
        if len(wl) >= 20:
            await query.answer("⚠️ Maksimal 20 ta coin tanlash mumkin!", show_alert=True)
            return
        await add_to_watchlist(chat_id, symbol)
        await query.answer(f"✅ {symbol} qo'shildi", show_alert=False)

    wl = await get_user_watchlist(chat_id)
    page = user_state.get(chat_id, {}).get("page", 0)
    kb = build_coin_keyboard(HALAL_COINS, wl, page)
    try:
        await query.edit_message_reply_markup(reply_markup=kb)
    except Exception:
        pass


async def handle_coin_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    page = int(query.data.replace("coin_page_", ""))
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]["page"] = page
    wl = await get_user_watchlist(chat_id)
    kb = build_coin_keyboard(HALAL_COINS, wl, page)
    try:
        await query.edit_message_reply_markup(reply_markup=kb)
    except Exception:
        pass


async def handle_save_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    wl = await get_user_watchlist(chat_id)
    text = (
        f"✅ *Saqlandi!*\n\n"
        f"Siz {len(wl)} ta coin tanladingiz:\n"
        f"{' '.join(f'`{c}`' for c in wl)}\n\n"
        f"Bu coinlar har 10 daqiqada yangilanadi."
    )
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_back_button())


async def handle_clear_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    await clear_watchlist(chat_id)
    await query.edit_message_text(
        "🗑️ *Watchlist tozalandi.*\n\nQayta coin tanlash uchun tugmani bosing.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Coin tanlash", callback_data="edit_watchlist")],
            [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
        ])
    )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    wl = await get_user_watchlist(chat_id)
    if not wl:
        text = "⭐ Watchlistingiz bo'sh. /start orqali coin tanlang."
    else:
        text = f"⭐ *Mening Coinlarim:*\n{' '.join(f'`{c}`' for c in wl)}"
    await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────────────────────────
# COINLAR RO'YXATI
# ──────────────────────────────────────────────

async def handle_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Narxlar bilan coin ro'yxati
    text = "🪙 *Halol Coinlar — Joriy Narxlar*\n\n"
    count = 0
    for sym in HALAL_COINS[:20]:
        price = market_cache.get_price(sym)
        ticker = market_cache.get_ticker(sym)
        if price and price > 0:
            chg = ticker.get("change_pct", 0) if ticker else 0
            em = "📈" if chg > 0 else "📉" if chg < 0 else "➡️"
            text += f"{em} *{sym}*: {format_price(price)} ({chg:+.2f}%)\n"
            count += 1

    if count == 0:
        text += "⏳ Ma'lumotlar yuklanmoqda..."

    text += f"\n_Jami {len(HALAL_COINS)} ta halol coin kuzatilmoqda_"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="coins")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buyruq: /coin [SYMBOL]"""
    if not context.args:
        await update.message.reply_text("Namuna: `/coin BTC`", parse_mode="Markdown")
        return

    symbol = context.args[0].upper().replace("USDT", "")
    if symbol not in HALAL_COINS:
        await update.message.reply_text(
            f"❌ *{symbol}* halol coinlar ro'yxatida yo'q.\n"
            f"Halol coinlar: {', '.join(HALAL_COINS[:10])}...",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ {symbol} tahlil qilinmoqda...", parse_mode="Markdown")

    # Kline yuklanmagan bo'lsa yuklab olish
    if market_cache.is_kline_stale(symbol):
        df = await binance.fetch_klines(symbol)
        if df is not None:
            market_cache.set_klines(symbol, df)

    result = analyze_coin(symbol)
    if not result:
        await update.message.reply_text("❌ Tahlil qilib bo'lmadi. Keyinroq urinib ko'ring.")
        return

    text = format_coin_detail(result)

    # Kuchli signal bo'lsa grafik ham yuborish
    chart = None
    if result.signal_type in ("KUCHLI_SOTIB_OLISH", "SOTIB_OLISH", "KUCHLI_SOTISH") and result.confidence >= 65:
        chart = await generate_signal_chart(result)

    if chart:
        await update.message.reply_photo(photo=chart, caption=text[:1024], parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────────────────────────
# SOZLAMALAR
# ──────────────────────────────────────────────

async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    from database import init_database
    user = await get_or_create_user(chat_id)
    alerts_on = bool(user.get("receive_alerts", 1))

    text = (
        f"⚙️ *Sozlamalar*\n\n"
        f"🔔 Alertlar: {'✅ Yoqilgan' if alerts_on else '❌ O\'chirilgan'}\n\n"
        f"Bu yerda siz:\n"
        f"• Alertlarni yoqish/o'chirish\n"
        f"• Coinlaringizni boshqarish\n"
        f"mumkin."
    )
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=build_settings_menu(alerts_on))


async def handle_alerts_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    enable = query.data == "alerts_on"
    await update_user_alert_setting(chat_id, enable)
    status = "✅ Alertlar yoqildi" if enable else "❌ Alertlar o'chirildi"
    await query.answer(status, show_alert=True)
    # Yangilash
    await handle_settings(update, context)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    user = await get_or_create_user(chat_id)
    alerts_on = bool(user.get("receive_alerts", 1))
    text = (
        f"⚙️ *Sozlamalar*\n\n"
        f"🔔 Alertlar: {'✅ Yoqilgan' if alerts_on else '❌ O\'chirilgan'}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=build_settings_menu(alerts_on))


# ──────────────────────────────────────────────
# YORDAM
# ──────────────────────────────────────────────

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        HELP_TEXT, parse_mode="Markdown", reply_markup=build_back_button()
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


# ──────────────────────────────────────────────
# CALLBACK DISPATCHER
# ──────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "main_menu":
        await show_main_menu(update, context)
    elif data == "signal":
        await handle_signal(update, context)
    elif data == "coins":
        await handle_coins(update, context)
    elif data == "watchlist":
        await handle_watchlist(update, context)
    elif data == "edit_watchlist":
        await handle_edit_watchlist(update, context)
    elif data == "save_watchlist":
        await handle_save_watchlist(update, context)
    elif data == "clear_watchlist":
        await handle_clear_watchlist(update, context)
    elif data == "market":
        await handle_market(update, context)
    elif data == "rising":
        await handle_rising(update, context)
    elif data == "top_opps":
        await handle_top_opps(update, context)
    elif data == "halal_coins":
        await handle_halal_coins(update, context)
    elif data == "haram_coins":
        await handle_haram_coins(update, context)
    elif data == "meme_coins":
        await handle_meme_coins(update, context)
    elif data == "settings":
        await handle_settings(update, context)
    elif data in ("alerts_on", "alerts_off"):
        await handle_alerts_toggle(update, context)
    elif data == "help":
        await handle_help(update, context)
    elif data.startswith("toggle_"):
        await handle_toggle_coin(update, context)
    elif data.startswith("coin_page_"):
        await handle_coin_page(update, context)
    elif data == "noop":
        await query.answer()
    else:
        await query.answer("Noma'lum buyruq")


# ──────────────────────────────────────────────
# FON VAZIFALARI (APScheduler)
# ──────────────────────────────────────────────

async def job_market_scan(context: ContextTypes.DEFAULT_TYPE):
    """Har 60 soniyada market skanerlash"""
    try:
        await market_scanner.run_full_scan(HALAL_COINS)
    except Exception as e:
        logger.error(f"Market scan job xatosi: {e}")


async def job_watchlist_updates(context: ContextTypes.DEFAULT_TYPE):
    """Har 10 daqiqada watchlist yangilash"""
    try:
        users = await get_all_active_users()
        bot = context.bot

        for user in users:
            chat_id = user["chat_id"]
            wl = await get_user_watchlist(chat_id)
            if not wl:
                continue

            results = []
            for sym in wl[:8]:
                r = analyze_coin(sym)
                if r:
                    results.append(r)

            if not results:
                continue

            text = "📡 *Mening Coinlarim — Yangilanish*\n\n"
            for r in results:
                text += format_watchlist_signal(r) + "\n\n─────────────\n\n"
            text += "⚠️ _Ta'lim maqsadida._"

            await safe_send_message(bot, chat_id, text, "Markdown")
            await asyncio.sleep(0.05)

    except Exception as e:
        logger.error(f"Watchlist update job xatosi: {e}")


async def job_strong_signal_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 daqiqada kuchli signallarni tekshirish va yuborish"""
    try:
        strong_signals = get_strong_signals(MIN_CONFIDENCE_FOR_ALERT)
        if not strong_signals:
            return

        bot = context.bot
        users = await get_all_active_users()
        groups = await get_all_active_groups()

        all_targets = (
            [u["chat_id"] for u in users] +
            [g["chat_id"] for g in groups]
        )

        for sig in strong_signals[:3]:  # Max 3 ta signal
            text = format_strong_alert(sig)

            # Grafik tayyorlash
            chart = await generate_signal_chart(sig)

            # Signal saqlash
            await save_signal(
                symbol=sig.symbol,
                signal_type=sig.signal_type,
                price=sig.price,
                confidence=sig.confidence,
                score=sig.score,
                trend=sig.trend,
                risk_level=sig.risk_level,
                analysis="\n".join(sig.reasons)
            )

            for chat_id in all_targets:
                ok = await can_send_alert(chat_id, sig.symbol, ALERT_COOLDOWN_MINUTES)
                if not ok:
                    continue
                sent = await safe_send_message(
                    bot, chat_id, text, "Markdown", photo=chart
                )
                if sent:
                    await record_alert(chat_id, sig.symbol, sig.signal_type)
                await asyncio.sleep(0.05)

    except Exception as e:
        logger.error(f"Alert job xatosi: {e}")


async def job_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Kuniga bir marta eski yozuvlarni tozalash"""
    await cleanup_old_alerts(days=7)
    logger.info("♻️ Eski yozuvlar tozalandi")


# ──────────────────────────────────────────────
# ERROR HANDLER
# ──────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xato: {context.error}", exc_info=True)


# ──────────────────────────────────────────────
# ASOSIY ISHGA TUSHIRISH
# ──────────────────────────────────────────────

async def post_init(application: Application):
    """Bot ishga tushganda dastlabki scan"""
    logger.info("🚀 Bot ishga tushmoqda...")
    try:
        await binance.start()
        await init_database()
        logger.info("📡 Dastlabki market scan...")
        await market_scanner.run_full_scan(HALAL_COINS)
        logger.info("✅ Dastlabki scan tugadi")
    except Exception as e:
        logger.error(f"Ishga tushirish xatosi: {e}")


async def post_shutdown(application: Application):
    await binance.close()
    logger.info("👋 Bot to'xtatildi")


def main():
    setup_logging(config.LOG_LEVEL, config.LOG_FILE)

    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN .env faylida ko'rsatilmagan!")
        return

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Handlerlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("rising", cmd_rising))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("coin", cmd_coin))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)

    # Jadval vazifalari
    jq = app.job_queue
    jq.run_repeating(job_market_scan, interval=60, first=10)
    jq.run_repeating(job_strong_signal_alerts, interval=300, first=90)
    jq.run_repeating(job_watchlist_updates, interval=600, first=120)
    jq.run_daily(job_cleanup, time=__import__("datetime").time(3, 0))

    logger.info("🤖 Halol Crypto AI Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
