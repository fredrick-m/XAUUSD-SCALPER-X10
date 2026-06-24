# Phase 1: Core Infrastructure & First Agents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation — database, BaseAgent, Orchestrator, Token Manager, Model Router, and Data Agent — so that the system can start, run agents, track costs, and acquire data autonomously.

**Architecture:** A Python daemon (Orchestrator) launches agents as separate threads (not processes — simpler for SQLite sharing). Each agent inherits from BaseAgent which provides DB access, heartbeat, event logging, and LLM calls. All state lives in a single SQLite database with WAL mode for concurrent reads.

**Tech Stack:** Python 3.11+, SQLite (WAL mode), Anthropic SDK, MetaTrader5 Python package, pandas, ta, Flask (dashboard comes in Phase 2)

**Phases Overview:**
- **Phase 1 (this plan):** core/, db, BaseAgent, Orchestrator, Token Manager, Model Router, Data Agent
- **Phase 2:** Backtest Runner (improved engine), Strategy Factory
- **Phase 3:** Evolution Agent, Plugin Scout
- **Phase 4:** Meta Agent, UI Director + Dashboard

---

## File Structure

```
agents/
├── __init__.py              — Package init
├── base_agent.py            — BaseAgent abstract class (heartbeat, DB, LLM, events)
├── orchestrator.py          — Main daemon (launch, monitor, restart agents)
├── token_manager.py         — Track and optimize API costs
├── model_router.py          — Route LLM calls to optimal model
├── data_agent.py            — Acquire and maintain market data
└── dynamic/                 — (empty dir, for future Meta Agent use)

core/
├── __init__.py              — Package init
├── db.py                    — Thread-safe SQLite wrapper, schema init
├── config.py                — System-wide constants and paths
├── logger.py                — Structured logging to file + DB events
└── api_client.py            — Anthropic API client with automatic token tracking

tests/
├── __init__.py
├── test_db.py               — DB schema, CRUD, concurrency
├── test_base_agent.py       — BaseAgent lifecycle, heartbeat, events
├── test_orchestrator.py     — Agent launch, restart, internet check
├── test_token_manager.py    — Token tracking, aggregation
├── test_model_router.py     — Routing logic, fallback
├── test_data_agent.py       — Data download, quality check
└── test_api_client.py       — API client, token recording

start.py                     — Entry point
requirements.txt             — Dependencies
```

---

### Task 1: Dependencies and project setup

**Files:**
- Create: `requirements.txt`
- Create: `start.py` (stub)
- Create: `agents/__init__.py`
- Create: `agents/dynamic/` (empty dir)
- Create: `core/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write requirements.txt**

```txt
anthropic>=0.40.0
MetaTrader5>=5.0.45
pandas>=2.0
numpy>=1.24
ta>=0.11.0
optuna>=3.6
flask>=3.0
plotly>=5.18
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Create package init files**

`core/__init__.py`:
```python
"""Core infrastructure for the multi-agent system."""
```

`agents/__init__.py`:
```python
"""Autonomous trading agents."""
```

`tests/__init__.py`:
```python
"""Tests for the multi-agent system."""
```

- [ ] **Step 3: Create empty dynamic agents directory**

Create `agents/dynamic/__init__.py`:
```python
"""Dynamically created agents (managed by Meta Agent)."""
```

- [ ] **Step 4: Create start.py stub**

```python
"""
XAUUSD-SCALPER-X10 Autonomous Multi-Agent System
Entry point: python start.py
"""


def main():
    print("XAUUSD-SCALPER-X10 Multi-Agent System")
    print("Starting...")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 6: Verify start.py runs**

Run: `python start.py`
Expected: Prints "Starting..."

- [ ] **Step 7: Commit**

```bash
git add requirements.txt start.py core/__init__.py agents/__init__.py agents/dynamic/__init__.py tests/__init__.py
git commit -m "feat: project setup with dependencies and package structure"
```

---

### Task 2: Core config module

**Files:**
- Create: `core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the test**

`tests/test_config.py`:
```python
"""Tests for core.config module."""
import os
from pathlib import Path


def test_base_dir_exists():
    from core.config import BASE_DIR
    assert isinstance(BASE_DIR, Path)
    assert BASE_DIR.exists()


def test_db_path_is_under_base():
    from core.config import BASE_DIR, DB_PATH
    assert str(DB_PATH).startswith(str(BASE_DIR))
    assert DB_PATH.name == "agent_db.sqlite"


def test_data_dir_exists():
    from core.config import DATA_DIR
    assert isinstance(DATA_DIR, Path)


def test_strategies_dir_exists():
    from core.config import STRATEGIES_DIR
    assert isinstance(STRATEGIES_DIR, Path)


def test_core_agents_list():
    from core.config import CORE_AGENTS
    assert isinstance(CORE_AGENTS, list)
    assert len(CORE_AGENTS) >= 3
    names = [a["name"] for a in CORE_AGENTS]
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names


def test_model_constants():
    from core.config import MODELS
    assert "haiku" in MODELS
    assert "sonnet" in MODELS
    assert "opus" in MODELS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

`core/config.py`:
```python
"""System-wide configuration and constants."""
from pathlib import Path

# ── Paths ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "agent_db.sqlite"
DATA_DIR = BASE_DIR / "data"
STRATEGIES_DIR = BASE_DIR / "strategies"
PLUGINS_DIR = BASE_DIR / "plugins"
DYNAMIC_AGENTS_DIR = BASE_DIR / "agents" / "dynamic"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, STRATEGIES_DIR, PLUGINS_DIR, DYNAMIC_AGENTS_DIR, LOG_DIR,
          DATA_DIR / "raw", DATA_DIR / "processed"]:
    d.mkdir(parents=True, exist_ok=True)

