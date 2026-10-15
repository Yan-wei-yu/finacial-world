from datetime import timedelta

import pytest

from pipeline.io_utils import to_iso
from pipeline.news_rank import build_rules, classify, cluster, is_excluded, merge_news, rank_items
from pipeline.text import jaccard, strip_source_suffix, tokenize


@pytest.fixture
def rules(config):
    return build_rules(config.news, config.holdings)


def _raw(title, source="Reuters", published="2026-10-15T10:00:00Z", **extra):
    return {
        "title": title,
        "url": f"https://example.com/{abs(hash(title))}",
        "source": source,
        "published": published,
        "summary": "",
        "lang": "en",
        "feed": "test",
        "hint_categories": [],
        "hint_symbols": [],
        **extra,
    }


def test_strip_source_suffix():
    assert strip_source_suffix("Chips slump - Reuters", "Reuters") == "Chips slump"
    assert strip_source_suffix("Chips slump | CNBC", "CNBC") == "Chips slump"
    assert strip_source_suffix("Reuters - Chips slump", "Reuters") == "Reuters - Chips slump"
    assert strip_source_suffix("Chips slump", "") == "Chips slump"


def test_tokenize_handles_english_and_chinese():
    english = tokenize("The Fed signals a rate cut")
    chinese = tokenize("費半重挫")

    assert "the" not in english and "fed" in english and "cut" in english
    assert {"費半", "半重", "重挫"} <= chinese


def test_tokenize_keeps_direction_words():
    assert tokenize("Nvidia shares up") != tokenize("Nvidia shares down")


def test_jaccard_bounds():
    a = frozenset({"a", "b"})

    assert jaccard(a, a) == 1.0
    assert jaccard(a, frozenset({"c"})) == 0.0
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_classify_holding_alias_scores_highest(rules):
    result = classify("SK hynix shares jump on HBM orders", "", [], [], rules)

    assert "holdings" in result["categories"]
    assert result["symbols"][0] == "SKHY"
    assert result["score"] >= 6


def test_classify_topic_links_memory_news_to_dram_etf(rules):
    result = classify("Micron raises outlook as memory prices climb", "", [], [], rules)

    assert "DRAM" in result["symbols"]
    assert "semis" in result["categories"]


def test_classify_macro_and_case_sensitive_acronyms(rules):
    assert "macro" in classify("Fed signals rate cut as CPI cools", "", [], [], rules)["categories"]
    assert "macro" not in classify("Investors fed up with delays", "", [], [], rules)["categories"]
    assert "semis" not in classify("Thai airline said profits rose", "", [], [], rules)["categories"]


def test_classify_chinese_keywords(rules):
    categories = classify("聯準會降息預期升溫，費半大漲", "", [], [], rules)["categories"]

    assert {"macro", "semis", "market"} <= set(categories)


def test_classify_uses_feed_hints_when_no_keyword_matches(rules):
    result = classify("Company announces quarterly update", "", ["macro"], ["NOK"], rules)

    assert result["categories"] == ["holdings", "macro"]
    assert result["symbols"] == ["NOK"]


def test_classify_irrelevant_item_has_no_categories(rules):
    assert classify("Celebrity chef opens restaurant", "", [], [], rules)["categories"] == []


def test_is_excluded_by_source_and_pattern(rules):
    assert is_excluded(_raw("Is SK hynix a Buy Now?", source="The Motley Fool"), rules)
    assert is_excluded(_raw("Nokia Oyj (NYSE:NOK) Shares Sold by Acme LLC", source="Defense World"), rules)
    assert is_excluded(_raw("Quantum Computing Market Report 2026: Key Players"), rules)
    assert not is_excluded(_raw("Nokia wins 5G deal"), rules)


def test_rank_items_filters_noise_and_scores(rules, now):
    raws = [
        _raw("SK hynix wins Nvidia HBM order"),
        _raw("Celebrity chef opens restaurant", source="CNBC"),
        _raw("Is SK hynix a Buy Now?", source="The Motley Fool"),
        _raw("Quarterly update", source="Yahoo Finance", hint_symbols=["QNT"]),
    ]

    ranked = rank_items(raws, rules, now)

    titles = [r["title"] for r in ranked]
    assert titles == ["SK hynix wins Nvidia HBM order", "Quarterly update"]
    top = ranked[0]
    assert top["source_bonus"] == 1
    assert top["base_score"] > ranked[1]["base_score"]
    assert top["first_seen"] == to_iso(now)
    assert len(top["id"]) == 16


def _ranked(title, source, published, score=5.0, first_seen="2026-10-15T13:00:00Z", url=None):
    return {
        "id": (url or title)[:16].ljust(16, "x"),
        "title": title,
        "url": url or f"https://example.com/{source}",
        "source": source,
        "published": published,
        "lang": "en",
        "feed": "f",
        "categories": ["semis"],
        "symbols": [],
        "base_score": score,
        "source_bonus": 0,
        "score": score,
        "coverage": 1,
        "also": [],
        "first_seen": first_seen,
    }


