"""Plugin Scout Agent: discovers, evaluates, and installs useful external packages."""
import subprocess
import sys
from datetime import datetime, timezone
from typing import List, Tuple

import requests

from agents.base_agent import BaseAgent


# ── Search configuration ──────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "python trading indicators",
    "python technical analysis library",
    "python backtesting framework",
    "python XAUUSD forex",
    "python optuna trading optimization",
    "python financial data source",
    "python MetaTrader5 connector",
]

# Known useful packages the scout should be aware of (won't re-discover)
KNOWN_PACKAGES = {
    "ta", "pandas", "numpy", "optuna", "plotly", "flask",
    "anthropic", "MetaTrader5", "requests",
}

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_candidate(candidate: dict, min_stars: int = 50) -> Tuple[bool, str]:
    """
    Evaluate a GitHub repository candidate.

    Returns (passed, reason). `reason` explains rejection or acceptance.
    """
    name = candidate.get("full_name", "unknown")
    stars = candidate.get("stargazers_count", 0)
    archived = candidate.get("archived", False)
    pushed_at = candidate.get("pushed_at", "")

    if archived:
        return False, f"{name}: archived repository"

    if stars < min_stars:
        return False, f"{name}: only {stars} stars (minimum {min_stars})"

    # Check if last push was within the last 2 years
    if pushed_at:
        try:
            last_push = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_push).days
            if age_days > 730:
                return False, f"{name}: last push {age_days} days ago (stale)"
        except (ValueError, TypeError):
            pass

    lic = candidate.get("license")
    if lic is None:
        return False, f"{name}: no license specified"

    return True, f"{name}: {stars} stars, active, licensed"


# ── Agent ─────────────────────────────────────────────────────────────────────

class PluginScout(BaseAgent):
    """Discovers and installs useful Python packages from GitHub/PyPI."""

    name = "plugin_scout"

    def __init__(self, db):
        super().__init__(agent_id="plugin_scout", db=db)
        self._query_index = 0

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Plugin Scout ready")

    def tick(self):
        # Rotate through search queries one per tick
        query = SEARCH_QUERIES[self._query_index % len(SEARCH_QUERIES)]
        self._query_index += 1

        self.logger.info(f"Searching GitHub for: {query}")
        candidates = self._search_github(query)

        if not candidates:
            self.logger.info("No candidates found this tick")
            return

        installed_count = 0
        for candidate in candidates[:5]:  # Evaluate top 5 results per query
            passed, reason = evaluate_candidate(candidate, min_stars=50)
            if not passed:
                self.logger.debug(f"Rejected: {reason}")
                continue

            pkg_name = self._extract_package_name(candidate)
            if not pkg_name or self._is_already_installed(pkg_name):
                continue
            if pkg_name in KNOWN_PACKAGES:
                continue

            # Try installing
            success = self._safe_install(pkg_name)
            if success:
                self._register_plugin(
                    plugin_id=pkg_name,
                    name=candidate.get("name", pkg_name),
                    source_url=candidate.get("html_url", ""),
                    install_type="pip",
                    description=candidate.get("description", "")[:200],
                )
                installed_count += 1
                self.emit_event("milestone",
                    f"Installed plugin: {pkg_name}",
                    metadata={"package": pkg_name, "stars": candidate.get("stargazers_count")},
                )

        if installed_count:
            self.logger.info(f"Installed {installed_count} new package(s)")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 3600)

    # ── GitHub search ──────────────────────────────────────────────────────────

    def _search_github(self, query: str) -> list:
        """Search GitHub repositories. Returns list of repo dicts."""
        try:
            resp = requests.get(
                GITHUB_SEARCH_URL,
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                timeout=15,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                return resp.json().get("items", [])
            self.logger.warning(f"GitHub search returned {resp.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.warning(f"GitHub search failed: {e}")
            return []

    # ── Package extraction ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_package_name(candidate: dict) -> str:
        """
        Extract a pip-installable package name from a GitHub repo.
        Uses the repo name as the pip package name (common convention).
        """
        name = candidate.get("name", "")
        # Sanitize: only allow alphanumeric, hyphens, underscores
        sanitized = "".join(c for c in name if c.isalnum() or c in "-_")
        return sanitized.lower() if sanitized else ""

    # ── Safe installation ──────────────────────────────────────────────────────

    # Allowlist of packages safe to auto-install
    APPROVED_PACKAGES = {
        "pandas-ta", "ta-lib", "mplfinance", "vectorbt", "backtesting",
        "pyalgotrade", "finplot", "lightweight-charts", "yfinance",
        "ccxt", "freqtrade", "jesse", "tulipy", "finta",
    }

    def _safe_install(self, package_name: str) -> bool:
        """
        Install a pip package in a subprocess. Returns True on success.
        Only installs packages from the approved allowlist.
        """
        if package_name not in self.APPROVED_PACKAGES:
            self.logger.info(f"Skipping {package_name}: not in approved allowlist (scout-only)")
            self._register_plugin(
                plugin_id=package_name,
                name=package_name,
                source_url="",
                install_type="scouted",
                description=f"Discovered but not auto-installed (not in allowlist)",
            )
            return False

        self.logger.info(f"Attempting to install approved package: {package_name}")
        try:
            # Dry run first
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--dry-run", package_name],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self.logger.warning(f"Dry-run failed for {package_name}: {result.stderr[:200]}")
                return False

            # Actual install
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                self.logger.info(f"Successfully installed {package_name}")
                return True
            else:
                self.logger.warning(f"Install failed for {package_name}: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Install timed out for {package_name}")
            return False
        except Exception as e:
            self.logger.error(f"Install error for {package_name}: {e}")
            return False

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _register_plugin(
        self,
        plugin_id: str,
        name: str,
        source_url: str,
        install_type: str,
        description: str,
    ):
        """Insert a new plugin record into the plugins table."""
        self.db.execute(
            "INSERT OR IGNORE INTO plugins "
            "(id, name, source_url, install_type, status, installed_by, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (plugin_id, name, source_url, install_type, "installed", self.agent_id, description),
        )

    def _is_already_installed(self, plugin_id: str) -> bool:
        """Check if a plugin is already registered in the DB."""
        row = self.db.fetchone("SELECT id FROM plugins WHERE id = ?", (plugin_id,))
        return row is not None