# ── Models ─────────────────────────────────────────
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# Cost per 1M tokens (USD) — used by Token Manager
MODEL_COSTS = {
    "claude-haiku-4-5-20251001":  {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":          {"input": 3.00, "output": 15.00},
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
}

# ── Orchestrator ───────────────────────────────────
HEARTBEAT_INTERVAL = 10       # seconds between orchestrator ticks
HEARTBEAT_TIMEOUT = 60        # agent considered dead after this
MAX_AGENT_RESTARTS = 5        # max restarts before disabling
INTERNET_CHECK_URL = "https://api.anthropic.com"
INTERNET_CHECK_INTERVAL = 30  # seconds between connectivity checks when offline

# ── Agent defaults ─────────────────────────────────
DEFAULT_TICK_INTERVAL = 60    # seconds between agent ticks

# ── Core agents to register at startup ─────────────
CORE_AGENTS = [
    {
        "name": "token_manager",
        "module_path": "agents.token_manager",
        "class_name": "TokenManager",
        "config": {"tick_interval": 60},
        "can_spawn_children": False,
    },
    {
        "name": "model_router",
        "module_path": "agents.model_router",
        "class_name": "ModelRouter",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "data_agent",
        "module_path": "agents.data_agent",
        "class_name": "DataAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
]

# ── Backtest defaults ──────────────────────────────
INITIAL_BALANCE = 50.0
PIP_VALUE = 100.0
DEFAULT_RISK_PCT = 0.05
MIN_LOT = 0.001
MAX_LOT = 100.0
DEFAULT_SPREAD = 0.35
SLIPPAGE_PER_FILL = 0.05

# ── Validation thresholds ──────────────────────────
MIN_WIN_RATE = 0.62
MIN_PROFIT_FACTOR = 2.0
MAX_DRAWDOWN = 0.35
MIN_X10_COUNT = 5
MIN_TRADES = 200
MIN_REGIMES = 3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py
git commit -m "feat: add core config module with paths, models, and constants"
```

---

### Task 3: SQLite database layer

**Files:**
- Create: `core/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the tests**

`tests/test_db.py`:
```python
"""Tests for core.db module."""
import os
import tempfile
import threading
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    from core.db import Database
    db_path = tmp_path / "test.sqlite"
    db = Database(db_path)
    db.init_schema()
    yield db
    db.close()


def test_database_creates_file(tmp_path):
    from core.db import Database
    db_path = tmp_path / "test.sqlite"
    db = Database(db_path)
    db.init_schema()
    assert db_path.exists()
    db.close()


def test_schema_creates_all_tables(tmp_db):
    tables = tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in tables}
    expected = {
        "agent_registry", "task_queue", "strategies",
        "backtest_results", "token_usage", "events",
        "data_registry", "plugins",
    }
    assert expected.issubset(table_names)


def test_insert_and_query_agent(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "agents.test", "TestAgent"),
    )
    row = tmp_db.execute("SELECT name FROM agent_registry WHERE id = ?", ("test1",)).fetchone()
    assert row[0] == "test_agent"


def test_insert_event(tmp_db):
    tmp_db.execute(
        "INSERT INTO events (agent_id, event_type, message) VALUES (?, ?, ?)",
        ("agent1", "info", "test event"),
    )
    row = tmp_db.execute("SELECT message FROM events WHERE agent_id = ?", ("agent1",)).fetchone()
    assert row[0] == "test event"


def test_insert_token_usage(tmp_db):
    tmp_db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("agent1", "claude-haiku-4-5-20251001", 100, 200, 0.001, "test"),
    )
    row = tmp_db.execute("SELECT cost_usd FROM token_usage WHERE agent_id = ?", ("agent1",)).fetchone()
    assert row[0] == 0.001


def test_concurrent_writes(tmp_db):
    """Verify WAL mode allows concurrent writes without errors."""
    errors = []

    def writer(agent_id):
        try:
            for i in range(20):
                tmp_db.execute(
                    "INSERT INTO events (agent_id, event_type, message) VALUES (?, ?, ?)",
                    (agent_id, "info", f"msg {i}"),
                )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(f"agent_{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    count = tmp_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 80


def test_upsert_agent_heartbeat(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("a1", "agent1", "agents.a1", "A1"),
    )
    tmp_db.update_heartbeat("a1")
    row = tmp_db.execute("SELECT last_heartbeat FROM agent_registry WHERE id = ?", ("a1",)).fetchone()
    assert row[0] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — cannot import Database

- [ ] **Step 3: Write implementation**

`core/db.py`:
```python
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
        schema = _SCHEMA_SQL
        with self._lock:
            self._conn.executescript(schema)

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
```

Note: In the schema, the column is `event_message` (not `message`) to avoid SQLite keyword conflicts. Update test accordingly:

Replace in `tests/test_db.py` the two occurrences of `message` column name:
- `"INSERT INTO events (agent_id, event_type, message)"` → `"INSERT INTO events (agent_id, event_type, event_message)"`
- `"SELECT message FROM events"` → `"SELECT event_message FROM events"`

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer with full schema and thread safety"
```

---

### Task 4: Structured logger

**Files:**
- Create: `core/logger.py`
- Test: `tests/test_logger.py`

- [ ] **Step 1: Write the test**

`tests/test_logger.py`:
```python
"""Tests for core.logger module."""
import logging
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_get_logger_returns_logger():
    from core.logger import get_logger
    log = get_logger("test_agent")
    assert isinstance(log, logging.Logger)
    assert log.name == "agent.test_agent"


def test_log_event_writes_to_db(tmp_db):
    from core.logger import log_event
    log_event(tmp_db, "agent1", "info", "hello world", {"key": "val"})
    row = tmp_db.fetchone("SELECT * FROM events WHERE agent_id = ?", ("agent1",))
    assert row["event_message"] == "hello world"
    assert row["event_type"] == "info"


def test_log_event_without_metadata(tmp_db):
    from core.logger import log_event
    log_event(tmp_db, "agent1", "warning", "something happened")
    row = tmp_db.fetchone("SELECT * FROM events WHERE agent_id = ?", ("agent1",))
    assert row["event_message"] == "something happened"
    assert row["metadata"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_logger.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`core/logger.py`:
```python
"""Structured logging: file + DB events."""
import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.config import LOG_DIR


def get_logger(name: str) -> logging.Logger:
    """Get a named logger that writes to file and console."""
    logger = logging.getLogger(f"agent.{name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(ch)

    # File handler
    log_file = LOG_DIR / "system.log"
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    ))
    logger.addHandler(fh)

    return logger


def log_event(
    db,
    agent_id: str,
    event_type: str,
    message: str,
    metadata: Optional[dict] = None,
):
    """Write a structured event to the events table."""
    meta_json = json.dumps(metadata) if metadata else None
    db.execute(
        "INSERT INTO events (agent_id, event_type, event_message, metadata) VALUES (?, ?, ?, ?)",
        (agent_id, event_type, message, meta_json),
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_logger.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/logger.py tests/test_logger.py
git commit -m "feat: add structured logger with file and DB event support"
```

---

### Task 5: Anthropic API client with token tracking

**Files:**
- Create: `core/api_client.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the test**

`tests/test_api_client.py`:
```python
"""Tests for core.api_client — token-tracking Anthropic wrapper."""
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_record_usage_writes_to_db(tmp_db):
    from core.api_client import record_usage
    record_usage(
        db=tmp_db,
        agent_id="test_agent",
        model="claude-haiku-4-5-20251001",
        tokens_in=500,
        tokens_out=200,
        task_type="test_call",
        cached_tokens=100,
    )
    row = tmp_db.fetchone("SELECT * FROM token_usage WHERE agent_id = ?", ("test_agent",))
    assert row["tokens_in"] == 500
    assert row["tokens_out"] == 200
    assert row["cost_usd"] > 0


def test_cost_calculation(tmp_db):
    from core.api_client import record_usage
    # Haiku: $0.80/1M in, $4.00/1M out
    record_usage(
        db=tmp_db,
        agent_id="test",
        model="claude-haiku-4-5-20251001",
        tokens_in=1_000_000,
        tokens_out=1_000_000,
        task_type="test",
    )
    row = tmp_db.fetchone("SELECT cost_usd FROM token_usage WHERE agent_id = ?", ("test",))
    assert abs(row["cost_usd"] - 4.80) < 0.01  # $0.80 + $4.00


def test_api_client_init():
    from core.api_client import APIClient
    # Should not raise even without API key (lazy connect)
    client = APIClient(db=None, agent_id="test")
    assert client.agent_id == "test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`core/api_client.py`:
```python
"""Anthropic API client with automatic token usage tracking."""
import os
from typing import Optional

import anthropic

from core.config import MODELS, MODEL_COSTS


def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Compute cost in USD for a given model and token counts."""
    costs = MODEL_COSTS.get(model, {"input": 15.0, "output": 75.0})
    return (tokens_in * costs["input"] + tokens_out * costs["output"]) / 1_000_000


def record_usage(
    db,
    agent_id: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    task_type: str,
    cached_tokens: int = 0,
):
    """Record a single API call's token usage to the database."""
    cost = _compute_cost(model, tokens_in, tokens_out)
    db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type, cached_tokens) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent_id, model, tokens_in, tokens_out, cost, task_type, cached_tokens),
    )


