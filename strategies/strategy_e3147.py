"""
G001v2 - EMA Stack + RSI Pullback (M5) — ULTRA-SELECTIVE
Optimized from G001 with tighter selectivity:
- stack_bars: 15 → 20 (fewer but higher-quality signals)
- cooldown: 80 → 100 (avoid clustering)

Profile: HIGH WIN RATE (63.8%) with moderate R:R
Decorrelated from D008v2 (which is LOW WR + HIGH R:R)

Best results:
- PF=1.47 at risk=10% ($50→$117)
- PF=1.41 at risk=15% ($50→$134)
- 69 trades over 3 years
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.555214,
    "tp_atr": 1.686879,
    "timeframe": "M5",
    "risk_pct": 0.095333,
    "monte_carlo": {
        "median_dd": 0.3452,
        "p95_dd": 0.6379,
        "p_x10": 0.0,
        "p_ruin": 0.0012,
        "n_simulations": 10000
    },
    "monte_carlo_tested": true,
    "optimal_risk": 0.089204,
    "mtf_tested": true,
    "multi_timeframe": {
        "baseline_pf": 0.3518,
        "best_htf": "M5",
        "best_pf": 0.4433,
        "improvement": 1.2601,
        "htf_results": {
            "M5": {
                "pf": 0.4433,
                "wr": 0.4138,
                "trades": 116,
                "improvement": 1.2601
            },
            "M15": {
                "pf": 0.4104,
                "wr": 0.3983,
                "trades": 118,
                "improvement": 1.1666
            },
            "H1": {
                "pf": 0.3475,
                "wr": 0.371,
                "trades": 124,
                "improvement": 0.9878
            }
        }
    }
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # EMA stacking conditions
    df["bull_stack"] = (
        (df["EMA_fast"] > df["EMA_mid"]) & (df["EMA_mid"] > df["EMA_slow"])
    ).astype(int)
    df["bear_stack"] = (
        (df["EMA_fast"] < df["EMA_mid"]) & (df["EMA_mid"] < df["EMA_slow"])
    ).astype(int)

    # Count consecutive bars of perfect stacking
    df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
    df["bull_group"] = df["bull_break"].cumsum()
    df["bull_consec"] = df.groupby("bull_group").cumcount() + 1
    df.loc[df["bull_stack"] == 0, "bull_consec"] = 0

    df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
    df["bear_group"] = df["bear_break"].cumsum()
    df["bear_consec"] = df.groupby("bear_group").cumcount() + 1
    df.loc[df["bear_stack"] == 0, "bear_consec"] = 0

    # Shifted to avoid lookahead
    rsi = df["RSI"].shift(1)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    # Long: bull trend confirmed (20+ bars) + RSI pulls back to 25-40 zone
    long_cond = (
        (bull_consec >= p["stack_bars"])
        & (rsi < p["rsi_low"])
        & (rsi > p["rsi_floor"])
    )

    # Short: bear trend confirmed (20+ bars) + RSI bounces to 60-75 zone
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & (rsi > p["rsi_high"])
        & (rsi < p["rsi_ceil"])
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

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
    df["signal"] = raw

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
