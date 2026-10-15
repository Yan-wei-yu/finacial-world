import json

import pytest

from pipeline.news_fetch import fetch_all, google_news_url, parse_cnyes, parse_rss

GN_FEED = {"id": "gn-en-skhy", "type": "google_news", "lang": "en", "query": "\"SK hynix\"", "symbols": ["SKHY"]}
YH_FEED = {"id": "yh-nok", "type": "rss", "lang": "en", "source": "Yahoo Finance", "url": "https://x", "symbols": ["NOK"]}
CN_FEED = {"id": "cnyes-us", "type": "cnyes", "lang": "zh", "source": "鉅亨網", "url": "https://api.cnyes.com/x"}


def test_google_news_url_uses_locale_and_time_window():
    zh = google_news_url("費半 OR 費城半導體", "zh", "2d")
    en = google_news_url("Nokia", "en", "1d")

    assert zh.startswith("https://news.google.com/rss/search?")
    assert "hl=zh-TW" in zh and "gl=TW" in zh
    assert "when%3A2d" in zh
    assert "hl=en-US" in en and "when%3A1d" in en


def test_parse_google_news_strips_source_suffix(fixtures_dir, now):
    content = (fixtures_dir / "gnews_sample.xml").read_bytes()

    items = parse_rss(content, GN_FEED, now, limit=40)

    assert len(items) == 3
    first = items[0]
    assert first["title"] == "SK Hynix conditions new US factory on more US chip equipment"
    assert first["source"] == "Reuters"
    assert first["published"] == "2026-10-15T02:02:00Z"
    assert first["url"] == "https://news.google.com/rss/articles/AAA111?oc=5"
    assert first["hint_symbols"] == ["SKHY"]
    assert first["summary"] == ""
    assert first["lang"] == "en" and first["feed"] == "gn-en-skhy"


def test_parse_rss_respects_limit(fixtures_dir, now):
    content = (fixtures_dir / "gnews_sample.xml").read_bytes()

    assert len(parse_rss(content, GN_FEED, now, limit=1)) == 1


def test_parse_yahoo_rss_drops_unsafe_links_and_cleans_summary(fixtures_dir, now):
    content = (fixtures_dir / "yahoo_sample.xml").read_bytes()

    items = parse_rss(content, YH_FEED, now, limit=40)

    assert [i["title"] for i in items] == [
        "Nokia wins 5G core network deal with Eastlink",
        "Quantum Computing in Healthcare Market Report 2026: Google, Microsoft, IBM Profiled",
    ]
    assert items[0]["source"] == "Yahoo Finance"
    assert items[0]["summary"] == "Nokia said on Wednesday it would supply its 5G core to Eastlink & expand AI-RAN trials."
    assert all(i["url"].startswith("https://") for i in items)


def test_parse_cnyes_builds_links_and_strips_markup(fixtures_dir, now):
    payload = json.loads((fixtures_dir / "cnyes_sample.json").read_text(encoding="utf-8"))

    items = parse_cnyes(payload, CN_FEED, now, limit=40)

    assert len(items) == 2
    assert items[0]["url"] == "https://news.cnyes.com/news/id/6631113"
    assert items[0]["source"] == "鉅亨網"
    assert "\n" not in items[0]["summary"] and "&#10;" not in items[0]["summary"]
    assert items[1]["title"] == "費半重挫3.7% 輝達、美光領跌"
    assert items[1]["published"].endswith("Z")


def test_parse_cnyes_handles_unexpected_payload(now):
    assert parse_cnyes({}, CN_FEED, now, limit=10) == []
    assert parse_cnyes({"items": None}, CN_FEED, now, limit=10) == []


class _Response:
    def __init__(self, content=b"", payload=None, status=200, url="https://x.example/feed"):
        self.content = json.dumps(payload).encode("utf-8") if payload is not None else content
        self.status_code = status
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, routes):
        self.routes = routes
        self.requested = []

    def get(self, url, timeout, stream=False):
        self.requested.append(url)
        for needle, response in self.routes.items():
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                return response
        return _Response(status=404)


def test_fetch_all_collects_items_and_isolates_failures(fixtures_dir, now):
    cnyes_payload = json.loads((fixtures_dir / "cnyes_sample.json").read_text(encoding="utf-8"))
    session = _Session(
        {
            "news.google.com": _Response(content=(fixtures_dir / "gnews_sample.xml").read_bytes()),
            "api.cnyes.com": _Response(payload=cnyes_payload),
            "broken.example": ConnectionError("timed out"),
        }
    )
    feeds = [GN_FEED, CN_FEED, {**YH_FEED, "id": "broken", "url": "https://broken.example/rss"}]

    items, errors = fetch_all(feeds, now, {"per_feed_limit": 40, "google_window": "2d"}, session=session)

    assert len(items) == 5
    assert set(errors) == {"broken"}
    assert errors["broken"] == "ConnectionError"
    assert any("news.google.com/rss/search" in url for url in session.requested)


def test_fetch_all_reports_http_errors(now):
    session = _Session({"x.example": _Response(status=503)})
    feed = {**YH_FEED, "id": "down", "url": "https://x.example/rss"}

    items, errors = fetch_all([feed], now, {}, session=session)

    assert items == []
    assert "503" in errors["down"]


@pytest.mark.parametrize("bad_type", ["ftp", "unknown"])
def test_fetch_all_rejects_unknown_feed_types(now, bad_type):
    items, errors = fetch_all([{"id": "weird", "type": bad_type, "lang": "en", "url": "https://x"}], now, {}, session=_Session({}))

    assert items == []
    assert "weird" in errors


class _StreamResponse(_Response):
    def __init__(self, chunks, url="https://x.example/rss", status=200):
        super().__init__(status=status)
        self._chunks = chunks
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


class _StreamSession:
    def __init__(self, response):
        self.response = response

    def get(self, url, timeout, stream=False):
        return self.response


def test_fetch_all_rejects_oversized_feeds(now):
    huge = _StreamResponse([b"x" * (1024 * 1024)] * 3)
    feed = {**YH_FEED, "id": "huge", "url": "https://x.example/rss"}

    items, errors = fetch_all([feed], now, {}, session=_StreamSession(huge))

    assert items == []
    assert "huge" in errors
    assert huge.closed


def test_fetch_all_rejects_redirects_to_plain_http(now):
    downgraded = _StreamResponse([b"<rss></rss>"], url="http://x.example/rss")
    feed = {**YH_FEED, "id": "downgrade", "url": "https://x.example/rss"}

    _, errors = fetch_all([feed], now, {}, session=_StreamSession(downgraded))

    assert "downgrade" in errors


def test_published_errors_do_not_leak_urls(now):
    session = _Session({"x.example": ConnectionError("failed to reach https://x.example/secret?token=abc")})
    feed = {**YH_FEED, "id": "down", "url": "https://x.example/rss"}

    _, errors = fetch_all([feed], now, {}, session=session)

    assert errors["down"] == "ConnectionError"
