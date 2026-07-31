import os
from typing import Optional

import numpy as np
import joblib
from loguru import logger

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models_saved")


class OnlineLearner:
    def __init__(self, symbol: str, buffer_size: int = 500):
        self.symbol = symbol
        self.buffer_size = buffer_size
        self.X_buffer: list = []
        self.y_buffer: list = []
        self.updates = 0
        self.path = os.path.join(MODEL_DIR, f"online_{symbol.replace('/', '_')}.joblib")

    def add_sample(self, features: np.ndarray, label: int):
        self.X_buffer.append(features)
        self.y_buffer.append(label)
        if len(self.X_buffer) > self.buffer_size:
            self.X_buffer.pop(0)
            self.y_buffer.pop(0)

    def should_update(self) -> bool:
        return len(self.X_buffer) >= 50 and len(self.X_buffer) - self.updates * 50 >= 50

    def partial_fit(self):
        if len(self.X_buffer) < 50:
            return

        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
            X = np.array(self.X_buffer[-100:])
            y = np.array(self.y_buffer[-100:])
            model = HistGradientBoostingClassifier(max_iter=50, max_depth=4, learning_rate=0.03)
            model.fit(X, y)

            path = os.path.join(MODEL_DIR, f"model_{self.symbol.replace('/', '_')}_online.joblib")
            joblib.dump({"model": model}, path)
            self.updates = len(self.X_buffer) // 50
            logger.debug(f"Online learner updated: {self.symbol}, {len(X)} samples, pos_rate={y.mean():.2f}")
        except Exception as e:
            logger.error(f"Online learner failed: {e}")


def get_online_predict(symbol: str, features: np.ndarray) -> Optional[dict]:
    path = os.path.join(MODEL_DIR, f"model_{symbol.replace('/', '_')}_online.joblib")
    if not os.path.exists(path):
        return None
    try:
        data = joblib.load(path)
        model = data["model"]
        prob = float(model.predict_proba(features.reshape(1, -1))[0, 1])
        return {"probability": round(prob, 4), "direction": "long" if prob > 0.5 else "short",
                "confidence": round(max(prob, 1 - prob), 3)}
    except Exception:
        return None
