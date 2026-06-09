"""
Halol Crypto AI Bot - Bozor skaneri va ma'lumot oluvchi
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import aiohttp
import pandas as pd
import numpy as np

from config import (
    BINANCE_BASE_URL, HALAL_COINS,
    PRICE_CACHE_TTL_SECONDS, MARKET_CACHE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# GLOBAL CACHE (barcha foydalanuvchilar uchun bitta)
# ──────────────────────────────────────────────

class MarketCache:
    def __init__(self):
        self._prices: Dict[str, Dict] = {}
        self._klines: Dict[str, pd.DataFrame] = {}
        self._ticker_24h: Dict[str, Dict] = {}
        self._last_price_update: float = 0
        self._last_kline_update: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def is_price_stale(self) -> bool:
        return time.time() - self._last_price_update > PRICE_CACHE_TTL_SECONDS

    def is_kline_stale(self, symbol: str) -> bool:
        last = self._last_kline_update.get(symbol, 0)
        return time.time() - last > MARKET_CACHE_TTL_SECONDS

    def get_price(self, symbol: str) -> Optional[float]:
        data = self._prices.get(symbol)
        if data and data.get("price", 0) > 0:
            return data["price"]
        return None

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        return self._ticker_24h.get(symbol)

    def get_klines(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._klines.get(symbol)

    def set_prices(self, prices: Dict):
        self._prices = prices
        self._last_price_update = time.time()

    def set_ticker(self, symbol: str, data: Dict):
        self._ticker_24h[symbol] = data

    def set_klines(self, symbol: str, df: pd.DataFrame):
        self._klines[symbol] = df
        self._last_kline_update[symbol] = time.time()

    def all_symbols(self) -> List[str]:
        return list(self._prices.keys())


# Global cache obyekti
market_cache = MarketCache()


# ──────────────────────────────────────────────
# BINANCE API WRAPPER
# ──────────────────────────────────────────────

class BinanceClient:
    def __init__(self):
        self.base_url = BINANCE_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(10)  # Max 10 parallel requests

    async def start(self):
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": "HalolCryptoBot/1.0"}
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def _get(self, endpoint: str, params: Dict = None, retries: int = 3) -> Optional[Any]:
        """Binance API'ga so'rov yuborish (retry bilan)"""
        for attempt in range(retries):
            try:
                async with self._semaphore:
                    url = f"{self.base_url}{endpoint}"
                    async with self.session.get(url, params=params) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            wait = 2 ** attempt
                            logger.warning(f"Rate limit! {wait}s kutish...")
                            await asyncio.sleep(wait)
                        else:
                            logger.warning(f"API xatosi {resp.status}: {endpoint}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout ({attempt+1}/{retries}): {endpoint}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"So'rov xatosi ({attempt+1}/{retries}): {e}")
                await asyncio.sleep(1)
        return None

    async def fetch_all_prices(self) -> Dict[str, float]:
        """Barcha coinlar narxini olish"""
        data = await self._get("/api/v3/ticker/price")
        if not data:
            return {}
        result = {}
        for item in data:
            sym = item.get("symbol", "")
            if sym.endswith("USDT"):
                coin = sym[:-4]
                try:
                    price = float(item["price"])
                    if price > 0:
                        result[coin] = {"symbol": coin, "price": price}
                except (ValueError, KeyError):
                    pass
        return result

    async def fetch_ticker_24h(self, symbol: str) -> Optional[Dict]:
        """24 soatlik statistika"""
        data = await self._get("/api/v3/ticker/24hr", {"symbol": f"{symbol}USDT"})
        if not data:
            return None
        try:
            return {
                "symbol": symbol,
                "price": float(data["lastPrice"]),
                "change_pct": float(data["priceChangePercent"]),
                "high": float(data["highPrice"]),
                "low": float(data["lowPrice"]),
                "volume": float(data["volume"]),
                "quote_volume": float(data["quoteVolume"]),
                "open": float(data["openPrice"]),
            }
        except (KeyError, ValueError) as e:
            logger.error(f"Ticker parse xatosi {symbol}: {e}")
            return None

    async def fetch_multiple_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """Ko'p coinlar uchun 24h ticker"""
        tasks = [self.fetch_ticker_24h(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = {}
        for sym, res in zip(symbols, results):
            if isinstance(res, dict) and res:
                out[sym] = res
        return out

    async def fetch_klines(self, symbol: str, interval: str = "1h",
                            limit: int = 200) -> Optional[pd.DataFrame]:
        """OHLCV ma'lumotlarini olish"""
        data = await self._get("/api/v3/klines", {
            "symbol": f"{symbol}USDT",
            "interval": interval,
            "limit": limit
        })
        if not data or len(data) < 50:
            return None
        try:
            df = pd.DataFrame(data, columns=[
                "timestamp", "open", "high", "low", "close",
                "volume", "close_time", "quote_volume", "trades",
                "taker_buy_vol", "taker_buy_quote", "ignore"
            ])
            for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.dropna(subset=["close"])
            df = df[df["close"] > 0]
            return df if len(df) >= 20 else None
        except Exception as e:
            logger.error(f"Kline parse xatosi {symbol}: {e}")
            return None

    async def fetch_all_tickers_bulk(self) -> Dict[str, Dict]:
        """Barcha tickerlarni bir so'rovda olish"""
        data = await self._get("/api/v3/ticker/24hr")
        if not data:
            return {}
        result = {}
        for item in data:
            sym = item.get("symbol", "")
            if sym.endswith("USDT"):
                coin = sym[:-4]
                if coin in HALAL_COINS:
                    try:
                        result[coin] = {
                            "symbol": coin,
                            "price": float(item["lastPrice"]),
                            "change_pct": float(item["priceChangePercent"]),
                            "high": float(item["highPrice"]),
                            "low": float(item["lowPrice"]),
                            "volume": float(item["volume"]),
                            "quote_volume": float(item["quoteVolume"]),
                            "open": float(item["openPrice"]),
                        }
                    except (ValueError, KeyError):
                        pass
        return result


# Global Binance client
binance = BinanceClient()


# ──────────────────────────────────────────────
# MARKET SCANNER
# ──────────────────────────────────────────────

class MarketScanner:
    """
    Bir marta scan qiladi va natijalarni cache'da saqlaydi.
    Barcha foydalanuvchilar bir xil cache'dan foydalanadi.
    """
    def __init__(self):
        self._scanning = False
        self._last_full_scan: float = 0
        self._scan_results: Dict[str, Any] = {}

    @property
    def scan_results(self) -> Dict[str, Any]:
        return self._scan_results

    async def update_prices(self):
        """Narxlarni yangilash"""
        if not market_cache.is_price_stale():
            return

        prices = await binance.fetch_all_prices()
        if prices:
            market_cache.set_prices(prices)
            logger.debug(f"Narxlar yangilandi: {len(prices)} ta coin")

    async def update_tickers(self):
        """24h ticker yangilash"""
        tickers = await binance.fetch_all_tickers_bulk()
        for sym, data in tickers.items():
            market_cache.set_ticker(sym, data)
        logger.debug(f"Tickerlar yangilandi: {len(tickers)} ta coin")

    async def update_klines_for_symbols(self, symbols: List[str]):
        """Ko'rsatilgan coinlar uchun kline yangilash"""
        stale = [s for s in symbols if market_cache.is_kline_stale(s)]
        if not stale:
            return

        # Parallel ravishda olish (5 ta bir vaqtda)
        chunk_size = 5
        for i in range(0, len(stale), chunk_size):
            chunk = stale[i:i + chunk_size]
            tasks = [binance.fetch_klines(s) for s in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, df in zip(chunk, results):
                if isinstance(df, pd.DataFrame) and df is not None:
                    market_cache.set_klines(sym, df)

    async def run_full_scan(self, symbols: List[str]) -> Dict[str, Any]:
        """To'liq market skanerlash"""
        if self._scanning:
            return self._scan_results

        self._scanning = True
        try:
            await self.update_prices()
            await self.update_tickers()
            await self.update_klines_for_symbols(symbols)
            self._last_full_scan = time.time()
            logger.info(f"✅ Market scan tugadi: {len(symbols)} ta coin")
        except Exception as e:
            logger.error(f"Market scan xatosi: {e}")
        finally:
            self._scanning = False

        return self._scan_results

    def get_top_gainers(self, n: int = 10) -> List[Dict]:
        """Eng ko'p o'sgan coinlar"""
        results = []
        for sym in HALAL_COINS:
            ticker = market_cache.get_ticker(sym)
            if ticker and ticker.get("quote_volume", 0) > 100_000:
                results.append(ticker)
        results.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
        return results[:n]

    def get_market_sentiment(self) -> Dict:
        """Umumiy bozor kayfiyati"""
        positive = 0
        negative = 0
        total = 0
        for sym in HALAL_COINS:
            ticker = market_cache.get_ticker(sym)
            if ticker:
                total += 1
                chg = ticker.get("change_pct", 0)
                if chg > 0:
                    positive += 1
                elif chg < 0:
                    negative += 1
        if total == 0:
            return {"trend": "neutral", "positive_pct": 50, "negative_pct": 50}
        pos_pct = (positive / total) * 100
        neg_pct = (negative / total) * 100
        if pos_pct >= 60:
            trend = "bullish"
        elif neg_pct >= 60:
            trend = "bearish"
        else:
            trend = "neutral"
        return {
            "trend": trend,
            "positive_pct": round(pos_pct),
            "negative_pct": round(neg_pct),
            "total_coins": total,
        }


# Global scanner
market_scanner = MarketScanner()
