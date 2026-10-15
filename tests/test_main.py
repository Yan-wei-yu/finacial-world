import json
import shutil

import pytest

from pipeline.io_utils import read_json
from pipeline.main import Deps, main, run


@pytest.fixture
def root(tmp_path, config_dir):
    shutil.copytree(config_dir, tmp_path / "config")
    return tmp_path


def _quote(price):
    return {"price": price, "prev_close": price, "change": 0, "change_pct": 0, "history": [], "stale": False}


def fake_quotes(symbols, now):
    return {s: _quote(10.0) for s in symbols if s != "QNT"}, ["QNT: no data"]


def fake_news(feeds, now, settings):
    return (
        [
            {
                "title": "SK hynix wins Nvidia HBM order",
                "url": "https://example.com/a",
                "source": "Reuters",
                "published": "2026-10-15T12:00:00Z",
                "summary": "",
                "lang": "en",
                "feed": "gn-en-skhy",
                "hint_categories": [],
                "hint_symbols": ["SKHY"],
            }
        ],
        {"cnbc-top": "HTTP 503"},
    )


def fake_earnings(watch, now):
    return {"generated_at": "x", "upcoming": [{"symbol": "NOK"}], "recent": [], "history": {}}, []


def fake_macro(events_cfg, terms, now):
    return {"generated_at": "x", "week": [], "upcoming": [{"title": "FOMC"}]}, []


def fake_summary(ctx, now):
    return {"headline": "測試", "generated_at": "2026-10-15T13:00:00Z"}, "ok"


def _deps(**overrides):
    base = dict(
        collect_quotes=fake_quotes,
        fetch_news=fake_news,
        collect_earnings=fake_earnings,
        collect_macro=fake_macro,
        generate_summary=fake_summary,
    )
    return Deps(**{**base, **overrides})


def test_quotes_mode_only_writes_quotes(root, now):
    code = run("quotes", root, now=now, summary=True, deps=_deps())

    data = root / "site" / "data"
    quotes = read_json(data / "quotes.json", None)
    assert code == 0
    assert [h["symbol"] for h in quotes["holdings"]] == ["NOK", "DRAM", "QNT", "SKHY"]
    assert quotes["quotes"]["NOK"]["price"] == 10.0
    assert quotes["fx"]["USDTWD"] == 10.0
    assert any(entry["tv_symbol"] == "NASDAQ:SOXX" for entry in quotes["tradingview"])
    assert "QNT: no data" in quotes["errors"]
    assert not (data / "news.json").exists()
    assert not (data / "meta.json").exists()


