"""
Halol Crypto AI Bot - Konfiguratsiya fayli
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Binance API
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
BINANCE_BASE_URL = "https://api.binance.com"

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "halol_crypto.db")

# Scanner settings
SCAN_INTERVAL_SECONDS = 60          # Global scan every 60 seconds
WATCHLIST_UPDATE_MINUTES = 10       # Watchlist update every 10 min
ALERT_COOLDOWN_MINUTES = 30         # Same coin alert cooldown
MIN_CONFIDENCE_FOR_ALERT = 70       # Min confidence % for immediate alert
MIN_SCORE_FOR_STRONG_SIGNAL = 7     # Min score for strong signal

# Cache
PRICE_CACHE_TTL_SECONDS = 30        # Price cache lifetime
MARKET_CACHE_TTL_SECONDS = 60       # Market cache lifetime

# Chart settings
CHART_DPI = 150
CHART_FIGSIZE = (12, 8)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Admin chat IDs (comma-separated in .env)
ADMIN_CHAT_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS", "").split(",")
    if x.strip().isdigit()
]

# ============================================================
# HALOL COINLAR RO'YXATI
# ============================================================
HALAL_COINS = [
    "BTC", "ETH", "BNB", "SOL", "ADA", "AVAX", "DOT", "LINK",
    "MATIC", "ATOM", "NEAR", "FTM", "ALGO", "XTZ", "HBAR",
    "VET", "ONE", "EGLD", "IOTA", "XLM", "XRP", "LTC",
    "BCH", "ETC", "FIL", "THETA", "AAVE", "UNI", "CRV",
    "SNX", "COMP", "MKR", "YFI", "SUSHI", "1INCH", "BAL",
    "GRT", "LRC", "ENJ", "MANA", "SAND", "AXS", "CHZ",
    "OMG", "ZIL", "RVN", "DGB", "SYS", "WAVES", "ZEN",
    "DASH", "ZEC", "XMR", "DCR", "SC", "LSK", "STEEM",
    "KCS", "HT", "OKB", "CRO", "GT", "MX",
    "OP", "ARB", "IMX", "LDO", "RUNE", "INJ", "TIA",
    "SEI", "SUI", "APT", "BLUR", "CFX", "STX", "ROSE",
    "KAVA", "CELO", "GLMR", "MOVR", "KSM", "BAND",
    "API3", "UMA", "BAT", "CVC", "DNT", "STORJ",
    "SKL", "NMR", "OXT", "REP", "RLC", "CTSI",
    "ALICE", "TRB", "BNT", "ANT", "GNO", "MLN",
]

# HARAM COINLAR (misol uchun)
HARAM_COINS = {
    "LUNC": "Terra Luna Classic - loyiha ishdan chiqqan",
    "UST": "Algoritmik stablecoin - ishdan chiqqan",
    "FTT": "FTX almashinuv tokeni - ishdan chiqqan",
    "HOOK": "Gambling elementlari mavjud",
    "WIN": "Lottery va gambling",
    "LAZIO": "Fan tokeni - spekulyativ",
    "PORTO": "Fan tokeni - spekulyativ",
    "SANTOS": "Fan tokeni - spekulyativ",
    "TRX": "Bahs mavjud - ehtiyot bo'ling",
}

# MEME COINLAR
MEME_COINS = {
    "DOGE": "Meme coin - iqtisodiy asosi yo'q",
    "SHIB": "Meme coin - yuqori spekul.",
    "PEPE": "Meme coin",
    "FLOKI": "Meme coin",
    "BONK": "Meme coin",
    "WIF": "Meme coin",
    "BOME": "Meme coin",
    "MEME": "Meme coin",
    "TURBO": "Meme coin",
    "WOJAK": "Meme coin",
    "MOG": "Meme coin",
    "POPCAT": "Meme coin",
    "CAT": "Meme coin",
    "COQ": "Meme coin",
    "BRETT": "Meme coin",
    "NEIRO": "Meme coin",
    "PNUT": "Meme coin",
    "GOAT": "Meme coin",
    "MOODENG": "Meme coin",
}

# Signal type emojilar
SIGNAL_EMOJI = {
    "KUCHLI_SOTIB_OLISH": "🟢",
    "SOTIB_OLISH": "🟢",
    "KUTISH": "🟡",
    "SOTISH": "🔴",
    "KUCHLI_SOTISH": "🔴",
}

SIGNAL_NAMES = {
    "KUCHLI_SOTIB_OLISH": "KUCHLI SOTIB OLISH",
    "SOTIB_OLISH": "SOTIB OLISH",
    "KUTISH": "KUTISH",
    "SOTISH": "SOTISH",
    "KUCHLI_SOTISH": "KUCHLI SOTISH",
}

RISK_NAMES = {
    "past": "Past",
    "o'rta": "O'rta",
    "yuqori": "Yuqori",
}

# Trend emojilar
TREND_EMOJI = {
    "bullish": "📈",
    "bearish": "📉",
    "neutral": "➡️",
}

TREND_NAMES = {
    "bullish": "O'sish",
    "bearish": "Tushish",
    "neutral": "Neytral",
}
