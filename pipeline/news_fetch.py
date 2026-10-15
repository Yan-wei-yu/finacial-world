"""Download news from RSS feeds, Google News searches and the cnyes (鉅亨網) API."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import feedparser
import requests

from pipeline.io_utils import to_iso
from pipeline.text import clean_text, sanitize_url, strip_source_suffix

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
TIMEOUT = (5, 20)  # (connect, read) seconds
MAX_FEED_BYTES = 2 * 1024 * 1024


class FeedError(Exception):
    """A feed problem whose message is safe to publish (no URLs, no response bodies)."""
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
GOOGLE_LOCALES = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "zh": {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
}


def google_news_url(query: str, lang: str, window: str = "2d") -> str:
    params = {"q": f"{query} when:{window}", **GOOGLE_LOCALES[lang]}
    return f"{GOOGLE_NEWS_BASE}?{urlencode(params)}"


def _raw_item(title: str, url: str, source: str, published: datetime, summary: str, feed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "source": source,
        "published": to_iso(published),
        "summary": summary,
        "lang": feed.get("lang", "en"),
        "feed": feed["id"],
        "hint_categories": list(feed.get("categories", [])),
        "hint_symbols": list(feed.get("symbols", [])),
    }


def _clamp(published: datetime | None, now: datetime) -> datetime:
    if published is None or published > now + timedelta(hours=1):
        return now
    return published


def _entry_time(entry: Mapping[str, Any], now: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    published = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else None
    return _clamp(published, now)


def _entry_source(entry: Mapping[str, Any], feed: Mapping[str, Any]) -> str:
    source = entry.get("source")
    if isinstance(source, Mapping) and source.get("title"):
        return clean_text(source["title"], 80)
    return feed.get("source") or "Google News"


def parse_rss(content: bytes, feed: Mapping[str, Any], now: datetime, limit: int) -> list[dict[str, Any]]:
    is_google = feed.get("type") == "google_news"
    items = []
    # BytesIO: feedparser treats raw bytes as a possible file path / URL otherwise.
    for entry in feedparser.parse(io.BytesIO(content)).entries[:limit]:
        title = clean_text(entry.get("title", ""), 300)
        url = sanitize_url(entry.get("link"))
        if not title or not url:
            continue
        source = _entry_source(entry, feed)
        if is_google:
            title = strip_source_suffix(title, source)
        summary = "" if is_google else clean_text(entry.get("summary", ""), 280)
        items.append(_raw_item(title, url, source, _entry_time(entry, now), summary, feed))
    return items


def parse_cnyes(payload: Any, feed: Mapping[str, Any], now: datetime, limit: int) -> list[dict[str, Any]]:
    container = payload.get("items") if isinstance(payload, Mapping) else None
    data = container.get("data") if isinstance(container, Mapping) else None
    items = []
    for entry in (data if isinstance(data, list) else [])[:limit]:
        if not isinstance(entry, Mapping):
            continue
        title = clean_text(entry.get("title"), 300)
        news_id = entry.get("newsId")
        if not title or not isinstance(news_id, int) or isinstance(news_id, bool):
            continue
        publish_at = entry.get("publishAt")
        published = datetime.fromtimestamp(publish_at, tz=timezone.utc) if isinstance(publish_at, int) else None
        items.append(
            _raw_item(
                title,
                f"https://news.cnyes.com/news/id/{news_id}",
                feed.get("source") or "鉅亨網",
                _clamp(published, now),
                clean_text(entry.get("summary"), 280),
                feed,
            )
        )
    return items


def _feed_url(feed: Mapping[str, Any], settings: Mapping[str, Any]) -> str:
    if feed["type"] == "google_news":
        return google_news_url(feed["query"], feed["lang"], settings.get("google_window") or "2d")
    return feed["url"]


def _read_capped(response: Any) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_content(chunk_size=65536):
        size += len(chunk)
        if size > MAX_FEED_BYTES:
            raise FeedError(f"response larger than {MAX_FEED_BYTES // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_feed(feed: Mapping[str, Any], session: Any, now: datetime, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    if feed.get("type") not in ("google_news", "rss", "cnyes"):
        raise FeedError(f"unsupported feed type {feed.get('type')!r}")
    limit = int(settings.get("per_feed_limit") or 40)
    response = session.get(_feed_url(feed, settings), timeout=TIMEOUT, stream=True)
    try:
        if response.status_code >= 400:
            raise FeedError(f"HTTP {response.status_code}")
        if not str(getattr(response, "url", "https://")).startswith("https://"):
            raise FeedError("redirected away from https")
        body = _read_capped(response)
    finally:
        response.close()
    if feed["type"] == "cnyes":
        return parse_cnyes(json.loads(body), feed, now, limit)
    return parse_rss(body, feed, now, limit)


def public_error(exc: Exception) -> str:
    """Error text that is safe to commit to the public repo."""
    return str(exc) if isinstance(exc, FeedError) else type(exc).__name__


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
    return session


def fetch_all(
    feeds: Sequence[Mapping[str, Any]],
    now: datetime,
    settings: Mapping[str, Any],
    *,
    session: Any = None,
    max_workers: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Fetch every feed concurrently; one failing feed never stops the others."""
    owned = session is None
    http = _new_session() if owned else session

    def run(feed: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], str | None]:
        try:
            return feed["id"], fetch_feed(feed, http, now, settings), None
        except Exception as exc:  # requests/feedparser raise many unrelated types
            return feed["id"], [], public_error(exc)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(run, feeds))
    finally:
        if owned:
            http.close()
    items = [item for _, feed_items, _ in results for item in feed_items]
    errors = {feed_id: error for feed_id, _, error in results if error}
    return items, errors
