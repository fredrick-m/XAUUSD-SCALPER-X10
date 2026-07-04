# ENS_WEIGHTED_068

**Status** : validated
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-07-03 22:57:54

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | 64.0% |
| Profit Factor | 1.97 |
| Max Drawdown | 17.7% |
| x10 Count | 0 |
| Final Balance | $268.86 |

## Parameters
```json
{
  "method": "weighted",
  "component_ids": [
    "T06408",
    "T04521",
    "ENS_VOTE_064"
  ],
  "weights": {
    "T06408": 3.1297,
    "T04521": 2.7308,
    "ENS_VOTE_064": 2.0385
  },
  "avg_sl_atr": 2.1908,
  "avg_tp_atr": 2.29,
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8347,
    "best_htf": "M15",
    "best_pf": 1.0362,
    "improvement": 1.2414,
    "htf_results": {
      "M5": {
        "pf": 0.841,
        "wr": 0.545,
        "trades": 211,
        "improvement": 1.0075
      },
      "M15": {
        "pf": 1.0362,
        "wr": 0.5459,
        "trades": 229,
        "improvement": 1.2414
      },
      "H1": {
        "pf": 0.8286,
        "wr": 0.5134,
        "trades": 187,
        "improvement": 0.9927
      }
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_068 Backtest]]
