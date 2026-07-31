import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class StrategySignal:
    strategy: str
    direction: Direction
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str


def trend_following_signal(df: pd.DataFrame) -> StrategySignal:
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    ema_9 = latest.get("ema_9", np.nan)
    ema_21 = latest.get("ema_21", np.nan)
    ema_50 = latest.get("ema_50", np.nan)
    adx = latest.get("adx_14", 0)
    close = latest["close"]

    if pd.isna(ema_9) or pd.isna(ema_21) or pd.isna(ema_50):
        return StrategySignal("trend_following", Direction.NEUTRAL, 0, close, close, close, "insufficient data")

    bullish = ema_9 > ema_21 > ema_50 and close > ema_9
    bearish = ema_9 < ema_21 < ema_50 and close < ema_9

    if bullish and adx > 20:
        atr = latest.get("atr_14", close * 0.01)
        sl = close - 2 * atr
        tp = close + 3 * atr
        confidence = min(0.8, 0.5 + (adx - 20) / 60)
        return StrategySignal("trend_following", Direction.LONG, confidence, close, sl, tp, f"bullish EMA stack, ADX={adx:.0f}")
    elif bearish and adx > 20:
        atr = latest.get("atr_14", close * 0.01)
        sl = close + 2 * atr
        tp = close - 3 * atr
        confidence = min(0.8, 0.5 + (adx - 20) / 60)
        return StrategySignal("trend_following", Direction.SHORT, confidence, close, sl, tp, f"bearish EMA stack, ADX={adx:.0f}")

    return StrategySignal("trend_following", Direction.NEUTRAL, 0, close, close, close, "no setup")


def mean_reversion_signal(df: pd.DataFrame) -> StrategySignal:
    latest = df.iloc[-1]
    close = latest["close"]
    rsi = latest.get("rsi_14", 50)
    bb_lower = latest.get("bb_lower", np.nan)
    bb_upper = latest.get("bb_upper", np.nan)

    if pd.isna(rsi) or pd.isna(bb_lower):
        return StrategySignal("mean_reversion", Direction.NEUTRAL, 0, close, close, close, "insufficient data")

    diff_prev = (df["close"] - df["close"].shift(1)).iloc[-1]
    rsi_rising = df["rsi_14"].diff().iloc[-1] > 0 if "rsi_14" in df.columns else False

    if close <= bb_lower and rsi < 30 and rsi_rising:
        atr = latest.get("atr_14", close * 0.01)
        sl = close - 1.5 * atr
        tp = close + 2.5 * atr
        confidence = 0.6 + (30 - rsi) / 50
        return StrategySignal("mean_reversion", Direction.LONG, confidence, close, sl, tp, f"oversold bounce, RSI={rsi:.0f}")
    elif close >= bb_upper and rsi > 70 and not rsi_rising:
        atr = latest.get("atr_14", close * 0.01)
        sl = close + 1.5 * atr
        tp = close - 2.5 * atr
        confidence = 0.6 + (rsi - 70) / 50
        return StrategySignal("mean_reversion", Direction.SHORT, confidence, close, sl, tp, f"overbought reversal, RSI={rsi:.0f}")

    return StrategySignal("mean_reversion", Direction.NEUTRAL, 0, close, close, close, "no setup")


def breakout_signal(df: pd.DataFrame) -> StrategySignal:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = latest["close"]
    atr = latest.get("atr_14", np.nan)
    vol_sma = latest.get("volume_sma_20", np.nan)

    if pd.isna(atr) or pd.isna(vol_sma):
        return StrategySignal("breakout", Direction.NEUTRAL, 0, close, close, close, "insufficient data")

    lookback_20 = df.iloc[-21:-1]
    resistance = lookback_20["high"].max()
    support = lookback_20["low"].min()

    vol_expanding = latest["volume"] > 1.5 * vol_sma
    breakout_up = close > resistance and vol_expanding and close > prev["close"]
    breakout_down = close < support and vol_expanding and close < prev["close"]

    if breakout_up:
        sl = close - 1.5 * atr
        tp = close + 3 * atr
        return StrategySignal("breakout", Direction.LONG, 0.7, close, sl, tp, f"breakout above resistance {resistance:.2f}")
    elif breakout_down:
        sl = close + 1.5 * atr
        tp = close - 3 * atr
        return StrategySignal("breakout", Direction.SHORT, 0.7, close, sl, tp, f"breakdown below support {support:.2f}")

    return StrategySignal("breakout", Direction.NEUTRAL, 0, close, close, close, "no breakout")


def generate_signals(df: pd.DataFrame) -> list[StrategySignal]:
    from core.engine.indicators import compute_all_indicators

    df_with_ind = compute_all_indicators(df)

    signals = [
        trend_following_signal(df_with_ind),
        mean_reversion_signal(df_with_ind),
        breakout_signal(df_with_ind),
    ]
    return [s for s in signals if s.direction != Direction.NEUTRAL]
