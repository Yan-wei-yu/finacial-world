import time

import pytest

from pipeline.text import MAX_URL_LENGTH, clean_text, sanitize_url


def test_clean_text_is_fast_on_hostile_markup():
    hostile = "<" * 200_000 + "x"

    started = time.perf_counter()
    result = clean_text(hostile, 300)

    assert time.perf_counter() - started < 1.0
    assert len(result) <= 300


def test_clean_text_still_strips_tags_and_entities():
    assert clean_text("<p>Hello</p><p>world &amp; <b>chips</b></p>", 100) == "Hello world & chips"


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/feed",
        "https://example.com/a\nb",
        "https://example.com/" + "a" * MAX_URL_LENGTH,
        "ftp://example.com",
        "https://",
    ],
)
def test_sanitize_url_rejects_suspicious_links(url):
    assert sanitize_url(url) is None


def test_sanitize_url_accepts_normal_links():
    assert sanitize_url(" https://news.cnyes.com/news/id/1 ") == "https://news.cnyes.com/news/id/1"
