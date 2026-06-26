"""Register all existing strategy files in the database for backtesting."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import DB_PATH, STRATEGIES_DIR
from core.db import Database


def register_all():
    db = Database(DB_PATH)
    db.init_schema()

    registered = 0

    # Root strategies: strategy_s001.py .. strategy_s050.py
    for f in sorted(STRATEGIES_DIR.glob("strategy_s*.py")):
        sid = f.stem.replace("strategy_", "").upper()
        _register(db, sid, str(f), "root")
        registered += 1

    # Batch2: b001.py .. b050.py
    batch2 = STRATEGIES_DIR / "batch2"
    if batch2.exists():
        for f in sorted(batch2.glob("b*.py")):
            sid = f.stem.upper()
            _register(db, sid, str(f), "batch2")
            registered += 1

    # Batch3: individual strategies
    batch3 = STRATEGIES_DIR / "batch3"
    if batch3.exists():
        for f in sorted(batch3.glob("*.py")):
            if f.stem.startswith("__"):
                continue
            sid = f.stem.upper()
            _register(db, sid, str(f), "batch3")
            registered += 1

    total = db.fetchone("SELECT COUNT(*) as c FROM strategies")["c"]
    candidates = db.fetchone("SELECT COUNT(*) as c FROM strategies WHERE status = 'candidate'")["c"]
    db.close()

    print(f"Registered {registered} strategies ({candidates} candidates ready for backtest)")
    print(f"Total in DB: {total}")


def _register(db, strategy_id, file_path, family):
    existing = db.fetchone("SELECT id FROM strategies WHERE id = ?", (strategy_id,))
    if existing:
        return
    db.execute(
        "INSERT INTO strategies (id, file_path, family, description, created_by, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (strategy_id, file_path, family, f"Pre-built {family} strategy", "manual", "candidate"),
    )


if __name__ == "__main__":
    register_all()
