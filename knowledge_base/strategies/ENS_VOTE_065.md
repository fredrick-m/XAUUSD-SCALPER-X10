# ENS_VOTE_065

**Status** : validated
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-07-03 22:24:30

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | 61.7% |
| Profit Factor | 1.67 |
| Max Drawdown | 20.8% |
| x10 Count | 0 |
| Final Balance | $229.44 |

## Parameters
```json
{
  "method": "vote",
  "component_ids": [
    "T04078",
    "T04521",
    "T06319"
  ],
  "weights": {
    "T04078": 2.9866,
    "T04521": 2.7308,
    "T06319": 2.5429
  },
  "avg_sl_atr": 1.9023,
  "avg_tp_atr": 2.3431,
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.6312,
    "best_htf": "M5",
    "best_pf": 1.1314,
    "improvement": 1.7925,
    "htf_results": {
      "M5": {
        "pf": 1.1314,
        "wr": 0.5357,
        "trades": 308,
        "improvement": 1.7925
      },
      "M15": {
        "pf": 0.6234,
        "wr": 0.4132,
        "trades": 121,
        "improvement": 0.9876
      },
      "H1": {
        "pf": 0.8489,
        "wr": 0.4798,
        "trades": 248,
        "improvement": 1.3449
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_WEIGHTED_065",
  "redundant_cluster": [
    "ENS_VOTE_065",
    "ENS_WEIGHTED_065"
  ]
}
```

## Links
- [[ENS_VOTE_065 Backtest]]