class APIClient:
    """Wrapper around the Anthropic SDK that tracks token usage per call."""

    def __init__(self, db, agent_id: str):
        self.db = db
        self.agent_id = agent_id
        self._client = None  # lazy init

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
        return self._client

    def call(
        self,
        prompt: str,
        model_key: str = "sonnet",
        system: str = "",
        max_tokens: int = 4096,
        task_type: str = "general",
        temperature: float = 0.7,
    ) -> str:
        """Call Claude and record token usage. Returns the text response."""
        model_id = MODELS.get(model_key, model_key)

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        # Extract token counts
        usage = response.usage
        tokens_in = usage.input_tokens
        tokens_out = usage.output_tokens
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Record usage
        if self.db is not None:
            record_usage(
                db=self.db,
                agent_id=self.agent_id,
                model=model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                task_type=task_type,
                cached_tokens=cached,
            )

        # Return text content
        return response.content[0].text
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/api_client.py tests/test_api_client.py
git commit -m "feat: add Anthropic API client with automatic token tracking"
```

---

### Task 6: BaseAgent abstract class

**Files:**
- Create: `agents/base_agent.py`
- Test: `tests/test_base_agent.py`

- [ ] **Step 1: Write the tests**

`tests/test_base_agent.py`:
```python
"""Tests for agents.base_agent."""
import time
import threading

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


class FakeAgent:
    """Concrete agent for testing BaseAgent lifecycle."""

    def __init__(self, db):
        from agents.base_agent import BaseAgent
        # We can't instantiate BaseAgent directly, so we subclass inline
        pass


def _make_agent_class():
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test_agent"

        def __init__(self, db):
            super().__init__(agent_id="test1", db=db)
            self.tick_count = 0
            self.setup_called = False
            self.cleanup_called = False

        def setup(self):
            self.setup_called = True

        def tick(self):
            self.tick_count += 1
            if self.tick_count >= 3:
                self.request_shutdown()

        def tick_interval(self) -> float:
            return 0.01  # fast ticks for testing

        def cleanup(self):
            self.cleanup_called = True

    return TestAgent