def test_cluster_merges_near_duplicate_headlines():
    a = _ranked("SK Hynix conditions new US factory on more US chip equipment", "Reuters", "2026-10-15T02:02:00Z", 7)
    b = _ranked(
        "SK Hynix conditions new US factory on more US chip equipment purchases",
        "Yahoo Finance",
        "2026-10-15T03:10:00Z",
        5,
        first_seen="2026-10-15T01:00:00Z",
    )
    c = _ranked("Nvidia shares fall after export news", "CNBC", "2026-10-15T04:00:00Z", 4)

    merged = cluster([b, c, a], threshold=0.6)

    assert len(merged) == 2
    story = next(m for m in merged if m["source"] == "Reuters")
    assert story["coverage"] == 2
    assert story["also"] == [{"source": "Yahoo Finance", "url": "https://example.com/Yahoo Finance"}]
    assert story["published"] == "2026-10-15T02:02:00Z"
    assert story["first_seen"] == "2026-10-15T01:00:00Z"
    assert story["score"] > story["base_score"]


def test_cluster_does_not_double_count_same_source():
    a = _ranked("Chip stocks slide as AI selloff deepens", "Reuters", "2026-10-15T02:00:00Z")
    b = _ranked("Chip stocks slide as AI selloff deepens", "Reuters", "2026-10-15T02:05:00Z", url="https://r.com/2")

    [story] = cluster([a, b], threshold=0.6)

    assert story["coverage"] == 1
    assert story["also"] == []


def test_merge_news_prunes_old_items_and_keeps_first_seen(now):
    old = _ranked("Old story about chips", "CNBC", to_iso(now - timedelta(hours=120)))
    kept = _ranked("Fed holds rates steady", "Reuters", to_iso(now - timedelta(hours=10)), first_seen="2026-10-15T03:00:00Z")
    fresh_dup = {**kept, "first_seen": to_iso(now)}
    brand_new = _ranked("TSMC beats estimates", "CNBC", to_iso(now - timedelta(hours=1)))

    merged = merge_news([old, kept], [fresh_dup, brand_new], now, retention_hours=96, max_items=10, threshold=0.6)

    titles = [m["title"] for m in merged]
    assert titles == ["TSMC beats estimates", "Fed holds rates steady"]
    assert merged[1]["first_seen"] == "2026-10-15T03:00:00Z"


def test_merge_news_drops_noise_and_ages_out_low_scores(now):
    noise = _ranked("Evernorth rings the closing bell", "Nasdaq", to_iso(now - timedelta(hours=1)), score=0.9)
    old_minor = _ranked("Stocks drift in quiet session", "CNBC", to_iso(now - timedelta(hours=30)), score=1.5)
    old_major = _ranked("SK hynix plunges on rate fears", "Reuters", to_iso(now - timedelta(hours=30)), score=9)
    fresh_minor = _ranked("Nasdaq slips at the open", "CNBC", to_iso(now - timedelta(hours=2)), score=1.5)

    merged = merge_news(
        [],
        [noise, old_minor, old_major, fresh_minor],
        now,
        retention_hours=96,
        max_items=10,
        threshold=0.6,
        min_score=1.2,
        low_score=4,
        low_score_hours=24,
    )

    assert [m["title"] for m in merged] == ["Nasdaq slips at the open", "SK hynix plunges on rate fears"]


def test_min_score_ignores_source_bonus(now):
    off_topic = {**_ranked("Ambassador profile", "WSJ", to_iso(now - timedelta(hours=1)), score=0.6), "source_bonus": 1.0}

    merged = merge_news([], [off_topic], now, retention_hours=96, max_items=10, threshold=0.6, min_score=1.3)

    assert merged == []


def test_merge_news_enforces_max_items(now):
    titles = ["Apple earnings beat", "Oil prices spike", "Fed minutes released", "Tesla recalls cars", "Gold hits record"]
    items = [_ranked(t, "CNBC", to_iso(now - timedelta(hours=i))) for i, t in enumerate(titles)]

    merged = merge_news([], items, now, retention_hours=96, max_items=3, threshold=0.6)

    assert [m["title"] for m in merged] == titles[:3]


def test_cluster_keeps_repeated_headlines_far_apart():
    monday = _ranked("Wall Street Week Ahead: earnings in focus", "Reuters", "2026-10-12T20:00:00Z", url="https://r.com/mon")
    wednesday = _ranked("Wall Street Week Ahead: earnings in focus", "Reuters", "2026-10-14T20:00:00Z", url="https://r.com/wed")

    merged = cluster([monday, wednesday], threshold=0.6)

    assert sorted(m["url"] for m in merged) == ["https://r.com/mon", "https://r.com/wed"]


def test_cap_prefers_important_stories_over_recent_noise(now):
    major = _ranked("SK hynix plunges on rate fears", "Reuters", to_iso(now - timedelta(hours=30)), score=10)
    minor = [_ranked(f"Minor market blip number {word}", "CNBC", to_iso(now - timedelta(hours=1)), score=2.5) for word in ["alpha", "bravo", "charlie", "delta", "echo"]]

    merged = merge_news([], [major, *minor], now, retention_hours=96, max_items=5, threshold=0.95)

    assert "SK hynix plunges on rate fears" in [m["title"] for m in merged]
    assert [m["published"] for m in merged] == sorted((m["published"] for m in merged), reverse=True)
