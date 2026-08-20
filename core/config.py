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
        "config": {"tick_interval": 5},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_factory",
        "module_path": "agents.strategy_factory",
        "class_name": "StrategyFactory",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    {
        "name": "template_factory",
        "module_path": "agents.template_factory",
        "class_name": "TemplateFactory",
        "config": {"tick_interval": 15, "batch_size": 20},
        "can_spawn_children": False,
    },
    {
        "name": "evolution_agent",
        "module_path": "agents.evolution_agent",
        "class_name": "EvolutionAgent",
        "config": {"tick_interval": 60},
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
    # ── Tier 1: Quality & Robustness ──────────────────
    {
        "name": "regime_filter",
        "module_path": "agents.regime_filter",
        "class_name": "RegimeFilter",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "monte_carlo",
        "module_path": "agents.monte_carlo",
        "class_name": "MonteCarlo",
        "config": {
            "tick_interval": 300,
            "n_simulations": 10000,
            "initial_balance": 500.0,
            "horizon_days": 10,
            "target_multiple": 10.0,
        },
        "can_spawn_children": False,
    },
    {
        "name": "correlation_agent",
        "module_path": "agents.correlation_agent",
        "class_name": "CorrelationAgent",
        "config": {"tick_interval": 600},
        "can_spawn_children": False,
    },
    {
        "name": "ensemble_agent",
        "module_path": "agents.ensemble_agent",
        "class_name": "EnsembleAgent",
        "config": {"tick_interval": 900},
        "can_spawn_children": False,
    },
    # ── Tier 2: Anti-overfitting ──────────────────────
    {
        "name": "sensitivity_agent",
        "module_path": "agents.sensitivity_agent",
        "class_name": "SensitivityAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "news_calendar",
        "module_path": "agents.news_calendar",
        "class_name": "NewsCalendarAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "multi_timeframe",
        "module_path": "agents.multi_timeframe",
        "class_name": "MultiTimeframeAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    # ── Tier 3: Live Trading & Reporting ──────────────
    {
        "name": "signal_gatekeeper",
        "module_path": "agents.signal_gatekeeper",
        "class_name": "SignalGatekeeper",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "risk_manager",
        "module_path": "agents.risk_manager",
        "class_name": "RiskManager",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "paper_trade",
        "module_path": "agents.paper_trade",
        "class_name": "PaperTradeAgent",
        "config": {"tick_interval": 60},
        "can_spawn_children": False,
    },
    {
        "name": "trade_supervisor",
        "module_path": "agents.trade_supervisor",
        "class_name": "TradeSupervisor",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "report_agent",
        "module_path": "agents.report_agent",
        "class_name": "ReportAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    # ── Tier 4: Learning & Optimization ──────────────
    {
        "name": "param_optimizer",
        "module_path": "agents.param_optimizer",
        "class_name": "ParamOptimizer",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_analyzer",
        "module_path": "agents.strategy_analyzer",
        "class_name": "StrategyAnalyzer",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    # ── Tier 5: Memory & Knowledge ───────────────────
    {
        "name": "knowledge_base_agent",
        "module_path": "agents.knowledge_base_agent",
        "class_name": "KnowledgeBaseAgent",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
]

# ── Knowledge Base (Obsidian vault) ───────────────
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"

# ── Research objective ─────────────────────────────
# The project evaluates whether a strategy/portfolio can plausibly compound a
# $500 account to $5,000 in 10 trading days. These constants define the research
# target; they are NOT a promise that live trading can achieve it.
INITIAL_BALANCE = 500.0
X10_TARGET_MULTIPLE = 10.0
X10_HORIZON_DAYS = 10
X10_TARGET_BALANCE = INITIAL_BALANCE * X10_TARGET_MULTIPLE
# Monte Carlo calls an account "ruined" once 80% of starting capital is lost.
MC_RUIN_BALANCE_FRACTION = 0.20

# ── Backtest defaults ──────────────────────────────
PIP_VALUE = 100.0
DEFAULT_RISK_PCT = 0.04
MIN_LOT = 0.01
MAX_LOT = 100.0
DEFAULT_SPREAD = 0.35
SLIPPAGE_PER_FILL = 0.05

# ── Validation thresholds (M1) ─────────────────────
MIN_WIN_RATE = 0.62
MIN_PROFIT_FACTOR = 2.0
MAX_DRAWDOWN = 0.35
MIN_X10_COUNT = 5
MIN_TRADES = 200
MIN_REGIMES = 3

# ── Validation thresholds (M5) ─────────────────────
# MIN_TRADES 100: with thousands of strategies tested on the same dataset,
# small samples pass by pure chance (multiple-testing bias).
M5_MIN_WIN_RATE = 0.60
M5_MIN_PROFIT_FACTOR = 1.3
M5_MAX_DRAWDOWN = 0.25
M5_MIN_X10_COUNT = 0
M5_MIN_TRADES = 100
M5_MIN_REGIMES = 2

# ── Probation tier ─────────────────────────────────
PROBATION_MIN_TRADES = 30
PROBATION_MIN_PF = 1.6
PROBATION_MAX_DD = 0.20
PROBATION_MIN_WR_LB = 0.50
PROBATION_HOLDOUT_MIN_TRADES = 5
PROBATION_HOLDOUT_MIN_PF = 1.0

# ── Final holdout (never used for selection) ───────
HOLDOUT_MONTHS = 6
HOLDOUT_MIN_PF = 1.2
HOLDOUT_MIN_TRADES = 15

# ── Family robustness gate (deployment filter) ─────
FAMILY_MIN_TESTED = 5
FAMILY_MIN_GOOD_RATIO = 0.4

# ── Portfolio diversification (execution-time) ─────
FAMILY_MAX_OPEN = 2

# ── Edge decay defense: periodic re-validation ─────
REVALIDATION_DAYS = 7

# ── Backtest vs live divergence tracking ───────────
DIVERGENCE_MIN_TRADES = 20
DIVERGENCE_MAX_WR_DROP = 0.15
DIVERGENCE_MIN_PF_RATIO = 0.5
