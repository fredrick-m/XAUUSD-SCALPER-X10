"""
Strategy B007: VWAP + EMA Confluence Zone
Family  : VWAP Mean Reversion
Goal    : High win-rate M1 scalp at VWAP pullback with EMA(50) + RSI confluence
Timeframe: M1 (XAUUSD)

Entry  : Long — price within 0.3 ATR of VWAP, VWAP > EMA(50), RSI 40-55, vol > avg
         Short — price within 0.3 ATR of VWAP, VWAP < EMA(50), RSI 45-60, vol > avg
Exit   : SL = 2.0 × ATR  |  TP = 1.2 × ATR
Session: 08:00-19:00 UTC
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 1.2,
    "ema_period": 50,
    "rsi_period": 14,
    "vwap_dist_atr": 0.3,
    "vol_avg_period": 20,
    "rsi_long_lo": 40,
    "rsi_long_hi": 55,
    "rsi_short_lo": 45,
    "rsi_short_hi": 60,
    "session_start": 8,
    "session_end": 19,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA50"] = ta.trend.ema_indicator(df["Close"], window=p["ema_period"])
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # --- Intraday VWAP (reset daily) ---
    if "time" in df.columns:
        df["_dt"] = pd.to_datetime(df["time"])
    elif "Time" in df.columns:
        df["_dt"] = pd.to_datetime(df["Time"])
    else:
        # fallback: treat index as sequential, no daily reset
        df["_dt"] = pd.Timestamp("2020-01-01") + pd.to_timedelta(df.index, unit="min")

    df["hour"] = df["_dt"].dt.hour
    df["_date"] = df["_dt"].dt.date

    # Typical price
    tp_price = (df["High"] + df["Low"] + df["Close"]) / 3.0

    # Use Volume column (tick_volume mapped to Volume)
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    vol = df[vol_col].astype(float)

    # Cumulative sums within each day
    cum_vol = vol.groupby(df["_date"]).cumsum()
    cum_tp_vol = (tp_price * vol).groupby(df["_date"]).cumsum()

    df["VWAP"] = cum_tp_vol / cum_vol.replace(0, np.nan)

    # --- Session filter ---
    in_session = (df["hour"] >= p["session_start"]) & (df["hour"] < p["session_end"])

    # --- Volume filter ---
    df["vol_avg"] = vol.rolling(window=p["vol_avg_period"]).mean()
    vol_ok = vol.shift(1) > df["vol_avg"].shift(1)

    # --- Price distance to VWAP (use shifted values for entry on prior bar close) ---
    vwap_dist = (df["Close"].shift(1) - df["VWAP"].shift(1)).abs()
    close_to_vwap = vwap_dist < (p["vwap_dist_atr"] * df["ATR"].shift(1))

    # --- Trend: VWAP vs EMA50 ---
    vwap_above_ema = df["VWAP"].shift(1) > df["EMA50"].shift(1)
    vwap_below_ema = df["VWAP"].shift(1) < df["EMA50"].shift(1)

    # --- RSI conditions ---
    rsi_prev = df["RSI"].shift(1)
    rsi_long = (rsi_prev >= p["rsi_long_lo"]) & (rsi_prev <= p["rsi_long_hi"])
    rsi_short = (rsi_prev >= p["rsi_short_lo"]) & (rsi_prev <= p["rsi_short_hi"])

    # --- Signals ---
    df["signal"] = 0

    long_cond = in_session & close_to_vwap & vwap_above_ema & rsi_long & vol_ok
    short_cond = in_session & close_to_vwap & vwap_below_ema & rsi_short & vol_ok

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Cleanup ---
    df.drop(
        columns=["EMA50", "RSI", "VWAP", "_dt", "hour", "_date", "vol_avg"],
        inplace=True,
        errors="ignore",
    )
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
