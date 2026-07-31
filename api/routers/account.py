from fastapi import APIRouter

from api.routers.signals import risk_manager

router = APIRouter()


@router.get("/summary")
async def get_account_summary():
    snapshot = risk_manager.get_snapshot()
    positions = [
        {
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_price": p.entry_price,
            "current_price": p.current_price,
            "quantity": round(p.quantity, 6),
            "unrealized_pnl": round(p.unrealized_pnl, 2),
        }
        for p in risk_manager.account.positions
    ]
    return {**snapshot, "positions": positions}


@router.get("/positions")
async def get_positions():
    return {
        "positions": [
            {
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "quantity": round(p.quantity, 6),
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
            }
            for p in risk_manager.account.positions
        ]
    }
