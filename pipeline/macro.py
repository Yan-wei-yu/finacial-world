"""Economic calendar: ForexFactory's weekly feed plus static FOMC / recurring indicator dates."""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from pipeline.io_utils import parse_iso, to_iso
from pipeline.text import clean_text

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
EASTERN = ZoneInfo("America/New_York")
TAIPEI = ZoneInfo("Asia/Taipei")
FOMC_DECISION_TIME = time(14, 0)


def fetch_ff() -> list[dict[str, Any]]:
    response = requests.get(FF_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0 (finacial-world dashboard)"})
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def translate_title(title: str, terms: Mapping[str, Any]) -> str:
    exact = terms.get("titles", {}).get(title)
    if exact:
        return exact
    for pattern in terms.get("patterns", []):
        match = re.match(pattern["regex"], title)
        if match:
            return pattern["zh"].format(*match.groups())
    return title


def parse_ff(raw: Any, terms: Mapping[str, Any]) -> list[dict[str, Any]]:
    filters = {country: set(levels) for country, levels in terms.get("filters", {}).items()}
    labels = terms.get("country_labels", {})
    events = []
    for event in raw if isinstance(raw, list) else []:
        if not isinstance(event, Mapping):
            continue
        title, country, impact = clean_text(event.get("title"), 120), event.get("country"), event.get("impact")
        moment = parse_iso(event.get("date"))
        if not title or moment is None or impact not in filters.get(country, set()):
            continue
        events.append(
            {
                "title": title,
                "title_zh": translate_title(title, terms),
                "country": country,
                "country_label": labels.get(country, country),
                "impact": impact,
                "datetime": to_iso(moment),
                "forecast": clean_text(event.get("forecast"), 24) or None,
                "previous": clean_text(event.get("previous"), 24) or None,
            }
        )
    return sorted(events, key=lambda e: e["datetime"])


def _taipei_date(moment: datetime) -> str:
    return moment.astimezone(TAIPEI).date().isoformat()


def fomc_events(meetings: Sequence[Mapping[str, Any]], now: datetime, horizon_days: int) -> list[dict[str, Any]]:
    events = []
    for meeting in meetings:
        day = date.fromisoformat(meeting["date"])
        moment = datetime.combine(day, FOMC_DECISION_TIME, tzinfo=EASTERN)
        if not now - timedelta(hours=6) <= moment <= now + timedelta(days=horizon_days):
            continue
        events.append(
            {
                "id": f"fomc-{day.isoformat()}",
                "title": "FOMC 利率決議" + ("（含點陣圖）" if meeting.get("sep") else ""),
                "date": _taipei_date(moment),
                "datetime": to_iso(moment),
                "kind": "fomc",
                "approx": False,
                "affects": ["NASDAQ", "SOX"],
                "note": "聲明公布後 30 分鐘主席召開記者會",
            }
        )
    return events


def _month_days(start: date, end: date, day_rule: Any) -> list[date]:
    days, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        last = calendar.monthrange(year, month)[1]
        day = last if day_rule == "last" else min(int(day_rule), last)
        candidate = date(year, month, day)
        if start <= candidate <= end:
            days.append(candidate)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return days


def recurring_events(specs: Sequence[Mapping[str, Any]], now: datetime, horizon_days: int) -> list[dict[str, Any]]:
    start = now.astimezone(TAIPEI).date()
    end = start + timedelta(days=horizon_days)
    events = []
    for spec in specs:
        for day in _month_days(start, end, spec["day"]):
            events.append(
                {
                    "id": spec["id"],
                    "title": spec["title"],
                    "date": day.isoformat(),
                    "datetime": None,
                    "kind": "indicator",
                    "approx": bool(spec.get("approx")),
                    "affects": list(spec.get("affects", [])),
                    "note": spec.get("note", ""),
                }
            )
    return events


def one_off_events(specs: Sequence[Mapping[str, Any]], now: datetime, horizon_days: int) -> list[dict[str, Any]]:
    start = now.astimezone(TAIPEI).date()
    end = start + timedelta(days=horizon_days)
    events = []
    for spec in specs:
        day = date.fromisoformat(spec["date"])
        if start <= day <= end:
            events.append(
                {
                    "id": f"event-{day.isoformat()}",
                    "title": spec["title"],
                    "date": day.isoformat(),
                    "datetime": None,
                    "kind": "event",
                    "approx": bool(spec.get("approx")),
                    "affects": list(spec.get("affects", [])),
                    "note": spec.get("note", ""),
                }
            )
    return events


def build_macro(week: Sequence[Mapping[str, Any]], events_cfg: Mapping[str, Any], now: datetime, horizon_days: int = 60) -> dict[str, Any]:
    upcoming = [
        *fomc_events(events_cfg.get("fomc", []), now, horizon_days),
        *recurring_events(events_cfg.get("recurring", []), now, horizon_days),
        *one_off_events(events_cfg.get("one_off", []), now, horizon_days),
    ]
    upcoming.sort(key=lambda e: (e["date"], e["datetime"] or ""))
    return {"generated_at": to_iso(now), "week": list(week), "upcoming": upcoming}


def collect_macro(
    events_cfg: Mapping[str, Any],
    terms: Mapping[str, Any],
    now: datetime,
    *,
    fetcher: Callable[[], Any] = fetch_ff,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        week = parse_ff(fetcher(), terms)
    except Exception as exc:  # network / JSON errors
        week = []
        errors.append(f"ForexFactory calendar: {type(exc).__name__}: {exc}")
    return build_macro(week, events_cfg, now), errors
