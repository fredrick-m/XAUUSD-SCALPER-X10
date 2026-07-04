# ENS_VOTE_007

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:29:28

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
    "median_dd": 0.061,
    "p95_dd": 0.1018,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7762,
    "best_htf": null,
    "best_pf": 0.7762,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.6661,
        "wr": 0.48,
        "trades": 75,
        "improvement": 0.8582
      },
      "M15": {
        "pf": 0.7588,
        "wr": 0.5075,
        "trades": 67,
        "improvement": 0.9776
      },
      "H1": {
        "pf": 1.0042,
        "wr": 0.5625,
        "trades": 64,
        "improvement": 1.2937
      }
    }
  },
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.667,
    "robustness_score": 0.9858,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.5238,
          "pf": 0.5819,
          "wr": 0.4524,
          "pf_ratio": 0.8724
        },
        {
          "factor": 0.8,
          "value": 1.7415,
          "pf": 0.6095,
          "wr": 0.4691,
          "pf_ratio": 0.9138
        },
        {
          "factor": 0.9,
          "value": 1.9592,
          "pf": 0.652,
          "wr": 0.4634,
          "pf_ratio": 0.9775
        },
        {
          "factor": 1.1,
          "value": 2.3946,
          "pf": 0.6369,
          "wr": 0.4744,
          "pf_ratio": 0.9549
        },
        {
          "factor": 1.2,
          "value": 2.6123,
          "pf": 0.5364,
          "wr": 0.4068,
          "pf_ratio": 0.8042
        },
        {
          "factor": 1.3,
          "value": 2.83,
          "pf": 0.6797,
          "wr": 0.4487,
          "pf_ratio": 1.019
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.019,
          "pf": 0.7724,
          "wr": 0.5517,
          "pf_ratio": 1.158
        },
        {
          "factor": 0.8,
          "value": 2.3074,
          "pf": 0.6711,
          "wr": 0.5122,
          "pf_ratio": 1.0061
        },
        {
          "factor": 0.9,
          "value": 2.5959,
          "pf": 0.6502,
          "wr": 0.4938,
          "pf_ratio": 0.9748
        },
        {
          "factor": 1.1,
          "value": 3.1727,
          "pf": 0.6474,
          "wr": 0.5063,
          "pf_ratio": 0.9706
        },
        {
          "factor": 1.2,
          "value": 3.4612,
          "pf": 0.6568,
          "wr": 0.4938,
          "pf_ratio": 0.9847
        },
        {
          "factor": 1.3,
          "value": 3.7496,
          "pf": 0.6468,
          "wr": 0.5,
          "pf_ratio": 0.9697
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.6735,
          "wr": 0.5128,
          "pf_ratio": 1.0097
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.6125,
          "wr": 0.5128,
          "pf_ratio": 0.9183
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.658,
          "wr": 0.5125,
          "pf_ratio": 0.9865
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.6577,
          "wr": 0.506,
          "pf_ratio": 0.9861
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.7473,
          "wr": 0.5057,
          "pf_ratio": 1.1204
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.7451,
          "wr": 0.5057,
          "pf_ratio": 1.1171
        }
      ]
    }
  }
}
```

## Links
- [[ENS_VOTE_007 Backtest]]
