from datetime import date, datetime

import pandas as pd
import pytest

from pipeline.earnings import build_earnings, collect_earnings, parse_calendar, parse_history, session_label

NOK_CAL = {
    "Earnings Date": [date(2026, 10, 22)],
    "Earnings High": 0.08023,
    "Earnings Low": 0.056,
    "Earnings Average": 0.07203,
    "Revenue High": 5227000000,
    "Revenue Low": 4983000000,
    "Revenue Average": 5066953280,
}

WATCH = [
    {"symbol": "NOK", "name_zh": "諾基亞", "group": "holding", "rev_currency": "EUR"},
    {"symbol": "TSM", "name_zh": "台積電", "group": "semis", "rev_currency": "TWD"},
    {"symbol": "MU", "name_zh": "美光", "group": "memory", "rev_currency": "USD"},
    {"symbol": "FAR", "name_zh": "遠期", "group": "semis", "rev_currency": "USD"},
]


def test_parse_calendar_extracts_estimates():
    parsed = parse_calendar(NOK_CAL)

    assert parsed == {
        "date": "2026-10-22",
        "eps_est": 0.07203,
        "eps_low": 0.056,
        "eps_high": 0.08023,
        "rev_est": 5066953280.0,
        "rev_low": 4983000000.0,
        "rev_high": 5227000000.0,
    }


def test_parse_calendar_uses_first_date_of_range_and_handles_empty():
    ranged = {**NOK_CAL, "Earnings Date": [date(2026, 10, 27), date(2026, 10, 31)]}

    assert parse_calendar(ranged)["date"] == "2026-10-27"
    assert parse_calendar({}) is None
    assert parse_calendar(None) is None
    assert parse_calendar({"Earnings Date": []}) is None
    assert parse_calendar({"Earnings Date": "2026-11-10"})["date"] == "2026-11-10"


def test_parse_history_from_yfinance_frame():
    index = pd.DatetimeIndex(
        [pd.Timestamp("2026-10-22 08:00", tz="America/New_York"), pd.Timestamp("2026-07-23 01:00", tz="America/New_York")],
        name="Earnings Date",
    )
    frame = pd.DataFrame(
        {"EPS Estimate": [0.07, 0.07], "Reported EPS": [float("nan"), 0.08], "Surprise(%)": [float("nan"), 17.12]},
        index=index,
    )

    rows = parse_history(frame)

    assert rows[0] == {
        "datetime": "2026-10-22T12:00:00Z",
        "date": "2026-10-22",
        "eps_est": 0.07,
        "eps_actual": None,
        "surprise_pct": None,
        "suspect": False,
    }
    assert rows[1]["eps_actual"] == 0.08 and rows[1]["surprise_pct"] == 17.12
    assert parse_history(None) == []
    assert parse_history(pd.DataFrame()) == []


def test_parse_history_flags_implausible_surprise():
    index = pd.DatetimeIndex([pd.Timestamp("2026-07-28 16:00", tz="America/New_York")])
    frame = pd.DataFrame({"EPS Estimate": [4.87], "Reported EPS": [90.62], "Surprise(%)": [1760.69]}, index=index)

    [row] = parse_history(frame)

    assert row["surprise_pct"] is None
    assert row["suspect"] is True


@pytest.mark.parametrize(
    ("iso", "label"),
    [
        ("2026-10-22T12:00:00Z", "盤前"),
        ("2026-10-22T21:00:00Z", "盤後"),
        ("2026-10-22T16:00:00Z", "盤中"),
        ("2026-11-03T20:00:00Z", "盤後"),  # Yahoo keeps 20:00Z after DST ends (15:00 EST)
        ("2026-10-22T04:00:00Z", "時間未定"),
        (None, "時間未定"),
    ],
)
def test_session_label(iso, label):
    assert session_label(iso) == label


def test_build_earnings_splits_upcoming_recent_and_history(now):
    calendars = {
        "NOK": parse_calendar(NOK_CAL),
        "TSM": {"date": "2026-10-15", "eps_est": 4.52, "eps_low": None, "eps_high": None, "rev_est": 1.46e12, "rev_low": None, "rev_high": None},
        "MU": {"date": "2026-09-24", "eps_est": 30.0, "eps_low": None, "eps_high": None, "rev_est": None, "rev_low": None, "rev_high": None},
        "FAR": {"date": "2027-06-01", "eps_est": 1.0, "eps_low": None, "eps_high": None, "rev_est": None, "rev_low": None, "rev_high": None},
    }
    histories = {
        "NOK": [
            {"datetime": "2026-10-22T12:00:00Z", "date": "2026-10-22", "eps_est": 0.07, "eps_actual": None, "surprise_pct": None},
            {"datetime": "2026-07-23T05:00:00Z", "date": "2026-07-23", "eps_est": 0.07, "eps_actual": 0.08, "surprise_pct": 17.12},
        ],
        "MU": [{"datetime": "2026-09-24T20:00:00Z", "date": "2026-09-24", "eps_est": 30.0, "eps_actual": 32.0, "surprise_pct": 6.7}],
    }

    doc = build_earnings(WATCH, calendars, histories, now, horizon_days=75, recent_days=30)

    upcoming = {e["symbol"]: e for e in doc["upcoming"]}
    assert list(upcoming) == ["TSM", "NOK"]
    assert upcoming["NOK"]["session"] == "盤前"
    assert upcoming["NOK"]["datetime"] == "2026-10-22T12:00:00Z"
    assert upcoming["NOK"]["eps_est"] == 0.07203
    assert upcoming["NOK"]["rev_currency"] == "EUR"
    assert upcoming["NOK"]["is_holding"] is True
    assert upcoming["TSM"]["session"] == "時間未定"
    assert [r["symbol"] for r in doc["recent"]] == ["MU"]
    assert doc["recent"][0]["surprise_pct"] == 6.7
    assert doc["history"]["NOK"][0]["date"] == "2026-07-23"
    assert "TSM" not in doc["history"]


