"""Chronological out-of-sample validation rules for X10 research.

These helpers are deliberately independent from MT5 and the strategy runner so
they can be unit-tested with synthetic metrics. They do not claim that a
strategy will be profitable; they only make the evidence bar harder to game.
"""
from __future__ import annotations

from statistics import median
from typing import Iterable


WF_FOLDS = 4
WF_INITIAL_TRAIN_FRACTION = 0.50
WF_MIN_ACTIVE_FOLDS = 3
WF_MIN_TRADES_PER_FOLD = 5
WF_MIN_PROFITABLE_RATIO = 0.75
WF_MIN_MEDIAN_PF = 1.10
WF_MIN_MEDIAN_PF_RATIO = 0.60
WF_MAX_WORST_DD = 0.30

PROBATION_WF_MIN_TRADES_PER_FOLD = 3
PROBATION_WF_MIN_ACTIVE_FOLDS = 2
PROBATION_WF_MIN_PROFITABLE_RATIO = 0.75
PROBATION_WF_MIN_MEDIAN_PF = 1.05

HOLDOUT_MAX_DD = 0.25
PROBATION_HOLDOUT_MAX_DD = 0.30


def build_anchored_walk_forward_ranges(
    n_bars: int,
    folds: int = WF_FOLDS,
    initial_train_fraction: float = WF_INITIAL_TRAIN_FRACTION,
) -> list[tuple[int, int, int, int]]:
    """Return expanding-train / non-overlapping OOS ranges.

    Each tuple is ``(train_start, train_end, test_start, test_end)`` and uses
    Python slice semantics. The first half is reserved as initial history; the
    remaining half is divided into chronological OOS folds.
    """
    if n_bars <= 0 or folds <= 0:
        return []
    train_end = int(n_bars * initial_train_fraction)
    train_end = max(1, min(train_end, n_bars - 1))
    remaining = n_bars - train_end
    if remaining < folds:
        return []

    base = remaining // folds
    extra = remaining % folds
    ranges = []
    cursor = train_end
    for i in range(folds):
        width = base + (1 if i < extra else 0)
        test_start = cursor
        test_end = cursor + width
        ranges.append((0, test_start, test_start, test_end))
        cursor = test_end
    return ranges


def _clean_metric(m: dict) -> dict:
    return {
        "trades": int(m.get("total_trades", 0) or 0),
        "pf": float(m.get("profit_factor", 0.0) or 0.0),
        "return_pct": float(m.get("return_pct", 0.0) or 0.0),
        "dd": float(m.get("max_drawdown", 1.0) or 0.0),
        "blown": bool(m.get("blown_account", False)),
    }


def assess_walk_forward(folds: Iterable[dict], probation: bool = False) -> dict:
    """Assess chronological OOS folds.

    ``folds`` items contain ``train`` and ``test`` metric dictionaries. An
    active OOS fold must contain enough closed trades. A profitable fold needs
    PF >= 1, positive return, acceptable drawdown and no account blow-up.
    ``pf_ratio`` penalizes a large collapse from the expanding historical
    sample even when the OOS PF remains barely positive.
    """
    rows = []
    min_trades = (
        PROBATION_WF_MIN_TRADES_PER_FOLD if probation else WF_MIN_TRADES_PER_FOLD
    )
    for idx, fold in enumerate(folds):
        train = _clean_metric(fold.get("train", {}))
        test = _clean_metric(fold.get("test", {}))
        pf_ratio = test["pf"] / train["pf"] if train["pf"] > 0 else 0.0
        active = test["trades"] >= min_trades
        profitable = (
            active
            and not test["blown"]
            and test["pf"] >= 1.0
            and test["return_pct"] > 0.0
            and test["dd"] <= WF_MAX_WORST_DD
        )
        rows.append({
            "fold": idx + 1,
            "active": active,
            "profitable": profitable,
            "pf_ratio": round(pf_ratio, 4),
            "train": train,
            "test": test,
        })

    active_rows = [r for r in rows if r["active"]]
    profitable_rows = [r for r in active_rows if r["profitable"]]
    active_count = len(active_rows)
    profitable_ratio = len(profitable_rows) / active_count if active_count else 0.0
    median_pf = median([r["test"]["pf"] for r in active_rows]) if active_rows else 0.0
    median_pf_ratio = median([r["pf_ratio"] for r in active_rows]) if active_rows else 0.0
    worst_dd = max([r["test"]["dd"] for r in active_rows], default=1.0)

    min_active = PROBATION_WF_MIN_ACTIVE_FOLDS if probation else WF_MIN_ACTIVE_FOLDS
    min_profitable_ratio = (
        PROBATION_WF_MIN_PROFITABLE_RATIO if probation else WF_MIN_PROFITABLE_RATIO
    )
    min_median_pf = PROBATION_WF_MIN_MEDIAN_PF if probation else WF_MIN_MEDIAN_PF

    passed = (
        active_count >= min_active
        and profitable_ratio >= min_profitable_ratio
        and median_pf >= min_median_pf
        and median_pf_ratio >= WF_MIN_MEDIAN_PF_RATIO
        and worst_dd <= WF_MAX_WORST_DD
    )
    return {
        "model": "anchored_walk_forward_v2",
        "passed": passed,
        "active_folds": active_count,
        "required_active_folds": min_active,
        "profitable_ratio": round(profitable_ratio, 4),
        "required_profitable_ratio": min_profitable_ratio,
        "median_oos_pf": round(float(median_pf), 4),
        "required_median_oos_pf": min_median_pf,
        "median_pf_ratio": round(float(median_pf_ratio), 4),
        "required_median_pf_ratio": WF_MIN_MEDIAN_PF_RATIO,
        "worst_oos_dd": round(float(worst_dd), 4),
        "max_worst_oos_dd": WF_MAX_WORST_DD,
        "folds": rows,
    }


def assess_holdout(
    metrics: dict,
    min_trades: int,
    min_pf: float,
    probation: bool = False,
) -> dict:
    """Final locked holdout gate with absolute quality constraints."""
    m = _clean_metric(metrics)
    max_dd = PROBATION_HOLDOUT_MAX_DD if probation else HOLDOUT_MAX_DD
    passed = (
        m["trades"] >= int(min_trades)
        and m["pf"] >= float(min_pf)
        and m["return_pct"] > 0.0
        and m["dd"] <= max_dd
        and not m["blown"]
    )
    return {
        "model": "locked_holdout_v2",
        "passed": passed,
        "min_trades": int(min_trades),
        "min_pf": float(min_pf),
        "max_dd": max_dd,
        "metrics": m,
    }
