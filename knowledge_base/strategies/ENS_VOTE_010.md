# ENS_VOTE_010

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:43:21

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
    "median_dd": 0.1416,
    "p95_dd": 0.2936,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8141,
    "best_htf": null,
    "best_pf": 0.8141,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.8208,
        "wr": 0.5625,
        "trades": 80,
        "improvement": 1.0082
      },
      "M15": {
        "pf": 0.6926,
        "wr": 0.5342,
        "trades": 73,
        "improvement": 0.8508
      },
      "H1": {
        "pf": 0.7957,
        "wr": 0.5593,
        "trades": 59,
        "improvement": 0.9774
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
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.8839,
    "robustness_score": 0.949,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.2739,
          "pf": 0.8707,
          "wr": 0.5149,
          "pf_ratio": 0.9851
        },
        {
          "factor": 0.8,
          "value": 1.4558,
          "pf": 0.7497,
          "wr": 0.5149,
          "pf_ratio": 0.8482
        },
        {
          "factor": 0.9,
          "value": 1.6378,
          "pf": 0.7972,
          "wr": 0.5347,
          "pf_ratio": 0.9019
        },
        {
          "factor": 1.1,
          "value": 2.0018,
          "pf": 0.7465,
          "wr": 0.4851,
          "pf_ratio": 0.8446
        },
        {
          "factor": 1.2,
          "value": 2.1838,
          "pf": 0.6884,
          "wr": 0.4848,
          "pf_ratio": 0.7788
        },
        {
          "factor": 1.3,
          "value": 2.3657,
          "pf": 0.696,
          "wr": 0.4742,
          "pf_ratio": 0.7874
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.3278,
          "pf": 0.9636,
          "wr": 0.5347,
          "pf_ratio": 1.0902
        },
        {
          "factor": 0.8,
          "value": 2.6604,
          "pf": 0.9034,
          "wr": 0.5347,
          "pf_ratio": 1.0221
        },
        {
          "factor": 0.9,
          "value": 2.9929,
          "pf": 0.9111,
          "wr": 0.5347,
          "pf_ratio": 1.0308
        },
        {
          "factor": 1.1,
          "value": 3.6581,
          "pf": 0.847,
          "wr": 0.5347,
          "pf_ratio": 0.9583
        },
        {
          "factor": 1.2,
          "value": 3.9906,
          "pf": 0.8302,
          "wr": 0.5347,
          "pf_ratio": 0.9392
        },
        {
          "factor": 1.3,
          "value": 4.3232,
          "pf": 0.8543,
          "wr": 0.5347,
          "pf_ratio": 0.9665
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.8353,
          "wr": 0.5347,
          "pf_ratio": 0.945
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.871,
          "wr": 0.5446,
          "pf_ratio": 0.9854
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.9097,
          "wr": 0.5545,
          "pf_ratio": 1.0292
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.899,
          "wr": 0.5446,
          "pf_ratio": 1.0171
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.8764,
          "wr": 0.5446,
          "pf_ratio": 0.9915
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.8487,
          "wr": 0.5347,
          "pf_ratio": 0.9602
        }
      ]
    }
  }
}
```

## Links
- [[ENS_VOTE_010 Backtest]]
