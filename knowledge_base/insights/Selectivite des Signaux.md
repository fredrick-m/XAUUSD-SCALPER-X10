# Selectivite des Signaux

**Date** : 2026-06-25
**Importance** : FONDAMENTALE

## Regle d'Or

> **< 200 signaux sur 200K barres M5 = PROFITABLE**
> **> 500 signaux sur 200K barres M5 = PERTE ASSUREE**

## Preuves

### Strategies avec < 200 signaux (GAGNANTES)
| Strat | Signaux | PF | WR |
|-------|---------|-----|-----|
| D008v2 | 193 | 1.40 | 35.8% |
| G001v2 | 101 | 1.47 | 63.8% |
| C007 | 7 | 5.42 | 85.7% |
| G001 | 122 | 1.19 | 61.0% |

### Strategies avec > 500 signaux (PERDANTES)
| Strat | Signaux | PF | WR |
|-------|---------|-----|-----|
| F001 | 773 | 0.35 | 34.0% |
| F003 | 1571 | 0.62 | 43.5% |
| F004 | 996 | 0.78 | 46.7% |
| F005 | 1183 | 0.62 | 47.3% |
| G001e (rsi<45) | 1067 | 0.54 | 37.8% |

## Pourquoi

Le spread XAUUSD ($0.35-$0.40) est un cout fixe par trade.
- Avec peu de trades : chaque signal est soigneusement filtre → edge reel
- Avec beaucoup de trades : on trade le bruit → spread mange le profit

## Implication pour Strategy Factory

Toute nouvelle strategie doit etre rejetee si elle genere > 300 signaux
sur les donnees historiques M5. Pas de backtest necessaire — echec garanti.

## Liens
- [[M5 Breakthrough]]
- [[G001 — RSI Pullback Discovery]]
