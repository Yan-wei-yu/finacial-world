import json

import pytest

from pipeline.macro import (
    build_macro,
    collect_macro,
    fomc_events,
    one_off_events,
    parse_ff,
    recurring_events,
    translate_title,
)


@pytest.fixture
def terms(config):
    return config.macro_terms


@pytest.fixture
def ff_raw(fixtures_dir):
    return json.loads((fixtures_dir / "ff_sample.json").read_text(encoding="utf-8"))


def test_translate_title_exact_pattern_and_fallback(terms):
    assert translate_title("CPI y/y", terms) == "CPI 年增率"
    assert translate_title("FOMC Member Waller Speaks", terms) == "FOMC 委員 Waller 談話"
    assert translate_title("Fed Chairman Warsh Speaks", terms) == "聯準會主席 Warsh 談話"
    assert translate_title("Some New Indicator", terms) == "Some New Indicator"


def test_parse_ff_filters_by_country_and_impact(terms, ff_raw):
    events = parse_ff(ff_raw, terms)

    assert [e["title"] for e in events] == ["CPI y/y", "FOMC Member Waller Speaks", "GDP q/y"]
    cpi = events[0]
    assert cpi["datetime"] == "2026-10-14T12:30:00Z"
    assert cpi["title_zh"] == "CPI 年增率"
    assert cpi["country_label"] == "美國"
    assert cpi["forecast"] == "3.6%" and cpi["previous"] == "3.4%"
    assert events[1]["forecast"] is None
    assert events[2]["country"] == "CNY"


def test_parse_ff_tolerates_garbage(terms):
    assert parse_ff(None, terms) == []
    assert parse_ff(["nope", {"country": "USD"}], terms) == []


def test_fomc_events_convert_eastern_time_across_dst(config, now):
    events = fomc_events(config.events["fomc"], now, horizon_days=60)

    assert [e["datetime"] for e in events] == ["2026-10-28T18:00:00Z", "2026-12-09T19:00:00Z"]
    assert events[0]["date"] == "2026-10-29"  # 02:00 the next morning in Taipei
    assert "點陣圖" in events[1]["title"]
    assert events[0]["kind"] == "fomc"


def test_recurring_events_within_horizon(config, now):
    events = recurring_events(config.events["recurring"], now, horizon_days=45)
    by_id = {}
    for e in events:
        by_id.setdefault(e["id"], []).append(e["date"])

    assert by_id["korea-exports"] == ["2026-11-01"]
    assert by_id["korea-exports-20d"] == ["2026-10-21", "2026-11-21"]
    assert by_id["dram-contract"] == ["2026-10-31"]  # 11/30 is just past the 45-day horizon
    assert by_id["tsmc-revenue"] == ["2026-11-10"]
    assert all(e["datetime"] is None for e in events)


def test_one_off_events_respect_horizon(config, now):
    assert [e["date"] for e in one_off_events(config.events["one_off"], now, horizon_days=60)] == ["2026-11-30"]
    assert one_off_events(config.events["one_off"], now, horizon_days=10) == []


def test_build_macro_sorts_upcoming_by_date(config, terms, ff_raw, now):
    doc = build_macro(parse_ff(ff_raw, terms), config.events, now, horizon_days=45)

    dates = [e["date"] for e in doc["upcoming"]]
    assert dates == sorted(dates)
    assert len(doc["week"]) == 3
    assert doc["generated_at"] == "2026-10-15T13:00:00Z"


def test_collect_macro_keeps_static_events_when_feed_fails(config, terms, now):
    def broken():
        raise ConnectionError("ff down")

    doc, errors = collect_macro(config.events, terms, now, fetcher=broken)

    assert doc["week"] == []
    assert doc["upcoming"]
    assert errors and "ff down" in errors[0]


def test_collect_macro_success(config, terms, ff_raw, now):
    doc, errors = collect_macro(config.events, terms, now, fetcher=lambda: ff_raw)

    assert errors == []
    assert len(doc["week"]) == 3
