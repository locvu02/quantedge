import pandas as pd
import numpy as np
from typing import Optional

from core.engine.indicators import compute_all_indicators


def higher_tf_confirm(symbol: str, direction: str, entries: Optional[dict] = None) -> tuple[bool, float]:
    from core.data.pipeline import load_ohlcv_from_db

    df = load_ohlcv_from_db(symbol, "4h")
    if len(df) < 50:
        return True, 0.5

    df = compute_all_indicators(df)
    latest = df.iloc[-1]

    ema_21 = latest.get("ema_21", 0)
    ema_50 = latest.get("ema_50", 0)
    close = latest["close"]

    htf_bullish = close > ema_21 > ema_50
    htf_bearish = close < ema_21 < ema_50

    if direction == "long" and htf_bullish:
        return True, min(0.9, 0.6 + (close - ema_50) / ema_50 * 10)
    elif direction == "short" and htf_bearish:
        return True, min(0.9, 0.6 + (ema_50 - close) / close * 10)
    elif direction == "long" and htf_bearish:
        return False, 0.0
    elif direction == "short" and htf_bullish:
        return False, 0.0

    return True, 0.5


def htf_filter_only(symbol: str, direction: str) -> bool:
    ok, _ = higher_tf_confirm(symbol, direction)
    return ok
