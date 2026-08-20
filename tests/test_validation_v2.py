from agents.validation_v2 import (
    build_anchored_walk_forward_ranges,
    assess_walk_forward,
    assess_holdout,
)


def _m(trades=20, pf=1.4, ret=10.0, dd=0.12, blown=False):
    return {
        "total_trades": trades,
        "profit_factor": pf,
        "return_pct": ret,
        "max_drawdown": dd,
        "blown_account": blown,
    }


def test_anchored_ranges_are_chronological_and_non_overlapping():
    ranges = build_anchored_walk_forward_ranges(1000, folds=4, initial_train_fraction=0.5)
    assert len(ranges) == 4
    assert ranges[0] == (0, 500, 500, 625)
    assert ranges[-1] == (0, 875, 875, 1000)
    for previous, current in zip(ranges, ranges[1:]):
        assert previous[3] == current[2]
        assert current[1] == current[2]


def test_walk_forward_passes_three_of_four_good_oos_folds():
    folds = [
        {"train": _m(pf=1.8), "test": _m(pf=1.3, ret=8.0, dd=0.10)},
        {"train": _m(pf=1.7), "test": _m(pf=1.2, ret=6.0, dd=0.14)},
        {"train": _m(pf=1.6), "test": _m(pf=1.15, ret=4.0, dd=0.18)},
        {"train": _m(pf=1.5), "test": _m(pf=0.9, ret=-2.0, dd=0.20)},
    ]
    result = assess_walk_forward(folds)
    assert result["passed"] is True
    assert result["active_folds"] == 4
    assert result["profitable_ratio"] == 0.75


def test_walk_forward_fails_when_oos_edge_collapses_vs_training():
    folds = [
        {"train": _m(pf=3.0), "test": _m(pf=1.2, ret=3.0, dd=0.10)},
        {"train": _m(pf=2.8), "test": _m(pf=1.15, ret=3.0, dd=0.10)},
        {"train": _m(pf=3.2), "test": _m(pf=1.25, ret=3.0, dd=0.10)},
        {"train": _m(pf=3.1), "test": _m(pf=1.2, ret=3.0, dd=0.10)},
    ]
    result = assess_walk_forward(folds)
    assert result["passed"] is False
    assert result["median_pf_ratio"] < result["required_median_pf_ratio"]


def test_walk_forward_fails_on_excessive_oos_drawdown():
    folds = [
        {"train": _m(pf=1.6), "test": _m(pf=1.3, ret=5.0, dd=0.10)},
        {"train": _m(pf=1.6), "test": _m(pf=1.3, ret=5.0, dd=0.12)},
        {"train": _m(pf=1.6), "test": _m(pf=1.3, ret=5.0, dd=0.35)},
        {"train": _m(pf=1.6), "test": _m(pf=1.3, ret=5.0, dd=0.15)},
    ]
    result = assess_walk_forward(folds)
    assert result["passed"] is False
    assert result["worst_oos_dd"] == 0.35


def test_holdout_requires_positive_return_and_drawdown_limit():
    good = assess_holdout(_m(trades=20, pf=1.3, ret=4.0, dd=0.20), 15, 1.2)
    high_dd = assess_holdout(_m(trades=20, pf=1.5, ret=8.0, dd=0.30), 15, 1.2)
    losing = assess_holdout(_m(trades=20, pf=1.5, ret=-1.0, dd=0.10), 15, 1.2)

    assert good["passed"] is True
    assert high_dd["passed"] is False
    assert losing["passed"] is False


def test_probation_accepts_smaller_but_not_empty_oos_sample():
    folds = [
        {"train": _m(trades=30, pf=1.7), "test": _m(trades=3, pf=1.2, ret=2.0, dd=0.10)},
        {"train": _m(trades=40, pf=1.6), "test": _m(trades=4, pf=1.15, ret=2.0, dd=0.12)},
        {"train": _m(trades=50, pf=1.5), "test": _m(trades=2, pf=1.4, ret=2.0, dd=0.10)},
        {"train": _m(trades=60, pf=1.5), "test": _m(trades=3, pf=1.1, ret=2.0, dd=0.10)},
    ]
    result = assess_walk_forward(folds, probation=True)
    assert result["passed"] is True
    assert result["active_folds"] == 3
