# ENS_WEIGHTED_066

**Status** : validated
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-07-03 22:50:06

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | 63.0% |
| Profit Factor | 1.94 |
| Max Drawdown | 23.5% |
| x10 Count | 0 |
| Final Balance | $243.56 |

## Parameters
```json
{
  "method": "weighted",
  "component_ids": [
    "T06408",
    "T04078",
    "ENS_VOTE_064"
  ],
  "weights": {
    "T06408": 3.1297,
    "T04078": 2.9866,
    "ENS_VOTE_064": 2.0385
  },
  "avg_sl_atr": 2.0408,
  "avg_tp_atr": 2.1312,
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8108,
    "best_htf": "M15",
    "best_pf": 1.0013,
    "improvement": 1.235,
    "htf_results": {
      "M5": {
        "pf": 0.9961,
        "wr": 0.5527,
        "trades": 237,
        "improvement": 1.2285
      },
      "M15": {
        "pf": 1.0013,
        "wr": 0.5325,
        "trades": 231,
        "improvement": 1.235
      },
      "H1": {
        "pf": 0.8266,
        "wr": 0.5158,
        "trades": 190,
        "improvement": 1.0195
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_064",
  "redundant_cluster": [
    "ENS_VOTE_064",
    "ENS_WEIGHTED_064",
    "ENS_VOTE_066",
    "ENS_WEIGHTED_066",
    "ENS_VOTE_067",
    "ENS_WEIGHTED_067"
  ]
}
```

## Links
- [[ENS_WEIGHTED_066 Backtest]]
