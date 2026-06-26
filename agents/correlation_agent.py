"""Correlation Agent: analyzes inter-strategy correlations and builds diversified portfolios."""
import importlib.util
import json
import traceback
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR


class CorrelationAgent(BaseAgent):
    """Analyzes correlations between validated strategies and builds diversified portfolios."""

    name = "correlation_agent"

    # Thresholds
    HIGH_CORR_THRESHOLD = 0.7   # strategies above this are considered duplicates
    LOW_CORR_THRESHOLD = 0.3    # strategies below this are considered uncorrelated

    def __init__(self, db):
        super().__init__(agent_id="correlation_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Correlation Agent ready")

    def tick(self):
        """Main tick: compute correlations, find clusters, build portfolio."""
        strategies = self._get_validated_strategies()
        if len(strategies) < 2:
            self.logger.info(
                f"Need at least 2 validated strategies for correlation analysis, have {len(strategies)}"
            )
            return

        # Load M1 data
        df = self._load_data()
        if df is None:
            self.logger.warning("No market data available for signal generation")
            return

        # Generate signals for all validated strategies
        signals = self._load_all_signals(strategies, df)
        if len(signals) < 2:
            self.logger.info(f"Could only generate signals for {len(signals)} strategies, need >= 2")
            return

        # Build correlation matrix
        corr_matrix = self._compute_correlation_matrix(signals)
        strategy_ids = list(signals.keys())

        # Store correlation matrix in events
        self._store_correlation_matrix(strategy_ids, corr_matrix)

        # Find clusters of highly correlated strategies
        clusters = self._find_clusters(strategy_ids, corr_matrix)
        if clusters:
            self._tag_redundant_strategies(clusters, strategies)

        # Build diversified portfolio of uncorrelated strategies
        portfolio = self._build_portfolio(strategy_ids, corr_matrix, strategies)
        self._store_portfolio(portfolio)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 600)

    # ──────────────────────────────────────────────────
    # Strategy retrieval
    # ──────────────────────────────────────────────────

    def _get_validated_strategies(self) -> List[dict]:
        """Get all validated strategies that have backtest results."""
        rows = self.db.fetchall(
            "SELECT DISTINCT s.id, s.file_path, s.family, s.best_profit_factor, "
            "s.best_win_rate, s.best_max_drawdown, s.best_x10_count, s.best_config "
            "FROM strategies s "
            "INNER JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'validated'"
        )
        return [dict(row) for row in rows]

    # ──────────────────────────────────────────────────
    # Data loading (mirrors backtest_runner pattern)
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load XAUUSD M1 data from data/raw. Cached after first load."""
        if self._data_cache is not None:
            return self._data_cache

        raw_dir = DATA_DIR / "raw"
        candidates = sorted(raw_dir.glob("XAUUSD_M1*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        self.logger.info(f"Loading data from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])

        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)

        self._data_cache = df
        return df

    # ──────────────────────────────────────────────────
    # Strategy module loading (mirrors backtest_runner pattern)
    # ──────────────────────────────────────────────────

    def _load_strategy_module(self, strategy_id: str, file_path: str):
        """Dynamically load a strategy module. Returns the module or None."""
        candidate_paths = []

        if file_path:
            db_path = Path(file_path)
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)

        candidate_paths.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")

        module_path = None
        for p in candidate_paths:
            if p.exists():
                module_path = p
                break

        if module_path is None:
            self.logger.debug(f"Strategy file not found for {strategy_id}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"strategy_{strategy_id.lower()}", str(module_path)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            self.logger.error(f"Failed to load strategy module {module_path}: {exc}")
            return None

    # ──────────────────────────────────────────────────
    # Signal generation
    # ──────────────────────────────────────────────────

    def _load_all_signals(self, strategies: List[dict], df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Load strategy modules and generate signal series on the same data.

        Returns a dict mapping strategy_id -> signal array (1, -1, 0).
        """
        signals = {}
        for strat in strategies:
            strategy_id = strat["id"]
            file_path = strat.get("file_path", "")
            module = self._load_strategy_module(strategy_id, file_path)
            if module is None:
                continue

            if not hasattr(module, "generate_signals"):
                self.logger.debug(f"Strategy {strategy_id} has no generate_signals function")
                continue

            try:
                params = getattr(module, "PARAMS", {})
                result_df = module.generate_signals(df.copy(), params)
                if "signal" not in result_df.columns:
                    self.logger.debug(f"Strategy {strategy_id} generate_signals has no 'signal' column")
                    continue
                signals[strategy_id] = result_df["signal"].fillna(0).values.astype(float)
            except Exception as exc:
                self.logger.error(f"Signal generation failed for {strategy_id}: {exc}")

        return signals

    # ──────────────────────────────────────────────────
    # Correlation computation
    # ──────────────────────────────────────────────────

    def _compute_correlation_matrix(self, signals: Dict[str, np.ndarray]) -> np.ndarray:
        """
        Compute pairwise Pearson correlation between signal series.

        Returns a 2D numpy array of shape (n, n) where n = len(signals).
        """
        ids = list(signals.keys())
        n = len(ids)
        signal_matrix = np.column_stack([signals[sid] for sid in ids])

        # Build correlation matrix using pandas for NaN handling
        df_signals = pd.DataFrame(signal_matrix, columns=ids)
        corr_df = df_signals.corr(method="pearson")

        # Fill any NaN correlations (e.g. constant signals) with 0
        corr_matrix = corr_df.values
        corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

        return corr_matrix

    # ──────────────────────────────────────────────────
    # Cluster detection
    # ──────────────────────────────────────────────────

    def _find_clusters(
        self, strategy_ids: List[str], corr_matrix: np.ndarray, threshold: float = None
    ) -> List[List[str]]:
        """
        Group strategies with correlation > threshold into clusters.

        Uses a simple union-find approach: if A correlates with B and B with C,
        all three end up in the same cluster.

        Returns a list of clusters, each cluster being a list of strategy IDs
        with at least 2 members.
        """
        if threshold is None:
            threshold = self.HIGH_CORR_THRESHOLD

        n = len(strategy_ids)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i, j in combinations(range(n), 2):
            if abs(corr_matrix[i, j]) > threshold:
                union(i, j)

        # Group by root
        groups: Dict[int, List[str]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(strategy_ids[i])

        # Return only clusters with 2+ members
        return [members for members in groups.values() if len(members) >= 2]

    # ──────────────────────────────────────────────────
    # Redundancy tagging
    # ──────────────────────────────────────────────────

    def _tag_redundant_strategies(self, clusters: List[List[str]], strategies: List[dict]):
        """
        For each cluster, keep the best-performing strategy (highest profit_factor)
        and tag the rest as redundant in their config JSON.
        """
        strat_map = {s["id"]: s for s in strategies}

        for cluster in clusters:
            # Sort by profit factor descending, keep the best
            cluster_strats = [
                (sid, (strat_map.get(sid, {}).get("best_profit_factor") or 0.0))
                for sid in cluster
            ]
            cluster_strats.sort(key=lambda x: x[1], reverse=True)

            best_id = cluster_strats[0][0]
            redundant_ids = [sid for sid, _ in cluster_strats[1:]]

            for sid in redundant_ids:
                # Read current config
                row = self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?", (sid,))
                config = {}
                if row and row["best_config"]:
                    try:
                        config = json.loads(row["best_config"]) if isinstance(row["best_config"], str) else row["best_config"]
                    except (json.JSONDecodeError, TypeError):
                        config = {}

                config["redundant"] = True
                config["redundant_of"] = best_id
                config["redundant_cluster"] = cluster

                self.db.execute(
                    "UPDATE strategies SET best_config = ? WHERE id = ?",
                    (json.dumps(config), sid),
                )

            self.logger.info(
                f"Cluster: best={best_id}, tagged {len(redundant_ids)} as redundant: {redundant_ids}"
            )

    # ──────────────────────────────────────────────────
    # Portfolio construction
    # ──────────────────────────────────────────────────

    def _build_portfolio(
        self,
        strategy_ids: List[str],
        corr_matrix: np.ndarray,
        strategies: List[dict],
        threshold: float = None,
    ) -> List[str]:
        """
        Build a portfolio of uncorrelated strategies (all pairwise correlations < threshold).

        Greedy approach: sort by profit_factor descending, add each strategy if it
        has low correlation with all already-selected strategies.

        Returns a list of strategy IDs in the portfolio.
        """
        if threshold is None:
            threshold = self.LOW_CORR_THRESHOLD

        strat_map = {s["id"]: s for s in strategies}
        id_to_idx = {sid: i for i, sid in enumerate(strategy_ids)}

        # Sort candidates by profit factor descending
        candidates = sorted(
            strategy_ids,
            key=lambda sid: (strat_map.get(sid, {}).get("best_profit_factor") or 0.0),
            reverse=True,
        )

        # Filter out strategies tagged as redundant
        candidates = [
            sid for sid in candidates
            if not self._is_redundant(strat_map.get(sid, {}))
        ]

        portfolio = []
        for sid in candidates:
            idx = id_to_idx[sid]
            # Check correlation with every strategy already in portfolio
            is_uncorrelated = True
            for existing_sid in portfolio:
                existing_idx = id_to_idx[existing_sid]
                if abs(corr_matrix[idx, existing_idx]) >= threshold:
                    is_uncorrelated = False
                    break

            if is_uncorrelated:
                portfolio.append(sid)

        return portfolio

    @staticmethod
    def _is_redundant(strat: dict) -> bool:
        """Check if a strategy dict has been tagged as redundant."""
        config = strat.get("best_config")
        if not config:
            return False
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                return False
        return bool(config.get("redundant"))

    # ──────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────

    def _store_correlation_matrix(self, strategy_ids: List[str], corr_matrix: np.ndarray):
        """Store the correlation matrix as an event with metadata."""
        # Convert to a serialisable dict
        matrix_dict = {}
        for i, sid_a in enumerate(strategy_ids):
            row = {}
            for j, sid_b in enumerate(strategy_ids):
                row[sid_b] = round(float(corr_matrix[i, j]), 4)
            matrix_dict[sid_a] = row

        self.emit_event(
            "info",
            f"Correlation matrix computed for {len(strategy_ids)} strategies",
            metadata={
                "type": "correlation_matrix",
                "strategy_ids": strategy_ids,
                "matrix": matrix_dict,
            },
        )

    def _store_portfolio(self, portfolio: List[str]):
        """Store the portfolio composition as a milestone event."""
        if not portfolio:
            self.logger.info("No uncorrelated portfolio could be built")
            return

        self.emit_event(
            "milestone",
            f"Diversified portfolio built with {len(portfolio)} uncorrelated strategies",
            metadata={
                "type": "portfolio_composition",
                "strategies": portfolio,
                "count": len(portfolio),
            },
        )
        self.logger.info(f"Portfolio: {portfolio}")
