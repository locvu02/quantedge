import os
from typing import Optional

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from loguru import logger

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models_saved")
os.makedirs(MODEL_DIR, exist_ok=True)


class TradingEnv(gym.Env):
    def __init__(self, df, initial_balance=10000.0):
        super().__init__()
        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.current_step = 50
        self.balance = initial_balance
        self.position = 0
        self.entry_price = 0

        self.action_space = spaces.Discrete(5)

        obs_dim = 12
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)

    def _get_obs(self):
        row = self.df.iloc[self.current_step]
        obs = np.array([
            row.get("close", 0), row.get("rsi_14", 50) / 100,
            row.get("adx_14", 15) / 100, row.get("atr_14", 0) / row.get("close", 1),
            row.get("ema_9", 0) / row.get("close", 1) - 1 if row.get("close", 0) > 0 else 0,
            row.get("ema_21", 0) / row.get("close", 1) - 1 if row.get("close", 0) > 0 else 0,
            row.get("macd_hist", 0) / row.get("close", 1) if row.get("close", 0) > 0 else 0,
            row.get("bb_position", 0.5), row.get("returns", 0),
            self.position, self.balance / self.initial_balance,
        ], dtype=np.float32)
        return np.nan_to_num(obs, 0)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 50
        self.balance = self.initial_balance
        self.position = 0
        return self._get_obs(), {}

    def step(self, action):
        row = self.df.iloc[self.current_step]
        price = float(row["close"])
        reward = 0

        if action == 0:
            self.position = 1
            self.entry_price = price
        elif action == 1:
            self.position = -1
            self.entry_price = price
        elif action >= 2:
            if self.position != 0:
                multiplier = [0.5, 1.0, 1.5][action - 2]
                pnl = (price - self.entry_price) * self.position * multiplier
                reward = np.tanh(pnl / 100.0)
                self.balance += pnl
                self.position = 0

        self.current_step += 1
        terminated = self.current_step >= len(self.df) - 1
        truncated = self.balance <= self.initial_balance * 0.7

        return self._get_obs(), reward, terminated, truncated, {}


def train_ppo(symbol: str, epochs: int = 5):
    try:
        from stable_baselines3 import PPO
    except ImportError:
        logger.warning("stable-baselines3 not installed")
        return None

    from core.data.pipeline import load_ohlcv_from_db
    from core.engine.indicators import compute_all_indicators

    df = load_ohlcv_from_db(symbol, "1h")
    if len(df) < 500:
        return None

    df = compute_all_indicators(df)
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["returns"] = df["close"].pct_change()
    df = df.dropna()

    env = TradingEnv(df)
    model = PPO("MlpPolicy", env, verbose=0, learning_rate=0.0003, n_steps=2048)

    for epoch in range(epochs):
        model.learn(total_timesteps=min(10000, len(df) - 100), reset_num_timesteps=(epoch == 0))
        logger.info(f"PPO epoch {epoch + 1}/{epochs} for {symbol}")

    path = os.path.join(MODEL_DIR, f"ppo_{symbol.replace('/', '_')}.zip")
    model.save(path)
    logger.info(f"PPO agent saved: {path}")
    return model


def load_ppo(symbol: str):
    try:
        from stable_baselines3 import PPO
    except ImportError:
        return None
    path = os.path.join(MODEL_DIR, f"ppo_{symbol.replace('/', '_')}.zip")
    if not os.path.exists(path):
        return None
    return PPO.load(path)
