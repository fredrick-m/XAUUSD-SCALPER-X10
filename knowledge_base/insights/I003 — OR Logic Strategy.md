# I003 — OR Logic Strategy

**Date** : 2026-06-25
**Importance** : BREAKTHROUGH

## Decouverte

Combiner les triggers de D008v2 et G001v2 avec une logique OR produit la meilleure strategie du systeme.

### Logique d'entree
```
EMA(8) > EMA(21) > EMA(50) pendant 20+ bars (filtre)
+
RSI pullback (25 < RSI < 40) OU ATR expansion + pullback
```

Le signal se declenche si L'UNE OU L'AUTRE condition est remplie dans le cadre du filtre EMA-stack.

### Resultats (M5, sl=1.5 ATR, tp=3.0 ATR, trailing=OFF)

| Metric | Full | IS (70%) | OOS (30%) |
|--------|------|----------|-----------|
| Signals | 279 | ~195 | ~84 |
| Trades | 188 | 137 | 51 |
| WR | 44.7% | 41.6% | 52.9% |
| PF | 1.62 | 1.18 | 1.75 |
| Balance | $1,377 | $149 | $440 |

Walk-forward: OOS/IS = 1.48 → PASSED

### Subsumption
I003 capture 94.8% des signaux de D008v2 et 93.1% de G001v2.
Un portefeuille des 3 strategies n'ajoute presque rien — I003 EST le portefeuille.

### Risk optimal (Monte Carlo)
4% risk par trade : $50 → $264, P(Ruin) = 1.7%
10% risk par trade : $50 → $1,377, P(Ruin) = 60% — INACCEPTABLE

## Parametres optimaux confirmes par grid search (45 configs)
- sl_atr = 1.5, tp_atr = 3.0, stack_bars = 20, cooldown = 100
- Aucune autre combinaison ne bat ces parametres

## Liens
- [[Monte Carlo Risk Analysis]]
- [[Trailing Stop Rule]]
- [[Selectivite des Signaux]]
- [[G001 — RSI Pullback Discovery]]
