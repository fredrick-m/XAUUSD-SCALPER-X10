"""
D004 - Exhaustion Reversal + Structure (M5)
Ultra-selective: Detects 8+ consecutive same-direction bars followed by
a strong reversal bar reverting toward EMA(50). Volume confirmation.
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
    "consecutive_bars": 8,
    "body_mult": 1.5,
    "body_avg_window": 10,
    "ema_trend": 50,
    "vol_mult": 1.5,
    "vol_window": 50,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Bar direction and body size
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["direction"] = np.where(df["Close"] > df["Open"], 1, -1)
    df["body_avg"] = df["body"].rolling(window=p["body_avg_window"]).mean()

    # Count consecutive same-direction bars
    # Use a cumulative group approach
    df["dir_change"] = (df["direction"] != df["direction"].shift(1)).astype(int)
    df["dir_group"] = df["dir_change"].cumsum()
    df["consec_count"] = df.groupby("dir_group").cumcount() + 1

    # Shifted indicators (no lookahead)
    consec = df["consec_count"].shift(2)  # the bar BEFORE the reversal bar
    prev_dir = df["direction"].shift(2)   # direction of the run
    rev_dir = df["direction"].shift(1)    # direction of the reversal bar
    rev_body = df["body"].shift(1)
    body_avg = df["body_avg"].shift(1)
    close_prev = df["Close"].shift(1)
    ema = df["EMA_trend"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Bullish reversal: 8+ down bars, then up reversal bar, reverting toward EMA
    long_cond = (
        (consec >= p["consecutive_bars"])
        & (prev_dir == -1)                           # was a downward run
        & (rev_dir == 1)                             # reversal bar is bullish
        & (rev_body > p["body_mult"] * body_avg)     # strong reversal bar
        & (close_prev < ema)                         # price below EMA (reverting toward it)
        & (vol > p["vol_mult"] * vol_avg)            # volume confirmation
    )

    # Bearish reversal: 8+ up bars, then down reversal bar, reverting toward EMA
    short_cond = (
        (consec >= p["consecutive_bars"])
        & (prev_dir == 1)                            # was an upward run
        & (rev_dir == -1)                            # reversal bar is bearish
        & (rev_body > p["body_mult"] * body_avg)     # strong reversal bar
        & (close_prev > ema)                         # price above EMA (reverting toward it)
        & (vol > p["vol_mult"] * vol_avg)            # volume confirmation
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

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
