import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime, timezone
from loguru import logger

from core.engine.strategies import generate_signals, Direction, StrategySignal
from core.risk.manager import RiskManager


class SignalEngine:
    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self.last_signal_time: dict[str, datetime] = {}

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        if symbol in self.last_signal_time:
            elapsed = (now - self.last_signal_time[symbol]).total_seconds()
            if elapsed < 3600 and df.index[-1] == df.index[-2]:
                return None

        signals = generate_signals(df)
        if not signals:
            return None

        votes = {"long": [], "short": []}
        for s in signals:
            votes[s.direction.value].append(s)

        best_direction = "long" if len(votes["long"]) >= len(votes["short"]) else "short"
        best_signals = votes[best_direction]

        if len(best_signals) < 1:
            return None

        avg_confidence = np.mean([s.confidence for s in best_signals])
        if avg_confidence < 0.5:
            return None

        avg_entry = np.mean([s.entry_price for s in best_signals])
        avg_sl = np.mean([s.stop_loss for s in best_signals])
        avg_tp = np.mean([s.take_profit for s in best_signals])

        rr_valid, rr = self.risk_manager.validate_risk_reward(avg_entry, avg_sl, avg_tp)
        if not rr_valid:
            logger.debug(f"{symbol}: signal ignored, RR={rr:.1f} < min")
            return None

        self.last_signal_time[symbol] = now

        return {
            "symbol": symbol,
            "direction": best_direction,
            "confidence": round(avg_confidence, 3),
            "entry_price": round(avg_entry, 2),
            "stop_loss": round(avg_sl, 2),
            "take_profit": round(avg_tp, 2),
            "risk_reward": round(rr, 2),
            "timestamp": now,
            "strategies": [s.strategy for s in best_signals],
            "reasons": [s.reason for s in best_signals],
        }