def test_agent_lifecycle(tmp_db):
    # Register agent in DB first
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )

    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)

    # Run in thread so we can wait for it
    t = threading.Thread(target=agent.run)
    t.start()
    t.join(timeout=5)

    assert agent.setup_called
    assert agent.cleanup_called
    assert agent.tick_count >= 3


def test_agent_emits_event(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )

    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.emit_event("info", "hello from test")

    row = tmp_db.fetchone(
        "SELECT event_message FROM events WHERE agent_id = ?", ("test1",)
    )
    assert row["event_message"] == "hello from test"


def test_agent_posts_task(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )

    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.post_task("backtest_runner", "backtest", {"strategy_id": "S001"})

    row = tmp_db.fetchone("SELECT * FROM task_queue WHERE agent_target = ?", ("backtest_runner",))
    assert row["task_type"] == "backtest"


def test_agent_heartbeat_updates(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )

    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.update_heartbeat()

    row = tmp_db.fetchone("SELECT last_heartbeat FROM agent_registry WHERE id = ?", ("test1",))
    assert row["last_heartbeat"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`agents/base_agent.py`:
```python
"""Base class for all agents in the multi-agent system."""
import json
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Optional

from core.api_client import APIClient
from core.logger import get_logger, log_event


class BaseAgent(ABC):
    """Abstract base class. Subclasses implement setup(), tick(), cleanup()."""

    name: str = "unnamed_agent"

    def __init__(self, agent_id: str, db):
        self.agent_id = agent_id
        self.db = db
        self.logger = get_logger(self.name)
        self.api = APIClient(db=db, agent_id=agent_id)
        self._shutdown = False

    # ── Abstract methods (subclass must implement) ──

    @abstractmethod
    def setup(self):
        """Called once when agent starts."""

    @abstractmethod
    def tick(self):
        """Called repeatedly — the agent's main work."""

    @abstractmethod
    def tick_interval(self) -> float:
        """Seconds to sleep between ticks."""

    def cleanup(self):
        """Called once on shutdown. Override if needed."""

    # ── Lifecycle ──

    def run(self):
        """Main loop: setup → tick → cleanup. Do not override."""
        self.logger.info(f"Agent {self.name} ({self.agent_id}) starting")
        self.emit_event("info", f"Agent {self.name} started")

        try:
            self.setup()
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.emit_event("error", f"Setup failed: {traceback.format_exc()}")
            return

        while not self._shutdown:
            self.update_heartbeat()
            try:
                self.tick()
            except Exception as e:
                self.logger.error(f"Tick error: {e}")
                self.emit_event("error", f"Tick error: {traceback.format_exc()}")
                self._increment_error_count()
            time.sleep(self.tick_interval())

        self.logger.info(f"Agent {self.name} shutting down")
        try:
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
        self.emit_event("info", f"Agent {self.name} stopped")

    def request_shutdown(self):
        """Signal the agent to stop after current tick."""
        self._shutdown = True

    # ── Communication helpers ──

    def emit_event(self, event_type: str, message: str, metadata: Optional[dict] = None):
        """Write an event to the events table."""
        log_event(self.db, self.agent_id, event_type, message, metadata)

    def post_task(self, target_agent: str, task_type: str, payload: dict, priority: int = 5):
        """Post a task for another agent to consume."""
        self.db.execute(
            "INSERT INTO task_queue (agent_target, task_type, payload, priority, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (target_agent, task_type, json.dumps(payload), priority, self.agent_id),
        )

    def get_pending_tasks(self) -> list:
        """Get pending tasks targeted at this agent, ordered by priority."""
        rows = self.db.fetchall(
            "SELECT * FROM task_queue WHERE agent_target = ? AND status = 'pending' ORDER BY priority, created_at",
            (self.agent_id,),
        )
        return [dict(row) for row in rows]

    def complete_task(self, task_id: int, result: Optional[dict] = None):
        """Mark a task as completed with optional result."""
        result_json = json.dumps(result) if result else None
        self.db.execute(
            "UPDATE task_queue SET status = 'completed', completed_at = datetime('now'), result = ? WHERE id = ?",
            (result_json, task_id),
        )

    def fail_task(self, task_id: int, error: str):
        """Mark a task as failed."""
        self.db.execute(
            "UPDATE task_queue SET status = 'failed', result = ? WHERE id = ?",
            (json.dumps({"error": error}), task_id),
        )

    def update_heartbeat(self):
        """Update last_heartbeat in agent_registry."""
        self.db.update_heartbeat(self.agent_id)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Read a config value from this agent's config JSON."""
        row = self.db.fetchone(
            "SELECT config FROM agent_registry WHERE id = ?", (self.agent_id,)
        )
        if row and row["config"]:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            return config.get(key, default)
        return default

    def set_config(self, key: str, value: Any):
        """Update a config value in this agent's config JSON."""
        row = self.db.fetchone(
            "SELECT config FROM agent_registry WHERE id = ?", (self.agent_id,)
        )
        config = {}
        if row and row["config"]:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        config[key] = value
        self.db.execute(
            "UPDATE agent_registry SET config = ? WHERE id = ?",
            (json.dumps(config), self.agent_id),
        )

    def call_llm(self, prompt: str, model: str = "sonnet", task_type: str = "general", **kwargs) -> str:
        """Call Claude via the API client. Model can be 'haiku', 'sonnet', or 'opus'."""
        return self.api.call(prompt=prompt, model_key=model, task_type=task_type, **kwargs)

    # ── Internal ──

    def _increment_error_count(self):
        self.db.execute(
            "UPDATE agent_registry SET error_count = error_count + 1 WHERE id = ?",
            (self.agent_id,),
        )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_base_agent.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/base_agent.py tests/test_base_agent.py
git commit -m "feat: add BaseAgent with lifecycle, events, tasks, heartbeat, LLM"
```

---

### Task 7: Token Manager agent

**Files:**
- Create: `agents/token_manager.py`
- Test: `tests/test_token_manager.py`

- [ ] **Step 1: Write the tests**

`tests/test_token_manager.py`:
```python
"""Tests for Token Manager agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    # Register the agent
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("token_manager", "token_manager", "agents.token_manager", "TokenManager", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_token_manager_imports():
    from agents.token_manager import TokenManager
    assert TokenManager.name == "token_manager"


def test_aggregate_usage(tmp_db):
    from agents.token_manager import TokenManager

    # Insert some usage data
    for i in range(5):
        tmp_db.execute(
            "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("strategy_factory", "claude-opus-4-6", 1000, 500, 0.09, "generate"),
        )
    for i in range(10):
        tmp_db.execute(
            "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("data_agent", "claude-haiku-4-5-20251001", 200, 100, 0.001, "classify"),
        )

    agent = TokenManager(tmp_db)
    summary = agent.compute_summary()

    assert summary["total_cost"] > 0
    assert summary["total_calls"] == 15
    assert "strategy_factory" in summary["by_agent"]
    assert "data_agent" in summary["by_agent"]


def test_token_manager_tick_no_crash(tmp_db):
    from agents.token_manager import TokenManager
    agent = TokenManager(tmp_db)
    agent.setup()
    agent.tick()  # should not raise even with no data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`agents/token_manager.py`:
```python
"""Token Manager: tracks and optimizes API token consumption."""
import json
from typing import Any

from agents.base_agent import BaseAgent


class TokenManager(BaseAgent):
    name = "token_manager"

    def __init__(self, db):
        super().__init__(agent_id="token_manager", db=db)

    def setup(self):
        self.logger.info("Token Manager ready")

    def tick(self):
        summary = self.compute_summary()
        if summary["total_calls"] > 0:
            self.logger.info(
                f"Tokens — calls: {summary['total_calls']}, "
                f"cost: ${summary['total_cost']:.4f}, "
                f"agents: {len(summary['by_agent'])}"
            )
            # Store summary as event for dashboard consumption
            self.emit_event("info", "token_summary", summary)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 60)

    def compute_summary(self) -> dict:
        """Aggregate token usage across all agents and models."""
        rows = self.db.fetchall(
            "SELECT agent_id, model, "
            "SUM(tokens_in) as total_in, SUM(tokens_out) as total_out, "
            "SUM(cost_usd) as total_cost, COUNT(*) as calls, "
            "SUM(cached_tokens) as cached "
            "FROM token_usage GROUP BY agent_id, model"
        )

        by_agent = {}
        by_model = {}
        total_cost = 0.0
        total_calls = 0
        total_cached = 0

        for row in rows:
            agent_id = row["agent_id"]
            model = row["model"]
            cost = row["total_cost"] or 0
            calls = row["calls"] or 0
            cached = row["cached"] or 0

            # By agent
            if agent_id not in by_agent:
                by_agent[agent_id] = {"cost": 0, "calls": 0}
            by_agent[agent_id]["cost"] += cost
            by_agent[agent_id]["calls"] += calls

            # By model
            if model not in by_model:
                by_model[model] = {"cost": 0, "calls": 0}
            by_model[model]["cost"] += cost
            by_model[model]["calls"] += calls

            total_cost += cost
            total_calls += calls
            total_cached += cached

        return {
            "total_cost": round(total_cost, 6),
            "total_calls": total_calls,
            "total_cached_tokens": total_cached,
            "by_agent": by_agent,
            "by_model": by_model,
        }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_manager.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/token_manager.py tests/test_token_manager.py
