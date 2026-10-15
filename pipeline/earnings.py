"""Earnings calendar (法說會) with consensus estimates and recent surprises, via yfinance."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.io_utils import num, parse_iso, to_iso

EASTERN = ZoneInfo("America/New_York")
SESSION_PRE, SESSION_MID, SESSION_POST, SESSION_TBD = "盤前", "盤中", "盤後", "時間未定"
HISTORY_KEEP = 4
MATCH_WINDOW_DAYS = 3
MAX_PLAUSIBLE_SURPRISE = 500.0  # larger values are unit mix-ups in Yahoo data (e.g. KRW vs USD)
MARKET_CLOSE = time(16, 0)

CalendarFetcher = Callable[[str], Any]
HistoryFetcher = Callable[[str], list[dict[str, Any]]]


def _to_date(value: Any) -> date | None:
    if isinstance(value, (list, tuple)):
        return _to_date(value[0]) if value else None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def parse_calendar(calendar: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not calendar:
        return None
    day = _to_date(calendar.get("Earnings Date"))
    if day is None:
        return None
    return {
        "date": day.isoformat(),
        "eps_est": num(calendar.get("Earnings Average")),
        "eps_low": num(calendar.get("Earnings Low")),
        "eps_high": num(calendar.get("Earnings High")),
        "rev_est": num(calendar.get("Revenue Average")),
        "rev_low": num(calendar.get("Revenue Low")),
        "rev_high": num(calendar.get("Revenue High")),
    }


def parse_history(frame: Any) -> list[dict[str, Any]]:
    """Rows of yfinance get_earnings_dates(): estimate, reported EPS and surprise, newest first."""
    if frame is None or getattr(frame, "empty", True):
        return []
    rows = []
    for index, row in frame.iterrows():
        moment = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
        if not isinstance(moment, datetime):
            continue
        aware = moment if moment.tzinfo else moment.replace(tzinfo=EASTERN)
        surprise = num(row.get("Surprise(%)"))
        suspect = surprise is not None and abs(surprise) > MAX_PLAUSIBLE_SURPRISE
        rows.append(
            {
                "datetime": to_iso(aware),
                "date": aware.astimezone(EASTERN).date().isoformat(),
                "eps_est": num(row.get("EPS Estimate")),
                "eps_actual": num(row.get("Reported EPS")),
                "surprise_pct": None if suspect else surprise,
                "suspect": suspect,
            }
        )
    return sorted(rows, key=lambda r: r["datetime"], reverse=True)


def session_label(moment_iso: str | None) -> str:
    moment = parse_iso(moment_iso)
    if moment is None:
        return SESSION_TBD
    eastern = moment.astimezone(EASTERN)
    minutes = eastern.hour * 60 + eastern.minute
    if minutes == 0:
        return SESSION_TBD  # Yahoo uses midnight when the time is unknown
    if minutes < 9 * 60 + 30:
        return SESSION_PRE
    if minutes >= 15 * 60:  # Yahoo keeps after-close placeholders at 20:00Z even after DST ends
        return SESSION_POST
    return SESSION_MID


def fetch_calendar(symbol: str) -> Any:
    import yfinance as yf

    return yf.Ticker(symbol).calendar


def fetch_earnings_history(symbol: str) -> list[dict[str, Any]]:
    import yfinance as yf

    return parse_history(yf.Ticker(symbol).get_earnings_dates(limit=8))


def _days_apart(left: str, right: str) -> int:
    return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)


def _event_time(match: Mapping[str, Any] | None) -> tuple[str | None, str | None, str]:
    """(exchange date, normalised ISO time, session) for a pending Yahoo earnings row."""
    moment = parse_iso(match["datetime"]) if match else None
    if moment is None:
        return None, None, SESSION_TBD
    eastern = moment.astimezone(EASTERN)
    session = session_label(match["datetime"])
    if session == SESSION_TBD:
        return eastern.date().isoformat(), None, session  # only the date is known
    if session == SESSION_POST:
        moment = datetime.combine(eastern.date(), MARKET_CLOSE, tzinfo=EASTERN)
    return eastern.date().isoformat(), to_iso(moment), session


def _upcoming_entry(watch: Mapping[str, Any], calendar: Mapping[str, Any] | None, history: Sequence[Mapping[str, Any]], today: date, horizon: date) -> dict[str, Any] | None:
    pending = [r for r in history if r["eps_actual"] is None and date.fromisoformat(r["date"]) >= today]
    target = calendar["date"] if calendar else (pending[-1]["date"] if pending else None)
    if target is None or not today <= date.fromisoformat(target) <= horizon:
        return None
    if any(r["eps_actual"] is not None and _days_apart(r["date"], target) <= 1 for r in history):
        return None  # already reported; it will show up under recent results
    match = next((r for r in pending if _days_apart(r["date"], target) <= MATCH_WINDOW_DAYS), None)
    exchange_date, moment, session = _event_time(match)
    estimates = calendar or {}
    return {
        "symbol": watch["symbol"],
        "name_zh": watch.get("name_zh", watch["symbol"]),
        "group": watch.get("group"),
        "date": exchange_date or target,
        "datetime": moment,
        "session": session,
        "eps_est": estimates.get("eps_est") if estimates.get("eps_est") is not None else (match or {}).get("eps_est"),
        "eps_low": estimates.get("eps_low"),
        "eps_high": estimates.get("eps_high"),
        "rev_est": estimates.get("rev_est"),
        "rev_currency": watch.get("rev_currency", "USD"),
        "is_holding": watch.get("group") == "holding",
    }


def build_earnings(
    watch: Sequence[Mapping[str, Any]],
    calendars: Mapping[str, Mapping[str, Any] | None],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
    now: datetime,
    horizon_days: int = 75,
    recent_days: int = 30,
) -> dict[str, Any]:
    today = now.astimezone(EASTERN).date()
    horizon = today + timedelta(days=horizon_days)
    upcoming, recent, history_by_symbol = [], [], {}
    for entry in watch:
        symbol = entry["symbol"]
        history = list(histories.get(symbol) or [])
        upcoming_entry = _upcoming_entry(entry, calendars.get(symbol), history, today, horizon)
        if upcoming_entry:
            upcoming.append(upcoming_entry)
        reported = [r for r in history if r["eps_actual"] is not None]
        for row in reported:
            if (today - date.fromisoformat(row["date"])).days <= recent_days:
                recent.append({"symbol": symbol, "name_zh": entry.get("name_zh", symbol), "group": entry.get("group"), "is_holding": entry.get("group") == "holding", **row})
        if entry.get("group") == "holding":
            history_by_symbol[symbol] = reported[:HISTORY_KEEP]
    upcoming.sort(key=lambda e: (e["date"], e["symbol"]))
    recent.sort(key=lambda e: e["datetime"], reverse=True)
    return {"upcoming": upcoming, "recent": recent, "history": history_by_symbol}


def merge_earnings(
    fresh: Mapping[str, Any],
    previous: Any,
    failed_calendar: set[str],
    failed_history: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Keep the previous entries of symbols whose lookups failed this run instead of silently dropping them."""
    prev = previous if isinstance(previous, Mapping) else {}
    today = now.astimezone(EASTERN).date().isoformat()
    fresh_upcoming = list(fresh.get("upcoming", []))
    have = {e.get("symbol") for e in fresh_upcoming}
    carried_upcoming = [
        e
        for e in prev.get("upcoming", [])
        if isinstance(e, Mapping) and e.get("symbol") in failed_calendar and e.get("symbol") not in have and str(e.get("date", "")) >= today
    ]
    carried_recent = [r for r in prev.get("recent", []) if isinstance(r, Mapping) and r.get("symbol") in failed_history]
    history = dict(fresh.get("history", {}))
    for symbol, rows in (prev.get("history") or {}).items():
        if symbol in failed_history and rows:
            history[symbol] = rows
    return {
        **fresh,
        "upcoming": sorted([*fresh_upcoming, *carried_upcoming], key=lambda e: (e.get("date", ""), e.get("symbol", ""))),
        "recent": sorted([*fresh.get("recent", []), *carried_recent], key=lambda r: r.get("datetime") or "", reverse=True),
        "history": history,
    }


