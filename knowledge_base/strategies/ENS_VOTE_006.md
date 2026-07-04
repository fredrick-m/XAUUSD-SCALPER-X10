# ENS_VOTE_006

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:25:29

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
    "T00903"
  ],
  "weights": {
    "c007": 6.7682,
    "T01769": 4.8155,
    "T00903": 2.6287
  },
  "avg_sl_atr": 2.0877,
  "avg_tp_atr": 2.6259,
  "monte_carlo": {
    "median_dd": 0.0567,
    "p95_dd": 0.1089,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8106,
    "best_htf": null,
    "best_pf": 0.8106,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7631,
        "wr": 0.4694,
        "trades": 49,
        "improvement": 0.9414
      },
      "M15": {
        "pf": 0.7802,
        "wr": 0.4912,
        "trades": 57,
        "improvement": 0.9625
      },
      "H1": {
        "pf": 0.9322,
        "wr": 0.5385,
        "trades": 65,
        "improvement": 1.15
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_027",
  "redundant_cluster": [
    "T00903",
    "ENS_VOTE_006",
    "ENS_WEIGHTED_006",
    "ENS_VOTE_013",
    "ENS_WEIGHTED_013",
    "ENS_VOTE_019",
    "ENS_WEIGHTED_019",
    "ENS_VOTE_023",
    "ENS_WEIGHTED_023",
    "ENS_VOTE_024",
    "ENS_WEIGHTED_024",
    "ENS_VOTE_025",
    "ENS_WEIGHTED_025",
    "ENS_VOTE_026",
    "ENS_WEIGHTED_026",
    "ENS_VOTE_027",
    "ENS_WEIGHTED_027",
    "ENS_VOTE_028",
    "ENS_WEIGHTED_028",
    "ENS_VOTE_029",
    "ENS_WEIGHTED_029",
    "ENS_VOTE_030",
    "ENS_WEIGHTED_030",
    "ENS_VOTE_031",
    "ENS_WEIGHTED_031",
    "ENS_VOTE_032",
    "ENS_WEIGHTED_032",
    "ENS_VOTE_033",
    "ENS_WEIGHTED_033",
    "ENS_VOTE_034",
    "ENS_WEIGHTED_034",
    "ENS_VOTE_035",
    "ENS_WEIGHTED_035",
    "ENS_VOTE_036",
    "ENS_WEIGHTED_036",
    "ENS_VOTE_037",
    "ENS_WEIGHTED_037",
    "ENS_VOTE_038",
    "ENS_WEIGHTED_038",
    "ENS_VOTE_039",
    "ENS_WEIGHTED_039",
    "ENS_VOTE_040",
    "ENS_WEIGHTED_040",
    "ENS_VOTE_041",
    "ENS_WEIGHTED_041",
    "ENS_VOTE_042",
    "ENS_WEIGHTED_042"
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 1.0877,
    "robustness_score": 0.8763,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.4614,
          "pf": 0.4772,
          "wr": 0.4149,
          "pf_ratio": 0.4387
        },
        {
          "factor": 0.8,
          "value": 1.6702,
          "pf": 0.8925,
          "wr": 0.4726,
          "pf_ratio": 0.8205
        },
        {
          "factor": 0.9,
          "value": 1.8789,
          "pf": 0.6656,
          "wr": 0.4417,
          "pf_ratio": 0.6119
        },
        {
          "factor": 1.1,
          "value": 2.2965,
          "pf": 1.1063,
          "wr": 0.4863,
          "pf_ratio": 1.0171
        },
        {
          "factor": 1.2,
          "value": 2.5052,
          "pf": 1.1034,
          "wr": 0.4726,
          "pf_ratio": 1.0144
        },
        {
          "factor": 1.3,
          "value": 2.714,
          "pf": 1.1106,
          "wr": 0.4932,
          "pf_ratio": 1.0211
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 1.8381,
          "pf": 1.2367,
          "wr": 0.5616,
          "pf_ratio": 1.137
        },
        {
          "factor": 0.8,
          "value": 2.1007,
          "pf": 1.1862,
          "wr": 0.5137,
          "pf_ratio": 1.0906
        },
        {
          "factor": 0.9,
          "value": 2.3633,
          "pf": 1.1527,
          "wr": 0.4863,
          "pf_ratio": 1.0598
        },
        {
          "factor": 1.1,
          "value": 2.8885,
          "pf": 1.1171,
          "wr": 0.4795,
          "pf_ratio": 1.027
        },
        {
          "factor": 1.2,
          "value": 3.1511,
          "pf": 0.6579,
          "wr": 0.4359,
          "pf_ratio": 0.6049
        },
        {
          "factor": 1.3,
          "value": 3.4137,
          "pf": 0.6533,
          "wr": 0.4397,
          "pf_ratio": 0.6006
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 1.1649,
          "wr": 0.4863,
          "pf_ratio": 1.071
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 1.1677,
          "wr": 0.4932,
          "pf_ratio": 1.0735
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 1.1458,
          "wr": 0.4932,
          "pf_ratio": 1.0534
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.8983,
          "wr": 0.4863,
          "pf_ratio": 0.8259
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.7082,
          "wr": 0.4615,
          "pf_ratio": 0.6511
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.712,
          "wr": 0.4692,
          "pf_ratio": 0.6546
        }
      ]
    }
  }
}
```

## Links
- [[ENS_VOTE_006 Backtest]]
