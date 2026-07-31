from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from core.data.database import init_db
from api.routers import data, signals, backtest, account, trading, sentiment_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="QuantEdge API",
    description="AI-powered automated trading system",
    version="0.2.0",
    lifespan=lifespan,
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


if os.path.exists(FRONTEND_DIR):
    @app.middleware("http")
    async def serve_frontend(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            response = await call_next(request)
            return response

        path = request.url.path.lstrip("/") or "index.html"
        file_path = os.path.join(FRONTEND_DIR, path)

        if os.path.isfile(file_path) and not os.path.isdir(file_path):
            return FileResponse(file_path)

        html_path = file_path + ".html"
        if os.path.isfile(html_path):
            return FileResponse(html_path, media_type="text/html")

        dir_index = os.path.join(file_path, "index.html")
        if os.path.isfile(dir_index):
            return FileResponse(dir_index, media_type="text/html")

        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

