import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import numpy as np
from loguru import logger

from core.models.finbert_sentiment import analyze_finbert

CACHE = {}
CACHE_TTL = 300  # 5 minutes


async def fetch_fear_greed() -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.alternative.me/fng/?limit=1")
            if resp.status_code == 200:
                data = resp.json()["data"][0]
                value = int(data["value"])
                if value <= 25:
                    zone = "extreme_fear"
                elif value <= 45:
                    zone = "fear"
                elif value <= 55:
                    zone = "neutral"
                elif value <= 75:
                    zone = "greed"
                else:
                    zone = "extreme_greed"
                return {"index": value, "zone": zone, "classification": data["value_classification"]}
    except Exception as e:
        logger.warning(f"Fear & Greed failed: {e}")
    return None


async def fetch_crypto_news_real(limit: int = 30) -> list[dict]:
    cache_key = "crypto_news"
    if cache_key in CACHE:
        ts, data = CACHE[cache_key]
        if (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL:
            return data

    articles = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&sortOrder=popular",
            )
            if resp.status_code == 200:
                for a in resp.json().get("Data", [])[:limit]:
                    articles.append({
                        "title": a["title"],
                        "body": a.get("body", ""),
                        "source": a.get("source", ""),
                        "published_at": datetime.fromtimestamp(a["published_on"], tz=timezone.utc),
                        "categories": a.get("categories", ""),
                        "url": a.get("url", ""),
                    })
    except Exception as e:
        logger.warning(f"News fetch failed: {e}")

    CACHE[cache_key] = (datetime.now(timezone.utc), articles)
    return articles


async def fetch_coin_stats(symbol: str) -> Optional[dict]:
    cg_map = {"BTC/USDT": "bitcoin", "ETH/USDT": "ethereum"}
    coin_id = cg_map.get(symbol)
    if not coin_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"},
            )
            if resp.status_code == 200:
                data = resp.json()
                market = data.get("market_data", {})
                return {
                    "price_change_24h": market.get("price_change_percentage_24h", 0),
                    "market_cap_rank": data.get("market_cap_rank"),
                    "sentiment_votes_up": data.get("sentiment_votes_up_percentage", 50),
                    "sentiment_votes_down": data.get("sentiment_votes_down_percentage", 50),
                }
    except Exception:
        pass
    return None


async def generate_news_signal(symbol: str) -> Optional[dict]:
    fear_greed = await fetch_fear_greed()
    articles = await fetch_crypto_news_real(limit=20)
    coin_stats = await fetch_coin_stats(symbol)

    if not articles:
        return None

    keywords_map = {
        "BTC/USDT": ["bitcoin", "btc", "crypto market", "crypto regulation", "bitcoin etf"],
        "ETH/USDT": ["ethereum", "eth", "defi", "layer 2", "smart contract"],
        "XAU/USD": ["gold", "xau", "precious metal", "inflation", "fed"],
        "EUR/USD": ["eur", "euro", "ecb", "dollar", "eurozone"],
    }
    keywords = keywords_map.get(symbol, [symbol.lower()])

    relevant = []
    for article in articles:
        text = (article["title"] + " " + article.get("body", "")).lower()
        if any(kw in text for kw in keywords):
            sentiment = analyze_finbert(article["title"])
            relevant.append({
                "title": article["title"],
                "sentiment": sentiment,
                "source": article["source"],
                "url": article.get("url", ""),
            })

    if len(relevant) < 3:
        return None

    avg_sentiment = float(np.mean([r["sentiment"]["sentiment_score"] for r in relevant]))
    biases = [r["sentiment"]["bias"] for r in relevant]
    dominant_bias = max(set(biases), key=biases.count)

    signal_strength = abs(avg_sentiment)

    if fear_greed:
        fg = fear_greed["index"]
        if fg <= 20 and dominant_bias == "bullish":
            signal_strength *= 1.5
            dominant_bias = "bullish"
        elif fg >= 80 and dominant_bias == "bearish":
            signal_strength *= 1.5
            dominant_bias = "bearish"

    if coin_stats:
        price_24h = coin_stats.get("price_change_24h", 0)
        sen_up = coin_stats.get("sentiment_votes_up", 50)
        if price_24h > 5 and dominant_bias == "bullish":
            signal_strength *= 1.2
        elif price_24h < -5 and dominant_bias == "bearish":
            signal_strength *= 1.2

    return {
        "symbol": symbol,
        "bias": dominant_bias,
        "strength": round(signal_strength, 3),
        "article_count": len(relevant),
        "top_headlines": [r["title"] for r in relevant[:5]],
        "fear_greed": fear_greed,
        "coin_stats": coin_stats,
        "signal": "BUY" if dominant_bias == "bullish" else "SELL" if dominant_bias == "bearish" else "HOLD",
    }


async def news_filter(symbol: str, direction: str) -> bool:
    signal = await generate_news_signal(symbol)
    if not signal:
        return True

    if direction == "long" and signal["bias"] == "bearish" and signal["strength"] > 0.3:
        logger.info(f"📰 NEWS BLOCK: {symbol} LONG blocked by bearish news (strength={signal['strength']:.2f})")
        return False
    if direction == "short" and signal["bias"] == "bullish" and signal["strength"] > 0.3:
        logger.info(f"📰 NEWS BLOCK: {symbol} SHORT blocked by bullish news (strength={signal['strength']:.2f})")
        return False
    return True
