"""
Strategy B008: Bollinger Band Squeeze + Momentum Burst
Family  : Volatility Breakout
Goal    : High win-rate M1 entry on BB squeeze breakout with ADX confirmation
Timeframe: M1 (XAUUSD)

Entry  : BB width < 0.5 × 50-bar avg BB width for 15+ bars (squeeze detected).
         When squeeze breaks: Close crosses above upper BB → long, below lower BB → short.
         ADX must be rising (ADX > ADX 3 bars ago).
         Max 1 signal per squeeze event.
Exit   : SL = 2.0 × ATR  |  TP = 1.5 × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 1.5,
    "bb_period": 20,
    "bb_std": 2.0,
    "bb_width_avg": 50,
    "squeeze_threshold": 0.5,
    "min_squeeze_bars": 15,
    "adx_period": 14,
    "adx_lookback": 3,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    bb = ta.volatility.BollingerBands(
        df["Close"], window=p["bb_period"], window_dev=p["bb_std"]
    )
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"] = bb.bollinger_mavg()
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_mid"]

    # Average BB width over lookback
    df["BB_width_avg"] = df["BB_width"].rolling(window=p["bb_width_avg"]).mean()

    # Squeeze: width < threshold * average width
    df["in_squeeze"] = df["BB_width"] < (p["squeeze_threshold"] * df["BB_width_avg"])

    # Count consecutive squeeze bars
    sq = df["in_squeeze"].astype(int)
    sq_group = (~df["in_squeeze"]).cumsum()
    df["squeeze_count"] = sq.groupby(sq_group).cumsum()

    # Squeeze was active for enough bars (check prior bar)
    had_squeeze = df["squeeze_count"].shift(1) >= p["min_squeeze_bars"]

    # Squeeze just broke: was in squeeze, now not
    squeeze_break = df["in_squeeze"].shift(1) & (~df["in_squeeze"])

    # Also catch: still technically squeezing but price burst through BB
    # Direction of break
    cross_above_upper = (df["Close"].shift(1) > df["BB_upper"].shift(1)) & (
        df["Close"].shift(2) <= df["BB_upper"].shift(2)
    )
    cross_below_lower = (df["Close"].shift(1) < df["BB_lower"].shift(1)) & (
        df["Close"].shift(2) >= df["BB_lower"].shift(2)
    )

    # ADX rising
    adx = ta.trend.ADXIndicator(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )
    df["ADX"] = adx.adx()
    adx_rising = df["ADX"].shift(1) > df["ADX"].shift(1 + p["adx_lookback"])

    # --- Build signals with 1-per-squeeze logic ---
    df["signal"] = 0

    # We need to iterate to enforce 1 signal per squeeze event
    signals = np.zeros(len(df), dtype=int)
    fired_this_squeeze = False
    prev_in_squeeze = False

    squeeze_count_arr = df["squeeze_count"].values
    had_squeeze_arr = had_squeeze.values
    cross_up_arr = cross_above_upper.values
    cross_dn_arr = cross_below_lower.values
    adx_rising_arr = adx_rising.values
    in_squeeze_arr = df["in_squeeze"].values

    for i in range(2, len(df)):
        # Track squeeze state
        if in_squeeze_arr[i] and not prev_in_squeeze:
            # New squeeze starting
            fired_this_squeeze = False
        if not in_squeeze_arr[i] and not prev_in_squeeze:
            # Outside squeeze, reset
            fired_this_squeeze = False

        prev_in_squeeze = bool(in_squeeze_arr[i])

        if fired_this_squeeze:
            continue

        # Check if prior bar had enough squeeze and we see a breakout
        if not had_squeeze_arr[i]:
            continue
        if not adx_rising_arr[i]:
            continue

        if cross_up_arr[i]:
            signals[i] = 1
            fired_this_squeeze = True
        elif cross_dn_arr[i]:
            signals[i] = -1
            fired_this_squeeze = True

    df["signal"] = signals

    # --- Cleanup ---
    df.drop(
        columns=[
            "BB_upper", "BB_lower", "BB_mid", "BB_width",
            "BB_width_avg", "in_squeeze", "squeeze_count", "ADX",
        ],
        inplace=True,
        errors="ignore",
    )
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
