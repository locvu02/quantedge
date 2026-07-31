from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np
from loguru import logger

from core.engine.indicators import compute_all_indicators
from core.engine.strategies import Direction
from core.engine.signals import generate_regime_signals
from core.engine.regime import detect_regime, regime_confidence, MarketRegime
from core.risk.manager import RiskManager, Position


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, initial_balance: float = 10000.0, commission_pct: float = 0.001, use_ml: bool = False):
        self.initial_balance = initial_balance
        self.commission_pct = commission_pct
        self.use_ml = use_ml

    def run(self, df: pd.DataFrame, symbol: str) -> BacktestResult:
        df = compute_all_indicators(df)
        rm = RiskManager(initial_balance=self.initial_balance)
        trades = []
        equity = []

        ml_model = None
        ml_scaler = None
        if self.use_ml:
            from core.models.trainer import load_model
            loaded = load_model(symbol)
            if loaded:
                ml_model, ml_meta, ml_scaler = loaded

        warmup = 200
        min_candles = max(warmup, 300)  # ML needs more data

        for i in range(min_candles, len(df)):
            window = df.iloc[: i + 1]
            current = df.iloc[i]
            ts = df.index[i]

            prices = {symbol: float(current["close"])}
            rm.update_market_prices(prices)

            stopped = rm.check_stops()
            for pos, reason in stopped:
                exit_price = pos.stop_loss if reason == "stop_loss" else pos.take_profit
                pnl = rm.close_position(pos, exit_price, reason)
                trades.append({
                    "symbol": pos.symbol,
                    "direction": pos.direction,
                    "entry_time": pos.entry_time.isoformat(),
                    "exit_time": ts.isoformat(),
                    "entry_price": pos.entry_price,
                    "exit_price": exit_price,
                    "quantity": pos.quantity,
                    "pnl": round(pnl, 2),
                    "exit_reason": reason,
                })

            if rm.account.open_positions_count == 0 and i < len(df) - 1:
                signals = generate_regime_signals(window)
                regime = detect_regime(window)
                regime_conf = regime_confidence(window, regime)

                if not signals:
                    continue

                long_signals = [s for s in signals if s.direction == Direction.LONG]
                short_signals = [s for s in signals if s.direction == Direction.SHORT]

                all_dir = long_signals + short_signals
                if not all_dir:
                    continue

                best_signals = long_signals if len(long_signals) >= len(short_signals) else short_signals
                if len(best_signals) >= 1:
                    avg_conf = np.mean([s.confidence for s in best_signals])
                    avg_conf = min(0.95, avg_conf + regime_conf * 0.2)
                    if avg_conf >= 0.5:
                        direction = best_signals[0].direction.value

                        if ml_model is not None:
                            from core.models.trainer import predict as ml_predict
                            ml_pred = ml_predict(ml_model, window, ml_scaler)
                            if ml_pred and ml_pred["direction"] != direction:
                                continue
                            if ml_pred and ml_pred["confidence"] < 0.55:
                                continue
                        entry = float(current["close"])
                        atr = float(current.get("atr_14", entry * 0.01))

                        if regime == MarketRegime.VOLATILE:
                            sl_m, tp_m = 3.0, 4.0
                        elif regime == MarketRegime.TRENDING:
                            sl_m, tp_m = 2.0, 3.5
                        else:
                            sl_m, tp_m = 2.0, 3.0

                        if direction == "long":
                            sl = entry - sl_m * atr
                            tp = entry + tp_m * atr
                        else:
                            sl = entry + sl_m * atr
                            tp = entry - tp_m * atr

                        rr_valid, _ = rm.validate_risk_reward(entry, sl, tp)
                        if rr_valid:
                            pos = rm.open_position(symbol, direction, entry, sl, tp)
                            if pos:
                                pos.entry_time = ts

            equity.append({
                "timestamp": ts.isoformat(),
                "balance": round(rm.account.balance, 2),
                "equity": round(rm.account.equity, 2),
                "drawdown": round(rm.account.drawdown_pct, 4),
            })

        for pos in list(rm.account.positions):
            exit_price = float(df.iloc[-1]["close"])
            pnl = rm.close_position(pos, exit_price, "end_of_test")
            trades.append({
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry_time": pos.entry_time.isoformat(),
                "exit_time": df.index[-1].isoformat(),
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "quantity": pos.quantity,
                "pnl": round(pnl, 2),
                "exit_reason": "end_of_test",
            })

        return self._compute_metrics(df, symbol, rm, trades, equity)

    def _compute_metrics(
        self, df: pd.DataFrame, symbol: str, rm: RiskManager, trades: list[dict], equity: list[dict]
    ) -> BacktestResult:
        final_balance = rm.account.balance
        total_return = (final_balance - self.initial_balance) / self.initial_balance

        winning = [t["pnl"] for t in trades if t["pnl"] > 0]
        losing = [t["pnl"] for t in trades if t["pnl"] <= 0]

        profit_factor = sum(winning) / abs(sum(losing)) if losing else float("inf")

        returns = pd.Series([e["equity"] for e in equity]).pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252 * 6)) if len(returns) > 0 and returns.std() > 0 else 0.0

        max_dd = max((e["drawdown"] for e in equity), default=0.0) if equity else 0.0

        tf = "1h"
        if "timeframe" in df.columns:
            tf = df["timeframe"].iloc[0]

        return BacktestResult(
            symbol=symbol,
            timeframe=tf,
            start_date=df.index[0],
            end_date=df.index[-1],
            initial_balance=self.initial_balance,
            final_balance=round(final_balance, 2),
            total_return_pct=round(total_return * 100, 2),
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(len(winning) / len(trades), 3) if trades else 0.0,
            avg_win=round(np.mean(winning), 2) if winning else 0.0,
            avg_loss=round(np.mean(losing), 2) if losing else 0.0,
            profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
            max_drawdown_pct=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 2),
            trades=trades,
            equity_curve=equity,
        )
