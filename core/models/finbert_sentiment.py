from typing import Optional

import numpy as np
import torch
from loguru import logger

_MODEL = None
_TOKENIZER = None


def _load_finbert():
    global _MODEL, _TOKENIZER
    if _MODEL is not None:
        return _MODEL, _TOKENIZER
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        _TOKENIZER = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        _MODEL = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        logger.info("FinBERT loaded successfully")
        return _MODEL, _TOKENIZER
    except Exception as e:
        logger.warning(f"FinBERT load failed: {e}")
        return None, None


def analyze_finbert(text: str) -> dict:
    model, tokenizer = _load_finbert()
    if model is None:
        return {"sentiment": 0.0, "bias": "neutral", "confidence": 0.0}

    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)[0]

    neg, neu, pos = probs.tolist()

    if pos > neg and pos > neu:
        bias = "bullish"
        score = pos
    elif neg > pos and neg > neu:
        bias = "bearish"
        score = -neg
    else:
        bias = "neutral"
        score = 0.0

    return {
        "sentiment_score": round(float(score), 3),
        "bias": bias,
        "confidence": round(float(max(probs)), 3),
    }


def batch_sentiment(texts: list[str]) -> list[dict]:
    return [analyze_finbert(t) for t in texts]


def get_market_sentiment(symbol: str) -> dict:
    headlines = {
        "BTC/USDT": [
            "Bitcoin price surges amid institutional adoption",
            "Crypto market faces regulatory pressure",
            "Bitcoin ETF inflows reach new record",
            "Federal Reserve hints at rate cuts boosting risk assets",
        ],
        "ETH/USDT": [
            "Ethereum DeFi ecosystem reaches new TVL highs",
            "ETH layer 2 solutions gain mainstream adoption",
            "Smart contract platforms compete for market share",
        ],
        "XAU/USD": [
            "Gold prices rise on geopolitical tensions",
            "Central banks increase gold reserves amid uncertainty",
            "Inflation fears drive precious metals demand",
        ],
    }

    texts = headlines.get(symbol, [f"{symbol} market outlook analysis"])
    sentiments = batch_sentiment(texts)

    avg_score = float(np.mean([s["sentiment_score"] for s in sentiments]))
    biases = [s["bias"] for s in sentiments]
    dominant = max(set(biases), key=biases.count)

    return {
        "symbol": symbol,
        "sentiment_score": round(avg_score, 3),
        "bias": dominant,
        "article_count": len(texts),
        "breakdown": sentiments,
    }
