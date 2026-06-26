"""
Download maximum XAUUSD M1 historical data from MT5.

Pre-requisite: In MT5, go to Tools -> Options -> Charts ->
               Set "Max bars in charts" to "Unlimited" or 1000000.
               Then restart MT5 before running this script.

Usage: python scripts/download_m1_data.py
"""
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def download_all_m1():
    import MetaTrader5 as mt5

    if not mt5.initialize():
        print("ERROR: MT5 failed to initialize")
        print("Make sure MetaTrader 5 is running.")
        return

    symbol = "XAUUSD"
    mt5.symbol_select(symbol, True)

    info = mt5.terminal_info()
    print(f"Terminal: {info.name}")
    print(f"Max bars in chart: {info.maxbars}")

    if info.maxbars <= 100000:
        print()
        print("WARNING: Max bars is still 100,000.")
        print("To get more M1 data:")
        print("  1. In MT5: Tools -> Options -> Charts")
        print("  2. Set 'Max bars in charts' to 'Unlimited'")
        print("  3. Click OK, restart MT5")
        print("  4. Run this script again")
        print()
        print("Continuing with current limit...")

    # Download in chunks of 50k bars using position offsets
    print(f"\nDownloading {symbol} M1 data...")
    all_dfs = []
    offset = 0
    chunk_size = 50000

    while True:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, offset, chunk_size)
        if rates is None or len(rates) == 0:
            break

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        first = df["time"].iloc[0].date()
        last = df["time"].iloc[-1].date()
        print(f"  Chunk offset={offset}: {len(rates)} bars ({first} -> {last})")
        all_dfs.append(df)

        if len(rates) < chunk_size:
            break
        offset += chunk_size

    mt5.shutdown()

    if not all_dfs:
        print("ERROR: No data downloaded")
        return

    # Merge and deduplicate
    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "tick_volume": "Volume",
    })

    cols = ["time", "Open", "High", "Low", "Close", "Volume", "spread", "real_volume"]
    available = [c for c in cols if c in df.columns]

    out_path = ROOT / "data" / "raw" / "XAUUSD_M1.csv"
    df[available].to_csv(out_path, index=False)

    days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
    print(f"\nDONE")
    print(f"  Bars:  {len(df):,}")
    print(f"  Range: {df['time'].iloc[0]} -> {df['time'].iloc[-1]} ({days} days)")
    print(f"  File:  {out_path}")

    target = 250_000
    if len(df) < target:
        print(f"\n  Still below {target:,} target. Increase 'Max bars in charts' in MT5 and retry.")
    else:
        print(f"\n  Target of {target:,} bars reached!")


if __name__ == "__main__":
    download_all_m1()
