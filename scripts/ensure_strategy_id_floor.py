"""Reserve runtime strategy IDs above every strategy file already on disk.

The research agents allocate E/T identifiers from the SQLite registry. A fresh
or rebuilt database can otherwise start again at E0001/T00001 and overwrite
strategy files shipped by Git. This guard scans the strategy directory and
inserts harmless retired reservation rows at the current file maxima so the
next runtime IDs are always above them.

Safe to run repeatedly. It never modifies an existing strategy row or file.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.config import DB_PATH, STRATEGIES_DIR
from core.db import Database

_PATTERNS = {
    "E": re.compile(r"^strategy_e(\d+)\.py$", re.IGNORECASE),
    "T": re.compile(r"^strategy_t(\d+)\.py$", re.IGNORECASE),
}


def _max_file_id(prefix: str) -> tuple[int, Path | None]:
    rx = _PATTERNS[prefix]
    best_num = 0
    best_path: Path | None = None
    if not STRATEGIES_DIR.exists():
        return best_num, best_path
    for path in STRATEGIES_DIR.iterdir():
        if not path.is_file():
            continue
        match = rx.match(path.name)
        if not match:
            continue
        num = int(match.group(1))
        if num > best_num:
            best_num = num
            best_path = path
    return best_num, best_path


def _reserve(db: Database, prefix: str, number: int, path: Path | None) -> None:
    if number <= 0 or path is None:
        return
    width = 4 if prefix == "E" else 5
    strategy_id = f"{prefix}{number:0{width}d}"
    # Never overwrite a real row. The reservation only matters when the file
    # maximum is not already represented in the registry.
    db.execute(
        "INSERT OR IGNORE INTO strategies "
        "(id,file_path,family,description,created_by,status) "
        "VALUES (?,?,?,?,?,?)",
        (
            strategy_id,
            str(path),
            "id_reservation",
            "Reserved strategy ID floor from files on disk; do not backtest",
            "system",
            "retired",
        ),
    )
    print(f"{prefix}_id_floor={strategy_id} file={path.name}")


def main() -> int:
    db = Database(DB_PATH)
    try:
        db.init_schema()
        for prefix in ("E", "T"):
            number, path = _max_file_id(prefix)
            _reserve(db, prefix, number, path)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
