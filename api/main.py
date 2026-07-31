from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from core.data.database import init_db
from api.routers import data, signals, backtest, account, trading, sentiment_router

app = FastAPI(
    title="QuantEdge API",
    description="AI-powered automated trading system",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router, prefix="/api/data", tags=["Data"])
app.include_router(signals.router, prefix="/api/signals", tags=["Signals"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(account.router, prefix="/api/account", tags=["Account"])
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(sentiment_router.router, prefix="/api/sentiment", tags=["Sentiment"])

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "out")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}
