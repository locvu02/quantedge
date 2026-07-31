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

        lstm_model = None
        if self.use_ml:
            from core.models.lstm_model import load_lstm
            lstm_loaded = load_lstm(symbol)
            if lstm_loaded:
                lstm_model, _ = lstm_loaded

        warmup = 200
        min_candles = max(warmup, 300)  # ML needs more data

        for i in range(min_candles, len(df)):
            window = df.iloc[: i + 1]
            current = df.iloc[i]
            ts = df.index[i]

            prices = {symbol: float(current["close"])}
            rm.update_market_prices(prices)

            # Dynamic trailing stop
            for pos in list(rm.account.positions):
                if pos.direction == "long":
                    profit_r = (pos.current_price - pos.entry_price) / (pos.entry_price - pos.stop_loss) if pos.entry_price > pos.stop_loss else 0
                    if profit_r > 1.0:
                        new_sl = pos.entry_price + (pos.current_price - pos.entry_price) * 0.5
                        if new_sl > pos.stop_loss:
                            pos.stop_loss = new_sl
                    if profit_r > 2.0:
                        new_sl = pos.entry_price + (pos.current_price - pos.entry_price) * 0.7
                        if new_sl > pos.stop_loss:
                            pos.stop_loss = new_sl
                else:
                    profit_r = (pos.entry_price - pos.current_price) / (pos.stop_loss - pos.entry_price) if pos.stop_loss > pos.entry_price else 0
                    if profit_r > 1.0:
                        new_sl = pos.entry_price - (pos.entry_price - pos.current_price) * 0.5
                        if new_sl < pos.stop_loss:
                            pos.stop_loss = new_sl
                    if profit_r > 2.0:
                        new_sl = pos.entry_price - (pos.entry_price - pos.current_price) * 0.7
                        if new_sl < pos.stop_loss:
                            pos.stop_loss = new_sl

                if pos.direction == "long" and pos.current_price <= pos.stop_loss:
                    pnl = rm.close_position(pos, pos.stop_loss, "trailing_stop")
                    trades.append({
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "entry_time": pos.entry_time.isoformat(),
                        "exit_time": ts.isoformat(),
                        "entry_price": pos.entry_price,
                        "exit_price": pos.stop_loss,
                        "quantity": pos.quantity,
                        "pnl": round(pnl, 2),
                        "exit_reason": "trailing_stop",
                    })
                elif pos.direction == "short" and pos.current_price >= pos.stop_loss:
                    pnl = rm.close_position(pos, pos.stop_loss, "trailing_stop")
                    trades.append({
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "entry_time": pos.entry_time.isoformat(),
                        "exit_time": ts.isoformat(),
                        "entry_price": pos.entry_price,
                        "exit_price": pos.stop_loss,
                        "quantity": pos.quantity,
                        "pnl": round(pnl, 2),
                        "exit_reason": "trailing_stop",
                    })

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

                        if lstm_model is not None:
                            from core.models.lstm_model import predict_lstm
                            lstm_pred = predict_lstm(lstm_model, window)
                            if lstm_pred and lstm_pred["direction"] != direction:
                                continue
                            if lstm_pred:
                                avg_conf = min(0.95, avg_conf + lstm_pred["confidence"] * 0.1)

                        from core.engine.multi_tf import higher_tf_confirm
                        htf_ok, htf_conf = higher_tf_confirm(symbol, direction)
                        if not htf_ok:
                            continue
                        avg_conf = min(0.95, avg_conf + htf_conf * 0.1)

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
                            # Kelly position sizing
                            if len(trades) >= 5:
                                wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
                                losses = len(trades) - wins
                                win_rate_kelly = wins / len(trades) if len(trades) > 0 else 0.5
                                avg_w = np.mean([t["pnl"] for t in trades if t.get("pnl", 0) > 0]) if wins > 0 else 100
                                avg_l = abs(np.mean([t["pnl"] for t in trades if t.get("pnl", 0) <= 0])) if losses > 0 else 100
                                kelly_r = avg_w / avg_l if avg_l > 0 else 2.0
                                kelly_f = max(0.01, min(0.03, win_rate_kelly - (1 - win_rate_kelly) / kelly_r))
                            else:
                                kelly_f = 0.02

                            if rm.account.drawdown_pct > 0.10:
                                kelly_f = min(kelly_f, 0.015)
                            elif rm.account.drawdown_pct > 0.05:
                                kelly_f = min(kelly_f, 0.02)

                            risk_amount = rm.account.equity * kelly_f
                            from core.engine.time_filter import session_risk_multiplier
                            risk_amount *= session_risk_multiplier(symbol, ts)
                            price_risk = abs(entry - sl)
                            if price_risk > 0:
                                qty = risk_amount / price_risk
                                pos = Position(
                                    symbol=symbol, direction=direction,
                                    entry_price=entry, quantity=qty,
                                    stop_loss=sl, take_profit=tp,
                                )
                                pos.current_price = entry
                                pos.entry_time = ts
                                rm.account.positions.append(pos)

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
