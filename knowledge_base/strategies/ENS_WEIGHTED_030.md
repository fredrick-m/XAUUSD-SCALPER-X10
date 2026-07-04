# ENS_WEIGHTED_030

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 16:50:52

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | — |
| Profit Factor | — |
| Max Drawdown | — |
| x10 Count | 0 |
| Final Balance | — |

## Parameters
```json
{
  "method": "weighted",
  "component_ids": [
    "ENS_VOTE_006",
    "ENS_WEIGHTED_006",
    "ENS_WEIGHTED_015"
  ],
  "weights": {
    "ENS_VOTE_006": 8.1739,
    "ENS_WEIGHTED_006": 8.1739,
    "ENS_WEIGHTED_015": 4.6282
  },
  "avg_sl_atr": 1.9678,
  "avg_tp_atr": 2.736,
  "monte_carlo": {
    "median_dd": 0.098,
    "p95_dd": 0.1724,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7447,
    "best_htf": null,
    "best_pf": 0.7447,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.8179,
        "wr": 0.5082,
        "trades": 61,
        "improvement": 1.0983
      },
      "M15": {
        "pf": 0.8306,
        "wr": 0.5139,
        "trades": 72,
        "improvement": 1.1153
      },
      "H1": {
        "pf": 0.8836,
        "wr": 0.525,
        "trades": 80,
        "improvement": 1.1865
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_027",
  "redundant_cluster": [
    "T00903",
    "ENS_VOTE_006",
    "ENS_WEIGHTED_006",
    "ENS_VOTE_013",
    "ENS_WEIGHTED_013",
    "ENS_VOTE_019",
    "ENS_WEIGHTED_019",
    "ENS_VOTE_023",
    "ENS_WEIGHTED_023",
    "ENS_VOTE_024",
    "ENS_WEIGHTED_024",
    "ENS_VOTE_025",
    "ENS_WEIGHTED_025",
    "ENS_VOTE_026",
    "ENS_WEIGHTED_026",
    "ENS_VOTE_027",
    "ENS_WEIGHTED_027",
    "ENS_VOTE_028",
    "ENS_WEIGHTED_028",
    "ENS_VOTE_029",
    "ENS_WEIGHTED_029",
    "ENS_VOTE_030",
    "ENS_WEIGHTED_030",
    "ENS_VOTE_031",
    "ENS_WEIGHTED_031",
    "ENS_VOTE_032",
    "ENS_WEIGHTED_032",
    "ENS_VOTE_033",
    "ENS_WEIGHTED_033",
    "ENS_VOTE_034",
    "ENS_WEIGHTED_034",
    "ENS_VOTE_035",
    "ENS_WEIGHTED_035",
    "ENS_VOTE_036",
    "ENS_WEIGHTED_036",
    "ENS_VOTE_037",
    "ENS_WEIGHTED_037",
    "ENS_VOTE_038",
    "ENS_WEIGHTED_038",
    "ENS_VOTE_039",
    "ENS_WEIGHTED_039",
    "ENS_VOTE_040",
    "ENS_WEIGHTED_040",
    "ENS_VOTE_041",
    "ENS_WEIGHTED_041",
    "ENS_VOTE_042",
    "ENS_WEIGHTED_042"
  ]
}
```

## Links
- [[ENS_WEIGHTED_030 Backtest]]
