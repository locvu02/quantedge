from fastapi import APIRouter
from datetime import datetime, timezone
import os

from core.execution.paper_engine import paper_engine
from core.data.database import SessionLocal
from core.data.models import OHLCV, Trade, AccountSnapshot
from core.models.trainer import load_model

router = APIRouter()


@router.get("/status")
async def system_status():
    db = SessionLocal()
    try:
        ohlcv_count = db.query(OHLCV).count()
        trade_count = db.query(Trade).count()
        last_snapshot = db.query(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).first()
    finally:
        db.close()

    models_loaded = []
    for symbol in ["BTC/USDT", "ETH/USDT", "XAU/USD", "EUR/USD"]:
        loaded = load_model(symbol)
        if loaded:
            _, meta, _ = loaded
            models_loaded.append({
                "symbol": symbol,
                "accuracy": meta.get("accuracy", 0),
                "trained_at": meta.get("trained_at", ""),
            })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "running",
        "paper_trading": paper_engine.running,
        "database": {
            "ohlcv_candles": ohlcv_count,
            "trades": trade_count,
        },
        "ml_models": models_loaded,
        "account": paper_engine.get_status() if paper_engine.running else None,
        "version": "0.2.0",
    }
