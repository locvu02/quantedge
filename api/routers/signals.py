from fastapi import APIRouter, Query
from datetime import datetime, timezone

from core.data.pipeline import load_ohlcv_from_db
from core.engine.signals import SignalEngine
from core.risk.manager import RiskManager

router = APIRouter()

risk_manager = RiskManager(initial_balance=10000)
signal_engine = SignalEngine(risk_manager)


@router.get("/analyze/{symbol:path}")
async def analyze_symbol(
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1h|4h|1d)$"),
):
    df = load_ohlcv_from_db(symbol, timeframe)
    if df.empty:
        return {"symbol": symbol, "timeframe": timeframe, "signal": None, "error": "No data"}

    signal = signal_engine.analyze(df, symbol)
    return {"symbol": symbol, "timeframe": timeframe, "signal": signal}


@router.get("/scan")
async def scan_all(timeframe: str = Query("1h", pattern="^(1h|4h|1d)$")):
    symbols = ["BTC/USDT", "ETH/USDT", "XAU/USD", "EUR/USD"]
    results = []
    for sym in symbols:
        df = load_ohlcv_from_db(sym, timeframe)
        if df.empty:
            results.append({"symbol": sym, "signal": None})
            continue
        signal = signal_engine.analyze(df, sym)
        results.append({"symbol": sym, "signal": signal})
    return {"timeframe": timeframe, "results": results, "timestamp": datetime.now(timezone.utc).isoformat()}
