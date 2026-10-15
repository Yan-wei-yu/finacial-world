"""Classify, score, de-duplicate and merge news items. Everything here is pure."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline.config import Holding
from pipeline.io_utils import num, parse_iso, to_iso
from pipeline.text import has_cjk, jaccard, sanitize_url, tokenize

KIND_PRIORITY = {"alias": 0, "topic": 1, "hint": 2}
HINT_FACTOR = 0.4  # a category implied only by the search query, with no keyword in the headline
MAX_ALSO = 5
CLUSTER_WINDOW = timedelta(hours=36)  # the same headline days apart is a new story (e.g. weekly columns)
IMPORTANCE_HALF_LIFE_HOURS = 18
EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
REQUIRED_FIELDS = ("id", "title", "url", "source", "published")


@dataclass(frozen=True)
class KeywordMatcher:
    ci: re.Pattern[str] | None
    cs: re.Pattern[str] | None
    cjk: tuple[str, ...]

    def search(self, text: str) -> bool:
        if self.ci is not None and self.ci.search(text):
            return True
        if self.cs is not None and self.cs.search(text):
            return True
        return any(keyword in text for keyword in self.cjk)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    weight: float
    matcher: KeywordMatcher


@dataclass(frozen=True)
class SymbolRule:
    symbol: str
    alias: KeywordMatcher
    topic: KeywordMatcher


@dataclass(frozen=True)
class Rules:
    categories: tuple[Category, ...]
    symbols: tuple[SymbolRule, ...]
    holding_weights: Mapping[str, float]
    exclude_patterns: tuple[re.Pattern[str], ...]
    exclude_sources: frozenset[str]
    source_bonus: Mapping[str, float]
    labels: Mapping[str, str]


def _latin_pattern(words: Iterable[str], flags: int) -> re.Pattern[str] | None:
    unique = sorted(set(words), key=len, reverse=True)
    if not unique:
        return None
    alternation = "|".join(re.escape(word) for word in unique)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternation})(?![A-Za-z0-9])", flags)


def compile_keywords(keywords: Iterable[str], case_sensitive: Iterable[str] = ()) -> KeywordMatcher:
    keywords = list(keywords)
    return KeywordMatcher(
        ci=_latin_pattern((k for k in keywords if not has_cjk(k)), re.IGNORECASE),
        cs=_latin_pattern((k for k in case_sensitive if not has_cjk(k)), 0),
        cjk=tuple(k for k in [*keywords, *case_sensitive] if has_cjk(k)),
    )


def build_rules(news_cfg: Mapping[str, Any], holdings: Sequence[Holding]) -> Rules:
    categories_cfg = news_cfg.get("categories", {})
    holding_cfg = categories_cfg.get("holdings", {})
    categories = tuple(
        Category(
            key=key,
            label=cfg.get("label", key),
            weight=float(cfg.get("weight", 1)),
            matcher=compile_keywords(cfg.get("keywords", []), cfg.get("case_sensitive", [])),
        )
        for key, cfg in categories_cfg.items()
        if key != "holdings"
    )
    return Rules(
        categories=categories,
        symbols=tuple(SymbolRule(h.symbol, compile_keywords(h.aliases), compile_keywords(h.topics)) for h in holdings),
        holding_weights={
            "alias": float(holding_cfg.get("alias_weight", 6)),
            "topic": float(holding_cfg.get("topic_weight", 3)),
            "hint": float(holding_cfg.get("hint_weight", 2)),
        },
        exclude_patterns=tuple(re.compile(p, re.IGNORECASE) for p in news_cfg.get("exclude_patterns", [])),
        exclude_sources=frozenset(s.lower() for s in news_cfg.get("exclude_sources", [])),
        source_bonus={k: float(v) for k, v in news_cfg.get("source_bonus", {}).items()},
        labels={"holdings": holding_cfg.get("label", "我的持股"), **{c.key: c.label for c in categories}},
    )


def classify(title: str, summary: str, hint_categories: Sequence[str], hint_symbols: Sequence[str], rules: Rules) -> dict[str, Any]:
    text = f"{title}\n{summary}" if summary else title
    matched: dict[str, str] = {}
    for rule in rules.symbols:
        if rule.alias.search(text):
            matched[rule.symbol] = "alias"
        elif rule.topic.search(text):
            matched[rule.symbol] = "topic"
    for symbol in hint_symbols:
        matched.setdefault(symbol, "hint")

    categories: list[str] = []
    score = 0.0
    if matched:
        categories.append("holdings")
        score += max(rules.holding_weights[kind] for kind in matched.values())
    hinted = set(hint_categories)
    for category in rules.categories:
        if category.matcher.search(text):
            categories.append(category.key)
            score += category.weight
        elif category.key in hinted:
            categories.append(category.key)
            score += category.weight * HINT_FACTOR
    symbols = sorted(matched, key=lambda s: KIND_PRIORITY[matched[s]])
    return {"categories": categories, "symbols": symbols, "score": round(score, 2)}


def is_excluded(item: Mapping[str, Any], rules: Rules) -> bool:
    if str(item.get("source", "")).strip().lower() in rules.exclude_sources:
        return True
    title = str(item.get("title", ""))
    return any(pattern.search(title) for pattern in rules.exclude_patterns)


def make_id(url: str, title: str) -> str:
    return hashlib.sha1((url or title.lower()).encode("utf-8")).hexdigest()[:16]


def _coverage_bonus(coverage: int) -> float:
    return min(2.0, 0.5 * max(0, coverage - 1))


def _score(base: float, bonus: float, coverage: int) -> float:
    return round(base + bonus + _coverage_bonus(coverage), 2)


def rank_items(raw_items: Iterable[Mapping[str, Any]], rules: Rules, now: datetime) -> list[dict[str, Any]]:
    ranked = []
    for raw in raw_items:
        if is_excluded(raw, rules):
            continue
        result = classify(raw["title"], raw.get("summary", ""), raw.get("hint_categories") or [], raw.get("hint_symbols") or [], rules)
        if not result["categories"]:
            continue
        bonus = rules.source_bonus.get(raw.get("source", ""), 0.0)
        ranked.append(
            {
                "id": make_id(raw["url"], raw["title"]),
                "title": raw["title"],
                "url": raw["url"],
                "source": raw.get("source", ""),
                "published": raw["published"],
                "summary": raw.get("summary", ""),
                "lang": raw.get("lang", "en"),
                "feed": raw.get("feed", ""),
                "categories": result["categories"],
                "symbols": result["symbols"],
                "base_score": result["score"],
                "source_bonus": bonus,
                "score": _score(result["score"], bonus, 1),
                "coverage": 1,
                "also": [],
                "first_seen": to_iso(now),
            }
        )
    return ranked


def _union(left: Sequence[str], right: Sequence[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def _merge_pair(rep: Mapping[str, Any], other: Mapping[str, Any]) -> dict[str, Any]:
    sources = {rep["source"], *(a["source"] for a in rep["also"])}
    also = list(rep["also"])
    for candidate in [{"source": other["source"], "url": other["url"]}, *other.get("also", [])]:
        if candidate["source"] not in sources and len(also) < MAX_ALSO:
            also.append({"source": candidate["source"], "url": candidate["url"]})
            sources.add(candidate["source"])
    coverage = 1 + len(also)
    return {
        **rep,
        "categories": _union(rep["categories"], other["categories"]),
        "symbols": _union(rep["symbols"], other["symbols"]),
        "published": min(rep["published"], other["published"]),
        "first_seen": min(rep["first_seen"], other["first_seen"]),
        "also": also,
        "coverage": coverage,
        "score": _score(rep["base_score"], rep["source_bonus"], coverage),
    }


def cluster(items: Iterable[Mapping[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Merge near-identical headlines; the highest scoring copy becomes the representative."""
    ordered = sorted(items, key=lambda it: (-(it["base_score"] + it["source_bonus"]), it["published"]))
    reps: list[dict[str, Any]] = []
    rep_tokens: list[frozenset[str]] = []
    rep_times: list[datetime] = []
    index_by_id: dict[str, int] = {}
    for item in ordered:
        tokens = tokenize(item["title"])
        moment = parse_iso(item["published"]) or EPOCH
        index = index_by_id.get(item["id"])
        if index is None:
            index = next(
                (i for i, other in enumerate(rep_tokens) if abs(rep_times[i] - moment) <= CLUSTER_WINDOW and jaccard(tokens, other) >= threshold),
                None,
            )
        if index is None:
            also = list(item.get("also", []))
            reps.append({**item, "also": also, "coverage": 1 + len(also), "score": _score(item["base_score"], item["source_bonus"], 1 + len(also))})
            rep_tokens.append(tokens)
            rep_times.append(moment)
            index = len(reps) - 1
        else:
            reps[index] = _merge_pair(reps[index], item)
        index_by_id[item["id"]] = index
    return reps