git commit -m "feat: add Token Manager agent for API cost tracking"
```

---

### Task 8: Model Router agent

**Files:**
- Create: `agents/model_router.py`
- Test: `tests/test_model_router.py`

- [ ] **Step 1: Write the tests**

`tests/test_model_router.py`:
```python
"""Tests for Model Router agent."""
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("model_router", "model_router", "agents.model_router", "ModelRouter", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_route_generate_strategy():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("generate_strategy")
    assert model == "opus"


def test_route_syntax_check():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("syntax_check")
    assert model == "haiku"


def test_route_analyze_results():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("analyze_results")
    assert model == "sonnet"


def test_route_unknown_defaults_to_sonnet():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("something_unknown")
    assert model == "sonnet"


def test_model_router_tick_no_crash(tmp_db):
    from agents.model_router import ModelRouter
    agent = ModelRouter(tmp_db)
    agent.setup()
    agent.tick()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model_router.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`agents/model_router.py`:
```python
"""Model Router: picks the optimal Claude model for each task type."""
from agents.base_agent import BaseAgent

# Default routing table — Model Router evolves this over time
_ROUTING_TABLE = {
    # Cheap tasks → Haiku
    "syntax_check": "haiku",
    "parse_data": "haiku",
    "classify": "haiku",
    "format": "haiku",
    "quality_check": "haiku",
    # Medium tasks → Sonnet
    "analyze_results": "sonnet",
    "evaluate_plugin": "sonnet",
    "debug_strategy": "sonnet",
    "summarize": "sonnet",
    # Expensive tasks → Opus
    "generate_strategy": "opus",
    "meta_decision": "opus",
    "create_agent": "opus",
    "complex_analysis": "opus",
}

_DEFAULT_MODEL = "sonnet"


class ModelRouter(BaseAgent):
    name = "model_router"

    def __init__(self, db):
        super().__init__(agent_id="model_router", db=db)

    def setup(self):
        self.logger.info("Model Router ready")

    def tick(self):
        # Analyze success rates per model per task and adjust routing
        # For now: log current routing table stats
        rows = self.db.fetchall(
            "SELECT model, task_type, COUNT(*) as calls, AVG(tokens_out) as avg_out "
            "FROM token_usage GROUP BY model, task_type"
        )
        if rows:
            self.logger.debug(f"Model usage: {len(rows)} task/model combos tracked")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    @staticmethod
    def route_task(task_type: str) -> str:
        """Return the model key ('haiku', 'sonnet', 'opus') for a given task type."""
        return _ROUTING_TABLE.get(task_type, _DEFAULT_MODEL)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_model_router.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/model_router.py tests/test_model_router.py
git commit -m "feat: add Model Router agent with task-based model selection"
```

---

### Task 9: Data Agent

**Files:**
- Create: `agents/data_agent.py`
- Test: `tests/test_data_agent.py`

- [ ] **Step 1: Write the tests**

`tests/test_data_agent.py`:
```python
"""Tests for Data Agent."""
import csv
import pytest
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("data_agent", "data_agent", "agents.data_agent", "DataAgent", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_data_agent_imports():
    from agents.data_agent import DataAgent
    assert DataAgent.name == "data_agent"


def test_check_existing_data(tmp_db):
    """DataAgent should detect existing M1 data files."""
    from agents.data_agent import DataAgent
    agent = DataAgent(tmp_db)
    inventory = agent.scan_existing_data()
    # Should return a list (possibly empty if no data on disk for test)
    assert isinstance(inventory, list)


def test_quality_check_on_sample_data(tmp_path, tmp_db):
    """Quality check should score a clean CSV highly."""
    from agents.data_agent import DataAgent, quality_score

    # Write a small clean CSV
    csv_path = tmp_path / "sample.csv"
    rows = []
    for i in range(100):
        rows.append({
            "time": f"2025-01-01 00:{i // 60:02d}:{i % 60:02d}",
            "Open": 2000 + i * 0.1,
            "High": 2000 + i * 0.1 + 0.5,
            "Low": 2000 + i * 0.1 - 0.3,
            "Close": 2000 + i * 0.1 + 0.2,
            "Volume": 100 + i,
        })
    import pandas as pd
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    score = quality_score(csv_path)
    assert score >= 0.8  # clean data should score high


def test_register_data_in_db(tmp_db):
    """DataAgent should register discovered data in data_registry."""
    from agents.data_agent import DataAgent
    agent = DataAgent(tmp_db)
    agent.register_data(
        data_id="xauusd_m1_mt5",
        timeframe="M1",
        source="MT5",
        file_path="/fake/path.csv",
        start_date="2025-01-01",
        end_date="2025-12-31",
        bar_count=100000,
        quality=0.95,
    )
    row = tmp_db.fetchone("SELECT * FROM data_registry WHERE id = ?", ("xauusd_m1_mt5",))
    assert row["timeframe"] == "M1"
    assert row["bar_count"] == 100000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`agents/data_agent.py`:
```python
"""Data Agent: acquires, maintains, and quality-checks market data."""
import hashlib
import json
from datetime import datetime
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
        df = pd.read_csv(file_path, parse_dates=["time"] if "time" in pd.read_csv(file_path, nrows=0).columns else [0])
    except Exception:
        return 0.0

    if len(df) < 10:
        return 0.0

    score = 1.0

    # Check for NaN values
    nan_pct = df.isnull().sum().sum() / (len(df) * len(df.columns))
    score -= nan_pct * 0.5

    # Check for duplicate timestamps
    time_col = "time" if "time" in df.columns else df.columns[0]
    dup_pct = df[time_col].duplicated().sum() / len(df)
    score -= dup_pct * 0.3

    # Check for price anomalies (> 5 std dev moves)
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
        # 1. Scan for any new/updated data files
        existing = self.scan_existing_data()

        # 2. Check if we need more data
        total_m1_bars = sum(e["bars"] for e in existing if e["timeframe"] == "M1")
        if total_m1_bars < 250_000:  # < ~1 year
            self.emit_event("warning", f"Only {total_m1_bars} M1 bars available, need 250k+")
            self._try_download_mt5()

        # 3. Register/update data in DB
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
        """Scan data/raw/ for CSV files and assess each."""
        raw_dir = DATA_DIR / "raw"
        results = []

        if not raw_dir.exists():
            return results

        for csv_file in sorted(raw_dir.glob("*.csv")):
            try:
                # Quick read to get row count and date range
                df = pd.read_csv(csv_file, nrows=5)
                total_rows = sum(1 for _ in open(csv_file, encoding="utf-8")) - 1  # minus header

                # Detect timeframe from filename
                fname = csv_file.stem.upper()
                if "M1" in fname:
                    tf = "M1"
                elif "M5" in fname:
                    tf = "M5"
                elif "H1" in fname:
                    tf = "H1"
                else:
                    tf = "UNKNOWN"

                # Get date range
                time_col = "time" if "time" in df.columns else df.columns[0]
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

    def register_data(
        self,
        data_id: str,
        timeframe: str,
        source: str,
        file_path: str,
        start_date: Optional[str],
        end_date: Optional[str],
        bar_count: int,
        quality: float,
    ):
        """Register or update a dataset in the data_registry table."""
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

    def _try_download_mt5(self):
        """Attempt to download data from MetaTrader 5."""
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                self.emit_event("warning", "MT5 not available, cannot download data")
                return

            self.emit_event("info", "MT5 connected, downloading XAUUSD M1 data")

            from datetime import datetime, timedelta
            utc_to = datetime.utcnow()
            utc_from = utc_to - timedelta(days=365)  # 1 year

            rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M1, utc_from, utc_to)
            mt5.shutdown()

            if rates is None or len(rates) == 0:
                self.emit_event("warning", "MT5 returned no data for XAUUSD M1")
                return

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "tick_volume": "Volume",
            })

            out_path = DATA_DIR / "raw" / "XAUUSD_M1_mt5.csv"
            cols = ["time", "Open", "High", "Low", "Close", "Volume", "spread", "real_volume"]
            available_cols = [c for c in cols if c in df.columns]
            df[available_cols].to_csv(out_path, index=False)

            self.emit_event("milestone", f"Downloaded {len(df)} M1 bars from MT5 to {out_path}")
            self.logger.info(f"Downloaded {len(df)} bars from MT5")

        except ImportError:
            self.emit_event("warning", "MetaTrader5 package not installed")
        except Exception as e:
            self.emit_event("error", f"MT5 download failed: {e}")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_data_agent.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/data_agent.py tests/test_data_agent.py
