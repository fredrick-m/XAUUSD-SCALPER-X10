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
HEARTBEAT_INTERVAL = 10
HEARTBEAT_TIMEOUT = 60
MAX_AGENT_RESTARTS = 5
INTERNET_CHECK_URL = "https://api.anthropic.com"
INTERNET_CHECK_INTERVAL = 30

# ── Agent defaults ─────────────────────────────────
DEFAULT_TICK_INTERVAL = 60
DASHBOARD_PORT = 8050

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
    {
        "name": "backtest_runner",
        "module_path": "agents.backtest_runner",
        "class_name": "BacktestRunner",
        "config": {"tick_interval": 10},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_factory",
        "module_path": "agents.strategy_factory",
        "class_name": "StrategyFactory",
        "config": {"tick_interval": 600},
        "can_spawn_children": False,
    },
    {
        "name": "evolution_agent",
        "module_path": "agents.evolution_agent",
        "class_name": "EvolutionAgent",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "plugin_scout",
        "module_path": "agents.plugin_scout",
        "class_name": "PluginScout",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "ui_director",
        "module_path": "agents.ui_director",
        "class_name": "UIDirector",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "meta_agent",
        "module_path": "agents.meta_agent",
        "class_name": "MetaAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": True,
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
