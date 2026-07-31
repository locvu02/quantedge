from fastapi import APIRouter

from core.models.sentiment import scan_sentiment

router = APIRouter()


@router.get("/scan")
async def scan():
    results = await scan_sentiment()
    return {"results": results}
