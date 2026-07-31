from datetime import datetime, timezone
from typing import Optional

import pandas as pd


TRADING_SESSIONS = {
    "asia": (0, 8),
    "london": (7, 15),
    "ny": (12, 20),
    "overlap": (12, 15),
    "weekend": (-1, -1),
}


def get_session(ts: Optional[datetime] = None) -> str:
    if ts is None:
        ts = datetime.now(timezone.utc)

    if ts.weekday() >= 5:
        return "weekend"

    hour = ts.hour

    if 12 <= hour < 15:
        return "overlap"
    if 0 <= hour < 8:
        return "asia"
    if 7 <= hour < 15:
        return "london"
    if 12 <= hour < 20:
        return "ny"
    return "asia"


def session_risk_multiplier(symbol: str, ts: Optional[datetime] = None) -> float:
    session = get_session(ts)
    is_crypto = "/USDT" in symbol

    multipliers = {
        "overlap": 1.0,
        "london": 1.0,
        "ny": 1.0,
        "asia": 0.7 if not is_crypto else 1.0,
        "weekend": 0.5 if not is_crypto else 0.8,
    }
    return multipliers.get(session, 1.0)


def should_trade_now(symbol: str, ts: Optional[datetime] = None) -> bool:
    session = get_session(ts)
    if session == "weekend":
        return "/USDT" in symbol
    return True
