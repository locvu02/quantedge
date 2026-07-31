import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score
from sklearn.preprocessing import StandardScaler

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models_saved")
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLS = [
    "ema_9", "ema_21", "ema_50", "ema_200",
    "sma_20", "sma_50",
    "rsi_14",
    "bb_upper", "bb_mid", "bb_lower",
    "atr_14", "adx_14",
    "macd", "macd_signal", "macd_hist",
    "volume_sma_20",
    "returns", "volatility_20",
    "close_to_ema9", "close_to_ema21", "close_to_ema50",
    "bb_position", "bb_width",
    "rsi_momentum",
    "volume_ratio",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    from core.engine.indicators import compute_all_indicators

    df = compute_all_indicators(df)

    df["close_to_ema9"] = (df["close"] - df["ema_9"]) / df["ema_9"].replace(0, np.nan)
    df["close_to_ema21"] = (df["close"] - df["ema_21"]) / df["ema_21"].replace(0, np.nan)
    df["close_to_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"].replace(0, np.nan)

    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)

    df["rsi_momentum"] = df["rsi_14"].diff(3)

    df["volume_ratio"] = df["volume"] / df["volume_sma_20"].replace(0, np.nan)

    return df


def create_labels(df: pd.DataFrame, forward_periods: int = 4, threshold_pct: float = 0.005) -> pd.Series:
    future_close = df["close"].shift(-forward_periods)
    future_return = (future_close - df["close"]) / df["close"]
    return (future_return > threshold_pct).astype(int)


def prepare_data(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    df = engineer_features(df)
    labels = create_labels(df)

    df = df.dropna()
    valid_idx = labels.loc[df.index].dropna().index
    df = df.loc[valid_idx]
    labels = labels.loc[valid_idx]

    X = df[FEATURE_COLS].values.astype(np.float32)
    y = labels.values.astype(np.int32)

    return X, y, df.index


def train_model(
    symbol: str,
    df: pd.DataFrame,
    test_split: float = 0.2,
) -> Optional[HistGradientBoostingClassifier]:
    try:
        X, y, _ = prepare_data(df)
        if len(X) < 200:
            logger.warning(f"{symbol}: not enough data for training ({len(X)} rows)")
            return None
    except Exception as e:
        logger.error(f"{symbol}: feature engineering failed: {e}")
        return None

    split_idx = int(len(X) * (1 - test_split))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    model = HistGradientBoostingClassifier(
        max_iter=200,
        max_depth=5,
        learning_rate=0.05,
        max_leaf_nodes=31,
        early_stopping=True,
        validation_fraction=0.2,
        random_state=42,
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)

    logger.info(
        f"{symbol}: trained HGB | samples={len(X)} acc={acc:.3f} prec={prec:.3f} "
        f"pos_rate={sum(y)/len(y):.2f}"
    )

    path = os.path.join(MODEL_DIR, f"model_{symbol.replace('/', '_')}.joblib")
    meta = {
        "symbol": symbol,
        "accuracy": acc,
        "precision": prec,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_cols": FEATURE_COLS,
        "n_samples": len(X),
    }
    joblib.dump({"model": model, "scaler": scaler, "meta": meta}, path)
    logger.info(f"  saved to {path}")

    return model


def load_model(symbol: str) -> Optional[Tuple[HistGradientBoostingClassifier, dict, StandardScaler]]:
    path = os.path.join(MODEL_DIR, f"model_{symbol.replace('/', '_')}.joblib")
    if not os.path.exists(path):
        return None
    data = joblib.load(path)
    return data["model"], data["meta"], data.get("scaler")


def predict(model: HistGradientBoostingClassifier, df: pd.DataFrame, scaler=None) -> Optional[dict]:
    try:
        X, y, idx = prepare_data(df)
        if len(X) == 0:
            return None
    except Exception:
        return None

    latest = X[-1:]
    if scaler is not None:
        latest = scaler.transform(latest)

    prob = float(model.predict_proba(latest)[0, 1])
    pred = int(prob > 0.5)

    return {
        "probability": round(prob, 4),
        "direction": "long" if pred == 1 else "short",
        "confidence": round(max(prob, 1 - prob), 3),
    }