git commit -m "feat: add Data Agent with MT5 download, quality scoring, and registry"
```

---

### Task 10: Orchestrator

**Files:**
- Create: `agents/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the tests**

`tests/test_orchestrator.py`:
```python
"""Tests for the Orchestrator daemon."""
import threading
import time
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_orchestrator_imports():
    from agents.orchestrator import Orchestrator
    assert Orchestrator is not None


def test_register_core_agents(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()

    agents = tmp_db.fetchall("SELECT name FROM agent_registry")
    names = {row["name"] for row in agents}
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names


def test_check_internet():
    from agents.orchestrator import check_internet
    # Should return True or False without crashing
    result = check_internet()
    assert isinstance(result, bool)


def test_orchestrator_start_and_stop(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()

    # Start in thread, let it run briefly, then stop
    t = threading.Thread(target=orch.run)
    t.start()
    time.sleep(2)
    orch.shutdown()
    t.join(timeout=10)

    assert not t.is_alive()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

`agents/orchestrator.py`:
```python
"""Orchestrator: main daemon that launches, monitors, and restarts agents."""
import importlib
import json
import signal
import threading
import time
from typing import Dict, Optional

import requests

from core.config import CORE_AGENTS, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, MAX_AGENT_RESTARTS, INTERNET_CHECK_URL
from core.db import Database
from core.logger import get_logger, log_event