def _clean_also(value: Any) -> list[dict[str, str]]:
    cleaned = []
    for entry in value if isinstance(value, list) else []:
        if isinstance(entry, Mapping) and isinstance(entry.get("source"), str) and sanitize_url(entry.get("url")):
            cleaned.append({"source": entry["source"], "url": entry["url"]})
    return cleaned[:MAX_ALSO]


def sanitize_items(items: Any) -> list[dict[str, Any]]:
    """Defensive copy of items loaded from a previous news.json (drop anything malformed)."""
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping) or not all(isinstance(item.get(k), str) and item.get(k) for k in REQUIRED_FIELDS):
            continue
        published = parse_iso(item["published"])
        if published is None or not sanitize_url(item["url"]):
            continue
        base, bonus = num(item.get("base_score")) or 0.0, num(item.get("source_bonus")) or 0.0
        also = _clean_also(item.get("also"))
        cleaned.append(
            {
                **item,
                "published": to_iso(published),
                "first_seen": to_iso(parse_iso(item.get("first_seen")) or published),
                "categories": [c for c in item.get("categories") or [] if isinstance(c, str)],
                "symbols": [s for s in item.get("symbols") or [] if isinstance(s, str)],
                "base_score": base,
                "source_bonus": bonus,
                "also": also,
                "coverage": 1 + len(also),
                "score": _score(base, bonus, 1 + len(also)),
            }
        )
    return cleaned


