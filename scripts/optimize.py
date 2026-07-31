import itertools

import numpy as np
import pandas as pd
from loguru import logger

from core.data.pipeline import load_ohlcv_from_db
from core.engine.indicators import compute_all_indicators
from core.engine.strategies import generate_signals, Direction
from core.risk.manager import RiskManager
from config.settings import settings

PARAM_GRID = {
    "sl_mult": [1.5, 2.0, 2.5, 3.0],
    "tp_mult": [2.0, 2.5, 3.0, 3.5, 4.0],
    "min_confidence": [0.45, 0.50, 0.55, 0.60],
    "min_rr": [1.2, 1.5, 1.8, 2.0],
}


def run_grid_search(symbol: str, timeframe: str = "1h") -> list[dict]:
    df = load_ohlcv_from_db(symbol, timeframe)
    if len(df) < 300:
        return []

    df_ind = compute_all_indicators(df)
    results = []

    keys = list(PARAM_GRID.keys())
    total_combos = np.prod([len(PARAM_GRID[k]) for k in keys])

    for idx, (sl_m, tp_m, min_conf, min_rr) in enumerate(itertools.product(*PARAM_GRID.values())):
        rm = RiskManager(initial_balance=10000.0)
        trades = []
        warmup = 200

        for i in range(warmup, len(df_ind)):
            window = df_ind.iloc[: i + 1]
            current = df_ind.iloc[i]

            prices = {symbol: float(current["close"])}
            rm.update_market_prices(prices)

            stopped = rm.check_stops()
            for pos, reason in stopped:
                exit_price = pos.stop_loss if reason == "stop_loss" else pos.take_profit
                pnl = rm.close_position(pos, exit_price, reason)
                trades.append({"pnl": pnl})

            if rm.account.open_positions_count == 0:
                signals = generate_signals(window)
                if not signals:
                    continue

                long_s = [s for s in signals if s.direction == Direction.LONG]
                short_s = [s for s in signals if s.direction == Direction.SHORT]
                best = long_s if len(long_s) >= len(short_s) else short_s
                if not best:
                    continue

                avg_conf = np.mean([s.confidence for s in best])
                if avg_conf < min_conf:
                    continue

                direction = best[0].direction.value
                entry = float(current["close"])
                atr = float(current.get("atr_14", entry * 0.01))

                if direction == "long":
                    sl = entry - sl_m * atr
                    tp = entry + tp_m * atr
                else:
                    sl = entry + sl_m * atr
                    tp = entry - tp_m * atr

                rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
                if rr < min_rr:
                    continue

                rm.open_position(symbol, direction, entry, sl, tp)

        final_balance = rm.account.balance
        total_return = (final_balance - 10000.0) / 10000.0
        winning = [t["pnl"] for t in trades if t["pnl"] > 0]
        losing = [t["pnl"] for t in trades if t["pnl"] <= 0]
        win_rate = len(winning) / len(trades) if trades else 0
        profit_factor = sum(winning) / abs(sum(losing)) if losing else (999 if winning else 0)
        avg_win = np.mean(winning) if winning else 0
        avg_loss = np.mean(losing) if losing else 0

        results.append({
            "sl_mult": sl_m,
            "tp_mult": tp_m,
            "min_confidence": min_conf,
            "min_rr": min_rr,
            "total_return_pct": round(total_return * 100, 2),
            "total_trades": len(trades),
            "win_rate": round(win_rate, 3),
            "profit_factor": round(profit_factor, 2) if profit_factor != 999 else 999,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "final_balance": round(final_balance, 2),
            "score": round(total_return * 100 * win_rate * min(profit_factor, 10), 2),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def optimize_all():
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        logger.info(f"Optimizing {symbol}...")
        results = run_grid_search(symbol)
        if not results:
            continue

        best = results[0]
        logger.info(
            f"  Best: sl={best['sl_mult']} tp={best['tp_mult']} "
            f"conf={best['min_confidence']} rr={best['min_rr']} "
            f"return={best['total_return_pct']}% wr={best['win_rate']*100:.0f}% "
            f"pf={best['profit_factor']} trades={best['total_trades']} "
            f"score={best['score']}"
        )

        top5 = results[:5]
        for r in top5:
            print(f"  {r['sl_mult']}/{r['tp_mult']} conf={r['min_confidence']} rr={r['min_rr']} "
                  f"→ ret={r['total_return_pct']}% wr={r['win_rate']*100:.0f}% "
                  f"pf={r['profit_factor']} score={r['score']}")


if __name__ == "__main__":
    optimize_all()
