"""News Calendar Agent: fetches economic calendar events and provides news-aware trading filters."""
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests

from agents.base_agent import BaseAgent


# High-impact USD events that move XAUUSD
USD_HIGH_IMPACT_KEYWORDS = [
    "Non-Farm Employment Change",
    "Nonfarm Payrolls",
    "NFP",
    "FOMC",
    "Federal Funds Rate",
    "CPI",
    "Consumer Price Index",
    "PPI",
    "Producer Price Index",
    "GDP",
    "Gross Domestic Product",
    "Retail Sales",
    "Unemployment Claims",
    "Initial Jobless Claims",
    "Unemployment Rate",
    "Core CPI",
    "Core PPI",
    "Core PCE",
    "PCE Price Index",
    "ISM Manufacturing",
    "ISM Services",
    "ADP Non-Farm",
    "JOLTS",
    "Jackson Hole",
    "Fed Chair",
    "Powell",
]

# Forex Factory calendar API (free, no auth required)
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Blackout window: minutes before and after a high-impact event
BLACKOUT_BEFORE_MINUTES = 30
BLACKOUT_AFTER_MINUTES = 30


def _parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse Forex Factory date and time strings into a UTC datetime."""
    if not date_str or not time_str:
        return None
    # FF uses formats like "01-10-2026" and "8:30am"
    time_str = time_str.strip()
    if time_str.lower() in ("", "all day", "tentative", "day"):
        return None
    try:
        combined = f"{date_str} {time_str}"
        # Try common FF formats
        for fmt in ("%m-%d-%Y %I:%M%p", "%m-%d-%Y %H:%M"):
            try:
                dt = datetime.strptime(combined, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _is_usd_high_impact(event: dict) -> bool:
    """Check if an event is a USD high-impact event relevant to XAUUSD."""
    country = event.get("country", "").upper()
    if country != "USD":
        return False
    impact = event.get("impact", "").lower()
    if impact not in ("high", "holiday"):
        return False
    title = event.get("title", "")
    for keyword in USD_HIGH_IMPACT_KEYWORDS:
        if keyword.lower() in title.lower():
            return True
    # If it's marked high impact and USD, include it anyway
    return impact == "high"


def _build_static_fallback_events() -> List[dict]:
    """Generate a static list of known recurring high-impact events for the current week."""
    now = datetime.now(timezone.utc)
    events = []

    # Find the first Friday of this month (approximate NFP)
    first_day = now.replace(day=1)
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    nfp_date = first_friday.replace(hour=12, minute=30, second=0, microsecond=0)
    if abs((nfp_date - now).days) <= 7:
        events.append({
            "title": "Non-Farm Employment Change",
            "country": "USD",
            "date": nfp_date.strftime("%m-%d-%Y"),
            "time": "8:30am",
            "impact": "High",
            "forecast": "",
            "previous": "",
            "dt": nfp_date,
        })

    # CPI is typically mid-month (around the 13th)
    cpi_date = now.replace(day=13, hour=12, minute=30, second=0, microsecond=0)
    if abs((cpi_date - now).days) <= 7:
        events.append({
            "title": "CPI m/m",
            "country": "USD",
            "date": cpi_date.strftime("%m-%d-%Y"),
            "time": "8:30am",
            "impact": "High",
            "forecast": "",
            "previous": "",
            "dt": cpi_date,
        })

    # FOMC: 8 times a year, roughly every 6 weeks (approximate with known months)
    fomc_months = [1, 3, 5, 6, 7, 9, 11, 12]
    if now.month in fomc_months:
        # Approximate: 3rd Wednesday of the month
        third_wed = now.replace(day=1)
        days_until_wed = (2 - third_wed.weekday()) % 7
        third_wed = third_wed + timedelta(days=days_until_wed + 14)
        fomc_date = third_wed.replace(hour=18, minute=0, second=0, microsecond=0)
        if abs((fomc_date - now).days) <= 7:
            events.append({
                "title": "FOMC Statement",
                "country": "USD",
                "date": fomc_date.strftime("%m-%d-%Y"),
                "time": "2:00pm",
                "impact": "High",
                "forecast": "",
                "previous": "",
                "dt": fomc_date,
            })

    return events


def is_blackout_period(db, timestamp: Optional[datetime] = None) -> bool:
    """Check if a given timestamp falls within a news blackout window.

    Args:
        db: Database instance
        timestamp: The datetime to check (UTC). Defaults to now.

    Returns:
        True if the timestamp is within a blackout window.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Make sure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    row = db.fetchone(
        "SELECT config FROM agent_registry WHERE id = ?", ("news_calendar",)
    )
    if not row or not row["config"]:
        return False

    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    blackout_windows = config.get("blackout_windows", [])

    for window in blackout_windows:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        if start <= timestamp <= end:
            return True
    return False


