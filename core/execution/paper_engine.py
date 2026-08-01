import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import settings
from core.data.pipeline import load_ohlcv_from_db, fetch_ohlcv
from core.data.database import SessionLocal
from core.data.models import OHLCV, Trade as TradeModel, Signal as SignalModel, AccountSnapshot
from core.engine.strategies import generate_signals, Direction
from core.engine.signals import SignalEngine
from core.risk.manager import RiskManager
from core.models.trainer import load_model, predict as ml_predict

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XAU/USD", "XAG/USD", "USD/JPY"]
TIMEFRAMES = ["1h", "4h"]


class PaperTradingEngine:
    def __init__(self):
        self.risk = RiskManager(initial_balance=10000.0)
        self.signal_engine = SignalEngine(self.risk)
        self.running = False
        self.last_candle: dict[str, datetime] = {}

    async def start(self):
        self.running = True
        logger.info("Paper trading engine started")
        while self.running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Tick error: {e}")
            await asyncio.sleep(60)

    def stop(self):
        self.running = False
        logger.info("Paper trading engine stopped")

    async def _tick(self):
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                await self._process_symbol(symbol, tf)

    async def _process_symbol(self, symbol: str, tf: str):
        key = f"{symbol}_{tf}"
        df = load_ohlcv_from_db(symbol, tf)

        if df.empty:
            return

        latest_ts = df.index[-1]
        if key in self.last_candle and self.last_candle[key] >= latest_ts:
            return
        self.last_candle[key] = latest_ts

        signal = self.signal_engine.analyze(df, symbol)
        if not signal:
            return

        loaded = load_model(symbol)
        if loaded:
            model, meta, scaler = loaded
            ml_pred = ml_predict(model, df, scaler)
            if ml_pred and ml_pred["direction"] != signal["direction"]:
                return
            if ml_pred and ml_pred["confidence"] < 0.55:
                return

        # Sentiment filter
        try:
            from core.models.sentiment import fetch_crypto_news, get_sentiment_for_symbol
            articles = await fetch_crypto_news(limit=10)
            sentiment = get_sentiment_for_symbol(symbol, articles)
            if sentiment and sentiment["bias"] == "bearish" and direction == "long":
                return
            if sentiment and sentiment["bias"] == "bullish" and direction == "short":
                return
        except Exception:
            pass

        # Real-time news filter
        try:
            from core.models.news_crawler import news_filter
            if not await news_filter(symbol, direction):
                return
        except Exception:
            pass

        # Market microstructure filter
        try:
            from core.models.microstructure import microstructure as ms
            micro = await ms.get_micro_signal(symbol)
            if micro and micro["direction"] != direction and micro["confidence"] > 0.3:
                return
        except Exception:
            pass

        # Whale tracking filter
        try:
            from core.models.whale_tracker import get_whale_alert
            whale = await get_whale_alert(symbol)
            if whale and whale["direction"] != "neutral" and whale["direction"] != direction and whale["whale_signal"] != 0 and abs(whale["whale_signal"]) >= 2:
                logger.info(f"🐋 WHALE BLOCK: {symbol} {direction} blocked by whale alert ({whale['alerts']})")
                return
        except Exception:
            pass

        direction = signal["direction"]
        entry = signal["entry_price"]
        sl = signal["stop_loss"]
        tp = signal["take_profit"]

        pos = self.risk.open_position(symbol, direction, entry, sl, tp)
        if pos:
            logger.info(
                f"PAPER TRADE: {symbol} {direction.upper()} "
                f"entry={entry:.2f} sl={sl:.2f} tp={tp:.2f} "
                f"conf={signal['confidence']:.2f}"
            )
            self._save_trade_to_db(pos, signal)

        self._check_and_update_positions()

    def _check_and_update_positions(self):
        prices = {}
        for pos in self.risk.account.positions:
            df = load_ohlcv_from_db(pos.symbol, "1h", limit=1)
            if not df.empty:
                prices[pos.symbol] = float(df.iloc[-1]["close"])

        if prices:
            self.risk.update_market_prices(prices)

        stopped = self.risk.check_stops()
        for pos, reason in stopped:
            exit_price = pos.stop_loss if reason == "stop_loss" else pos.take_profit
            pnl = self.risk.close_position(pos, exit_price, reason)
            logger.info(
                f"CLOSED: {pos.symbol} {pos.direction} "
                f"pnl=${pnl:.2f} reason={reason}"
            )
            self._update_trade_in_db(pos, exit_price, pnl, reason)

        self._save_snapshot()

    def _save_trade_to_db(self, position, signal: dict):
        db = SessionLocal()
        try:
            trade = TradeModel(
                symbol=position.symbol,
                direction=position.direction,
                entry_time=position.entry_time,
                entry_price=position.entry_price,
                quantity=position.quantity,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                status="open",
            )
            db.add(trade)

            sig = SignalModel(
                symbol=signal["symbol"],
                timestamp=signal["timestamp"],
                strategy="ensemble",
                direction=signal["direction"],
                confidence=signal["confidence"],
                entry_price=signal["entry_price"],
                stop_loss=signal["stop_loss"],
                take_profit=signal["take_profit"],
                features={"strategies": signal.get("strategies", [])},
            )
            db.add(sig)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save trade: {e}")
        finally:
            db.close()

    def _update_trade_in_db(self, position, exit_price: float, pnl: float, reason: str):
        db = SessionLocal()
        try:
            from sqlalchemy import select
            stmt = select(TradeModel).where(
                TradeModel.symbol == position.symbol,
                TradeModel.status == "open",
            ).order_by(TradeModel.entry_time.desc()).limit(1)
            trade = db.execute(stmt).scalar_one_or_none()
            if trade:
                trade.exit_time = datetime.now(timezone.utc)
                trade.exit_price = exit_price
                trade.pnl = pnl
                trade.pnl_pct = pnl / (trade.entry_price * trade.quantity) if trade.entry_price else 0
                trade.status = "closed"
                trade.note = reason
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update trade: {e}")
        finally:
            db.close()

    def _save_snapshot(self):
        db = SessionLocal()
        try:
            snap = AccountSnapshot(
                timestamp=datetime.now(timezone.utc),
                balance=self.risk.account.balance,
                equity=self.risk.account.equity,
                unrealized_pnl=self.risk.account.unrealized_pnl,
                realized_pnl=self.risk.account.realized_pnl,
                drawdown=self.risk.account.drawdown_pct,
                win_rate=self.risk.account.win_rate,
                total_trades=self.risk.account.total_trades,
            )
            db.add(snap)
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "account": self.risk.get_snapshot(),
            "positions": [
                {
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for p in self.risk.account.positions
            ],
        }


paper_engine = PaperTradingEngine()
