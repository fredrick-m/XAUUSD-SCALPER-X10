"""
D009 - Session Open Momentum (M5)
Ultra-selective: Only trades during first 2 hours of London (7-9 UTC)
or NY (13-15 UTC) sessions. Requires breakout of Asian range with
volume surge and ADX confirmation.
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
    "asian_start": 0,
    "asian_end": 7,
    "london_start": 7,
    "london_end": 9,
    "ny_start": 13,
    "ny_end": 15,
    "adx_period": 14,
    "adx_min": 25,
    "vol_mult": 2.0,
    "vol_window": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Extract hour
    if hasattr(df.index, 'hour'):
        hour = df.index.hour
    else:
        hour = pd.to_datetime(df.index).hour

    df["_hour"] = hour
    df["_date"] = pd.to_datetime(df.index).date

    # Asian session (00-07 UTC) high/low per day
    df["_is_asian"] = (
        (df["_hour"] >= p["asian_start"]) & (df["_hour"] < p["asian_end"])
    ).astype(int)

    # Calculate Asian range per day
    # Group by date and compute Asian high/low
    asian_mask = df["_is_asian"] == 1
    df["_asian_high"] = np.nan
    df["_asian_low"] = np.nan

    # Forward fill Asian high/low within each day
    for date_val in df["_date"].unique():
        day_mask = df["_date"] == date_val
        asian_day = df.loc[day_mask & asian_mask]
        if len(asian_day) > 0:
            a_high = asian_day["High"].max()
            a_low = asian_day["Low"].min()
            df.loc[day_mask, "_asian_high"] = a_high
            df.loc[day_mask, "_asian_low"] = a_low

    # Session filters
    in_london = (df["_hour"] >= p["london_start"]) & (df["_hour"] < p["london_end"])
    in_ny = (df["_hour"] >= p["ny_start"]) & (df["_hour"] < p["ny_end"])
    in_session = in_london | in_ny

    # Shifted indicators (no lookahead)
    close = df["Close"].shift(1)
    high_prev = df["High"].shift(1)
    low_prev = df["Low"].shift(1)
    asian_high = df["_asian_high"].shift(1)
    asian_low = df["_asian_low"].shift(1)
    adx = df["ADX"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)
    session = in_session.shift(1).fillna(False)

    # Long: breakout above Asian high, in session, ADX strong, volume surge
    long_cond = (
        (close > asian_high)
        & session
        & (adx > p["adx_min"])
        & (vol > p["vol_mult"] * vol_avg)
        & asian_high.notna()
    )

    # Short: breakdown below Asian low, in session, ADX strong, volume surge
    short_cond = (
        (close < asian_low)
        & session
        & (adx > p["adx_min"])
        & (vol > p["vol_mult"] * vol_avg)
        & asian_low.notna()
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
