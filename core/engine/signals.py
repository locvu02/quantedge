import numpy as np
from typing import Optional
from datetime import datetime, timezone
from loguru import logger

from core.engine.strategies import (
    generate_signals, trend_following_signal,
    mean_reversion_signal, breakout_signal,
    Direction, StrategySignal,
)
from core.engine.regime import detect_regime, regime_confidence, MarketRegime
from core.risk.manager import RiskManager

REGIME_STRATEGIES = {
    MarketRegime.TRENDING: [trend_following_signal, breakout_signal],
    MarketRegime.RANGING: [mean_reversion_signal, breakout_signal],
    MarketRegime.VOLATILE: [breakout_signal, trend_following_signal],
    MarketRegime.QUIET: [mean_reversion_signal, trend_following_signal],
}


def generate_regime_signals(df) -> list[StrategySignal]:
    from core.engine.indicators import compute_all_indicators

    regime = detect_regime(df)
    strategies = REGIME_STRATEGIES.get(regime, [])

    if not strategies:
        return []

    df_ind = compute_all_indicators(df)
    signals = []
    for strat_fn in strategies:
        s = strat_fn(df_ind)
        if s.direction != Direction.NEUTRAL:
            signals.append(s)
    return signals


class SignalEngine:
    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self.last_signal_time: dict[str, datetime] = {}

    def analyze(self, df, symbol: str) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        if symbol in self.last_signal_time:
            elapsed = (now - self.last_signal_time[symbol]).total_seconds()
            if elapsed < 3600 and df.index[-1] == df.index[-2]:
                return None

        regime = detect_regime(df)
        signals = generate_regime_signals(df)

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
        regime_boost = regime_confidence(df, regime) * 0.2
        avg_confidence = min(0.95, avg_confidence + regime_boost)

        if avg_confidence < 0.5:
            return None

        avg_entry = np.mean([s.entry_price for s in best_signals])
        avg_sl = np.mean([s.stop_loss for s in best_signals])
        avg_tp = np.mean([s.take_profit for s in best_signals])

        if regime == MarketRegime.VOLATILE:
            atr = best_signals[0].entry_price * 0.02 if not hasattr(best_signals[0], 'atr') else 0
            avg_sl = avg_entry - (avg_entry * 0.03) if best_direction == "long" else avg_entry + (avg_entry * 0.03)
            avg_tp = avg_entry + (avg_entry * 0.06) if best_direction == "long" else avg_entry - (avg_entry * 0.06)

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
            "regime": regime.value,
            "strategies": [s.strategy for s in best_signals],
            "reasons": [s.reason for s in best_signals],
        }
