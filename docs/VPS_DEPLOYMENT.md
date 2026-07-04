# Déploiement VPS — XAUUSD-SCALPER-X10

> **Pourquoi un VPS ?** Les logs locaux montrent régulièrement
> `Internet connection lost — pausing agents` et
> `Order failed: Request rejected due to absence of network connection`.
> Chaque coupure = signaux manqués et ordres rejetés. Un VPS de trading
> tourne 24/7 avec une latence de quelques millisecondes vers le broker.

---

## 1. Choisir le VPS

**Contrainte forte : Windows** (MetaTrader5 + le package Python `MetaTrader5`
ne tournent que sous Windows).

| Critère | Minimum | Recommandé |
|---|---|---|
| OS | Windows Server 2019 | Windows Server 2022 |
| vCPU | 2 | 4 (le pool de backtests utilise 3 workers) |
| RAM | 4 Go | 8 Go |
| Disque | 40 Go SSD | 60 Go NVMe |
| Localisation | Europe | **Londres (LD4/LD5)** — serveurs ICMarkets |

Fournisseurs habituels pour ce cas d'usage : ForexVPS.net, ChocoPing,
Contabo (Windows), OVH (VPS Windows). Un VPS "trading" à Londres donne
~1 ms vers ICMarkets ; un VPS généraliste européen donne 10-30 ms — déjà
100× mieux qu'une connexion résidentielle instable.

Budget indicatif : 15-35 $/mois.

## 2. Préparer le VPS (une fois connecté en RDP)

```powershell
# 1. Installer Python 3.12+ (cocher "Add to PATH")
#    https://www.python.org/downloads/windows/

# 2. Installer MetaTrader 5 (terminal du broker, ex. ICMarkets)
#    https://www.icmarkets.com/ → MT5 → se connecter au compte DÉMO
#    IMPORTANT: laisser le terminal MT5 OUVERT et connecté.
#    Dans MT5 : Outils → Options → Expert Advisors → cocher
#    "Autoriser le trading algorithmique".

# 3. Copier le projet (voir §3), puis :
cd C:\XAUUSD-SCALPER-X10
pip install -r requirements.txt

# 4. Test rapide
python -c "import MetaTrader5 as mt5; print(mt5.initialize(), mt5.account_info())"
# Doit afficher True + les infos du compte démo

# 5. Auto-démarrage au boot
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1

# 6. Lancer
start.bat
```

## 3. Quoi transférer depuis le PC local

Utiliser `scripts\package_for_vps.ps1` (crée `XAUUSD-SCALPER-X10_vps.zip`) :

**Inclus** — code (`agents/`, `core/`, `engine/`, `dashboard/`, `scripts/`,
`strategies/`), données (`data/raw/*.csv`), `knowledge_base/`,
`agent_db.sqlite` (≈19 Mo après nettoyage), `start.bat`, `start.py`,
`start_hidden.vbs`, `requirements.txt`.

**Exclus** — `logs/`, `__pycache__/`, `.git/`, `Nouveau Site Ia/`,
`backtrader-pullback-window-xauusd/`, `claude-trading-skills/` (sans rapport
avec l'exécution).

> Arrêter le système local avant de zipper (sinon la DB est en cours
> d'écriture). Après migration, **ne pas faire tourner les deux systèmes en
> même temps sur le même compte MT5** : deux instances passeraient des ordres
> en double. Arrêt local définitif = supprimer le raccourci dans
> `shell:startup`.

## 4. Sécurité

- **Le dashboard (port 8050) n'a pas d'authentification.** Il écoute
  désormais sur `127.0.0.1` par défaut : il n'est accessible que depuis le
  VPS lui-même (via RDP, ouvrir `http://localhost:8050`). Ne JAMAIS mettre
  `DASHBOARD_HOST=0.0.0.0` sur un VPS exposé à Internet.
- RDP : mot de passe fort, et si possible restreindre le port 3389 à ton IP
  dans le pare-feu du fournisseur.
- Windows Update : activer les mises à jour de sécurité automatiques,
  redémarrage planifié hors sessions de trading (samedi).

## 5. Vérifications post-migration

1. `logs\system.log` : `25 agents running`, `MT5 connected`.
2. Dashboard `http://localhost:8050` (depuis le VPS) : agents verts.
3. Attendre un scan : `Scanning N closed M5 bars` dans les logs.
4. Ordre test éventuel : `python scripts\force_test_trade.py` (compte démo).
5. Après 24 h : vérifier qu'aucun `Internet connection lost` n'apparaît.

## 6. Entretien

- La DB est nettoyée du gros historique (les courbes d'equity ne sont plus
  stockées). Si elle regrossit au-delà de ~500 Mo, investiguer avec
  `SELECT SUM(LENGTH(result)) FROM task_queue`.
- `logs/system.log` grossit sans rotation : purger de temps en temps.
