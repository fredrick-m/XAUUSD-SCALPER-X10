# ENS_WEIGHTED_001

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:09:00

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
    "median_dd": 0.2096,
    "p95_dd": 0.4081,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7086,
    "best_htf": "H1",
    "best_pf": 0.7166,
    "improvement": 1.0113,
    "htf_results": {
      "M5": {
        "pf": 0.7137,
        "wr": 0.4983,
        "trades": 289,
        "improvement": 1.0072
      },
      "M15": {
        "pf": 0.6908,
        "wr": 0.4982,
        "trades": 283,
        "improvement": 0.9749
      },
      "H1": {
        "pf": 0.7166,
        "wr": 0.4794,
        "trades": 267,
        "improvement": 1.0113
      }
    }
  },
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.7086,
    "robustness_score": 0.9176,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3975,
          "pf": 0.3922,
          "wr": 0.4329,
          "pf_ratio": 0.5535
        },
        {
          "factor": 0.8,
          "value": 1.5972,
          "pf": 0.4301,
          "wr": 0.4322,
          "pf_ratio": 0.607
        },
        {
          "factor": 0.9,
          "value": 1.7969,
          "pf": 0.553,
          "wr": 0.4522,
          "pf_ratio": 0.7804
        },
        {
          "factor": 1.1,
          "value": 2.1962,
          "pf": 0.7396,
          "wr": 0.4797,
          "pf_ratio": 1.0437
        },
        {
          "factor": 1.2,
          "value": 2.3958,
          "pf": 0.7687,
          "wr": 0.4673,
          "pf_ratio": 1.0848
        },
        {
          "factor": 1.3,
          "value": 2.5955,
          "pf": 0.8214,
          "wr": 0.4714,
          "pf_ratio": 1.1592
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.0168,
          "pf": 0.7465,
          "wr": 0.5,
          "pf_ratio": 1.0535
        },
        {
          "factor": 0.8,
          "value": 2.3049,
          "pf": 0.7285,
          "wr": 0.4837,
          "pf_ratio": 1.0281
        },
        {
          "factor": 0.9,
          "value": 2.593,
          "pf": 0.6941,
          "wr": 0.4736,
          "pf_ratio": 0.9795
        },
        {
          "factor": 1.1,
          "value": 3.1692,
          "pf": 0.5963,
          "wr": 0.4494,
          "pf_ratio": 0.8415
        },
        {
          "factor": 1.2,
          "value": 3.4573,
          "pf": 0.5946,
          "wr": 0.4505,
          "pf_ratio": 0.8391
        },
        {
          "factor": 1.3,
          "value": 3.7454,
          "pf": 0.5891,
          "wr": 0.4526,
          "pf_ratio": 0.8314
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.7732,
          "wr": 0.4766,
          "pf_ratio": 1.0912
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.6391,
          "wr": 0.443,
          "pf_ratio": 0.9019
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.662,
          "wr": 0.4624,
          "pf_ratio": 0.9342
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.6846,
          "wr": 0.4675,
          "pf_ratio": 0.9661
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.6134,
          "wr": 0.459,
          "pf_ratio": 0.8657
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.6771,
          "wr": 0.4654,
          "pf_ratio": 0.9555
        }
      ]
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_022",
  "redundant_cluster": [
    "ENS_VOTE_001",
    "ENS_WEIGHTED_001",
    "ENS_VOTE_022",
    "ENS_WEIGHTED_022"
  ]
}
```

## Links
- [[ENS_WEIGHTED_001 Backtest]]
