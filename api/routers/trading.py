import asyncio

from fastapi import APIRouter
from loguru import logger

from core.execution.paper_engine import paper_engine
from core.data.database import init_db

router = APIRouter()


@router.get("/status")
async def get_paper_status():
    return paper_engine.get_status()


@router.post("/start")
async def start_paper_trading():
    if paper_engine.running:
        return {"status": "already_running"}
    init_db()
    asyncio.create_task(paper_engine.start())
    logger.info("Paper trading started via API")
    return {"status": "started"}


@router.post("/stop")
async def stop_paper_trading():
    paper_engine.stop()
    return {"status": "stopped"}
