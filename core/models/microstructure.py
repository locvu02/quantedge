import asyncio
from datetime import datetime, timezone
from typing import Optional

import ccxt.pro as ccxtpro
import numpy as np
from loguru import logger


class MarketMicrostructure:
    def __init__(self):
        self.orderbook_imbalance: dict[str, float] = {}
        self.whale_alerts: list[dict] = []
        self.last_update: dict[str, datetime] = {}

    async def fetch_orderbook_imbalance(self, symbol: str, depth: int = 50) -> Optional[dict]:
        try:
            exchange = ccxtpro.binance({"enableRateLimit": True})
            ob = await exchange.fetch_order_book(symbol, limit=depth)

            bids_vol = sum(b[1] for b in ob["bids"][:depth])
            asks_vol = sum(a[1] for a in ob["asks"][:depth])
            total_vol = bids_vol + asks_vol

            if total_vol == 0:
                await exchange.close()
                return None

            imbalance = (bids_vol - asks_vol) / total_vol
            spread = (ob["asks"][0][0] - ob["bids"][0][0]) / ob["bids"][0][0] * 100 if ob["bids"] and ob["asks"] else 0

            bid_wall_idx = np.argmax([b[1] for b in ob["bids"][:10]])
            ask_wall_idx = np.argmax([a[1] for a in ob["asks"][:10]])
            bid_wall_price = ob["bids"][bid_wall_idx][0] if ob["bids"] else 0
            ask_wall_price = ob["asks"][ask_wall_idx][0] if ob["asks"] else 0

            await exchange.close()

            self.orderbook_imbalance[symbol] = imbalance
            self.last_update[symbol] = datetime.now(timezone.utc)

            return {
                "symbol": symbol,
                "imbalance": round(imbalance, 4),
                "spread_pct": round(spread, 4),
                "bid_wall": round(bid_wall_price, 2),
                "ask_wall": round(ask_wall_price, 2),
                "bids_total": round(bids_vol, 2),
                "asks_total": round(asks_vol, 2),
                "signal": self._interpret_imbalance(imbalance),
            }
        except Exception as e:
            logger.warning(f"Orderbook fetch failed for {symbol}: {e}")
            return None

    def _interpret_imbalance(self, imbalance: float) -> str:
        if imbalance > 0.3:
            return "STRONG_BUY"
        elif imbalance > 0.1:
            return "BUY"
        elif imbalance < -0.3:
            return "STRONG_SELL"
        elif imbalance < -0.1:
            return "SELL"
        return "NEUTRAL"

    async def fetch_liquidation_data(self, symbol: str) -> Optional[dict]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://open-api-v3.coinglass.com/api/futures/liquidation/v2",
                    headers={"coinglassSecret": "free"},
                    params={"symbol": symbol.replace("/USDT", ""), "timeType": "1"},
                )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    latest = data[-1]
                    return {
                        "symbol": symbol,
                        "long_liquidations": latest.get("longVolUsd", 0),
                        "short_liquidations": latest.get("shortVolUsd", 0),
                        "total_liquidations": latest.get("volUsd", 0),
                        "buy_vol": latest.get("buyVolUsd", 0),
                        "sell_vol": latest.get("sellVolUsd", 0),
                    }
        except Exception:
            pass
        return None

    async def get_micro_signal(self, symbol: str) -> Optional[dict]:
        ob_data = await self.fetch_orderbook_imbalance(symbol, depth=30)
        liq_data = await self.fetch_liquidation_data(symbol)

        if not ob_data:
            return None

        signal_strength = abs(ob_data["imbalance"])
        direction = "long" if ob_data["imbalance"] > 0 else "short"

        if liq_data and liq_data.get("total_liquidations", 0) > 10_000_000:
            if liq_data.get("long_liquidations", 0) > liq_data.get("short_liquidations", 0) * 2:
                direction = "short"
                signal_strength = min(1.0, signal_strength + 0.2)
            elif liq_data.get("short_liquidations", 0) > liq_data.get("long_liquidations", 0) * 2:
                direction = "long"
                signal_strength = min(1.0, signal_strength + 0.2)

        if signal_strength < 0.15:
            return None

        return {
            "symbol": symbol,
            "direction": direction,
            "confidence": round(signal_strength, 3),
            "orderbook": ob_data,
            "liquidations": liq_data,
        }


microstructure = MarketMicrostructure()
