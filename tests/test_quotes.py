import pandas as pd
import pytest

from pipeline.config import AdrPair
from pipeline.quotes import (
    adr_premium,
    build_indicators,
    build_quote,
    collect_quotes,
    extract_history,
    merge_quotes,
)

HISTORY = [("2026-10-13", 9.6), ("2026-10-14", 9.85)]


def test_regular_session_quote(now):
    info = {
        "regularMarketPrice": 9.4,
        "regularMarketPreviousClose": 9.85,
        "marketState": "REGULAR",
        "shortName": "Nokia Corporation",
        "currency": "USD",
        "regularMarketTime": 1792069200,
        "fiftyTwoWeekHigh": 10.2,
        "fiftyTwoWeekLow": 5.1,
    }

    quote = build_quote("NOK", info, HISTORY, now)

    assert quote["price"] == 9.4
    assert quote["prev_close"] == 9.85
    assert quote["change"] == pytest.approx(-0.45)
    assert quote["change_pct"] == pytest.approx(-4.57, abs=0.01)
    assert quote["market_state"] == "REGULAR"
    assert quote["ext"] is None
    assert quote["name"] == "Nokia Corporation"
    assert quote["high_52w"] == 10.2
    assert quote["history"] == [{"d": "2026-10-13", "c": 9.6}, {"d": "2026-10-14", "c": 9.85}]
    assert quote["stale"] is False


def test_pre_market_price_is_reported_as_extended_quote(now):
    info = {"regularMarketPrice": 10.0, "regularMarketPreviousClose": 9.5, "marketState": "PRE", "preMarketPrice": 10.5}

    quote = build_quote("NOK", info, HISTORY, now)

    assert quote["market_state"] == "PRE"
    assert quote["ext"] == {"label": "盤前", "price": 10.5, "change_pct": 5.0}


def test_overnight_state_shows_previous_after_hours_price(now):
    info = {"regularMarketPrice": 10.0, "regularMarketPreviousClose": 9.5, "marketState": "PREPRE", "postMarketPrice": 9.8}

    quote = build_quote("NOK", info, HISTORY, now)

    assert quote["market_state"] == "CLOSED"
    assert quote["ext"]["label"] == "盤後"
    assert quote["ext"]["change_pct"] == pytest.approx(-2.0)


def test_quote_falls_back_to_history_when_info_missing(now):
    quote = build_quote("QNT", {}, [("2026-10-13", 10.0), ("2026-10-14", 11.0)], now)

    assert quote["price"] == 11.0
    assert quote["prev_close"] == 10.0
    assert quote["change_pct"] == pytest.approx(10.0)
    assert quote["name"] == "QNT"
    assert quote["market_state"] is None


def test_quote_without_any_data_is_none(now):
    assert build_quote("XXX", {}, [], now) is None
    assert build_quote("XXX", None, None, now) is None


def test_history_is_capped_to_recent_points(now):
    long_history = [(f"2026-01-{i:02d}", float(i)) for i in range(1, 32)] * 3

    quote = build_quote("NOK", {}, long_history, now)

    assert len(quote["history"]) == 66


def test_adr_premium_matches_hand_calculation():
    # 1,262,000 KRW * 0.1 / 1343.16 KRW per USD = 93.96 USD implied, ADR at 147.55
    assert adr_premium(147.55, 1_262_000, 0.1, 1343.16) == pytest.approx(57.04, abs=0.02)


@pytest.mark.parametrize("args", [(None, 1, 1, 1), (10, 0, 1, 1), (10, 1, 1, 0), (10, 1, -1, 1)])
def test_adr_premium_rejects_invalid_inputs(args):
    assert adr_premium(*args) is None


def _q(price, history=None):
    return {"price": price, "history": history or []}


def test_build_indicators_computes_premium_and_history():
    pair = AdrPair(adr="SKHY", local="000660.KS", ratio=0.1, fx="KRW=X", label="SK 海力士 ADR 溢價", note="n")
    quotes = {
        "SKHY": _q(147.55, [{"d": "2026-10-13", "c": 150.0}, {"d": "2026-10-14", "c": 147.55}]),
        "000660.KS": _q(1_262_000, [{"d": "2026-10-13", "c": 1_250_000}, {"d": "2026-10-14", "c": 1_262_000}]),
        "KRW=X": _q(1343.16, [{"d": "2026-10-14", "c": 1343.16}]),
    }

    [indicator] = build_indicators(quotes, (pair,))

    assert indicator["id"] == "adr-SKHY"
    assert indicator["value"] == pytest.approx(57.04, abs=0.02)
    assert indicator["implied_price"] == pytest.approx(93.96, abs=0.01)
    assert [p["d"] for p in indicator["history"]] == ["2026-10-14"]


