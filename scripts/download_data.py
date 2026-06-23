"""
Download XAUUSD historical data from MetaTrader5.
Saves M1, M5, H1 bars to data/raw/ and a summary to data/raw/download_summary.txt.
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas package not installed. Run: pip install pandas")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR  = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ───────────────────────────────────────────────────────────────────
SYMBOL = "XAUUSDm"

JOBS = [
    {"timeframe": mt5.TIMEFRAME_M1,  "bars": 100_000, "filename": "XAUUSD_M1.csv",  "label": "M1"},
    {"timeframe": mt5.TIMEFRAME_M5,  "bars":  50_000, "filename": "XAUUSD_M5.csv",  "label": "M5"},
    {"timeframe": mt5.TIMEFRAME_H1,  "bars":  30_000, "filename": "XAUUSD_H1.csv",  "label": "H1"},
]

# Expected gap sizes in minutes for each timeframe
GAP_MINUTES = {
    mt5.TIMEFRAME_M1: 1,
    mt5.TIMEFRAME_M5: 5,
    mt5.TIMEFRAME_H1: 60,
}


def detect_gaps(df: pd.DataFrame, expected_gap_minutes: int) -> list[dict]:
    """Return list of gaps larger than expected_gap_minutes in the time index."""
    if df.empty or len(df) < 2:
        return []
    times = pd.to_datetime(df["time"])
    diffs = times.diff().dropna()
    expected = pd.Timedelta(minutes=expected_gap_minutes)
    # Allow up to 3x the expected gap before flagging (covers weekends for H1)
    threshold = expected * 3
    gaps = diffs[diffs > threshold]
    result = []
    for idx, gap in gaps.items():
        result.append({
            "from": str(times[idx - 1]),
            "to":   str(times[idx]),
            "gap":  str(gap),
        })
    return result


BATCH_SIZE = 50_000   # MT5 safe per-call limit


def download_bars(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    """Fetch `count` bars from MT5, batching in chunks of BATCH_SIZE."""
    frames = []
    remaining = count
    pos = 0  # start from the most-recent bar

    while remaining > 0:
        batch = min(remaining, BATCH_SIZE)
        rates = mt5.copy_rates_from_pos(symbol, timeframe, pos, batch)
        if rates is None or len(rates) == 0:
            break
        frames.append(pd.DataFrame(rates))
        fetched = len(rates)
        pos += fetched
        remaining -= fetched
        if fetched < batch:
            break  # MT5 returned fewer than requested — no more history

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df.drop_duplicates(subset="time", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def main():
    # ── Connect ───────────────────────────────────────────────────────────────
    print("Initialising MetaTrader5…")
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"ERROR: mt5.initialize() failed — {err}")
        sys.exit(1)

    info = mt5.terminal_info()
    print(f"Connected to: {info.name}  build={info.build}  connected={info.connected}")

    # Check symbol
    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        print(f"ERROR: Symbol '{SYMBOL}' not found in MT5. Check broker symbol name.")
        mt5.shutdown()
        sys.exit(1)
    if not sym_info.visible:
        mt5.symbol_select(SYMBOL, True)

    # ── Download ──────────────────────────────────────────────────────────────
    summary_lines = [
        f"XAUUSD Data Download Summary",
        f"Generated : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"Symbol    : {SYMBOL}",
        "=" * 60,
    ]

    for job in JOBS:
        label     = job["label"]
        filename  = job["filename"]
        out_path  = RAW_DIR / filename
        requested = job["bars"]

        print(f"\n[{label}] Downloading {requested:,} bars…")
        df = download_bars(SYMBOL, job["timeframe"], requested)

        if df.empty:
            msg = f"[{label}] ERROR: No data returned — {mt5.last_error()}"
            print(msg)
            summary_lines.append(msg)
            continue

        # Save CSV
        df.to_csv(out_path, index=False)

        actual     = len(df)
        date_start = str(df["time"].iloc[0])
        date_end   = str(df["time"].iloc[-1])
        gaps       = detect_gaps(df, GAP_MINUTES[job["timeframe"]])

        print(f"  Bars      : {actual:,} (requested {requested:,})")
        print(f"  From      : {date_start}")
        print(f"  To        : {date_end}")
        print(f"  Gaps (>{GAP_MINUTES[job['timeframe']]*3}min): {len(gaps)}")
        print(f"  Saved to  : {out_path}")

        summary_lines += [
            f"\n[{label}]",
            f"  Bars downloaded : {actual:,} / {requested:,} requested",
            f"  Date start      : {date_start}",
            f"  Date end        : {date_end}",
            f"  Gaps detected   : {len(gaps)}",
            f"  Output file     : {out_path}",
        ]
        if gaps:
            summary_lines.append("  Gap details:")
            for g in gaps[:10]:   # cap at first 10 gaps in summary
                summary_lines.append(f"    {g['from']}  ->  {g['to']}  ({g['gap']})")
            if len(gaps) > 10:
                summary_lines.append(f"    … and {len(gaps)-10} more gaps")

    # ── Shutdown ──────────────────────────────────────────────────────────────
    mt5.shutdown()
    print("\nMT5 connection closed.")

    # ── Write summary ─────────────────────────────────────────────────────────
    summary_path = RAW_DIR / "download_summary.txt"
    summary_text = "\n".join(summary_lines) + "\n"
    summary_path.write_text(summary_text, encoding="utf-8")
    print(f"\nSummary saved to: {summary_path}")
    sys.stdout.buffer.write(summary_text.encode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