def test_quotes_mode_reuses_previous_quotes_as_stale(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    (data / "quotes.json").write_text(json.dumps({"quotes": {"QNT": _quote(33.0)}}), encoding="utf-8")

    run("quotes", root, now=now, deps=_deps())

    qnt = read_json(data / "quotes.json", None)["quotes"]["QNT"]
    assert qnt["price"] == 33.0 and qnt["stale"] is True


def test_full_mode_writes_every_file_and_meta(root, now):
    code = run("full", root, now=now, summary=True, deps=_deps())

    data = root / "site" / "data"
    news = read_json(data / "news.json", None)
    meta = read_json(data / "meta.json", None)
    assert code == 0
    assert news["items"][0]["symbols"][0] == "SKHY"
    assert news["generated_at"] == "2026-10-15T13:00:00Z"
    assert news["categories"]["semis"] == "半導體／AI"
    assert read_json(data / "earnings.json", None)["upcoming"] == [{"symbol": "NOK"}]
    assert read_json(data / "macro.json", None)["upcoming"] == [{"title": "FOMC"}]
    assert read_json(data / "summary.json", None)["headline"] == "測試"
    assert meta["stages"]["news"]["ok"] is True
    assert "cnbc-top" in meta["stages"]["news"]["message"]
    assert meta["stages"]["summary"]["message"] == "ok"
    assert meta["last_full_run"] == "2026-10-15T13:00:00Z"


def test_full_mode_without_summary_keeps_previous_summary(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    (data / "summary.json").write_text(json.dumps({"headline": "舊摘要"}), encoding="utf-8")

    run("full", root, now=now, summary=False, deps=_deps())

    assert read_json(data / "summary.json", None)["headline"] == "舊摘要"
    assert read_json(data / "meta.json", None)["stages"]["summary"]["message"].startswith("skipped")


def test_failed_stage_keeps_previous_file(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    (data / "earnings.json").write_text(json.dumps({"upcoming": [{"symbol": "OLD"}]}), encoding="utf-8")

    def broken_earnings(watch, now):
        raise RuntimeError("yahoo exploded")

    code = run("full", root, now=now, deps=_deps(collect_earnings=broken_earnings))

    meta = read_json(data / "meta.json", None)
    assert code == 0
    assert read_json(data / "earnings.json", None)["upcoming"] == [{"symbol": "OLD"}]
    assert meta["stages"]["earnings"]["ok"] is False
    assert "yahoo exploded" in meta["stages"]["earnings"]["message"]
    assert meta["stages"]["news"]["ok"] is True


def test_news_merges_with_previous_items(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    previous = {
        "items": [
            {
                "id": "previous00000001",
                "title": "Fed holds rates steady",
                "url": "https://example.com/fed",
                "source": "CNBC",
                "published": "2026-10-15T01:00:00Z",
                "lang": "en",
                "feed": "cnbc-top",
                "categories": ["macro"],
                "symbols": [],
                "base_score": 4,
                "source_bonus": 1,
                "score": 5,
                "coverage": 1,
                "also": [],
                "first_seen": "2026-10-15T01:05:00Z",
            }
        ]
    }
    (data / "news.json").write_text(json.dumps(previous), encoding="utf-8")

    run("full", root, now=now, deps=_deps())

    titles = [i["title"] for i in read_json(data / "news.json", None)["items"]]
    assert titles == ["SK hynix wins Nvidia HBM order", "Fed holds rates steady"]


def test_invalid_config_returns_error_code(root, now):
    (root / "config" / "portfolio.json").write_text('{"holdings": []}', encoding="utf-8")

    assert run("full", root, now=now, deps=_deps()) == 2


def test_cli_parses_arguments(root, monkeypatch):
    seen = {}

    def fake_run(mode, root_path, now=None, summary=True, deps=None):
        seen.update(mode=mode, root=root_path, summary=summary)
        return 0

    monkeypatch.setattr("pipeline.main.run", fake_run)

    assert main(["--mode", "quotes", "--no-summary", "--root", str(root)]) == 0
    assert seen == {"mode": "quotes", "root": root, "summary": False}


def test_news_timestamp_kept_when_every_feed_fails(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    (data / "news.json").write_text(json.dumps({"generated_at": "2026-10-15T01:00:00Z", "items": []}), encoding="utf-8")

    run("full", root, now=now, deps=_deps(fetch_news=lambda feeds, now, settings: ([], {"all": "down"})))

    doc = read_json(data / "news.json", None)
    assert doc["generated_at"] == "2026-10-15T01:00:00Z"
    assert read_json(data / "meta.json", None)["stages"]["news"]["ok"] is False


def test_quotes_outage_keeps_timestamp_and_signals_no_deploy(root, now):
    data = root / "site" / "data"
    data.mkdir(parents=True)
    (data / "quotes.json").write_text(json.dumps({"generated_at": "2026-10-15T01:00:00Z", "quotes": {"NOK": _quote(9.4)}}), encoding="utf-8")

    code = run("quotes", root, now=now, deps=_deps(collect_quotes=lambda symbols, now: ({}, ["yahoo down"])))

    doc = read_json(data / "quotes.json", None)
    assert code == 3
    assert doc["generated_at"] == "2026-10-15T01:00:00Z"
    assert doc["quotes"]["NOK"]["stale"] is True


def test_earnings_stage_flags_failed_holding(root, now):
    def flaky(watch, now):
        return {"generated_at": "x", "upcoming": [{"symbol": "MU", "date": "2026-12-17", "datetime": None}], "recent": [], "history": {}, "failed_calendar": ["NOK"], "failed_history": []}, ["NOK calendar: 429"]

    run("full", root, now=now, deps=_deps(collect_earnings=flaky))

    meta = read_json(root / "site" / "data" / "meta.json", None)
    assert meta["stages"]["earnings"]["ok"] is False
    assert "NOK" in meta["stages"]["earnings"]["message"]
