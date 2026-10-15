import json

import pytest

from pipeline.config import ConfigError, load_config, parse_portfolio


def _holding(**overrides):
    base = {"symbol": "NOK", "shares": 10, "name": "Nokia"}
    return {**base, **overrides}


def test_real_config_loads_user_holdings(config):
    symbols = [h.symbol for h in config.holdings]
    shares = {h.symbol: h.shares for h in config.holdings}

    assert symbols == ["NOK", "DRAM", "QNT", "SKHY"]
    assert shares == {"NOK": 820, "DRAM": 75, "QNT": 40, "SKHY": 3}


def test_quote_symbols_are_unique_and_include_adr_dependencies(config):
    symbols = config.quote_symbols

    assert len(symbols) == len(set(symbols))
    assert symbols[:4] == ["NOK", "DRAM", "QNT", "SKHY"]
    for needed in ("^SOX", "^IXIC", "TWD=X", "000660.KS", "KRW=X", "2330.TW"):
        assert needed in symbols


def test_public_holding_view_hides_matching_keywords(config):
    public = config.holdings[0].to_public()

    assert public["symbol"] == "NOK"
    assert public["shares"] == 820
    assert "aliases" not in public and "topics" not in public
    assert public["drivers"]


def test_negative_shares_rejected():
    with pytest.raises(ConfigError, match="shares"):
        parse_portfolio({"holdings": [_holding(shares=-1)]})


def test_unsafe_symbol_rejected():
    with pytest.raises(ConfigError, match="symbol"):
        parse_portfolio({"holdings": [_holding(symbol="NOK; rm -rf /")]})


@pytest.mark.parametrize("cost", [0, -5, "abc"])
def test_cost_must_be_positive_number_or_null(cost):
    with pytest.raises(ConfigError, match="cost"):
        parse_portfolio({"holdings": [_holding(cost=cost)]})


def test_null_cost_and_fractional_shares_allowed():
    holdings = parse_portfolio({"holdings": [_holding(cost=None, shares=0.5)]})

    assert holdings[0].cost is None
    assert holdings[0].shares == 0.5


def test_duplicate_symbols_rejected():
    with pytest.raises(ConfigError, match="duplicate"):
        parse_portfolio({"holdings": [_holding(), _holding()]})


def test_empty_holdings_rejected():
    with pytest.raises(ConfigError):
        parse_portfolio({"holdings": []})


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="portfolio.json"):
        load_config(tmp_path)


def test_feed_with_non_https_url_rejected(tmp_path, config_dir):
    for name in ("portfolio.json", "watchlist.json", "events.json", "macro_terms.json"):
        (tmp_path / name).write_text((config_dir / name).read_text(encoding="utf-8"), encoding="utf-8")
    news = json.loads((config_dir / "news.json").read_text(encoding="utf-8"))
    news["feeds"] = [{"id": "bad", "type": "rss", "lang": "en", "url": "http://insecure.example/rss"}]
    (tmp_path / "news.json").write_text(json.dumps(news), encoding="utf-8")

    with pytest.raises(ConfigError, match="https"):
        load_config(tmp_path)


def test_tradingview_symbols_loaded(config):
    symbols = [entry["tv_symbol"] for entry in config.tradingview]

    assert "NASDAQ:SOXX" in symbols
    assert all(entry["label"] for entry in config.tradingview)


def test_invalid_tradingview_symbol_rejected():
    from pipeline.config import parse_watchlist

    with pytest.raises(ConfigError, match="tv_symbol"):
        parse_watchlist({"tradingview": [{"tv_symbol": "javascript:alert(1)", "label": "x"}]})


def test_symbol_with_trailing_newline_rejected():
    with pytest.raises(ConfigError, match="symbol"):
        parse_portfolio({"holdings": [_holding(symbol="NOK\n")]})


@pytest.mark.parametrize("url", ["https://user@feeds.example/rss", "https://127.0.0.1/rss", "https://localhost/rss", "https:///rss"])
def test_feed_urls_must_be_plain_public_https(tmp_path, config_dir, url):
    for name in ("portfolio.json", "watchlist.json", "events.json", "macro_terms.json"):
        (tmp_path / name).write_text((config_dir / name).read_text(encoding="utf-8"), encoding="utf-8")
    news = json.loads((config_dir / "news.json").read_text(encoding="utf-8"))
    news["feeds"] = [{"id": "bad", "type": "rss", "lang": "en", "url": url}]
    (tmp_path / "news.json").write_text(json.dumps(news), encoding="utf-8")

    with pytest.raises(ConfigError, match="url"):
        load_config(tmp_path)
