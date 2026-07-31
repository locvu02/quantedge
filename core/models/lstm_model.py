import os
import pickle
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from loguru import logger

from core.engine.indicators import compute_all_indicators

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models_saved")
os.makedirs(MODEL_DIR, exist_ok=True)

SEQ_LEN = 50
FEATURE_COLS = [
    "open", "high", "low", "close", "volume",
    "ema_9", "ema_21", "ema_50", "ema_200",
    "rsi_14", "adx_14", "atr_14",
    "bb_position", "bb_width",
    "macd_hist", "returns", "volatility_20",
    "volume_ratio",
]


class LSTMPredictor(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=dropout)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        last_out = lstm_out[:, -1, :]
        return self.fc(last_out)


def create_sequences(df: pd.DataFrame, seq_len: int = SEQ_LEN) -> Tuple[np.ndarray, np.ndarray]:
    df = compute_all_indicators(df)
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)
    df["returns"] = df["close"].pct_change()
    df["volatility_20"] = df["returns"].rolling(20).std()
    df["volume_ratio"] = df["volume"] / df["volume_sma_20"].replace(0, np.nan)

    available = [c for c in FEATURE_COLS if c in df.columns]
    df = df[available].dropna()

    X, y = [], []
    future_close = df["close"].shift(-4)
    y_vals = (future_close > df["close"]).astype(int)

    for i in range(len(df) - seq_len - 4):
        X.append(df.iloc[i : i + seq_len].values.astype(np.float32))
        y.append(y_vals.iloc[i + seq_len])

    if not X:
        return np.array([]), np.array([])

    X_np = np.stack(X)
    y_np = np.array(y, dtype=np.float32).reshape(-1, 1)

    nan_mask = ~np.isnan(X_np).any(axis=(1, 2)) & ~np.isnan(y_np).any(axis=1)
    return X_np[nan_mask], y_np[nan_mask]


def train_lstm(symbol: str, df: pd.DataFrame, epochs: int = 30) -> Optional[LSTMPredictor]:
    X, y = create_sequences(df)
    if len(X) < 200:
        logger.warning(f"{symbol}: not enough sequences ({len(X)})")
        return None

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    train_ds = TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    test_ds = TensorDataset(torch.tensor(X_test), torch.tensor(y_test))
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)

    input_dim = X.shape[2]
    model = LSTMPredictor(input_dim, hidden_dim=128, num_layers=2, dropout=0.3)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.BCEWithLogitsLoss()

    best_acc = 0
    for epoch in range(epochs):
        model.train()
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            output = model(batch_X)
            loss = criterion(output, batch_y)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            pred = (torch.sigmoid(model(torch.tensor(X_test))) > 0.5).float()
            acc = (pred == torch.tensor(y_test)).float().mean().item()
            if acc > best_acc:
                best_acc = acc
                torch.save(model.state_dict(), os.path.join(MODEL_DIR, f"lstm_{symbol.replace('/', '_')}.pt"))

    logger.info(f"{symbol}: LSTM trained | seqs={len(X)} acc={best_acc:.3f}")
    return model


def load_lstm(symbol: str) -> Optional[Tuple[LSTMPredictor, int]]:
    path = os.path.join(MODEL_DIR, f"lstm_{symbol.replace('/', '_')}.pt")
    if not os.path.exists(path):
        return None
    df_sample = None
    from core.data.pipeline import load_ohlcv_from_db
    df_sample = load_ohlcv_from_db(symbol, "1h", limit=100)
    if df_sample.empty:
        return None
    X, _ = create_sequences(df_sample)
    if len(X) == 0:
        return None
    input_dim = X.shape[2]
    model = LSTMPredictor(input_dim, hidden_dim=128, num_layers=2, dropout=0.3)
    model.load_state_dict(torch.load(path, weights_only=True))
    model.eval()
    return model, input_dim


def predict_lstm(model: LSTMPredictor, df: pd.DataFrame) -> Optional[dict]:
    X, _ = create_sequences(df)
    if len(X) == 0:
        return None
    last_seq = torch.tensor(X[-1:]).float()
    with torch.no_grad():
        logit = model(last_seq).item()
        prob = float(torch.sigmoid(torch.tensor(logit)))
    return {
        "probability": round(prob, 4),
        "direction": "long" if prob > 0.5 else "short",
        "confidence": round(max(prob, 1 - prob), 3),
    }
