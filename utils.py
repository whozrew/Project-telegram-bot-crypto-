"""
Halol Crypto AI Bot - Yordamchi funksiyalar
"""
import logging
import asyncio
from typing import Optional, List
from datetime import datetime

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, RetryAfter, Forbidden, BadRequest

logger = logging.getLogger(__name__)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    reply_markup=None,
    photo: bytes = None,
) -> Optional[int]:
    """Xabar yuborish (xatolik holati uchun)"""
    try:
        if photo:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text[:1024],
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        return msg.message_id
    except RetryAfter as e:
        logger.warning(f"Rate limit: {e.retry_after}s kutish ({chat_id})")
        await asyncio.sleep(e.retry_after + 1)
        return await safe_send_message(bot, chat_id, text, parse_mode, reply_markup, photo)
    except Forbidden:
        logger.warning(f"Bot {chat_id} ga xabar yubora olmadi (bloklangan)")
        return None
    except BadRequest as e:
        logger.warning(f"Noto'g'ri so'rov {chat_id}: {e}")
        if "can't parse" in str(e).lower():
            return await safe_send_message(bot, chat_id, text, "HTML", reply_markup, photo)
        return None
    except TelegramError as e:
        logger.error(f"Telegram xatosi {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Kutilmagan xato {chat_id}: {e}")
        return None


async def broadcast_to_users(
    bot: Bot,
    user_chat_ids: List[int],
    text: str,
    photo: bytes = None,
    parse_mode: str = "Markdown",
    delay: float = 0.05,
):
    """Ko'p foydalanuvchilarga xabar yuborish (spam oldini olish)"""
    success = 0
    fail = 0
    for chat_id in user_chat_ids:
        result = await safe_send_message(bot, chat_id, text, parse_mode, photo=photo)
        if result:
            success += 1
        else:
            fail += 1
        await asyncio.sleep(delay)
    logger.info(f"Broadcast: {success} ta muvaffaqiyatli, {fail} ta muvaffaqiyatsiz")
    return success, fail


def build_main_menu() -> InlineKeyboardMarkup:
    """Asosiy menyu tugmalar"""
    keyboard = [
        [
            InlineKeyboardButton("📡 Signal", callback_data="signal"),
            InlineKeyboardButton("🪙 Coinlar", callback_data="coins"),
        ],
        [
            InlineKeyboardButton("⭐ Mening Coinlarim", callback_data="watchlist"),
            InlineKeyboardButton("📈 Bozor", callback_data="market"),
        ],
        [
            InlineKeyboardButton("🚀 O'sayotgan Coinlar", callback_data="rising"),
            InlineKeyboardButton("📊 Top Imkoniyatlar", callback_data="top_opps"),
        ],
        [
            InlineKeyboardButton("✅ Halol Coinlar", callback_data="halal_coins"),
            InlineKeyboardButton("❌ Haram Coinlar", callback_data="haram_coins"),
        ],
        [
            InlineKeyboardButton("⚠️ Meme Coinlar", callback_data="meme_coins"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("ℹ️ Yordam", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_button(data: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Orqaga", callback_data=data)
    ]])


def build_coin_keyboard(coins: List[str], selected: List[str],
                         page: int = 0, per_page: int = 20) -> InlineKeyboardMarkup:
    """Coin tanlash klaviaturasi"""
    start = page * per_page
    end = start + per_page
    page_coins = coins[start:end]

    keyboard = []
    row = []
    for i, coin in enumerate(page_coins):
        check = "✅" if coin in selected else "◻️"
        row.append(InlineKeyboardButton(
            f"{check} {coin}", callback_data=f"toggle_{coin}"
        ))
        if len(row) == 3 or i == len(page_coins) - 1:
            keyboard.append(row)
            row = []

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"coin_page_{page-1}"))
    nav.append(InlineKeyboardButton(
        f"{page+1}/{(len(coins)-1)//per_page+1}", callback_data="noop"
    ))
    if end < len(coins):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"coin_page_{page+1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("✅ Saqlash", callback_data="save_watchlist")])
    keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def build_watchlist_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Coinlarni o'zgartirish", callback_data="edit_watchlist")],
        [InlineKeyboardButton("🗑️ Tozalash", callback_data="clear_watchlist")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])


def build_settings_menu(alerts_on: bool) -> InlineKeyboardMarkup:
    alerts_btn = (
        InlineKeyboardButton("🔕 Alertlarni o'chirish", callback_data="alerts_off")
        if alerts_on
        else InlineKeyboardButton("🔔 Alertlarni yoqish", callback_data="alerts_on")
    )
    return InlineKeyboardMarkup([
        [alerts_btn],
        [InlineKeyboardButton("⭐ Coinlarim", callback_data="edit_watchlist")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])


def setup_logging(log_level: str = "INFO", log_file: str = "bot.log"):
    """Logging sozlash"""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Tashqi kutubxonalarni susaytirish
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


WELCOME_TEXT = """
🌟 *Halol Crypto AI Botiga Xush Kelibsiz!*

Assalomu alaykum! Men sizga halol kripto pul bozorini tahlil qilishda yordam beraman.

*Bot nima qiladi?*

📡 Halol kripto valyutalarni real vaqtda kuzatadi
📊 Kuchli signal va imkoniyatlarni aniqlaydi
🚀 Eng tez o'suvchi coinlar haqida xabar beradi
📈 Bozor holatini tushuntiradi
⚡ Kuchli imkoniyatlarda darhol ogohlantiradi

*Halollik haqida:*

✅ Faqat halol screened coinlar tahlil qilinadi
❌ Meme coinlar va haram tokenlar istisno
⚠️ Barcha signallar ta'lim maqsadida

*Muhim eslatma:*
_Bu bot moliyaviy maslahat bermaydi. Investitsiya qarorlari faqat sizning mas'uliyatingiz._

👇 Boshlash uchun tugmani bosing:
"""

HELP_TEXT = """
ℹ️ *Yordam va Qo'llanma*

*Asosiy buyruqlar:*
/start — Botni boshlash
/signal — Tezkor signal olish
/market — Bozor holati
/rising — O'sayotgan coinlar
/top — Top imkoniyatlar
/watchlist — Mening coinlarim
/settings — Sozlamalar
/help — Yordam

*Qanday ishlaydi?*

1. ⭐ *Mening Coinlarim* — Kuzatmoqchi coinlarni tanlang
2. 📡 *Signal* — Istalgan coin bo'yicha signal oling
3. 📊 *Top Imkoniyatlar* — Eng yaxshi 10 imkoniyatni ko'ring
4. 🚀 *O'sayotgan Coinlar* — Eng tez o'suvchi coinlar

*Signallar haqida:*

🟢 KUCHLI SOTIB OLISH — Juda kuchli signal
🟢 SOTIB OLISH — Kuchli signal
🟡 KUTISH — Kuchli signal yo'q
🔴 SOTISH — Sotish signal
🔴 KUCHLI SOTISH — Juda kuchli sotish

*Guruh xususiyatlari:*
Bot guruhda ham ishlaydi. Kuchli signallar guruhga ham yuboriladi.

⚠️ _Barcha signallar ta'lim maqsadida._
"""
