"""
Strategy B009: Ichimoku Cloud Bounce
Family  : Ichimoku
Goal    : High win-rate M1 bounce off Kumo (cloud) support/resistance
Timeframe: M1 (XAUUSD)

Entry  : Long — price above cloud, drops to touch Senkou A (top of bullish cloud),
         bullish candle (Close > Open), Tenkan > Kijun.
         Short — mirror below cloud.
Exit   : SL = 3.0 × ATR (below the cloud)  |  TP = 1.0 × ATR (ride the bounce)
No session filter.
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 3.0,
    "tp_atr": 1.0,
    "tenkan_period": 9,
    "kijun_period": 26,
    "senkou_b_period": 52,
    "cloud_touch_atr": 0.3,
}


def _donchian_mid(series: pd.Series, period: int) -> pd.Series:
    """Donchian channel midline (used for Ichimoku components)."""
    high = series.rolling(window=period).max()
    low = series.rolling(window=period).min()
    return (high + low) / 2.0


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # --- ATR ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- Ichimoku components ---
    df["tenkan"] = _donchian_mid(df["High"], p["tenkan_period"]).combine_first(
        _donchian_mid(df["Close"], p["tenkan_period"])
    )
    # Recompute properly using High/Low
    hi = df["High"]
    lo = df["Low"]

    df["tenkan"] = (
        hi.rolling(p["tenkan_period"]).max() + lo.rolling(p["tenkan_period"]).min()
    ) / 2.0

    df["kijun"] = (
        hi.rolling(p["kijun_period"]).max() + lo.rolling(p["kijun_period"]).min()
    ) / 2.0

    # Senkou Span A = (Tenkan + Kijun) / 2, shifted forward 26
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2.0).shift(p["kijun_period"])

    # Senkou Span B = 52-period Donchian mid, shifted forward 26
    df["senkou_b"] = (
        (
            hi.rolling(p["senkou_b_period"]).max()
            + lo.rolling(p["senkou_b_period"]).min()
        )
        / 2.0
    ).shift(p["kijun_period"])

    # --- Cloud boundaries ---
    df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)
    df["cloud_bottom"] = df[["senkou_a", "senkou_b"]].min(axis=1)

    # --- Conditions (all using .shift(1) for prior bar) ---
    prev_close = df["Close"].shift(1)
    prev_low = df["Low"].shift(1)
    prev_high = df["High"].shift(1)
    prev_open = df["Open"].shift(1)
    prev_atr = df["ATR"].shift(1)

    # Price above cloud for longs
    above_cloud = prev_close > df["cloud_top"].shift(1)
    # Price below cloud for shorts
    below_cloud = prev_close < df["cloud_bottom"].shift(1)

    # Touch top of cloud (price came close to cloud top)
    # For longs: low touched near senkou_a (cloud top) — within cloud_touch_atr * ATR
    touch_dist_atr = p["cloud_touch_atr"]

    # For bullish cloud (senkou_a > senkou_b), the cloud top is senkou_a
    # The prev bar low should be close to cloud_top
    long_touch = (prev_low - df["cloud_top"].shift(1)).abs() < (
        touch_dist_atr * prev_atr
    )
    # For shorts: high touched near cloud_bottom
    short_touch = (prev_high - df["cloud_bottom"].shift(1)).abs() < (
        touch_dist_atr * prev_atr
    )

    # Bullish/bearish candle on prior bar
    bullish_candle = prev_close > prev_open
    bearish_candle = prev_close < prev_open

    # Tenkan > Kijun (bullish alignment) / Tenkan < Kijun (bearish)
    tenkan_bull = df["tenkan"].shift(1) > df["kijun"].shift(1)
    tenkan_bear = df["tenkan"].shift(1) < df["kijun"].shift(1)

    # --- Signals ---
    df["signal"] = 0

    long_cond = above_cloud & long_touch & bullish_candle & tenkan_bull
    short_cond = below_cloud & short_touch & bearish_candle & tenkan_bear

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Cleanup ---
    df.drop(
        columns=[
            "tenkan", "kijun", "senkou_a", "senkou_b",
            "cloud_top", "cloud_bottom",
        ],
        inplace=True,
        errors="ignore",
    )
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
