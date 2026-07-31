"""Train RL agent over multiple epochs for optimal position sizing."""
import numpy as np
from loguru import logger

from core.data.pipeline import load_ohlcv_from_db
from core.engine.indicators import compute_all_indicators
from core.engine.strategies import Direction
from core.engine.signals import generate_regime_signals
from core.engine.regime import detect_regime, regime_confidence, MarketRegime
from core.models.rl_agent import QLearningAgent
from core.risk.manager import RiskManager, Position


def train_rl_agent(symbol: str, epochs: int = 10):
    df = load_ohlcv_from_db(symbol, "1h")
    df = compute_all_indicators(df)

    agent = QLearningAgent(epsilon=0.5, alpha=0.15, gamma=0.95)
    best_sharpe = -999
    best_data = None

    warmup = 200

    for epoch in range(epochs):
        agent.epsilon = max(0.05, 0.5 * (0.6 ** epoch))
        rm = RiskManager(initial_balance=10000.0)
        trades = []
        equity = []
        win_streak = 0

        for i in range(warmup, len(df)):
            window = df.iloc[: i + 1]
            current = df.iloc[i]
            ts = df.index[i]

            prices = {symbol: float(current["close"])}
            rm.update_market_prices(prices)

            for pos in list(rm.account.positions):
                if pos.direction == "long":
                    profit_r = (pos.current_price - pos.entry_price) / max(abs(pos.entry_price - pos.stop_loss), 0.0001)
                    if profit_r > 1.0:
                        pos.stop_loss = max(pos.stop_loss, pos.entry_price + (pos.current_price - pos.entry_price) * 0.5)
                    if profit_r > 2.0:
                        pos.stop_loss = max(pos.stop_loss, pos.entry_price + (pos.current_price - pos.entry_price) * 0.7)
                else:
                    profit_r = (pos.entry_price - pos.current_price) / max(abs(pos.stop_loss - pos.entry_price), 0.0001)
                    if profit_r > 1.0:
                        pos.stop_loss = min(pos.stop_loss, pos.entry_price - (pos.entry_price - pos.current_price) * 0.5)
                    if profit_r > 2.0:
                        pos.stop_loss = min(pos.stop_loss, pos.entry_price - (pos.entry_price - pos.current_price) * 0.7)

            stopped = rm.check_stops()
            for pos, reason in stopped:
                exit_price = pos.stop_loss if reason == "stop_loss" else pos.take_profit
                pnl = rm.close_position(pos, exit_price, reason)
                trades.append({"pnl": pnl})
                win_streak = win_streak + 1 if pnl > 0 else win_streak - 1

                regime = detect_regime(window)
                vol = float(current.get("volatility_20", 0.015))
                next_s = agent._discretize_state(regime, win_streak, vol, 0.5)
                reward = np.tanh(pnl / 100.0)
                agent.learn(reward, next_s)

            if rm.account.open_positions_count == 0 and i < len(df) - 1:
                signals = generate_regime_signals(window)
                regime = detect_regime(window)
                reg_conf = regime_confidence(window, regime)

                long_s = [s for s in signals if s.direction == Direction.LONG]
                short_s = [s for s in signals if s.direction == Direction.SHORT]
                best = long_s if len(long_s) >= len(short_s) else short_s
                if not best:
                    continue

                avg_conf = np.mean([s.confidence for s in best])
                avg_conf = min(0.95, avg_conf + reg_conf * 0.2)
                if avg_conf < 0.5:
                    continue

                direction = best[0].direction.value
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

                rr = abs(tp - entry) / max(abs(entry - sl), 0.0001)
                if rr < 1.5:
                    continue

                # Kelly sizing
                if len(trades) >= 5:
                    wins = sum(1 for t in trades if t["pnl"] > 0)
                    losses = len(trades) - wins
                    wr = wins / len(trades)
                    avg_w = np.mean([t["pnl"] for t in trades if t["pnl"] > 0]) if wins > 0 else 100
                    avg_l = abs(np.mean([t["pnl"] for t in trades if t["pnl"] <= 0])) if losses > 0 else 100
                    kelly_f = max(0.01, min(0.03, wr - (1 - wr) / max(avg_w / max(avg_l, 0.01), 0.5)))
                else:
                    kelly_f = 0.02

                if rm.account.drawdown_pct > 0.10:
                    kelly_f = min(kelly_f, 0.015)

                risk_amount = rm.account.equity * kelly_f

                # RL position sizing
                volatility_pct = float(current.get("volatility_20", 0.015))
                rl_state = agent._discretize_state(regime, win_streak, volatility_pct, avg_conf)
                rl_multiplier, _ = agent.get_action(rl_state)
                risk_amount *= rl_multiplier

                price_risk = abs(entry - sl)
                if price_risk > 0:
                    qty = risk_amount / price_risk
                    pos = Position(symbol=symbol, direction=direction,
                                   entry_price=entry, quantity=qty,
                                   stop_loss=sl, take_profit=tp)
                    pos.current_price = entry
                    rm.account.positions.append(pos)

        final_balance = rm.account.balance
        total_return = (final_balance - 10000) / 10000
        winning = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = winning / len(trades) if trades else 0

        returns = pd.Series([e["equity"] for e in equity]).pct_change().dropna() if equity else pd.Series()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252 * 6)) if len(returns) > 0 and returns.std() > 0 else 0

        logger.info(f"Epoch {epoch + 1}/{epochs}: {len(trades)}t, {total_return*100:+.1f}%, WR={win_rate*100:.0f}%, Sharpe={sharpe:.2f}, epsilon={agent.epsilon:.2f}")

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            agent.save(symbol)

    logger.info(f"RL agent trained for {symbol}: best Sharpe={best_sharpe:.2f}")
    return agent


if __name__ == "__main__":
    import pandas as pd
    for sym in ["BTC/USDT", "ETH/USDT", "XAU/USD"]:
        train_rl_agent(sym, epochs=10)
