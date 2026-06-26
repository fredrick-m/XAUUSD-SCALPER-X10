"""
F003 - Bollinger Squeeze Breakout (M5)
Detects volatility contraction (BB width narrows) followed by expansion breakout.
Ultra-selective: target <300 signals over 200K M5 bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 4.0,
    "atr_period": 14,
    "cooldown": 80,
    "bb_period": 20,
    "bb_std": 2.0,
    "squeeze_window": 40,       # bars to measure squeeze
    "squeeze_percentile": 10,   # BB width must be in bottom 10% of recent range
    "breakout_bars": 3,         # price must close outside BB for N bars
    "ema_trend": 50,            # trend filter
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # ATR
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["Close"], window=p["bb_period"], window_dev=p["bb_std"])
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"] = bb.bollinger_mavg()
    df["BB_width"] = df["BB_upper"] - df["BB_lower"]

    # BB width percentile (rolling)
    df["BB_width_pctl"] = df["BB_width"].rolling(window=p["squeeze_window"]).rank(pct=True)

    # Trend filter
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # Shift to avoid lookahead
    bb_upper = df["BB_upper"].shift(1)
    bb_lower = df["BB_lower"].shift(1)
    bb_width_pctl = df["BB_width_pctl"].shift(1)
    close = df["Close"].shift(1)
    ema_trend = df["EMA_trend"].shift(1)

    # Was recently in squeeze (within last breakout_bars bars)?
    was_squeezed = bb_width_pctl.rolling(window=p["breakout_bars"]).min() <= (p["squeeze_percentile"] / 100.0)

    # Now breaking out
    long_breakout = (close > bb_upper) & was_squeezed & (close > ema_trend)
    short_breakout = (close < bb_lower) & was_squeezed & (close < ema_trend)

    df["raw_signal"] = 0
    df.loc[long_breakout, "raw_signal"] = 1
    df.loc[short_breakout, "raw_signal"] = -1

    # Cooldown
    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw.fillna(0).astype(int)

    return df
