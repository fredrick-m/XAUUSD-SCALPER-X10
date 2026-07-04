"""Data Agent: acquires, maintains, and quality-checks market data."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR


def quality_score(file_path) -> float:
    """Compute a 0-1 quality score for a data CSV file."""
    file_path = Path(file_path)
    if not file_path.exists():
        return 0.0
    try:
        header = pd.read_csv(file_path, nrows=0)
        date_col = ["time"] if "time" in header.columns else [0]
        df = pd.read_csv(file_path, parse_dates=date_col)
    except Exception:
        return 0.0
    if len(df) < 10:
        return 0.0
    score = 1.0
    nan_pct = df.isnull().sum().sum() / (len(df) * len(df.columns))
    score -= nan_pct * 0.5
    time_col = "time" if "time" in df.columns else df.columns[0]
    dup_pct = df[time_col].duplicated().sum() / len(df)
    score -= dup_pct * 0.3
    close_col = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
    if close_col:
        returns = df[close_col].pct_change().dropna()
        if len(returns) > 0:
            spike_threshold = returns.std() * 5
            spike_pct = (returns.abs() > spike_threshold).sum() / len(returns) if spike_threshold > 0 else 0
            score -= spike_pct * 0.2
    return max(0.0, min(1.0, round(score, 4)))


class DataAgent(BaseAgent):
    name = "data_agent"

    def __init__(self, db):
        super().__init__(agent_id="data_agent", db=db)

    def setup(self):
        self.logger.info("Data Agent starting — scanning existing data")
        existing = self.scan_existing_data()
        self.logger.info(f"Found {len(existing)} existing data files")
        for entry in existing:
            self.logger.info(f"  {entry['file']}: {entry['bars']} bars, quality={entry['quality']:.2f}")

    def tick(self):
        existing = self.scan_existing_data()
        total_m1_bars = sum(e["bars"] for e in existing if e["timeframe"] == "M1")
        if total_m1_bars < 250_000:
            self.emit_event("warning", f"Only {total_m1_bars} M1 bars available, need 250k+")
            self._try_download_mt5()
        self._refresh_m1_data()
        for entry in existing:
            self.register_data(
                data_id=entry["id"],
                timeframe=entry["timeframe"],
                source=entry.get("source", "file"),
                file_path=str(entry["path"]),
                start_date=entry.get("start"),
                end_date=entry.get("end"),
                bar_count=entry["bars"],
                quality=entry["quality"],
            )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    def scan_existing_data(self) -> List[dict]:
        raw_dir = DATA_DIR / "raw"
        results = []
        if not raw_dir.exists():
            return results
        for csv_file in sorted(raw_dir.glob("*.csv")):
            try:
                df = pd.read_csv(csv_file, nrows=5)
                with open(csv_file, encoding="utf-8") as f:
                    total_rows = sum(1 for _ in f) - 1
                fname = csv_file.stem.upper()
                if "M1" in fname:
                    tf = "M1"
                elif "M5" in fname:
                    tf = "M5"
                elif "H1" in fname:
                    tf = "H1"
                else:
                    tf = "UNKNOWN"
                first_df = pd.read_csv(csv_file, nrows=1)
                last_df = pd.read_csv(csv_file, skiprows=max(1, total_rows - 1), header=None)
                score = quality_score(csv_file)
                file_id = f"xauusd_{tf.lower()}_{csv_file.stem.lower()}"
                results.append({
                    "id": file_id,
                    "file": csv_file.name,
                    "path": csv_file,
                    "timeframe": tf,
                    "bars": total_rows,
                    "quality": score,
                    "source": "file",
                    "start": str(first_df.iloc[0, 0]) if len(first_df) > 0 else None,
                    "end": str(last_df.iloc[0, 0]) if len(last_df) > 0 else None,
                })
            except Exception as e:
                self.logger.warning(f"Error scanning {csv_file}: {e}")
        return results

    def register_data(self, data_id: str, timeframe: str, source: str, file_path: str,
                      start_date: Optional[str], end_date: Optional[str], bar_count: int, quality: float):
        existing = self.db.fetchone("SELECT id FROM data_registry WHERE id = ?", (data_id,))
        if existing:
            self.db.execute(
                "UPDATE data_registry SET bar_count=?, quality_score=?, start_date=?, end_date=?, "
                "updated_at=datetime('now') WHERE id=?",
                (bar_count, quality, start_date, end_date, data_id),
            )
        else:
            self.db.execute(
                "INSERT INTO data_registry (id, timeframe, source, file_path, start_date, end_date, "
                "bar_count, quality_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (data_id, timeframe, source, file_path, start_date, end_date, bar_count, quality),
            )

    def _refresh_m1_data(self):
        """Append fresh M1 bars from MT5 to the main dataset once a day.

        Keeps the dataset — and therefore the sliding 6-month holdout —
        current, so strategies are always validated against recent market
        behaviour instead of a frozen snapshot.
        """
        main_csv = DATA_DIR / "raw" / "XAUUSD_M1.csv"
        if not main_csv.exists():
            return
        try:
            last_line = None
            with open(main_csv, "rb") as f:
                f.seek(-2048, 2)
                last_line = f.read().decode("utf-8", errors="ignore").strip().splitlines()[-1]
            last_time = pd.to_datetime(last_line.split(",")[0])
        except Exception:
            return

        age_hours = (datetime.now() - last_time).total_seconds() / 3600
        if age_hours < 24:
            return  # fresh enough

        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return
            rates = mt5.copy_rates_range(
                "XAUUSD", mt5.TIMEFRAME_M1,
                last_time.to_pydatetime(), datetime.now(timezone.utc),
            )
            mt5.shutdown()
            if rates is None or len(rates) < 10:
                return

            df_new = pd.DataFrame(rates)
            df_new["time"] = pd.to_datetime(df_new["time"], unit="s")
            df_new = df_new.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "tick_volume": "Volume",
            })
            df_new = df_new[df_new["time"] > last_time]
            if df_new.empty:
                return

            header_cols = pd.read_csv(main_csv, nrows=0).columns.tolist()
            for col in header_cols:
                if col not in df_new.columns:
                    df_new[col] = 0
            df_new[header_cols].to_csv(main_csv, mode="a", header=False, index=False)
            self.emit_event(
                "milestone",
                f"M1 dataset refreshed: +{len(df_new)} bars "
                f"(now through {df_new['time'].iloc[-1]})",
            )
            self.logger.info(f"M1 refresh: appended {len(df_new)} bars")
        except ImportError:
            pass
        except Exception as e:
            self.logger.warning(f"M1 refresh failed: {e}")

    def _try_download_mt5(self):
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                self.emit_event("warning", "MT5 not available, cannot download data")
                return
            self.emit_event("info", "MT5 connected, downloading XAUUSD M1 data")
            from datetime import timedelta
            utc_to = datetime.now(timezone.utc)
            utc_from = utc_to - timedelta(days=365)
            rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M1, utc_from, utc_to)
            mt5.shutdown()
            if rates is None or len(rates) == 0:
                self.emit_event("warning", "MT5 returned no data for XAUUSD M1")
                return
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"})
            out_path = DATA_DIR / "raw" / "XAUUSD_M1_mt5.csv"
            cols = ["time", "Open", "High", "Low", "Close", "Volume", "spread", "real_volume"]
            available_cols = [c for c in cols if c in df.columns]
            df[available_cols].to_csv(out_path, index=False)
            self.emit_event("milestone", f"Downloaded {len(df)} M1 bars from MT5 to {out_path}")
        except ImportError:
            self.emit_event("warning", "MetaTrader5 package not installed")
        except Exception as e:
            self.emit_event("error", f"MT5 download failed: {e}")
