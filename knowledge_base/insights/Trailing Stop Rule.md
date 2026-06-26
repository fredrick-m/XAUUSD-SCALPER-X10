# Trailing Stop Rule

**Date** : 2026-06-25
**Importance** : CRITIQUE

## Decouverte

Le trailing stop DETRUIT les strategies a TP large (tp_atr >= 3.0).

### D008v2 (tp_atr = 4.0)
| Trailing | WR | PF | Balance |
|----------|-----|-----|---------|
| ON | 53.7% | 0.81 | $24 |
| OFF | 36.8% | 1.40 | $294 |

Le trailing coupe les gagnants trop tot. La strategie a besoin que les 36% de trades gagnants
fassent des mouvements de 4x ATR pour compenser les 64% de perdants.

### G001v2 (tp_atr = 2.0)
| Trailing | WR | PF | Balance |
|----------|-----|-----|---------|
| ON | 63.8% | 1.47 | $117 |
| OFF | 53.6% | 1.30 | $116 |

Avec TP serre, le trailing n'aide pas mais ne nuit pas non plus.

## Regle

> **tp_atr >= 3.0 → trailing_stop = False**
> **tp_atr < 3.0 → trailing_stop = True**

## Impact

D008v2 passe de $24 a $294 juste en desactivant le trailing stop.
C'est le fix le plus impactant de toute l'histoire du systeme.

## Liens
- [[D008v2 - ATR Expansion Trend]]
- [[G001 — RSI Pullback Discovery]]
