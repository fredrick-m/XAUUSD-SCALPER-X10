# ENS_WEIGHTED_015

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:07:23

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
    "median_dd": 0.0572,
    "p95_dd": 0.1016,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7058,
    "best_htf": null,
    "best_pf": 0.7058,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7153,
        "wr": 0.5676,
        "trades": 37,
        "improvement": 1.0135
      },
      "M15": {
        "pf": 0.702,
        "wr": 0.5789,
        "trades": 38,
        "improvement": 0.9946
      },
      "H1": {
        "pf": 0.9907,
        "wr": 0.6364,
        "trades": 33,
        "improvement": 1.4037
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_015",
  "redundant_cluster": [
    "ENS_VOTE_015",
    "ENS_WEIGHTED_015"
  ]
}
```

## Links
- [[ENS_WEIGHTED_015 Backtest]]
