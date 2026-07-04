# Pourquoi l'or — et la feuille de route multi-symboles

*Analyse du 2026-07-04, basée sur les 6 derniers mois de données réelles du projet.*

## 1. Pourquoi XAUUSD est un excellent choix (chiffres mesurés)

| Métrique (données réelles, 6 derniers mois) | Valeur |
|---|---|
| Spread médian | **0,05 $** (p90 : 0,10 $) |
| ATR(14) M5 médian | **5,48 $** (p10 : 3,10 $) |
| **Coût aller-retour / ATR** (spread + slippage) | **2,7 %** |

Le ratio coût/volatilité est LA métrique qui décide si le scalping est viable :
chaque trade paie ~2,7 % du mouvement moyen en frais. À titre de comparaison
(ordres de grandeur de marché) : EURUSD ≈ 4-8 %, GBPJPY ≈ 5-10 %, indices
CFD ≈ 3-6 %. **L'or est parmi les meilleurs ratios accessibles au retail.**

S'y ajoutent trois propriétés structurelles :
- **Persistance des tendances** : l'or tend fort et longtemps (le filtre
  EMA-stack du système exploite exactement ça — edge confirmé par les données)
- **Volatilité clusterisée** : les sessions Londres/NY concentrent le
  mouvement — exploitable par les paramètres de session
- **Liquidité 24/5** sans risque d'illiquidité de milieu de nuit fatal

Conclusion : le choix de l'or n'est pas un hasard historique du projet,
c'est le bon premier champ de bataille.

## 2. Ce que coûterait le multi-symboles (audit du code)

**60 références codées en dur** à `PIP_VALUE`/`XAUUSD` dans agents/, core/,
engine/. Les chantiers :

1. **Spécifications par symbole** : dict `SYMBOL_SPECS` (contract size,
   valeur du point, digits, spread par défaut, lot min) dans core/config.py
2. **Colonne `symbol`** dans les tables strategies / backtest_results /
   live_trades (migration SQLite)
3. **Paramétrage** de paper_trade, trade_supervisor, gatekeeper (heat
   multi-symboles !), engine (conversion spread), backtest_runner (données
   par symbole)
4. **Pipeline de données par symbole** : téléchargement, fusion,
   rafraîchissement quotidien, resampling
5. **Corrélation inter-symboles** : XAUUSD et EURUSD sont corrélés (dollar) —
   le correlation_agent devrait plafonner l'exposition dollar globale

Estimation : 1-2 jours de travail soigné + revalidation complète.

## 3. Recommandation : PAS MAINTENANT — séquencement

La machine (4 cœurs) vient de commencer à produire des validations honnêtes
sur l'or. Diviser le calcul entre 2 symboles = diviser par 2 la vitesse de
découverte sur chacun. La profondeur avant la largeur :

1. **Maintenant** : creuser l'or — 74 familles, évolution dirigée, banc de
   50+ stratégies déployables
2. **Ensuite** : VPS (stabilité) — prérequis absolu avant toute expansion
3. **Puis** : EURUSD comme 2ᵉ symbole (spread minimal, données abondantes,
   comportement différent de l'or = vraie diversification)
4. **Critère de déclenchement** : quand l'or a 50+ stratégies déployées et
   que le taux de découverte marginal chute (les familles saturent)

*Un symbole maîtrisé vaut mieux que trois symboles médiocres.*
