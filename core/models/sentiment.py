from typing import Optional

import httpx
import numpy as np
from loguru import logger

_sia = None


def _get_sia():
    global _sia
    if _sia is not None:
        return _sia
    try:
        import nltk
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment import SentimentIntensityAnalyzer
        _sia = SentimentIntensityAnalyzer()
        return _sia
    except Exception as e:
        logger.warning(f"NLTK/VADER unavailable: {e}")
        return None

ASSET_KEYWORDS = {
    "BTC/USDT": ["bitcoin", "btc", "crypto market cap", "crypto regulation"],
    "ETH/USDT": ["ethereum", "eth", "defi", "smart contract", "layer 2"],
    "XAU/USD": ["gold", "xau", "precious metals", "fed rate", "inflation"],
    "EUR/USD": ["eur", "euro", "ecb", "eurozone", "dollar index"],
}


async def fetch_crypto_news(limit: int = 20) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&sortOrder=popular",
            )
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("Data", [])[:limit]
                return [
                    {"title": a["title"], "body": a.get("body", ""), "source": a.get("source", "")}
                    for a in articles
                ]
    except Exception as e:
        logger.warning(f"Failed to fetch crypto news: {e}")
    return []


def analyze_text(text: str) -> float:
    sia = _get_sia()
    if sia is None:
        return 0.0
    scores = sia.polarity_scores(text)
    return scores["compound"]


def get_sentiment_for_symbol(symbol: str, articles: list[dict]) -> Optional[dict]:
    keywords = ASSET_KEYWORDS.get(symbol, [symbol.lower()])

    relevant = []
    for article in articles:
        text = (article["title"] + " " + article.get("body", "")).lower()
        if any(kw in text for kw in keywords):
            sentiment = analyze_text(article["title"])
            relevant.append(sentiment)

    if not relevant:
        return None

    avg_sentiment = float(np.mean(relevant))
    sentiment_count = len(relevant)

    if avg_sentiment > 0.3:
        bias = "bullish"
    elif avg_sentiment < -0.3:
        bias = "bearish"
    else:
        bias = "neutral"

    return {
        "symbol": symbol,
        "sentiment_score": round(avg_sentiment, 3),
        "bias": bias,
        "article_count": sentiment_count,
    }


async def scan_sentiment(symbols: list[str] = None) -> list[dict]:
    if symbols is None:
        symbols = ["BTC/USDT", "ETH/USDT", "XAU/USD", "EUR/USD"]

    articles = await fetch_crypto_news()
    if not articles:
        return []

    results = []
    for symbol in symbols:
        sentiment = get_sentiment_for_symbol(symbol, articles)
        if sentiment:
            results.append(sentiment)

    return results


def sentiment_filter(symbol: str, direction: str) -> bool:
    articles = fetch_crypto_news(limit=10)
    sentiment = get_sentiment_for_symbol(symbol, articles)
    if not sentiment:
        return True

    if direction == "long" and sentiment["bias"] == "bearish":
        return False
    if direction == "short" and sentiment["bias"] == "bullish":
        return False

    return True
