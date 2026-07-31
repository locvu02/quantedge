from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta

from core.data.pipeline import load_ohlcv_from_db, fetch_and_save_pipeline

router = APIRouter()

SYMBOLS = ["BTC/USDT", "ETH/USDT", "XAU/USD", "EUR/USD"]
TIMEFRAMES = ["1h", "4h", "1d"]


@router.get("/symbols")
async def get_symbols():
    return {"symbols": SYMBOLS, "timeframes": TIMEFRAMES}


@router.get("/ohlcv/{symbol:path}")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1h|4h|1d)$"),
    limit: int = Query(500, ge=1, le=2000),
):
    df = load_ohlcv_from_db(symbol, timeframe, limit=limit)
    if df.empty:
        return {"symbol": symbol, "timeframe": timeframe, "candles": []}
    df = df.reset_index()
    candles = []
    for _, row in df.iterrows():
        candles.append({
            "timestamp": row["timestamp"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles}


@router.post("/fetch")
async def trigger_fetch(days: int = Query(90, ge=1, le=365)):
    await fetch_and_save_pipeline(days_back=days)
    return {"status": "ok", "message": f"Fetched data for last {days} days"}


@router.get("/latest/{symbol:path}")
async def get_latest_price(symbol: str):
    df = load_ohlcv_from_db(symbol, "1h", limit=1)
    if df.empty:
        return {"symbol": symbol, "price": None}
    return {"symbol": symbol, "price": float(df.iloc[-1]["close"])}
