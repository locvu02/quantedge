import pickle
import os
from typing import Optional, Tuple

import numpy as np
from loguru import logger

from core.engine.regime import MarketRegime

RL_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models_saved")
os.makedirs(RL_MODEL_DIR, exist_ok=True)


class QLearningAgent:
    def __init__(self, epsilon: float = 0.3, alpha: float = 0.1, gamma: float = 0.95):
        self.q_table: dict[tuple, np.ndarray] = {}
        self.epsilon = epsilon
        self.alpha = alpha
        self.gamma = gamma
        self.actions = [0, 0.5, 1.0, 1.5, 2.0]
        self.last_state = None
        self.last_action_idx = None

    def _discretize_state(
        self,
        regime: MarketRegime,
        win_streak: int,
        volatility_pct: float,
        confidence: float,
    ) -> tuple:
        regime_idx = {MarketRegime.TRENDING: 0, MarketRegime.RANGING: 1,
                       MarketRegime.VOLATILE: 2, MarketRegime.QUIET: 3}[regime]

        if win_streak >= 3:
            streak_idx = 2
        elif win_streak <= -3:
            streak_idx = 0
        else:
            streak_idx = 1

        if volatility_pct > 0.025:
            vol_idx = 2
        elif volatility_pct > 0.012:
            vol_idx = 1
        else:
            vol_idx = 0

        if confidence > 0.7:
            conf_idx = 2
        elif confidence > 0.55:
            conf_idx = 1
        else:
            conf_idx = 0

        return (regime_idx, streak_idx, vol_idx, conf_idx)

    def get_action(self, state: tuple) -> Tuple[float, int]:
        if state not in self.q_table:
            self.q_table[state] = np.zeros(len(self.actions))

        if np.random.random() < self.epsilon:
            action_idx = np.random.randint(len(self.actions))
        else:
            action_idx = int(np.argmax(self.q_table[state]))

        self.last_state = state
        self.last_action_idx = action_idx
        return self.actions[action_idx], action_idx

    def learn(self, reward: float, next_state: tuple):
        if self.last_state is None or self.last_action_idx is None:
            return

        current_q = self.q_table[self.last_state][self.last_action_idx]

        if next_state not in self.q_table:
            self.q_table[next_state] = np.zeros(len(self.actions))

        max_future_q = np.max(self.q_table[next_state])
        new_q = current_q + self.alpha * (reward + self.gamma * max_future_q - current_q)
        self.q_table[self.last_state][self.last_action_idx] = new_q

        self.last_state = None
        self.last_action_idx = None

    def save(self, symbol: str):
        path = os.path.join(RL_MODEL_DIR, f"rl_agent_{symbol.replace('/', '_')}.pkl")
        with open(path, "wb") as f:
            pickle.dump({"q_table": self.q_table, "actions": self.actions}, f)
        logger.info(f"RL agent saved: {path}")

    def load(self, symbol: str) -> bool:
        path = os.path.join(RL_MODEL_DIR, f"rl_agent_{symbol.replace('/', '_')}.pkl")
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.q_table = data["q_table"]
        self.actions = data["actions"]
        return True

    def get_stats(self) -> dict:
        total_states = len(self.q_table)
        avg_q = np.mean([np.mean(v) for v in self.q_table.values()]) if self.q_table else 0
        best_actions = sum(1 for v in self.q_table.values() if np.argmax(v) >= 2) if self.q_table else 0
        return {
            "states_explored": total_states,
            "avg_q_value": round(float(avg_q), 4),
            "aggressive_states": best_actions,
        }
