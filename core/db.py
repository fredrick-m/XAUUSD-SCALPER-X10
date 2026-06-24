"""Thread-safe SQLite database wrapper for the multi-agent system."""
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional


class Database:
    """Thread-safe SQLite wrapper using WAL mode and a shared lock."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute SQL with thread safety. Auto-commits writes."""
        with self._lock:
            cursor = self._conn.execute(sql, params)
            if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")):
                self._conn.commit()
            return cursor

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Execute SQL for multiple param sets."""
        with self._lock:
            cursor = self._conn.executemany(sql, params_list)
            self._conn.commit()
            return cursor

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute and fetch one row."""
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute and fetch all rows."""
        return self.execute(sql, params).fetchall()

    def update_heartbeat(self, agent_id: str):
        """Update agent's last_heartbeat to now."""
        self.execute(
            "UPDATE agent_registry SET last_heartbeat = datetime('now') WHERE id = ?",
            (agent_id,),
        )

    def init_schema(self):
        """Create all tables if they don't exist."""
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self):
        """Close the database connection."""
        with self._lock:
            self._conn.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    module_path TEXT NOT NULL,
    class_name TEXT NOT NULL,
    status TEXT DEFAULT 'stopped',
    parent_agent TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON DEFAULT '{}',
    can_spawn_children BOOLEAN DEFAULT 0,
    last_heartbeat TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    restart_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_target TEXT NOT NULL,
    task_type TEXT NOT NULL,
    payload JSON NOT NULL,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result JSON
);

CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    family TEXT,
    description TEXT,
    generation INTEGER DEFAULT 1,
    parent_strategy TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'candidate',
    best_win_rate REAL,
    best_profit_factor REAL,
    best_max_drawdown REAL,
    best_x10_count INTEGER DEFAULT 0,
    best_final_balance REAL,
    regimes_passed INTEGER DEFAULT 0,
    walk_forward_passed BOOLEAN DEFAULT 0,
    best_config JSON
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    risk_pct REAL,
    config JSON,
    total_trades INTEGER,
    win_rate REAL,
    profit_factor REAL,
    max_drawdown REAL,
    x10_count INTEGER,
    final_balance REAL,
    return_pct REAL,
    blown_account BOOLEAN,
    regime_results JSON,
    walk_forward BOOLEAN DEFAULT 0,
    data_hash TEXT,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    task_type TEXT,
    cached_tokens INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    event_message TEXT NOT NULL,
    metadata JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_registry (
    id TEXT PRIMARY KEY,
    instrument TEXT DEFAULT 'XAUUSD',
    timeframe TEXT NOT NULL,
    source TEXT,
    file_path TEXT NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    bar_count INTEGER,
    quality_score REAL,
    regime_labeled BOOLEAN DEFAULT 0,
    hash TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT,
    install_type TEXT,
    status TEXT DEFAULT 'installed',
    installed_by TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    used_by JSON DEFAULT '[]'
);
"""
