# ENS_WEIGHTED_020

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:17:17

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
  "monte_carlo": {
    "median_dd": 0.1374,
    "p95_dd": 0.249,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7209,
    "best_htf": "M5",
    "best_pf": 0.732,
    "improvement": 1.0154,
    "htf_results": {
      "M5": {
        "pf": 0.732,
        "wr": 0.5143,
        "trades": 105,
        "improvement": 1.0154
      },
      "M15": {
        "pf": 0.6803,
        "wr": 0.5056,
        "trades": 89,
        "improvement": 0.9437
      },
      "H1": {
        "pf": 0.7518,
        "wr": 0.5342,
        "trades": 73,
        "improvement": 1.0429
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_003",
  "redundant_cluster": [
    "T01471",
    "ENS_VOTE_003",
    "ENS_WEIGHTED_003",
    "ENS_VOTE_010",
    "ENS_WEIGHTED_010",
    "ENS_VOTE_017",
    "ENS_WEIGHTED_017",
    "ENS_VOTE_020",
    "ENS_WEIGHTED_020",
    "ENS_VOTE_021",
    "ENS_WEIGHTED_021"
  ]
}
```

## Links
- [[ENS_WEIGHTED_020 Backtest]]
