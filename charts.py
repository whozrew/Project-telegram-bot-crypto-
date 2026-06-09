"""
Halol Crypto AI Bot - Grafik generatsiya moduli
"""
import io
import logging
import asyncio
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

from config import CHART_DPI, CHART_FIGSIZE
from scanner import market_cache
from signals import SignalResult, calc_rsi, calc_ema, calc_macd, calc_bollinger_bands

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# RANGLAR
# ──────────────────────────────────────────────
COLORS = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "text": "#c9d1d9",
    "text_dim": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "yellow": "#e3b341",
    "blue": "#58a6ff",
    "purple": "#bc8cff",
    "orange": "#f0883e",
    "grid": "#21262d",
    "candle_up": "#3fb950",
    "candle_down": "#f85149",
    "ema20": "#f0883e",
    "ema50": "#bc8cff",
    "ema200": "#58a6ff",
    "macd": "#3fb950",
    "signal": "#f85149",
    "rsi": "#f0883e",
    "volume": "#30363d",
    "entry": "#3fb950",
    "sl": "#f85149",
    "tp": "#58a6ff",
    "support": "#e3b341",
    "resistance": "#bc8cff",
}


def _apply_dark_style(ax, title: str = ""):
    ax.set_facecolor(COLORS["panel"])
    ax.tick_params(colors=COLORS["text_dim"], labelsize=8)
    ax.spines["bottom"].set_color(COLORS["grid"])
    ax.spines["left"].set_color(COLORS["grid"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.grid(True, color=COLORS["grid"], linewidth=0.5, alpha=0.6)
    if title:
        ax.set_title(title, color=COLORS["text_dim"], fontsize=8, pad=4)


def _format_price_label(price: float) -> str:
    if price >= 1000:
        return f"${price:,.1f}"
    elif price >= 1:
        return f"${price:.3f}"
    elif price >= 0.001:
        return f"${price:.5f}"
    return f"${price:.8f}"


async def generate_signal_chart(result: SignalResult) -> Optional[bytes]:
    """Signal grafigi yaratish (async wrapper)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _create_chart, result)


def _create_chart(result: SignalResult) -> Optional[bytes]:
    """Grafik yaratish (sinxron, executor'da ishlaydi)"""
    try:
        df = market_cache.get_klines(result.symbol)
        if df is None or len(df) < 50:
            return None

        # So'nggi 80 shamchani olish
        df = df.tail(80).copy().reset_index(drop=True)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]
        volume = df["volume"]

        # Indikatorlar
        rsi = calc_rsi(close)
        ema20 = calc_ema(close, 20)
        ema50 = calc_ema(close, 50)
        ema200 = calc_ema(close, 200)
        macd_line, signal_line, histogram = calc_macd(close)

        # ──────────────────────────────
        # Figure va panellar
        # ──────────────────────────────
        fig = plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI, facecolor=COLORS["bg"])
        gs = gridspec.GridSpec(4, 1, figure=fig,
                               height_ratios=[4, 1.2, 1.2, 0.8],
                               hspace=0.04, left=0.02, right=0.88,
                               top=0.93, bottom=0.06)

        ax_price = fig.add_subplot(gs[0])
        ax_volume = fig.add_subplot(gs[1], sharex=ax_price)
        ax_macd = fig.add_subplot(gs[2], sharex=ax_price)
        ax_rsi = fig.add_subplot(gs[3], sharex=ax_price)

        x = np.arange(len(df))

        # ──────────────────────────────
        # 1. SHAMCHALAR
        # ──────────────────────────────
        _apply_dark_style(ax_price)
        for i in range(len(df)):
            o, c, h, l = float(open_.iloc[i]), float(close.iloc[i]), float(high.iloc[i]), float(low.iloc[i])
            color = COLORS["candle_up"] if c >= o else COLORS["candle_down"]
            body_h = abs(c - o)
            body_y = min(o, c)
            if body_h == 0:
                body_h = c * 0.001
            rect = Rectangle((i - 0.35, body_y), 0.7, body_h,
                              color=color, linewidth=0, zorder=3)
            ax_price.add_patch(rect)
            ax_price.plot([i, i], [l, min(o, c)], color=color, linewidth=0.8, zorder=2)
            ax_price.plot([i, i], [max(o, c), h], color=color, linewidth=0.8, zorder=2)

        # EMA chiziqlar
        ax_price.plot(x, ema20, color=COLORS["ema20"], linewidth=1.2,
                      label="EMA 20", alpha=0.9, zorder=4)
        ax_price.plot(x, ema50, color=COLORS["ema50"], linewidth=1.2,
                      label="EMA 50", alpha=0.9, zorder=4)
        ax_price.plot(x, ema200, color=COLORS["ema200"], linewidth=1.2,
                      label="EMA 200", alpha=0.9, zorder=4)

        # Qo'llab-quvvatlash / Qarshilik
        if result.support:
            ax_price.axhline(result.support, color=COLORS["support"],
                             linewidth=1.0, linestyle="--", alpha=0.7, label="Qo'llab")
        if result.resistance:
            ax_price.axhline(result.resistance, color=COLORS["resistance"],
                             linewidth=1.0, linestyle="--", alpha=0.7, label="Qarshilik")

        # Kirish / SL / TP zonalar
        if result.entry_low and result.entry_high:
            ax_price.axhspan(result.entry_low, result.entry_high,
                             alpha=0.12, color=COLORS["entry"], label="Kirish zonasi")
        if result.stop_loss and result.stop_loss > 0:
            ax_price.axhline(result.stop_loss, color=COLORS["sl"],
                             linewidth=1.2, linestyle="-.", alpha=0.8, label="Stop Loss")
        if result.take_profit_1 and result.take_profit_1 > 0:
            ax_price.axhline(result.take_profit_1, color=COLORS["tp"],
                             linewidth=1.2, linestyle="-.", alpha=0.8, label="TP 1")
        if result.take_profit_2 and result.take_profit_2 > 0:
            ax_price.axhline(result.take_profit_2, color=COLORS["tp"],
                             linewidth=0.8, linestyle=":", alpha=0.6, label="TP 2")

        # Joriy narx chizig'i
        ax_price.axhline(result.price, color=COLORS["yellow"],
                         linewidth=0.8, alpha=0.6)

        # Legenda
        legend = ax_price.legend(loc="upper left", fontsize=7,
                                  facecolor=COLORS["panel"],
                                  edgecolor=COLORS["grid"],
                                  labelcolor=COLORS["text"])

        # Sarlavha
        from config import SIGNAL_NAMES, SIGNAL_EMOJI
        sig_name = SIGNAL_NAMES.get(result.signal_type, result.signal_type)
        sig_em = SIGNAL_EMOJI.get(result.signal_type, "")
        title_text = (
            f"{result.symbol}/USDT  |  1H  |  "
            f"{sig_em} {sig_name}  |  "
            f"{_format_price_label(result.price)}  |  "
            f"Ishonchlilik: {result.confidence}%"
        )
        ax_price.set_title(title_text, color=COLORS["text"], fontsize=10,
                           fontweight="bold", pad=8)
        ax_price.set_xlim(-1, len(df) + 1)
        ax_price.tick_params(labelbottom=False)
        ax_price.yaxis.tick_right()
        ax_price.tick_params(axis="y", colors=COLORS["text_dim"], labelsize=8)
        ax_price.set_facecolor(COLORS["panel"])
        ax_price.spines["bottom"].set_color(COLORS["grid"])
        ax_price.spines["left"].set_color(COLORS["grid"])
        ax_price.spines["top"].set_visible(False)
        ax_price.spines["right"].set_visible(False)
        ax_price.grid(True, color=COLORS["grid"], linewidth=0.4, alpha=0.5)

        # ──────────────────────────────
        # 2. HAJM
        # ──────────────────────────────
        _apply_dark_style(ax_volume, "Hajm")
        vol_colors = [COLORS["candle_up"] if float(close.iloc[i]) >= float(open_.iloc[i])
                      else COLORS["candle_down"] for i in range(len(df))]
        ax_volume.bar(x, volume, color=vol_colors, width=0.7, alpha=0.7)
        avg_vol = volume.rolling(20).mean()
        ax_volume.plot(x, avg_vol, color=COLORS["yellow"], linewidth=1.0, alpha=0.8)
        ax_volume.tick_params(labelbottom=False, colors=COLORS["text_dim"], labelsize=7)
        ax_volume.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{v/1e3:.0f}K")
        )

        # ──────────────────────────────
        # 3. MACD
        # ──────────────────────────────
        _apply_dark_style(ax_macd, "MACD")
        hist_colors = [COLORS["green"] if v >= 0 else COLORS["red"]
                       for v in histogram.values]
        ax_macd.bar(x, histogram, color=hist_colors, width=0.7, alpha=0.7)
        ax_macd.plot(x, macd_line, color=COLORS["macd"], linewidth=1.0, label="MACD")
        ax_macd.plot(x, signal_line, color=COLORS["signal"], linewidth=1.0, label="Signal")
        ax_macd.axhline(0, color=COLORS["grid"], linewidth=0.8)
        ax_macd.tick_params(labelbottom=False, colors=COLORS["text_dim"], labelsize=7)

        # ──────────────────────────────
        # 4. RSI
        # ──────────────────────────────
        _apply_dark_style(ax_rsi, "RSI (14)")
        ax_rsi.plot(x, rsi, color=COLORS["rsi"], linewidth=1.2)
        ax_rsi.axhline(70, color=COLORS["red"], linewidth=0.8, linestyle="--", alpha=0.6)
        ax_rsi.axhline(30, color=COLORS["green"], linewidth=0.8, linestyle="--", alpha=0.6)
        ax_rsi.axhline(50, color=COLORS["grid"], linewidth=0.6, alpha=0.5)
        ax_rsi.fill_between(x, 70, rsi, where=(rsi >= 70),
                            alpha=0.15, color=COLORS["red"])
        ax_rsi.fill_between(x, rsi, 30, where=(rsi <= 30),
                            alpha=0.15, color=COLORS["green"])
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_yticks([30, 50, 70])
        ax_rsi.tick_params(colors=COLORS["text_dim"], labelsize=7)

        # X o'qi: vaqt belgilari
        tick_step = max(1, len(df) // 8)
        tick_idx = x[::tick_step]
        tick_labels = [str(df["timestamp"].iloc[i].strftime("%m/%d %H:%M"))
                       if i < len(df) else "" for i in tick_idx]
        ax_rsi.set_xticks(tick_idx)
        ax_rsi.set_xticklabels(tick_labels, rotation=20, ha="right",
                                color=COLORS["text_dim"], fontsize=7)

        # Watermark
        fig.text(0.5, 0.02, "Halol Crypto AI — Ta'lim maqsadida",
                 ha="center", color=COLORS["text_dim"], fontsize=8, alpha=0.5)

        # PNG ga saqlash
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight",
                    facecolor=COLORS["bg"], dpi=CHART_DPI)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        logger.error(f"Grafik xatosi {result.symbol}: {e}", exc_info=True)
        try:
            plt.close("all")
        except Exception:
            pass
        return None