def merge_news(
    previous: Any,
    fresh: Sequence[Mapping[str, Any]],
    now: datetime,
    retention_hours: float,
    max_items: int,
    threshold: float,
    *,
    min_score: float = 0.0,
    low_score: float = 0.0,
    low_score_hours: float | None = None,
) -> list[dict[str, Any]]:
    """Merge with the previous snapshot, drop noise, age out minor stories, newest first.

    min_score applies to keyword relevance (base_score) so a reputable source alone cannot keep an off-topic story.
    """
    cutoff = to_iso(now - timedelta(hours=retention_hours))
    low_cutoff = to_iso(now - timedelta(hours=low_score_hours)) if low_score_hours else None
    pool = [item for item in [*sanitize_items(previous), *fresh] if item["published"] >= cutoff]
    kept = [
        item
        for item in cluster(pool, threshold)
        if item["base_score"] >= min_score and not (low_cutoff and item["published"] < low_cutoff and item["score"] < low_score)
    ]
    # Over the cap, keep the most important stories (score decayed by age), then list them newest first.
    kept.sort(key=lambda item: importance(item, now), reverse=True)
    selected = kept[:max_items]
    selected.sort(key=lambda item: item["published"], reverse=True)
    return selected


def importance(item: Mapping[str, Any], now: datetime) -> float:
    published = parse_iso(item.get("published")) or now
    age_hours = max(0.0, (now - published).total_seconds() / 3600)
    return float(item.get("score", 0)) * 0.5 ** (age_hours / IMPORTANCE_HALF_LIFE_HOURS)
