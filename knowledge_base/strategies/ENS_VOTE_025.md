# ENS_VOTE_025

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 16:35:06

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
  "method": "vote",
  "component_ids": [
    "ENS_VOTE_006",
    "ENS_WEIGHTED_006",
    "ENS_VOTE_002"
  ],
  "weights": {
    "ENS_VOTE_006": 8.1739,
    "ENS_WEIGHTED_006": 8.1739,
    "ENS_VOTE_002": 7.8848
  },
  "avg_sl_atr": 2.0226,
  "avg_tp_atr": 2.7164,
  "monte_carlo": {
    "median_dd": 0.0732,
    "p95_dd": 0.1326,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7266,
    "best_htf": null,
    "best_pf": 0.7266,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7682,
        "wr": 0.4906,
        "trades": 53,
        "improvement": 1.0573
      },
      "M15": {
        "pf": 0.774,
        "wr": 0.5077,
        "trades": 65,
        "improvement": 1.0652
      },
      "H1": {
        "pf": 0.8516,
        "wr": 0.527,
        "trades": 74,
        "improvement": 1.172
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
- [[ENS_VOTE_025 Backtest]]
