# ENS_VOTE_064

**Status** : validated
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-07-03 22:20:06

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | 65.0% |
| Profit Factor | 2.04 |
| Max Drawdown | 23.2% |
| x10 Count | 0 |
| Final Balance | $271.32 |

## Parameters
```json
{
  "method": "vote",
  "component_ids": [
    "T06408",
    "T04078",
    "T04521"
  ],
  "weights": {
    "T06408": 3.1297,
    "T04078": 2.9866,
    "T04521": 2.7308
  },
  "avg_sl_atr": 2.1007,
  "avg_tp_atr": 2.23,
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8634,
    "best_htf": "M15",
    "best_pf": 1.0218,
    "improvement": 1.1835,
    "htf_results": {
      "M5": {
        "pf": 0.8559,
        "wr": 0.5472,
        "trades": 212,
        "improvement": 0.9913
      },
      "M15": {
        "pf": 1.0218,
        "wr": 0.5371,
        "trades": 229,
        "improvement": 1.1835
      },
      "H1": {
        "pf": 0.8249,
        "wr": 0.516,
        "trades": 188,
        "improvement": 0.9554
      }
    }
  }
}
```

## Links
- [[ENS_VOTE_064 Backtest]]