def test_upcoming_date_and_time_come_from_eastern_timestamp(now):
    # Calendar dates can be shifted by the machine's local timezone; the timestamp is authoritative.
    watch = [{"symbol": "AMD", "name_zh": "超微", "group": "semis", "rev_currency": "USD"}]
    calendars = {"AMD": {"date": "2026-11-04", "eps_est": 1.93, "eps_low": None, "eps_high": None, "rev_est": None, "rev_low": None, "rev_high": None}}
    histories = {"AMD": [{"datetime": "2026-11-03T20:00:00Z", "date": "2026-11-03", "eps_est": 1.9, "eps_actual": None, "surprise_pct": None}]}

    [event] = build_earnings(watch, calendars, histories, now)["upcoming"]

    assert event["date"] == "2026-11-03"
    assert event["session"] == "盤後"
    assert event["datetime"] == "2026-11-03T21:00:00Z"  # normalised to 16:00 EST


def test_build_earnings_moves_reported_event_out_of_upcoming(now):
    calendars = {"TSM": {"date": "2026-10-15", "eps_est": 4.52, "eps_low": None, "eps_high": None, "rev_est": None, "rev_low": None, "rev_high": None}}
    histories = {"TSM": [{"datetime": "2026-10-15T06:00:00Z", "date": "2026-10-15", "eps_est": 4.52, "eps_actual": 4.8, "surprise_pct": 6.2}]}

    doc = build_earnings(WATCH[1:2], calendars, histories, now)

    assert doc["upcoming"] == []
    assert doc["recent"][0]["eps_actual"] == 4.8


def test_collect_earnings_isolates_symbol_failures(now):
    def calendar_fetcher(symbol):
        if symbol == "TSM":
            raise RuntimeError("Yahoo blocked")
        return NOK_CAL

    def history_fetcher(symbol):
        if symbol == "MU":
            raise RuntimeError("scrape failed")
        return []

    doc, errors = collect_earnings(WATCH[:3], now, calendar_fetcher=calendar_fetcher, history_fetcher=history_fetcher)

    assert [e["symbol"] for e in doc["upcoming"]] == ["MU", "NOK"]
    assert any("TSM" in e and "Yahoo blocked" in e for e in errors)
    assert any("MU" in e and "scrape failed" in e for e in errors)
    assert "generated_at" in doc


def test_unknown_release_time_has_no_datetime(now):
    watch = [{"symbol": "AMD", "name_zh": "超微", "group": "semis", "rev_currency": "USD"}]
    calendars = {"AMD": {"date": "2026-11-03", "eps_est": 1.9, "eps_low": None, "eps_high": None, "rev_est": None, "rev_low": None, "rev_high": None}}
    histories = {"AMD": [{"datetime": "2026-11-03T05:00:00Z", "date": "2026-11-03", "eps_est": 1.9, "eps_actual": None, "surprise_pct": None}]}

    [event] = build_earnings(watch, calendars, histories, now)["upcoming"]

    assert event["session"] == "時間未定"
    assert event["datetime"] is None


def test_collect_earnings_reports_failed_parts(now):
    def calendar_fetcher(symbol):
        if symbol == "NOK":
            raise RuntimeError("429")
        return NOK_CAL

    def history_fetcher(symbol):
        if symbol == "TSM":
            raise RuntimeError("blocked")
        return []

    doc, _ = collect_earnings(WATCH[:2], now, calendar_fetcher=calendar_fetcher, history_fetcher=history_fetcher)

    assert doc["failed_calendar"] == ["NOK"]
    assert doc["failed_history"] == ["TSM"]


def test_merge_earnings_carries_over_failed_symbols(now):
    from pipeline.earnings import merge_earnings

    previous = {
        "upcoming": [
            {"symbol": "NOK", "date": "2026-10-22", "datetime": None},
            {"symbol": "MU", "date": "2026-10-20", "datetime": None},
            {"symbol": "OLD", "date": "2026-10-01", "datetime": None},
        ],
        "recent": [{"symbol": "TSM", "date": "2026-10-15", "datetime": "2026-10-15T06:00:00Z"}],
        "history": {"NOK": [{"date": "2026-07-23"}]},
    }
    fresh = {"upcoming": [{"symbol": "MU", "date": "2026-12-17", "datetime": None}], "recent": [], "history": {"NOK": []}}

    merged = merge_earnings(fresh, previous, failed_calendar={"NOK", "OLD"}, failed_history={"NOK", "TSM"}, now=now)

    assert [(e["symbol"], e["date"]) for e in merged["upcoming"]] == [("NOK", "2026-10-22"), ("MU", "2026-12-17")]
    assert merged["history"]["NOK"] == [{"date": "2026-07-23"}]
    assert [r["symbol"] for r in merged["recent"]] == ["TSM"]
