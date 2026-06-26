"""
D006 - VWAP Extreme Deviation (M5)
Ultra-selective: Price > 2.0 std devs from intraday VWAP with RSI
confirmation. Session filter 8-18 UTC only.
Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 80,
    "vwap_std_mult": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "session_start": 8,
    "session_end": 18,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # Compute intraday VWAP with daily reset
    # Detect day boundaries
    if hasattr(df.index, 'hour'):
        hour = df.index.hour
    else:
        hour = pd.to_datetime(df.index).hour

    df["_hour"] = hour
    df["_date"] = pd.to_datetime(df.index).date
    df["_new_day"] = (df["_date"] != df["_date"].shift(1)).astype(int)
    df["_day_group"] = df["_new_day"].cumsum()

    # Typical price
    df["_tp"] = (df["High"] + df["Low"] + df["Close"]) / 3.0
    df["_tp_vol"] = df["_tp"] * df["Volume"]

    # Cumulative sums within each day
    df["_cum_vol"] = df.groupby("_day_group")["Volume"].cumsum()
    df["_cum_tp_vol"] = df.groupby("_day_group")["_tp_vol"].cumsum()

    # VWAP
    df["VWAP"] = df["_cum_tp_vol"] / df["_cum_vol"].replace(0, np.nan)

    # VWAP standard deviation (rolling within day)
    df["_tp_diff_sq"] = (df["_tp"] - df["VWAP"]) ** 2
    df["_cum_tp_diff_sq"] = df.groupby("_day_group")["_tp_diff_sq"].cumsum()
    df["_bar_count"] = df.groupby("_day_group").cumcount() + 1
    df["VWAP_std"] = np.sqrt(df["_cum_tp_diff_sq"] / df["_bar_count"])

    # Session filter
    in_session = (df["_hour"] >= p["session_start"]) & (df["_hour"] < p["session_end"])

    # Shifted indicators (no lookahead)
    close = df["Close"].shift(1)
    vwap = df["VWAP"].shift(1)
    vwap_std = df["VWAP_std"].shift(1)
    rsi = df["RSI"].shift(1)
    session = in_session.shift(1).fillna(False)

    # VWAP bands
    vwap_lower = vwap - p["vwap_std_mult"] * vwap_std
    vwap_upper = vwap + p["vwap_std_mult"] * vwap_std

    # Long: price below lower VWAP band, RSI oversold, in session
    long_cond = (
        (close < vwap_lower)
        & (rsi < p["rsi_oversold"])
        & session
    )

    # Short: price above upper VWAP band, RSI overbought, in session
    short_cond = (
        (close > vwap_upper)
        & (rsi > p["rsi_overbought"])
        & session
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    # Vectorized cooldown
    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw

    # Cleanup temp columns
    temp_cols = [c for c in df.columns if c.startswith("_")]
    df.drop(columns=temp_cols, inplace=True)

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
