import numpy as np
from dataclasses import dataclass
from loguru import logger

from core.data.pipeline import load_ohlcv_from_db
from core.backtest.engine import BacktestEngine


@dataclass
class WalkForwardResult:
    symbol: str
    total_return_pct: float
    avg_win_rate: float
    avg_sharpe: float
    avg_profit_factor: float
    max_drawdown_pct: float
    win_rate_std: float
    sharpe_std: float
    windows: int
    per_window: list


def walk_forward_validation(symbol: str, n_windows: int = 5, train_ratio: float = 0.7) -> WalkForwardResult:
    df = load_ohlcv_from_db(symbol, "1h")
    if len(df) < 500:
        return None

    total_len = len(df)
    window_size = total_len // (n_windows + 1)

    results = []
    for w in range(n_windows):
        train_end = (w + 1) * window_size
        test_start = train_end
        test_end = min(test_start + window_size, total_len)

        engine = BacktestEngine(use_ml=True, use_rl=False)
        test_df = df.iloc[:test_end]
        result = engine.run(test_df, symbol)

        results.append({
            "window": w,
            "return": result.total_return_pct,
            "win_rate": result.win_rate,
            "sharpe": result.sharpe_ratio,
            "profit_factor": result.profit_factor,
            "trades": result.total_trades,
        })

        logger.info(f"Walk-forward {symbol} window {w}: {result.total_trades}t, {result.total_return_pct:+.1f}%, WR={result.win_rate*100:.0f}%")

    returns = [r["return"] for r in results]
    sharpes = [r["sharpe"] for r in results]
    win_rates = [r["win_rate"] for r in results]
    pfs = [r["profit_factor"] for r in results]

    return WalkForwardResult(
        symbol=symbol,
        total_return_pct=round(np.mean(returns), 2),
        avg_win_rate=round(np.mean(win_rates), 3),
        avg_sharpe=round(np.mean(sharpes), 2),
        avg_profit_factor=round(np.mean(pfs), 2),
        max_drawdown_pct=round(max(abs(r["return"]) for r in results), 2),
        win_rate_std=round(np.std(win_rates), 3),
        sharpe_std=round(np.std(sharpes), 2),
        windows=n_windows,
        per_window=results,
    )


def monte_carlo_simulation(symbol: str, n_sims: int = 50, sample_pct: float = 0.7) -> dict:
    df = load_ohlcv_from_db(symbol, "1h")
    if len(df) < 500:
        return {}

    engine = BacktestEngine(use_ml=True, use_rl=False)
    results = []

    sample_size = int(len(df) * sample_pct)

    for sim in range(n_sims):
        start = np.random.randint(0, len(df) - sample_size)
        df_sample = df.iloc[start : start + sample_size]
        result = engine.run(df_sample, symbol)
        results.append({
            "return": result.total_return_pct,
            "sharpe": result.sharpe_ratio,
            "win_rate": result.win_rate,
            "trades": result.total_trades,
        })

    returns = [r["return"] for r in results]
    sharpes = [r["sharpe"] for r in results]
    winning_sims = sum(1 for r in results if r["return"] > 0)

    return {
        "symbol": symbol,
        "simulations": n_sims,
        "avg_return_pct": round(np.mean(returns), 2),
        "median_return_pct": round(np.median(returns), 2),
        "std_return_pct": round(np.std(returns), 2),
        "max_return_pct": round(max(returns), 2),
        "min_return_pct": round(min(returns), 2),
        "avg_sharpe": round(np.mean(sharpes), 2),
        "win_pct": round(winning_sims / n_sims * 100, 1),
        "positive_sims": winning_sims,
        "avg_trades": round(np.mean([r["trades"] for r in results]), 0),
    }