def get_upcoming_events(db, hours_ahead: int = 24) -> list:
    """Return list of upcoming economic events within the next N hours.

    Args:
        db: Database instance
        hours_ahead: How many hours ahead to look.

    Returns:
        List of event dicts with title, time, impact info.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    rows = db.fetchall(
        "SELECT event_message, metadata, timestamp FROM events "
        "WHERE agent_id = 'news_calendar' AND event_type = 'news_calendar' "
        "AND timestamp >= ? ORDER BY timestamp",
        (now.isoformat(),),
    )

    events = []
    for row in rows:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        event_time_str = meta.get("event_time")
        if event_time_str:
            event_time = datetime.fromisoformat(event_time_str)
            if event_time <= cutoff:
                events.append({
                    "title": meta.get("title", row["event_message"]),
                    "time": event_time_str,
                    "impact": meta.get("impact", "unknown"),
                    "country": meta.get("country", "USD"),
                    "forecast": meta.get("forecast", ""),
                    "previous": meta.get("previous", ""),
                })
    return events


class NewsCalendarAgent(BaseAgent):
    """Fetches economic calendar events and manages news blackout windows for XAUUSD."""

    name = "news_calendar"

    def __init__(self, db):
        super().__init__(agent_id="news_calendar", db=db)

    def setup(self):
        self.logger.info("News Calendar Agent starting")
        self.emit_event("info", "News Calendar Agent initialized")

    def tick(self):
        events = self._fetch_events()
        high_impact = [e for e in events if _is_usd_high_impact(e)]

        self.logger.info(f"Fetched {len(events)} events, {len(high_impact)} high-impact USD")

        # Store events in the events table
        self._store_events(high_impact)

        # Build and store blackout windows
        blackout_windows = self._build_blackout_windows(high_impact)
        self.set_config("blackout_windows", blackout_windows)
        self.set_config("last_fetch", datetime.now(timezone.utc).isoformat())

        # Emit summary of upcoming high-impact events (next 7 days)
        now = datetime.now(timezone.utc)
        upcoming_7d = [
            e for e in high_impact
            if e.get("dt") and e["dt"] > now and (e["dt"] - now).days <= 7
        ]
        if upcoming_7d:
            summary_lines = []
            for e in upcoming_7d:
                time_str = e["dt"].strftime("%Y-%m-%d %H:%M UTC") if e.get("dt") else "TBD"
                summary_lines.append(f"  {e['title']} @ {time_str}")
            summary = f"Upcoming high-impact events (next 7 days):\n" + "\n".join(summary_lines)
            self.emit_event("info", summary, {
                "event_count": len(upcoming_7d),
                "events": [
                    {"title": e["title"], "time": e["dt"].isoformat() if e.get("dt") else None}
                    for e in upcoming_7d
                ],
            })

        active_blackouts = [
            w for w in blackout_windows
            if datetime.fromisoformat(w["start"]) <= now <= datetime.fromisoformat(w["end"])
        ]
        if active_blackouts:
            names = ", ".join(w["event_name"] for w in active_blackouts)
            self.emit_event("warning", f"Active blackout windows: {names}")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 3600)

    def _fetch_events(self) -> List[dict]:
        """Fetch events from Forex Factory calendar API, with static fallback."""
        try:
            resp = requests.get(FF_CALENDAR_URL, timeout=15)
            resp.raise_for_status()
            raw_events = resp.json()
            events = []
            for ev in raw_events:
                dt = _parse_ff_datetime(ev.get("date", ""), ev.get("time", ""))
                events.append({
                    "title": ev.get("title", ""),
                    "country": ev.get("country", ""),
                    "date": ev.get("date", ""),
                    "time": ev.get("time", ""),
                    "impact": ev.get("impact", ""),
                    "forecast": ev.get("forecast", ""),
                    "previous": ev.get("previous", ""),
                    "dt": dt,
                })
            self.logger.info(f"Fetched {len(events)} events from Forex Factory")
            return events
        except Exception as e:
            self.logger.warning(f"Failed to fetch FF calendar: {e}. Using static fallback.")
            self.emit_event("warning", f"Calendar API failed: {e}. Using static fallback.")
            return _build_static_fallback_events()

    def _store_events(self, events: List[dict]):
        """Store high-impact events in the events table."""
        for ev in events:
            if not ev.get("dt"):
                continue
            metadata = {
                "title": ev["title"],
                "country": ev.get("country", "USD"),
                "impact": ev.get("impact", "High"),
                "event_time": ev["dt"].isoformat(),
                "forecast": ev.get("forecast", ""),
                "previous": ev.get("previous", ""),
            }
            self.emit_event(
                "news_calendar",
                f"{ev['title']} @ {ev['dt'].strftime('%Y-%m-%d %H:%M UTC')}",
                metadata,
            )

    def _build_blackout_windows(self, events: List[dict]) -> List[dict]:
        """Build blackout windows around high-impact events."""
        windows = []
        for ev in events:
            if not ev.get("dt"):
                continue
            start = ev["dt"] - timedelta(minutes=BLACKOUT_BEFORE_MINUTES)
            end = ev["dt"] + timedelta(minutes=BLACKOUT_AFTER_MINUTES)
            windows.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "event_name": ev["title"],
            })
        return windows
