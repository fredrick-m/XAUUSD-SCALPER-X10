"""
Strategy: RSI_VWAP_MeanReversion_XAUUSD_M1
Family  : RSI_VWAP_MeanReversion
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)

EDGE CONCEPT
------------
RSI + Daily VWAP Mean Reversion:
  - Daily VWAP resets at midnight UTC each session day.
    VWAP = cumsum(volume * typical_price) / cumsum(volume)
    where typical_price = (High + Low + Close) / 3
  - LONG  entry : RSI(14) < 35  AND  Close < VWAP  AND  ADX > 20
      Price is oversold relative to intraday fair value → expect reversion up.
  - SHORT entry : RSI(14) > 65  AND  Close > VWAP  AND  ADX > 20
      Price is overbought relative to intraday fair value → expect reversion down.
  - The ADX > 20 gate filters flat/choppy periods where mean reversion
    signals are noise (no directional energy to snap back against).

EXITS
-----
  - Primary   : SL = 1.5 × ATR(14), TP = 2.5 × ATR(14)
  - Secondary : Close position if price crosses VWAP (reversion complete)
                OR RSI crosses 50 from entry side (momentum neutralised)
  - Time cap  : Maximum 60 bars held (avoid overnight carry on M1)

RISK / REWARD
-------------
  - SL : 1.5 × ATR → expected dollar risk per lot = 1.5 × ATR × 100
  - TP : 2.5 × ATR → RR = 1.67 : 1 (2.5 / 1.5)
  - Breakeven win rate at 1.67 RR ≈ 37.5%

DYNAMIC LOT SIZING
------------------
  - Risk 2% of equity per trade
  - Lot = (equity × risk_pct) / (sl_distance × 100)
  - For XAUUSD: 1 lot = 100 oz, $1 price move = $100 P&L
  - Clipped to [min_lot, max_lot]
  - Starting balance: $50

NOTES
-----
  - VWAP resets at each UTC calendar day boundary in the CSV data.
  - `tick_volume` is used as volume proxy (real_volume = 0 for most
    retail XAUUSD M1 feeds).
  - Signals are generated on bar close (no look-ahead bias).
  - No pyramiding: a new signal is ignored while a position is open.
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
    # Indicators
    "rsi_period":    14,
    "rsi_oversold":  35,
    "rsi_overbought": 65,
    "atr_period":    14,
    "adx_period":    14,
    "adx_threshold": 20,

    # Risk / reward
    "sl_atr": 1.5,
    "tp_atr": 2.5,

    # Trade management
    "max_hold_bars": 60,   # time-cap: close after this many M1 bars

    # Dynamic lot sizing
    "starting_balance": 50.0,
    "risk_pct":         0.02,   # 2% per trade
    "min_lot":          0.01,
    "max_lot":          100.0,
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
# DAILY VWAP (resets at UTC midnight each day)
# ---------------------------------------------------------------------------
def add_daily_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute session-resetting VWAP.
    Groups by calendar date of 'time' column (UTC day boundary).
    Within each day: VWAP_i = sum(typical * volume) / sum(volume).
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    tv      = typical * df["Volume"]

    # UTC date key for daily grouping
    date_key = df["time"].dt.date

    cum_tv  = tv.groupby(date_key).cumsum()
    cum_vol = df["Volume"].groupby(date_key).cumsum()

    df["VWAP"] = cum_tv / cum_vol.replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------
def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    # Daily VWAP (resets each UTC day)
    df = add_daily_vwap(df)

    # RSI
    df["RSI"] = ta.momentum.RSIIndicator(
        df["Close"], window=p["rsi_period"]
    ).rsi()

    # ATR
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # ADX
    adx_ind = ta.trend.ADXIndicator(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )
    df["ADX"] = adx_ind.adx()

    return df


# ---------------------------------------------------------------------------
# SIGNAL GENERATION  (fully vectorised)
# ---------------------------------------------------------------------------
def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    adx_ok = df["ADX"] > p["adx_threshold"]

    # Entry signals (on bar close)
    long_entry  = (df["RSI"] < p["rsi_oversold"])  & (df["Close"] < df["VWAP"]) & adx_ok
    short_entry = (df["RSI"] > p["rsi_overbought"]) & (df["Close"] > df["VWAP"]) & adx_ok

    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1

    # Pre-compute VWAP cross and RSI-50 cross for early exit logic
    # (used bar-by-bar in the backtest loop)
    df["rsi_cross_50_up"]   = (df["RSI"] >= 50) & (df["RSI"].shift(1) < 50)
    df["rsi_cross_50_down"] = (df["RSI"] <= 50) & (df["RSI"].shift(1) > 50)
    df["price_cross_vwap_up"]   = (df["Close"] >= df["VWAP"]) & (df["Close"].shift(1) < df["VWAP"].shift(1))
    df["price_cross_vwap_down"] = (df["Close"] <= df["VWAP"]) & (df["Close"].shift(1) > df["VWAP"].shift(1))

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
    P&L simulation with SL/TP + early VWAP/RSI-50 exits.

    Exit priority per bar:
      1. SL hit (low/high crosses stop)
      2. TP hit (high/low crosses target)
      3. Early exit: price crosses VWAP or RSI crosses 50
      4. Time cap: max_hold_bars elapsed
    """
    max_hold = p["max_hold_bars"]

    sig_idx = df.index[df["signal"] != 0].tolist()
    if not sig_idx:
        return {"total_trades": 0, "final_equity": p["starting_balance"], "return_pct": 0.0}

    equity = p["starting_balance"]
    trades = []

    close_arr = df["Close"].values
    high_arr  = df["High"].values
    low_arr   = df["Low"].values
    atr_arr   = df["ATR"].values
    sig_arr   = df["signal"].values
    vwap_arr  = df["VWAP"].values
    rsi_arr   = df["RSI"].values
    n         = len(df)

    last_exit = -1  # no pyramiding

    for i in sig_idx:
        if i <= last_exit:
            continue

        direction = int(sig_arr[i])
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
        exit_px  = close_arr[end_idx]

        for j in range(i + 1, end_idx + 1):
            h = high_arr[j]
            l = low_arr[j]
            c = close_arr[j]
            r = rsi_arr[j]
            v = vwap_arr[j]

            # 1. SL
            if direction == 1 and l <= sl:
                pnl      = -sl_dist * lot * 100.0
                outcome  = "SL"
                exit_idx = j
                break
            if direction == -1 and h >= sl:
                pnl      = -sl_dist * lot * 100.0
                outcome  = "SL"
                exit_idx = j
                break

            # 2. TP
            if direction == 1 and h >= tp:
                pnl      = tp_dist * lot * 100.0
                outcome  = "TP"
                exit_idx = j
                break
            if direction == -1 and l <= tp:
                pnl      = tp_dist * lot * 100.0
                outcome  = "TP"
                exit_idx = j
                break

            # 3a. VWAP cross exit
            if direction == 1 and c >= v:        # long entered below VWAP, now above → reversion done
                pnl      = (c - entry) * lot * 100.0
                outcome  = "VWAP_cross"
                exit_idx = j
                break
            if direction == -1 and c <= v:       # short entered above VWAP, now below → reversion done
                pnl      = (entry - c) * lot * 100.0
                outcome  = "VWAP_cross"
                exit_idx = j
                break

            # 3b. RSI-50 cross exit
            if direction == 1 and (not np.isnan(r)) and r >= 50:   # RSI recovered to neutral
                pnl      = (c - entry) * lot * 100.0
                outcome  = "RSI50_cross"
                exit_idx = j
                break
            if direction == -1 and (not np.isnan(r)) and r <= 50:  # RSI recovered to neutral
                pnl      = (entry - c) * lot * 100.0
                outcome  = "RSI50_cross"
                exit_idx = j
                break

        else:
            # Time cap: exit at last bar close
            if direction == 1:
                pnl = (exit_px - entry) * lot * 100.0
            else:
                pnl = (entry - exit_px) * lot * 100.0
            outcome = "timeout"

        equity    += pnl
        last_exit  = exit_idx
        trades.append({
            "direction": direction,
            "lot":       lot,
            "pnl":       round(pnl, 4),
            "outcome":   outcome,
            "equity":    round(equity, 4),
        })

    if not trades:
        return {"total_trades": 0, "final_equity": equity, "return_pct": 0.0}

    res   = pd.DataFrame(trades)
    wins  = (res["pnl"] > 0).sum()
    total = len(res)
    ret   = (equity - p["starting_balance"]) / p["starting_balance"] * 100

    outcome_counts = res["outcome"].value_counts().to_dict()

    return {
        "total_trades":     total,
        "wins":             int(wins),
        "losses":           total - int(wins),
        "win_rate_pct":     round(wins / total * 100, 1),
        "final_equity_usd": round(equity, 2),
        "return_pct":       round(ret, 1),
        "starting_balance": p["starting_balance"],
        "outcome_TP":       outcome_counts.get("TP", 0),
        "outcome_SL":       outcome_counts.get("SL", 0),
        "outcome_VWAP":     outcome_counts.get("VWAP_cross", 0),
        "outcome_RSI50":    outcome_counts.get("RSI50_cross", 0),
        "outcome_timeout":  outcome_counts.get("timeout", 0),
    }


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = load_data()
    df = generate_signals(df)

    n_long  = (df["signal"] ==  1).sum()
    n_short = (df["signal"] == -1).sum()

    print("=" * 56)
    print("  Strategy: RSI_VWAP_MeanReversion_XAUUSD_M1")
    print("=" * 56)
    print(f"  Total bars    : {len(df):,}")
    print(f"  Signals total : {n_long + n_short}")
    print(f"    Long        : {n_long}")
    print(f"    Short       : {n_short}")
    print()
    print("  Running quick backtest ...")
    stats = quick_backtest_stats(df)
    print("  Results:")
    for k, v in stats.items():
        print(f"    {k:<26}: {v}")
    print("=" * 56)
