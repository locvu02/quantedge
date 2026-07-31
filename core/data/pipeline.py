import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import ccxt
import pandas as pd
from loguru import logger
from sqlalchemy import select, text

from config.settings import settings
from core.data.database import SessionLocal, init_db
from core.data.models import OHLCV

SYMBOLS = {
    "crypto": ["BTC/USDT", "ETH/USDT"],
    "forex": ["XAU/USD", "EUR/USD"],
}

TIMEFRAMES = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

EXCHANGE_CONFIG = {
    "crypto": {"exchange": "binance", "cls": ccxt.binance},
    "forex": {"exchange": "yfinance", "cls": None},
}


def _get_binance() -> ccxt.Exchange:
    kwargs = {"enableRateLimit": True}
    if settings.binance_api_key:
        kwargs["apiKey"] = settings.binance_api_key
        kwargs["secret"] = settings.binance_secret_key
    return ccxt.binance(kwargs)


def _fetch_forex_from_yahoo(symbol: str, timeframe: str, since_ms: int, limit: int):
    import yfinance as yf

    yf_map = {
        "XAU/USD": "GC=F",
        "EUR/USD": "EURUSD=X",
        "BTC/USDT": "BTC-USD",
        "ETH/USDT": "ETH-USD",
    }
    yf_symbol = yf_map.get(symbol, symbol.replace("/", "") + "=X")

    tf_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get(timeframe, "1d")

    if since_ms:
        start = datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc)
    else:
        start = datetime.now(timezone.utc) - timedelta(days=90)

    ticker = yf.Ticker(yf_symbol)
    end = datetime.now(timezone.utc)
    df = ticker.history(start=start, end=end, interval=interval)

    if df.empty:
        return []

    ohlcv_list = []
    for idx, row in df.iterrows():
        ts = int(idx.tz_convert("UTC").timestamp() * 1000) if idx.tz else int(idx.timestamp() * 1000)
        ohlcv_list.append([ts, row["Open"], row["High"], row["Low"], row["Close"], row["Volume"]])
    return ohlcv_list


def get_exchange(exchange_type: str) -> ccxt.Exchange:
    if exchange_type == "crypto":
        return _get_binance()
    raise ValueError(f"No live exchange for {exchange_type}; use yfinance for data")


async def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    since: Optional[datetime] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    exchange_type = "crypto" if "/USDT" in symbol else "forex"
    since_ms = int(since.timestamp() * 1000) if since else None

    if exchange_type == "crypto":
        try:
            exchange = get_exchange(exchange_type)
            ohlcv_data = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        except Exception:
            logger.warning(f"Binance failed for {symbol}, using yfinance fallback")
            ohlcv_data = _fetch_forex_from_yahoo(symbol, timeframe, since_ms, limit)
    else:
        ohlcv_data = _fetch_forex_from_yahoo(symbol, timeframe, since_ms, limit)

    df = pd.DataFrame(
        ohlcv_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["symbol"] = symbol
    df["timeframe"] = timeframe

    return df


def save_ohlcv_to_db(df: pd.DataFrame):
    db = SessionLocal()
    try:
        from core.data.models import OHLCV as OHLCVModel
        records = df.to_dict(orient="records")
        saved = 0
        for record in records:
            exists = db.query(OHLCVModel).filter(
                OHLCVModel.symbol == record["symbol"],
                OHLCVModel.timeframe == record["timeframe"],
                OHLCVModel.timestamp == record["timestamp"],
            ).first()
            if not exists:
                candle = OHLCVModel(
                    symbol=record["symbol"],
                    timeframe=record["timeframe"],
                    timestamp=record["timestamp"],
                    open=record["open"],
                    high=record["high"],
                    low=record["low"],
                    close=record["close"],
                    volume=record["volume"],
                )
                db.add(candle)
                saved += 1
        db.commit()
        logger.info(f"Saved {saved} new candles to DB (skipped {len(records) - saved} existing)")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save OHLCV: {e}")
    finally:
        db.close()


def load_ohlcv_from_db(
    symbol: str,
    timeframe: str = "1h",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    db = SessionLocal()
    try:
        stmt = select(OHLCV).where(
            OHLCV.symbol == symbol,
            OHLCV.timeframe == timeframe,
        )
        if start:
            stmt = stmt.where(OHLCV.timestamp >= start)
        if end:
            stmt = stmt.where(OHLCV.timestamp <= end)
        stmt = stmt.order_by(OHLCV.timestamp.asc())
        if limit:
            stmt = stmt.limit(limit)

        rows = db.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()

        data = [
            {
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
            }
            for r in rows
        ]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)
        return df
    finally:
        db.close()


async def fetch_and_save_pipeline(
    symbols: list[str] = None,
    timeframes: list[str] = None,
    days_back: int = 90,
):
    if symbols is None:
        symbols = SYMBOLS["crypto"] + SYMBOLS["forex"]
    if timeframes is None:
        timeframes = list(TIMEFRAMES.keys())

    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    for symbol in symbols:
        for tf in timeframes:
            logger.info(f"Fetching {symbol} {tf}...")
            try:
                df = await fetch_ohlcv(symbol, tf, since=since)
                if not df.empty:
                    save_ohlcv_to_db(df)
                    logger.info(f"  {symbol} {tf}: {len(df)} candles")
            except Exception as e:
                logger.error(f"  Failed {symbol} {tf}: {e}")
                continue


async def watch_ticker_ws(symbols: list[str] = None):
    if symbols is None:
        symbols = SYMBOLS["crypto"]

    exchange = ccxt.pro.binance({"enableRateLimit": True})

    while True:
        try:
            tickers = await exchange.watch_tickers(symbols)
            for symbol, ticker in tickers.items():
                logger.debug(
                    f"{symbol}: bid={ticker.get('bid')} ask={ticker.get('ask')} "
                    f"last={ticker.get('last')} change={ticker.get('percentage', 0):.2f}%"
                )
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await asyncio.sleep(5)


async def main():
    init_db()
    logger.info("Starting data pipeline...")
    await fetch_and_save_pipeline(days_back=90)
    logger.info("Historical data fetch complete.")


if __name__ == "__main__":
    import sys

    if "init" in sys.argv:
        init_db()
        logger.info("Database initialized.")
    elif "fetch" in sys.argv:
        asyncio.run(main())
    elif "ws" in sys.argv:
        asyncio.run(watch_ticker_ws())
    else:
        asyncio.run(main())