def collect_earnings(
    watch: Sequence[Mapping[str, Any]],
    now: datetime,
    *,
    calendar_fetcher: CalendarFetcher = fetch_calendar,
    history_fetcher: HistoryFetcher = fetch_earnings_history,
    max_workers: int = 4,
) -> tuple[dict[str, Any], list[str]]:
    def load(entry: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], dict[str, str]]:
        symbol, problems = entry["symbol"], {}
        try:
            calendar = parse_calendar(calendar_fetcher(symbol))
        except Exception as exc:  # yfinance raises assorted types
            calendar = None
            problems["calendar"] = f"{symbol} calendar: {type(exc).__name__}: {exc}"
        try:
            history = list(history_fetcher(symbol) or [])
        except Exception as exc:
            history = []
            problems["history"] = f"{symbol} history: {type(exc).__name__}: {exc}"
        return symbol, calendar, history, problems

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(load, watch))
    calendars = {symbol: calendar for symbol, calendar, _, _ in results}
    histories = {symbol: history for symbol, _, history, _ in results}
    errors = [message for *_, problems in results for message in problems.values()]
    doc = build_earnings(watch, calendars, histories, now)
    return {
        "generated_at": to_iso(now),
        **doc,
        "failed_calendar": sorted(symbol for symbol, *_, problems in results if "calendar" in problems),
        "failed_history": sorted(symbol for symbol, *_, problems in results if "history" in problems),
    }, errors
