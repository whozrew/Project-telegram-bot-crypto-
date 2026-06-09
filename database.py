"""
Halol Crypto AI Bot - Ma'lumotlar bazasi
"""
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


async def init_database():
    """Ma'lumotlar bazasini yaratish va jadvallarni sozlash"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA foreign_keys=ON;

            -- Foydalanuvchilar
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'uz',
                is_active INTEGER DEFAULT 1,
                receive_alerts INTEGER DEFAULT 1,
                alert_min_confidence INTEGER DEFAULT 70,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Guruhlar
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE NOT NULL,
                title TEXT,
                is_active INTEGER DEFAULT 1,
                receive_alerts INTEGER DEFAULT 1,
                alert_cooldown_minutes INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Watchlist (foydalanuvchi coin tanlovi)
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, symbol)
            );

            -- Sozlamalar
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Signal tarixi
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                price REAL NOT NULL,
                confidence INTEGER,
                score REAL,
                trend TEXT,
                risk_level TEXT,
                analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Alert tarixi (takror xabar yuborishni oldini olish)
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indekslar
            CREATE INDEX IF NOT EXISTS idx_users_chat_id ON users(chat_id);
            CREATE INDEX IF NOT EXISTS idx_watchlists_chat_id ON watchlists(chat_id);
            CREATE INDEX IF NOT EXISTS idx_signal_history_symbol ON signal_history(symbol);
            CREATE INDEX IF NOT EXISTS idx_alert_history_chat_symbol ON alert_history(chat_id, symbol);
        """)
        await db.commit()
    logger.info("✅ Ma'lumotlar bazasi tayyor")


# ──────────────────────────────────────────────
# Foydalanuvchilar
# ──────────────────────────────────────────────

async def get_or_create_user(chat_id: int, username: str = None,
                              first_name: str = None, last_name: str = None) -> Dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            INSERT INTO users (chat_id, username, first_name, last_name, last_active)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_active = CURRENT_TIMESTAMP,
                is_active = 1
        """, (chat_id, username, first_name, last_name))
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}


async def get_all_active_users() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE is_active = 1 AND receive_alerts = 1"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_user_alert_setting(chat_id: int, receive_alerts: bool):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET receive_alerts = ? WHERE chat_id = ?",
            (1 if receive_alerts else 0, chat_id)
        )
        await db.commit()


# ──────────────────────────────────────────────
# Guruhlar
# ──────────────────────────────────────────────

async def get_or_create_group(chat_id: int, title: str = None) -> Dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            INSERT INTO groups (chat_id, title)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, is_active = 1
        """, (chat_id, title))
        await db.commit()
        async with db.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}


async def get_all_active_groups() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM groups WHERE is_active = 1 AND receive_alerts = 1"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ──────────────────────────────────────────────
# Watchlist
# ──────────────────────────────────────────────

async def get_user_watchlist(chat_id: int) -> List[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT symbol FROM watchlists WHERE chat_id = ? ORDER BY created_at",
            (chat_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def add_to_watchlist(chat_id: int, symbol: str) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO watchlists (chat_id, symbol) VALUES (?, ?)",
                (chat_id, symbol.upper())
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Watchlist qo'shish xatosi: {e}")
        return False


async def remove_from_watchlist(chat_id: int, symbol: str) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "DELETE FROM watchlists WHERE chat_id = ? AND symbol = ?",
                (chat_id, symbol.upper())
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Watchlist o'chirish xatosi: {e}")
        return False


async def clear_watchlist(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM watchlists WHERE chat_id = ?", (chat_id,))
        await db.commit()


# ──────────────────────────────────────────────
# Signal tarixi
# ──────────────────────────────────────────────

async def save_signal(symbol: str, signal_type: str, price: float,
                       confidence: int, score: float, trend: str,
                       risk_level: str, analysis: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO signal_history
                (symbol, signal_type, price, confidence, score, trend, risk_level, analysis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, signal_type, price, confidence, score, trend, risk_level, analysis))
        await db.commit()


async def get_last_signal(symbol: str) -> Optional[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM signal_history
            WHERE symbol = ?
            ORDER BY created_at DESC LIMIT 1
        """, (symbol,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ──────────────────────────────────────────────
# Alert tarixi (spam oldini olish)
# ──────────────────────────────────────────────

async def can_send_alert(chat_id: int, symbol: str, cooldown_minutes: int = 30) -> bool:
    """Oxirgi alertdan beri yetarli vaqt o'tdimi?"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cutoff = (datetime.utcnow() - timedelta(minutes=cooldown_minutes)).isoformat()
        async with db.execute("""
            SELECT COUNT(*) FROM alert_history
            WHERE chat_id = ? AND symbol = ? AND sent_at > ?
        """, (chat_id, symbol, cutoff)) as cur:
            row = await cur.fetchone()
            return row[0] == 0


async def record_alert(chat_id: int, symbol: str, signal_type: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO alert_history (chat_id, symbol, signal_type)
            VALUES (?, ?, ?)
        """, (chat_id, symbol, signal_type))
        await db.commit()


async def cleanup_old_alerts(days: int = 7):
    """Eski alert yozuvlarini tozalash"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        await db.execute("DELETE FROM alert_history WHERE sent_at < ?", (cutoff,))
        await db.execute("DELETE FROM signal_history WHERE created_at < ?", (cutoff,))
        await db.commit()