def check_internet(url: str = INTERNET_CHECK_URL, timeout: float = 5) -> bool:
    """Check if internet is available."""
    try:
        requests.head(url, timeout=timeout)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


class Orchestrator:
    """Main daemon: registers, launches, monitors, and restarts agents."""

    def __init__(self, db: Database):
        self.db = db
        self.logger = get_logger("orchestrator")
        self._shutdown = False
        self._agent_threads: Dict[str, threading.Thread] = {}
        self._agent_instances: Dict[str, object] = {}

    def register_core_agents(self):
        """Register all core agents in the database if not already present."""
        for agent_def in CORE_AGENTS:
            existing = self.db.fetchone(
                "SELECT id FROM agent_registry WHERE name = ?", (agent_def["name"],)
            )
            if not existing:
                self.db.execute(
                    "INSERT INTO agent_registry (id, name, module_path, class_name, config, can_spawn_children) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        agent_def["name"],
                        agent_def["name"],
                        agent_def["module_path"],
                        agent_def["class_name"],
                        json.dumps(agent_def.get("config", {})),
                        agent_def.get("can_spawn_children", False),
                    ),
                )
                self.logger.info(f"Registered agent: {agent_def['name']}")

    def _load_agent(self, agent_row) -> Optional[object]:
        """Dynamically import and instantiate an agent from its registry entry."""
        try:
            module = importlib.import_module(agent_row["module_path"])
            agent_class = getattr(module, agent_row["class_name"])
            return agent_class(self.db)
        except Exception as e:
            self.logger.error(f"Failed to load agent {agent_row['name']}: {e}")
            log_event(self.db, agent_row["id"], "error", f"Load failed: {e}")
            return None

    def _start_agent(self, agent_row):
        """Start a single agent in its own thread."""
        agent_id = agent_row["id"]

        if agent_id in self._agent_threads and self._agent_threads[agent_id].is_alive():
            return  # already running

        agent = self._load_agent(agent_row)
        if agent is None:
            return

        self._agent_instances[agent_id] = agent

        thread = threading.Thread(
            target=agent.run,
            name=f"agent-{agent_id}",
            daemon=True,
        )
        thread.start()
        self._agent_threads[agent_id] = thread

        self.db.execute(
            "UPDATE agent_registry SET status = 'running' WHERE id = ?",
            (agent_id,),
        )
        self.logger.info(f"Started agent: {agent_id}")

    def _stop_agent(self, agent_id: str):
        """Stop an agent gracefully."""
        if agent_id in self._agent_instances:
            self._agent_instances[agent_id].request_shutdown()
            thread = self._agent_threads.get(agent_id)
            if thread:
                thread.join(timeout=10)
            self.db.execute(
                "UPDATE agent_registry SET status = 'stopped' WHERE id = ?",
                (agent_id,),
            )
            self.logger.info(f"Stopped agent: {agent_id}")

    def _check_agents(self):
        """Check all running agents, restart dead ones."""
        agents = self.db.fetchall(
            "SELECT * FROM agent_registry WHERE status IN ('running', 'stopped')"
        )

        for agent_row in agents:
            agent_id = agent_row["id"]
            thread = self._agent_threads.get(agent_id)

            if agent_row["status"] == "running" and (thread is None or not thread.is_alive()):
                # Agent died
                restart_count = agent_row["restart_count"] or 0
                if restart_count < MAX_AGENT_RESTARTS:
                    self.logger.warning(f"Agent {agent_id} died, restarting ({restart_count + 1}/{MAX_AGENT_RESTARTS})")
                    self.db.execute(
                        "UPDATE agent_registry SET restart_count = restart_count + 1 WHERE id = ?",
                        (agent_id,),
                    )
                    self._start_agent(agent_row)
                else:
                    self.logger.error(f"Agent {agent_id} exceeded max restarts, disabling")
                    self.db.execute(
                        "UPDATE agent_registry SET status = 'disabled' WHERE id = ?",
                        (agent_id,),
                    )
                    log_event(self.db, agent_id, "error", "Agent disabled after max restarts")

            elif agent_row["status"] == "stopped" and agent_row.get("created_by") is not None:
                # Dynamically created agent that should be running
                pass  # Meta Agent will handle this

    def run(self):
        """Main orchestrator loop."""
        self.logger.info("=" * 60)
        self.logger.info("XAUUSD-SCALPER-X10 Autonomous Multi-Agent System")
        self.logger.info("=" * 60)

        log_event(self.db, "orchestrator", "milestone", "System starting")

        # Start all registered agents
        agents = self.db.fetchall(
            "SELECT * FROM agent_registry WHERE status != 'disabled'"
        )
        for agent_row in agents:
            self._start_agent(agent_row)

        # Main loop
        internet_was_down = False
        while not self._shutdown:
            # Internet check
            if not check_internet():
                if not internet_was_down:
                    self.logger.warning("Internet connection lost — pausing agents")
                    log_event(self.db, "orchestrator", "warning", "Internet lost")
                    internet_was_down = True
                time.sleep(30)
                continue
            elif internet_was_down:
                self.logger.info("Internet restored — resuming")
                log_event(self.db, "orchestrator", "info", "Internet restored")
                internet_was_down = False

            # Check agent health
            self._check_agents()

            time.sleep(HEARTBEAT_INTERVAL)

        # Shutdown
        self.logger.info("Orchestrator shutting down...")
        for agent_id in list(self._agent_instances.keys()):
            self._stop_agent(agent_id)
        log_event(self.db, "orchestrator", "milestone", "System stopped")
        self.logger.info("All agents stopped. Goodbye.")

    def shutdown(self):
        """Signal the orchestrator to stop."""
        self._shutdown = True
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add Orchestrator daemon with agent lifecycle management"
```

---

### Task 11: Wire up start.py entry point

**Files:**
- Modify: `start.py`

- [ ] **Step 1: Write the final start.py**

`start.py`:
```python
"""
XAUUSD-SCALPER-X10 Autonomous Multi-Agent System
=================================================
Entry point: python start.py

Starts the Orchestrator daemon which launches all agents.
The system runs continuously until interrupted (Ctrl+C).
"""
import signal
import sys

