"""
D002 - Double Bollinger Band Extreme (M5)
Ultra-selective: Price must breach BOTH BB(20,2) and BB(20,3) bands
simultaneously with EMA(50) trend filter and volume confirmation.
Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 100,
    "bb_window": 20,
    "bb_std_inner": 2.0,
    "bb_std_outer": 3.0,
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

    # Inner Bollinger Bands (2 std)
    bb_inner = ta.volatility.BollingerBands(
        df["Close"], window=p["bb_window"], window_dev=p["bb_std_inner"]
    )
    df["bb_inner_lower"] = bb_inner.bollinger_lband()
    df["bb_inner_upper"] = bb_inner.bollinger_hband()

    # Outer Bollinger Bands (3 std)
    bb_outer = ta.volatility.BollingerBands(
        df["Close"], window=p["bb_window"], window_dev=p["bb_std_outer"]
    )
    df["bb_outer_lower"] = bb_outer.bollinger_lband()
    df["bb_outer_upper"] = bb_outer.bollinger_hband()

    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Shifted indicators (no lookahead)
    close = df["Close"].shift(1)
    ema = df["EMA_trend"].shift(1)
    bb_il = df["bb_inner_lower"].shift(1)
    bb_ol = df["bb_outer_lower"].shift(1)
    bb_iu = df["bb_inner_upper"].shift(1)
    bb_ou = df["bb_outer_upper"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Long: price below BOTH lower bands, in uptrend, volume surge
    long_cond = (
        (close < bb_il)
        & (close < bb_ol)
        & (close > ema)
        & (vol > p["vol_mult"] * vol_avg)
    )

    # Short: price above BOTH upper bands, in downtrend, volume surge
    short_cond = (
        (close > bb_iu)
        & (close > bb_ou)
        & (close < ema)
        & (vol > p["vol_mult"] * vol_avg)
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
