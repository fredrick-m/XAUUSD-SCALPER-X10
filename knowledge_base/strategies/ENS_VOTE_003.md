# ENS_VOTE_003

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:14:30

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
    "c007",
    "T01769",
    "T01471"
  ],
  "weights": {
    "c007": 6.7682,
    "T01769": 4.8155,
    "T01471": 2.7698
  },
  "avg_sl_atr": 1.9702,
  "avg_tp_atr": 3.0029,
  "monte_carlo": {
    "median_dd": 0.1074,
    "p95_dd": 0.2075,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8354,
    "best_htf": null,
    "best_pf": 0.8354,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7921,
        "wr": 0.5054,
        "trades": 93,
        "improvement": 0.9482
      },
      "M15": {
        "pf": 0.6849,
        "wr": 0.4815,
        "trades": 81,
        "improvement": 0.8198
      },
      "H1": {
        "pf": 0.7785,
        "wr": 0.4928,
        "trades": 69,
        "improvement": 0.9319
      }
    }
  },
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.8354,
    "robustness_score": 0.9924,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3791,
          "pf": 0.5473,
          "wr": 0.4737,
          "pf_ratio": 0.6551
        },
        {
          "factor": 0.8,
          "value": 1.5762,
          "pf": 0.706,
          "wr": 0.5,
          "pf_ratio": 0.8451
        },
        {
          "factor": 0.9,
          "value": 1.7732,
          "pf": 0.7836,
          "wr": 0.5263,
          "pf_ratio": 0.938
        },
        {
          "factor": 1.1,
          "value": 2.1672,
          "pf": 0.9496,
          "wr": 0.5351,
          "pf_ratio": 1.1367
        },
        {
          "factor": 1.2,
          "value": 2.3642,
          "pf": 0.8767,
          "wr": 0.5044,
          "pf_ratio": 1.0494
        },
        {
          "factor": 1.3,
          "value": 2.5613,
          "pf": 0.8357,
          "wr": 0.4956,
          "pf_ratio": 1.0004
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.102,
          "pf": 0.8464,
          "wr": 0.5088,
          "pf_ratio": 1.0132
        },
        {
          "factor": 0.8,
          "value": 2.4023,
          "pf": 0.8658,
          "wr": 0.5,
          "pf_ratio": 1.0364
        },
        {
          "factor": 0.9,
          "value": 2.7026,
          "pf": 0.843,
          "wr": 0.4912,
          "pf_ratio": 1.0091
        },
        {
          "factor": 1.1,
          "value": 3.3032,
          "pf": 0.8231,
          "wr": 0.4912,
          "pf_ratio": 0.9853
        },
        {
          "factor": 1.2,
          "value": 3.6035,
          "pf": 0.8281,
          "wr": 0.4912,
          "pf_ratio": 0.9913
        },
        {
          "factor": 1.3,
          "value": 3.9038,
          "pf": 0.8247,
          "wr": 0.4912,
          "pf_ratio": 0.9872
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.8998,
          "wr": 0.5175,
          "pf_ratio": 1.0771
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.8601,
          "wr": 0.5088,
          "pf_ratio": 1.0296
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.8243,
          "wr": 0.4912,
          "pf_ratio": 0.9867
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.8627,
          "wr": 0.4912,
          "pf_ratio": 1.0327
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.8773,
          "wr": 0.4912,
          "pf_ratio": 1.0502
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.8683,
          "wr": 0.5,
          "pf_ratio": 1.0394
        }
      ]
    }
  }
}
```

## Links
- [[ENS_VOTE_003 Backtest]]
