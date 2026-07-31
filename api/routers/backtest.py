from fastapi import APIRouter, Query

from core.data.pipeline import load_ohlcv_from_db
from core.backtest.engine import BacktestEngine

router = APIRouter()


@router.get("/run/{symbol:path}")
async def run_backtest(
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1h|4h|1d)$"),
    initial_balance: float = Query(10000, ge=100, le=1000000),
):
    df = load_ohlcv_from_db(symbol, timeframe)
    if len(df) < 300:
        return {"error": f"Need at least 300 candles, got {len(df)}"}

    engine = BacktestEngine(initial_balance=initial_balance)
    result = engine.run(df, symbol)

    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "initial_balance": result.initial_balance,
        "final_balance": result.final_balance,
        "total_return_pct": result.total_return_pct,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "win_rate": round(result.win_rate, 3),
        "avg_win": result.avg_win,
        "avg_loss": result.avg_loss,
        "profit_factor": result.profit_factor,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "trades": result.trades[-20:],
        "equity_curve": result.equity_curve,
    }


@router.get("/scan")
async def scan_backtests(timeframe: str = Query("1h", pattern="^(1h|4h|1d)$")):
    symbols = ["BTC/USDT", "ETH/USDT", "XAU/USD", "EUR/USD"]
    results = []
    engine = BacktestEngine(initial_balance=10000)

    for sym in symbols:
        df = load_ohlcv_from_db(sym, timeframe)
        if len(df) < 300:
            results.append({"symbol": sym, "error": "insufficient data"})
            continue
        r = engine.run(df, sym)
        results.append({
            "symbol": r.symbol,
            "total_return_pct": r.total_return_pct,
            "total_trades": r.total_trades,
            "win_rate": round(r.win_rate, 3),
            "profit_factor": r.profit_factor,
            "max_drawdown_pct": r.max_drawdown_pct,
            "sharpe_ratio": r.sharpe_ratio,
            "final_balance": r.final_balance,
        })

    return {"timeframe": timeframe, "results": results}
