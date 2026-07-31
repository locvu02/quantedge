from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings


@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class AccountState:
    balance: float
    equity: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    daily_pnl: float = 0.0
    daily_drawdown: float = 0.0
    peak_equity: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    positions: list[Position] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def open_positions_count(self) -> int:
        return len(self.positions)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity == 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity


class RiskManager:
    def __init__(self, initial_balance: float = 10000.0):
        self.account = AccountState(balance=initial_balance, equity=initial_balance, peak_equity=initial_balance)

    def can_open_position(self) -> tuple[bool, str]:
        if self.account.open_positions_count >= settings.max_open_positions:
            return False, f"max positions ({settings.max_open_positions}) reached"

        if self.account.daily_drawdown >= settings.max_daily_drawdown * self.account.balance:
            return False, f"daily drawdown limit ({settings.max_daily_drawdown*100:.0f}%) hit"

        if self.account.drawdown_pct >= settings.max_daily_drawdown:
            return False, f"peak drawdown limit ({settings.max_daily_drawdown*100:.0f}%) hit"

        return True, "ok"

    def calculate_position_size(self, entry: float, stop_loss: float, risk_pct: Optional[float] = None) -> float:
        if risk_pct is None:
            risk_pct = settings.max_risk_per_trade

        risk_amount = self.account.equity * risk_pct
        price_risk = abs(entry - stop_loss)

        if price_risk == 0:
            return 0.0

        quantity = risk_amount / price_risk

        max_notional = self.account.equity * 0.5
        if quantity * entry > max_notional:
            quantity = max_notional / entry

        return quantity

    def validate_risk_reward(self, entry: float, stop_loss: float, take_profit: float) -> tuple[bool, float]:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)

        if risk == 0:
            return False, 0.0

        rr_ratio = reward / risk
        valid = rr_ratio >= settings.min_risk_reward_ratio
        return valid, rr_ratio

    def open_position(self, symbol: str, direction: str, entry: float, stop_loss: float, take_profit: float) -> Optional[Position]:
        can_open, reason = self.can_open_position()
        if not can_open:
            return None

        rr_valid, rr = self.validate_risk_reward(entry, stop_loss, take_profit)
        if not rr_valid:
            return None

        qty = self.calculate_position_size(entry, stop_loss)
        if qty <= 0:
            return None

        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            quantity=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        position.current_price = entry
        self.account.positions.append(position)
        return position

    def close_position(self, position: Position, exit_price: float, note: str = "") -> float:
        if position.direction == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        pnl_pct = pnl / (position.entry_price * position.quantity)

        self.account.realized_pnl += pnl
        self.account.balance += pnl
        self.account.total_trades += 1
        if pnl > 0:
            self.account.winning_trades += 1
        else:
            self.account.losing_trades += 1

        if position in self.account.positions:
            self.account.positions.remove(position)

        return pnl

    def update_market_prices(self, prices: dict[str, float]):
        for pos in self.account.positions:
            if pos.symbol in prices:
                pos.current_price = prices[pos.symbol]
                if pos.direction == "long":
                    pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.quantity

        unrealized = sum(p.unrealized_pnl for p in self.account.positions)
        self.account.unrealized_pnl = unrealized
        self.account.equity = self.account.balance + unrealized
        self.account.daily_pnl = self.account.realized_pnl + unrealized

        if self.account.equity > self.account.peak_equity:
            self.account.peak_equity = self.account.equity

    def check_stops(self) -> list[tuple[Position, str]]:
        triggered = []
        for pos in list(self.account.positions):
            if pos.direction == "long":
                if pos.current_price <= pos.stop_loss:
                    triggered.append((pos, "stop_loss"))
                elif pos.current_price >= pos.take_profit:
                    triggered.append((pos, "take_profit"))
            else:
                if pos.current_price >= pos.stop_loss:
                    triggered.append((pos, "stop_loss"))
                elif pos.current_price <= pos.take_profit:
                    triggered.append((pos, "take_profit"))
        return triggered

    def get_snapshot(self) -> dict:
        return {
            "balance": self.account.balance,
            "equity": self.account.equity,
            "unrealized_pnl": self.account.unrealized_pnl,
            "realized_pnl": self.account.realized_pnl,
            "drawdown": self.account.drawdown_pct,
            "daily_drawdown": self.account.daily_drawdown,
            "win_rate": self.account.win_rate,
            "total_trades": self.account.total_trades,
            "open_positions": self.account.open_positions_count,
        }