from core.config import DB_PATH
from core.db import Database
from agents.orchestrator import Orchestrator


def main():
    print("=" * 60)
    print("  XAUUSD-SCALPER-X10")
    print("  Autonomous Multi-Agent Backtesting System")
    print("=" * 60)
    print()

    # Initialize database
    print("[1/3] Initializing database...")
    db = Database(DB_PATH)
    db.init_schema()
    print(f"  DB: {DB_PATH}")

    # Create orchestrator
    print("[2/3] Registering core agents...")
    orch = Orchestrator(db)
    orch.register_core_agents()

    # Handle Ctrl+C
    def handle_sigint(sig, frame):
        print("\n\nShutdown requested (Ctrl+C)...")
        orch.shutdown()

    signal.signal(signal.SIGINT, handle_sigint)

    # Start
    print("[3/3] Starting orchestrator...")
    print()
    orch.run()

    db.close()
    print("System terminated.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it starts and can be stopped**

Run: `python start.py`
Expected: System starts, agents begin ticking, Ctrl+C stops gracefully

- [ ] **Step 3: Commit**

```bash
git add start.py
git commit -m "feat: wire up start.py entry point for the multi-agent system"
```

---

### Task 12: Run all tests and verify everything works together

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (approximately 26 tests)

- [ ] **Step 2: Run the system for 30 seconds**

Run: `timeout 30 python start.py || true`
Expected: System starts, agents tick, no crashes. Data Agent scans existing data files.

- [ ] **Step 3: Verify database was populated**

Run: `python -c "from core.db import Database; from core.config import DB_PATH; db=Database(DB_PATH); print([dict(r) for r in db.fetchall('SELECT name, status FROM agent_registry')]); db.close()"`
Expected: Shows 3 agents with status 'running' or 'stopped'

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: integration fixes from end-to-end test"
```

---

## What Phase 1 delivers

After completing these 12 tasks, you have:
- A running daemon (`python start.py`) that launches 3 agents
- **Token Manager** tracking every API call's cost
- **Model Router** selecting the right model per task type
- **Data Agent** scanning existing data + downloading from MT5
- SQLite database with full schema for all future agents
- BaseAgent class — any new agent is just a subclass with `setup()`, `tick()`, `cleanup()`
- Heartbeat monitoring + automatic restart of crashed agents
- Internet connectivity detection with graceful pause/resume

## Next phases

- **Phase 2:** Backtest Runner (improved engine with trailing stop, time exit) + Strategy Factory (Claude-generated strategies)
- **Phase 3:** Evolution Agent (Optuna optimization, genetic crossover) + Plugin Scout
- **Phase 4:** Meta Agent (self-expanding) + UI Director (Flask dashboard)