def test_build_indicators_skips_pairs_with_missing_quotes():
    pair = AdrPair(adr="TSM", local="2330.TW", ratio=5, fx="TWD=X", label="x", note="")

    assert build_indicators({"TSM": _q(300)}, (pair,)) == []


def test_merge_quotes_keeps_previous_values_marked_stale():
    previous = {"A": {"price": 1, "stale": False}, "B": {"price": 2, "stale": False}}
    fresh = {"A": {"price": 1.5, "stale": False}}

    merged = merge_quotes(previous, fresh, ["A", "B", "C"])

    assert merged["A"]["price"] == 1.5
    assert merged["B"] == {"price": 2, "stale": True}
    assert "C" not in merged
    assert previous["B"]["stale"] is False  # input untouched


def test_extract_history_from_multiindex_frame_skips_nan():
    index = pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14"])
    frame = pd.DataFrame(
        {("NOK", "Close"): [9.0, float("nan"), 9.5], ("NOK", "Open"): [8.9, 9.1, 9.2], ("QNT", "Close"): [30, 31, 32]},
        index=index,
    )

    assert extract_history(frame, "NOK") == [("2026-10-12", 9.0), ("2026-10-14", 9.5)]
    assert extract_history(frame, "MISSING") == []
    assert extract_history(pd.DataFrame(), "NOK") == []


def test_extract_history_from_flat_frame():
    frame = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-10-13", "2026-10-14"]))

    assert extract_history(frame, "NOK") == [("2026-10-13", 1.0), ("2026-10-14", 2.0)]


def test_collect_quotes_survives_partial_failures(now):
    def info_fetcher(symbol):
        if symbol == "BAD":
            raise RuntimeError("429 Too Many Requests")
        return {"regularMarketPrice": 5.0, "regularMarketPreviousClose": 4.0, "marketState": "REGULAR"}

    def history_fetcher(symbols):
        return {"BAD": [("2026-10-13", 2.0), ("2026-10-14", 2.2)], "NONE": []}

    quotes, errors = collect_quotes(
        ["OK", "BAD", "NONE"], now, info_fetcher=info_fetcher, history_fetcher=history_fetcher, retry_delay=0
    )

    assert quotes["OK"]["price"] == 5.0
    assert quotes["BAD"]["price"] == 2.2  # history fallback
    assert "NONE" in quotes  # info alone is enough
    assert any("BAD" in e and "429" in e for e in errors)


def test_collect_quotes_reports_history_failure(now):
    def history_fetcher(symbols):
        raise ConnectionError("offline")

    quotes, errors = collect_quotes(
        ["OK"], now, info_fetcher=lambda s: {}, history_fetcher=history_fetcher, retry_delay=0
    )

    assert quotes == {}
    assert any("offline" in e for e in errors)
    assert any("OK" in e and "no data" in e for e in errors)


def test_history_only_quote_keeps_previous_static_fields():
    previous = {"NOK": {"price": 9.4, "name": "Nokia Corporation", "currency": "USD", "high_52w": 18.0, "low_52w": 5.0, "ext": {"label": "盤後", "price": 9.1, "change_pct": -3.2}, "stale": False}}
    fresh = {"NOK": {"price": 9.5, "name": "NOK", "currency": None, "high_52w": None, "low_52w": None, "ext": None, "source": "history", "stale": False}}

    merged = merge_quotes(previous, fresh, ["NOK"])

    quote = merged["NOK"]
    assert quote["price"] == 9.5
    assert quote["name"] == "Nokia Corporation"
    assert quote["currency"] == "USD"
    assert quote["high_52w"] == 18.0
    assert quote["degraded"] is True
    assert quote["ext"] is None  # a stale extended-hours price would be misleading


def test_build_quote_records_its_source(now):
    assert build_quote("NOK", {"regularMarketPrice": 9.4}, HISTORY, now)["source"] == "info"
    assert build_quote("NOK", {}, HISTORY, now)["source"] == "history"
