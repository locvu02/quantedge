import pandas as pd
import numpy as np
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    from core.engine.indicators import compute_all_indicators

    df = compute_all_indicators(df)
    latest = df.iloc[-1]

    adx = latest.get("adx_14", 15)
    atr = latest.get("atr_14", 0)
    close = latest["close"]
    atr_pct = (atr / close) if close > 0 else 0
    volatility = latest.get("volatility_20", atr_pct)
    bb_width = (latest.get("bb_upper", close) - latest.get("bb_lower", close)) / latest.get("bb_mid", close) if latest.get("bb_mid", 0) > 0 else 0

    if atr_pct > 0.05 or volatility > 0.04:
        return MarketRegime.VOLATILE
    if adx > 25:
        return MarketRegime.TRENDING
    if adx < 15 and bb_width < 0.02 and atr_pct < 0.015:
        return MarketRegime.QUIET
    return MarketRegime.RANGING


def regime_confidence(df: pd.DataFrame, regime: MarketRegime) -> float:
    from core.engine.indicators import compute_all_indicators

    df = compute_all_indicators(df)
    latest = df.iloc[-1]
    adx = latest.get("adx_14", 15)

    if regime == MarketRegime.TRENDING:
        return min(0.95, 0.5 + (adx - 25) / 50)
    elif regime == MarketRegime.RANGING:
        return min(0.85, 0.4 + (25 - adx) / 30)
    elif regime == MarketRegime.VOLATILE:
        atr = latest.get("atr_14", 0)
        close = latest["close"]
        atr_pct = (atr / close) if close > 0 else 0
        return min(0.9, 0.5 + atr_pct * 10)
    return 0.3
