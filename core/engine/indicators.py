import pandas as pd
import numpy as np


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_bollinger_bands(
    close: pd.Series, period: int = 20, std_dev: float = 2.0
) -> pd.DataFrame:
    sma = compute_sma(close, period)
    std = close.rolling(window=period).std()
    return pd.DataFrame(
        {"bb_mid": sma, "bb_upper": sma + std_dev * std, "bb_lower": sma - std_dev * std},
        index=close.index,
    )


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def compute_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram},
        index=close.index,
    )


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    o, h, l, c, v = result["open"], result["high"], result["low"], result["close"], result["volume"]

    result["ema_9"] = compute_ema(c, 9)
    result["ema_21"] = compute_ema(c, 21)
    result["ema_50"] = compute_ema(c, 50)
    result["ema_200"] = compute_ema(c, 200)

    result["sma_20"] = compute_sma(c, 20)
    result["sma_50"] = compute_sma(c, 50)

    result["rsi_14"] = compute_rsi(c, 14)

    bb = compute_bollinger_bands(c, 20, 2.0)
    result["bb_upper"] = bb["bb_upper"]
    result["bb_mid"] = bb["bb_mid"]
    result["bb_lower"] = bb["bb_lower"]

    result["atr_14"] = compute_atr(h, l, c, 14)
    result["adx_14"] = compute_adx(h, l, c, 14)

    macd = compute_macd(c)
    result["macd"] = macd["macd"]
    result["macd_signal"] = macd["signal"]
    result["macd_hist"] = macd["histogram"]

    result["volume_sma_20"] = compute_sma(v, 20)

    result["returns"] = c.pct_change()
    result["volatility_20"] = result["returns"].rolling(20).std()

    return result
