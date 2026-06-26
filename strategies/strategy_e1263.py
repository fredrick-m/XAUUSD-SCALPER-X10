"""
Strategy: CVD_Divergence_XAUUSD_M1
Family  : CVD_Divergence
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)

EDGE CONCEPT
------------
Cumulative Volume Delta (CVD) Divergence:
  - CVD = rolling cumulative sum of signed tick volume
      buy delta  when close > open (bullish bar)
      sell delta when close < open (bearish bar)
  - Bullish divergence : price[t] < price[t-N]  AND  CVD[t] > CVD[t-N]  → LONG
  - Bearish divergence : price[t] > price[t-N]  AND  CVD[t] < CVD[t-N]  → SHORT
  - Reveals hidden absorption / distribution before price reversal.

FILTERS
-------
  - ADX > 20 : confirm sufficient directional energy (avoid choppy periods)

RISK / REWARD
-------------
  - SL : 1.5 × ATR
  - TP : 3.0 × ATR  (RR = 2.0)

DYNAMIC LOT SIZING
------------------
  - Risk 2% of equity per trade
  - Lot = (equity × risk_pct) / (sl_distance × 100)
  - For XAUUSD: 1 lot = 100 oz, $1 price move = $100 P&L
  - Clipped to [min_lot, max_lot]
  - Starting balance: $50

NOTES
-----
  - Uses tick_volume as CVD proxy (real_volume = 0 for most retail XAUUSD feeds)
  - div_lookback controls the comparison period for divergence detection
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta

# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------
PARAMS = {
    "atr_period": 12,
    "adx_period": 13,
    "adx_threshold": 20,
    "cvd_smooth": 5,
    "div_lookback": 20,
    "sl_atr": 1.56632,
    "tp_atr": 3.0,
    "starting_balance": 55.870946,
    "risk_pct": 0.017968,
    "min_lot": 0.01,
    "max_lot": 100.0
}


# ---------------------------------------------------------------------------
# DATA LOADER
# ---------------------------------------------------------------------------
def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.rename(columns={
        "open":        "Open",
        "high":        "High",
        "low":         "Low",
        "close":       "Close",
        "tick_volume": "Volume",
    })
    df = df.sort_values("time").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------
def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    # ATR
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # ADX
    adx_ind = ta.trend.ADXIndicator(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )
    df["ADX"] = adx_ind.adx()

    # CVD: signed tick volume → cumsum → EMA smooth
    candle_sign  = np.sign(df["Close"] - df["Open"])
    raw_delta    = df["Volume"] * candle_sign
    df["CVD_raw"] = raw_delta.cumsum()
    df["CVD"]     = ta.trend.ema_indicator(df["CVD_raw"], window=p["cvd_smooth"])

    return df


# ---------------------------------------------------------------------------
# SIGNAL GENERATION  (fully vectorised)
# ---------------------------------------------------------------------------
def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    lb = p["div_lookback"]

    # Shift-based divergence comparison (vectorized, no rolling.apply)
    price_prev = df["Close"].shift(lb)
    cvd_prev   = df["CVD"].shift(lb)

    bull_div = (df["Close"] < price_prev) & (df["CVD"] > cvd_prev)
    bear_div = (df["Close"] > price_prev) & (df["CVD"] < cvd_prev)

    adx_ok = df["ADX"] > p["adx_threshold"]

    df["signal"] = 0
    df.loc[bull_div & adx_ok, "signal"] =  1
    df.loc[bear_div & adx_ok, "signal"] = -1

    df["sl_atr"] = p["sl_atr"]
    df["tp_atr"] = p["tp_atr"]

    return df


# ---------------------------------------------------------------------------
# DYNAMIC LOT SIZING
# ---------------------------------------------------------------------------
def compute_lot_size(
    equity: float,
    sl_distance: float,
    p: dict = PARAMS,
) -> float:
    """
    Risk-based lot size for XAUUSD.

    P&L per lot per $1 price move = $100  (100 oz × $1).
    dollar_risk = lot × sl_distance × 100
    → lot = dollar_risk / (sl_distance × 100)
    """
    if sl_distance <= 0:
        return p["min_lot"]
    dollar_risk = equity * p["risk_pct"]
    lot = dollar_risk / (sl_distance * 100.0)
    lot = round(max(p["min_lot"], min(p["max_lot"], lot)), 2)
    return lot


# ---------------------------------------------------------------------------
# VECTORISED QUICK STATS
# ---------------------------------------------------------------------------
def quick_backtest_stats(df: pd.DataFrame, p: dict = PARAMS) -> dict:
    """
    Approximate P&L simulation using fixed-bar forward returns.
    Checks whether price hits TP or SL within `max_hold` bars.
    No nested loops: uses numpy shift/roll for speed.
    """
    max_hold = 60  # maximum bars to hold per trade

    sig_idx  = df.index[df["signal"] != 0].tolist()
    if not sig_idx:
        return {"total_trades": 0, "final_equity": p["starting_balance"], "return_pct": 0.0}

    equity = p["starting_balance"]
    trades = []

    close_arr = df["Close"].values
    high_arr  = df["High"].values
    low_arr   = df["Low"].values
    atr_arr   = df["ATR"].values
    sig_arr   = df["signal"].values
    n         = len(df)

    last_exit = -1  # index of last trade exit (no pyramiding)

    for i in sig_idx:
        if i <= last_exit:
            continue  # still in previous trade

        direction = sig_arr[i]
        entry     = close_arr[i]
        atr       = atr_arr[i]

        if np.isnan(atr) or atr <= 0:
            continue

        sl_dist = p["sl_atr"] * atr
        tp_dist = p["tp_atr"] * atr
        sl      = entry - direction * sl_dist
        tp      = entry + direction * tp_dist
        lot     = compute_lot_size(equity, sl_dist, p)

        end_idx  = min(i + max_hold, n - 1)
        outcome  = "timeout"
        pnl      = 0.0
        exit_idx = end_idx

        for j in range(i + 1, end_idx + 1):
            if direction == 1:
                if low_arr[j] <= sl:
                    pnl      = -sl_dist * lot * 100
                    outcome  = "SL"
                    exit_idx = j
                    break
                if high_arr[j] >= tp:
                    pnl      = tp_dist * lot * 100
                    outcome  = "TP"
                    exit_idx = j
                    break
            else:
                if high_arr[j] >= sl:
                    pnl      = -sl_dist * lot * 100
                    outcome  = "SL"
                    exit_idx = j
                    break
                if low_arr[j] <= tp:
                    pnl      = tp_dist * lot * 100
                    outcome  = "TP"
                    exit_idx = j
                    break

        equity    += pnl
        last_exit  = exit_idx
        trades.append({"direction": direction, "lot": lot, "pnl": pnl,
                        "outcome": outcome, "equity": equity})

    if not trades:
        return {"total_trades": 0, "final_equity": equity, "return_pct": 0.0}

    res   = pd.DataFrame(trades)
    wins  = (res["pnl"] > 0).sum()
    total = len(res)
    ret   = (equity - p["starting_balance"]) / p["starting_balance"] * 100

    return {
        "total_trades":     total,
        "wins":             int(wins),
        "losses":           total - int(wins),
        "win_rate_pct":     round(wins / total * 100, 1),
        "final_equity_usd": round(equity, 2),
        "return_pct":       round(ret, 1),
        "starting_balance": p["starting_balance"],
    }


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = load_data()
    df = generate_signals(df)

    n_long  = (df["signal"] ==  1).sum()
    n_short = (df["signal"] == -1).sum()

    print("=" * 52)
    print("  Strategy: CVD_Divergence_XAUUSD_M1")
    print("=" * 52)
    print(f"  Total bars    : {len(df):,}")
    print(f"  Signals total : {n_long + n_short}")
    print(f"    Long        : {n_long}")
    print(f"    Short       : {n_short}")
    print()
    print("  Running quick backtest …")
    stats = quick_backtest_stats(df)
    print("  Results:")
    for k, v in stats.items():
        print(f"    {k:<22}: {v}")
    print("=" * 52)
