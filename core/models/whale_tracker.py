import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
import numpy as np
from loguru import logger

WHALE_CACHE: dict = {}
WHALE_TTL = 60


def _is_fresh(key: str) -> bool:
    if key not in WHALE_CACHE:
        return False
    ts, _ = WHALE_CACHE[key]
    return (datetime.now(timezone.utc) - ts).total_seconds() < WHALE_TTL


async def fetch_btc_whales() -> Optional[dict]:
    if _is_fresh("btc_whales"):
        return WHALE_CACHE["btc_whales"][1]

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get("https://blockchain.info/unconfirmed-transactions?format=json")
            if resp.status_code != 200:
                return None
            txs = resp.json().get("txs", [])

        whales = []
        total_btc = 0.0
        for tx in txs[:50]:
            btc_val = sum(o["value"] for o in tx.get("out", [])) / 1e8
            if btc_val > 50:
                whales.append({
                    "hash": tx["hash"][:12],
                    "btc": round(btc_val, 2),
                    "time": datetime.fromtimestamp(tx["time"], tz=timezone.utc),
                })
                total_btc += btc_val

        result = {
            "symbol": "BTC/USDT",
            "whale_count": len(whales),
            "total_btc_moved": round(total_btc, 1),
            "alert": "WHALE_ACTIVE" if len(whales) > 3 else ("NORMAL" if len(whales) > 0 else "QUIET"),
            "whales": whales[:5],
        }
        WHALE_CACHE["btc_whales"] = (datetime.now(timezone.utc), result)
        return result
    except Exception as e:
        logger.warning(f"BTC whale fetch failed: {e}")
    return None


async def fetch_eth_whales() -> Optional[dict]:
    if _is_fresh("eth_whales"):
        return WHALE_CACHE["eth_whales"][1]

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": "0x28C6c06298d514Db089934071355E5743bf21d60",
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": 20,
                    "sort": "desc",
                },
            )
            if resp.status_code != 200:
                return None
            txs = resp.json().get("result", [])

        whales = []
        for tx in txs[:20]:
            eth_val = float(tx["value"]) / 1e18
            if eth_val > 500:
                whales.append({
                    "hash": tx["hash"][:12],
                    "eth": round(eth_val, 2),
                    "from": tx["from"][:8],
                    "to": tx["to"][:8] if tx["to"] else "contract",
                })

        result = {
            "symbol": "ETH/USDT",
            "whale_count": len(whales),
            "alert": "WHALE_ACTIVE" if len(whales) > 2 else "NORMAL",
            "whales": whales[:5],
        }
        WHALE_CACHE["eth_whales"] = (datetime.now(timezone.utc), result)
        return result
    except Exception as e:
        logger.warning(f"ETH whale fetch failed: {e}")
    return None


async def fetch_exchange_flows() -> Optional[dict]:
    if _is_fresh("exchange_flows"):
        return WHALE_CACHE["exchange_flows"][1]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.whale-alert.io/v1/transactions",
                params={"api_key": "free", "min_value": 1000000, "limit": 10},
            )
            if resp.status_code != 200:
                return None
            txs = resp.json().get("transactions", [])

        inflows = []
        outflows = []
        for tx in txs:
            entry = {
                "amount": tx.get("amount_usd", 0),
                "symbol": tx.get("symbol", ""),
                "from": tx.get("from", {}).get("owner_type", "unknown"),
                "to": tx.get("to", {}).get("owner_type", "unknown"),
            }
            if entry["to"] == "exchange":
                inflows.append(entry)
            elif entry["from"] == "exchange":
                outflows.append(entry)

        total_in = sum(i["amount"] for i in inflows)
        total_out = sum(o["amount"] for o in outflows)

        net_flow = total_in - total_out

        if net_flow > 10_000_000:
            signal = "BULLISH"
        elif net_flow < -10_000_000:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        result = {
            "inflows_usd": round(total_in),
            "outflows_usd": round(total_out),
            "net_flow_usd": round(net_flow),
            "inflow_count": len(inflows),
            "outflow_count": len(outflows),
            "signal": signal,
        }
        WHALE_CACHE["exchange_flows"] = (datetime.now(timezone.utc), result)
        return result
    except Exception:
        return None


async def detect_volume_anomaly(symbol: str) -> Optional[dict]:
    from core.data.pipeline import load_ohlcv_from_db

    df = load_ohlcv_from_db(symbol, "1h", limit=50)
    if len(df) < 20:
        return None

    recent_vol = df["volume"].iloc[-5:].mean()
    baseline_vol = df["volume"].iloc[:30].mean()

    if baseline_vol == 0:
        return None

    ratio = recent_vol / baseline_vol

    if ratio > 2.5:
        alert = "VOLUME_SURGE"
        direction = "bullish" if df["close"].iloc[-1] > df["close"].iloc[-5] else "bearish"
    elif ratio < 0.3:
        alert = "VOLUME_DROUGHT"
        direction = "neutral"
    else:
        return None

    return {
        "symbol": symbol,
        "volume_ratio": round(ratio, 1),
        "alert": alert,
        "direction": direction,
        "recent_vol": round(recent_vol, 1),
        "baseline_vol": round(baseline_vol, 1),
    }


async def get_whale_alert(symbol: str) -> Optional[dict]:
    whales = None
    if symbol == "BTC/USDT":
        whales = await fetch_btc_whales()
    elif symbol == "ETH/USDT":
        whales = await fetch_eth_whales()

    flows = await fetch_exchange_flows()
    vol_anomaly = await detect_volume_anomaly(symbol)

    alerts = []
    whale_signal = 0

    if whales and whales.get("alert") == "WHALE_ACTIVE":
        alerts.append(f"{whales['whale_count']} whale tx detected")
        whale_signal += 1

    if flows:
        alerts.append(f"Net flow: ${flows['net_flow_usd']:,} ({flows['signal']})")
        if flows["signal"] == "BULLISH":
            whale_signal += 1
        elif flows["signal"] == "BEARISH":
            whale_signal -= 1

    if vol_anomaly:
        alerts.append(f"Volume {vol_anomaly['alert']} ({vol_anomaly['volume_ratio']}x)")
        if vol_anomaly["direction"] == "bullish":
            whale_signal += 1
        elif vol_anomaly["direction"] == "bearish":
            whale_signal -= 1

    if not alerts:
        return None

    if whale_signal > 0:
        direction = "long"
    elif whale_signal < 0:
        direction = "short"
    else:
        direction = "neutral"

    return {
        "symbol": symbol,
        "alerts": alerts,
        "alert_count": len(alerts),
        "whale_signal": whale_signal,
        "direction": direction,
        "whales": whales,
        "exchange_flows": flows,
        "volume_anomaly": vol_anomaly,
    }
