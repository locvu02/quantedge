import numpy as np
import pandas as pd
from typing import Optional

from core.data.pipeline import load_ohlcv_from_db


def compute_correlation(sym1: str, sym2: str, lookback: int = 100) -> float:
    df1 = load_ohlcv_from_db(sym1, "1h", limit=lookback)
    df2 = load_ohlcv_from_db(sym2, "1h", limit=lookback)

    if df1.empty or df2.empty:
        return 0.0

    common_idx = df1.index.intersection(df2.index)
    if len(common_idx) < 20:
        return 0.0

    ret1 = df1.loc[common_idx, "close"].pct_change().dropna()
    ret2 = df2.loc[common_idx, "close"].pct_change().dropna()
    common = ret1.index.intersection(ret2.index)

    if len(common) < 20:
        return 0.0

    return float(ret1.loc[common].corr(ret2.loc[common]))


class PortfolioRiskManager:
    def __init__(self, max_total_exposure: float = 0.08):
        self.max_total_exposure = max_total_exposure
        self.current_exposure: dict[str, float] = {}
        self.correlation_matrix: dict[tuple, float] = {}

    def update_correlations(self):
        pairs = [
            ("BTC/USDT", "ETH/USDT"),
            ("XAU/USD", "XAG/USD"),
            ("BTC/USDT", "SOL/USDT"),
        ]
        for a, b in pairs:
            self.correlation_matrix[(a, b)] = compute_correlation(a, b)

    def can_open_position(self, symbol: str, direction: str, proposed_exposure: float,
                          open_positions: list[dict]) -> tuple[bool, str, float]:
        total_current = sum(p.get("exposure_pct", 0) for p in open_positions)

        if total_current + proposed_exposure > self.max_total_exposure:
            return False, f"max total exposure {self.max_total_exposure*100:.0f}% exceeded", 0.0

        exposure_penalty = 1.0
        for pos in open_positions:
            pair = tuple(sorted([symbol, pos["symbol"]]))
            corr = self.correlation_matrix.get(pair, 0)
            if abs(corr) > 0.7 and direction == pos["direction"]:
                exposure_penalty *= 0.5
            elif abs(corr) > 0.7 and direction != pos["direction"]:
                exposure_penalty *= 1.2

        adjusted_exposure = proposed_exposure * exposure_penalty

        if total_current + adjusted_exposure > self.max_total_exposure:
            adjusted_exposure = self.max_total_exposure - total_current
            if adjusted_exposure <= 0:
                return False, "no capacity", 0.0

        return True, "ok", adjusted_exposure

    def risk_heatmap(self, symbols: list[str]) -> dict:
        heatmap = {}
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                pair = tuple(sorted([s1, s2]))
                if pair in self.correlation_matrix:
                    heatmap[f"{s1}↔{s2}"] = round(self.correlation_matrix[pair], 2)
        return heatmap
