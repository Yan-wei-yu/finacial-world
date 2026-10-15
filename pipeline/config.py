"""Load and validate the JSON configuration files under config/."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipeline.io_utils import num

SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=\-]{0,14}$")
TV_SYMBOL_RE = re.compile(r"^[A-Z0-9_]{1,20}:[A-Z0-9.!_\-]{1,20}$")
FEED_TYPES = frozenset({"google_news", "rss", "cnyes"})
LANGS = frozenset({"en", "zh"})
EARNINGS_GROUPS = frozenset({"holding", "memory", "semis", "capex", "peer"})
CONFIG_FILES = ("portfolio.json", "watchlist.json", "news.json", "events.json", "macro_terms.json")


class ConfigError(ValueError):
    """A configuration file is missing or invalid."""


@dataclass(frozen=True)
class Holding:
    symbol: str
    shares: float
    name: str
    name_zh: str
    kind: str
    exchange: str
    tv_symbol: str | None
    cost: float | None
    aliases: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    drivers: tuple[str, ...] = ()

    def to_public(self) -> dict[str, Any]:
        """Fields the web page needs (keyword lists stay in the pipeline)."""
        return {
            "symbol": self.symbol,
            "shares": self.shares,
            "cost": self.cost,
            "name": self.name,
            "name_zh": self.name_zh,
            "kind": self.kind,
            "exchange": self.exchange,
            "tv_symbol": self.tv_symbol,
            "drivers": list(self.drivers),
        }


@dataclass(frozen=True)
class AdrPair:
    adr: str
    local: str
    ratio: float
    fx: str
    label: str
    note: str = ""


@dataclass(frozen=True)
class Config:
    holdings: tuple[Holding, ...]
    market: tuple[dict[str, Any], ...]
    extra_symbols: tuple[str, ...]
    adr_pairs: tuple[AdrPair, ...]
    earnings_watch: tuple[dict[str, Any], ...]
    tradingview: tuple[dict[str, Any], ...]
    news: dict[str, Any]
    events: dict[str, Any]
    macro_terms: dict[str, Any]

    @property
    def quote_symbols(self) -> list[str]:
        ordered = [h.symbol for h in self.holdings]
        ordered += [m["symbol"] for m in self.market]
        ordered += list(self.extra_symbols)
        for pair in self.adr_pairs:
            ordered += [pair.adr, pair.local, pair.fx]
        return list(dict.fromkeys(ordered))


def _symbol(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SYMBOL_RE.fullmatch(value):
        raise ConfigError(f"{where}: invalid symbol {value!r}")
    return value


def _tv_symbol(value: Any, where: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not TV_SYMBOL_RE.fullmatch(value):
        raise ConfigError(f"{where}: invalid tv_symbol {value!r} (expected EXCHANGE:SYMBOL)")
    return value


def _str_list(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"{where}: expected a list of non-empty strings")
    return tuple(v.strip() for v in value)


def _shares(value: Any, where: str) -> float:
    shares = num(value)
    if shares is None or shares < 0:
        raise ConfigError(f"{where}: shares must be a number >= 0")
    return int(shares) if shares.is_integer() else shares


def _cost(value: Any, where: str) -> float | None:
    if value is None:
        return None
    cost = num(value)
    if cost is None or cost <= 0:
        raise ConfigError(f"{where}: cost must be a positive number or null")
    return cost


def _holding(raw: Any, where: str) -> Holding:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where}: name is required")
    return Holding(
        symbol=_symbol(raw.get("symbol"), where),
        shares=_shares(raw.get("shares"), where),
        name=name.strip(),
        name_zh=str(raw.get("name_zh") or name).strip(),
        kind=str(raw.get("kind") or "Stock"),
        exchange=str(raw.get("exchange") or ""),
        tv_symbol=_tv_symbol(raw.get("tv_symbol"), where),
        cost=_cost(raw.get("cost"), where),
        aliases=_str_list(raw.get("aliases"), where),
        topics=_str_list(raw.get("topics"), where),
        drivers=_str_list(raw.get("drivers"), where),
    )


def parse_portfolio(data: Any) -> tuple[Holding, ...]:
    raw_holdings = data.get("holdings") if isinstance(data, dict) else None
    if not isinstance(raw_holdings, list) or not raw_holdings:
        raise ConfigError("portfolio.json: holdings must be a non-empty list")
    holdings: list[Holding] = []
    for index, raw in enumerate(raw_holdings):
        holding = _holding(raw, f"portfolio.json holdings[{index}]")
        if any(h.symbol == holding.symbol for h in holdings):
            raise ConfigError(f"portfolio.json holdings[{index}]: duplicate symbol {holding.symbol}")
        holdings.append(holding)
    return tuple(holdings)


def _objects(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ConfigError(f"watchlist.json: {key} must be a list of objects")
    return value


def _tradingview(data: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    entries = []
    for index, entry in enumerate(_objects(data, "tradingview")):
        where = f"watchlist.json tradingview[{index}]"
        symbol = _tv_symbol(entry.get("tv_symbol"), where)
        if symbol is None or not isinstance(entry.get("label"), str) or not entry["label"].strip():
            raise ConfigError(f"{where}: tv_symbol and label are required")
        entries.append({"tv_symbol": symbol, "label": entry["label"].strip(), "tape": bool(entry.get("tape")), "chart": bool(entry.get("chart"))})
    return tuple(entries)


def parse_watchlist(data: Any) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], tuple[AdrPair, ...], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    if not isinstance(data, dict):
        raise ConfigError("watchlist.json must be an object")
    market = []
    for index, entry in enumerate(_objects(data, "market")):
        where = f"watchlist.json market[{index}]"
        _symbol(entry.get("symbol"), where)
        if not isinstance(entry.get("label"), str):
            raise ConfigError(f"{where}: label is required")
        market.append(dict(entry))
    extra = tuple(_symbol(s, "watchlist.json extra_symbols") for s in data.get("extra_symbols") or [])
    pairs = []
    for index, entry in enumerate(_objects(data, "adr_pairs")):
        where = f"watchlist.json adr_pairs[{index}]"
        ratio = num(entry.get("ratio"))
        if ratio is None or ratio <= 0:
            raise ConfigError(f"{where}: ratio must be > 0")
        pairs.append(
            AdrPair(
                adr=_symbol(entry.get("adr"), where),
                local=_symbol(entry.get("local"), where),
                ratio=ratio,
                fx=_symbol(entry.get("fx"), where),
                label=str(entry.get("label") or entry.get("adr")),
                note=str(entry.get("note") or ""),
            )
        )
    watch = []
    for index, entry in enumerate(_objects(data, "earnings_watch")):
        where = f"watchlist.json earnings_watch[{index}]"
        _symbol(entry.get("symbol"), where)
        if entry.get("group") not in EARNINGS_GROUPS:
            raise ConfigError(f"{where}: group must be one of {sorted(EARNINGS_GROUPS)}")
        watch.append(dict(entry))
    return tuple(market), extra, tuple(pairs), tuple(watch), _tradingview(data)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _public_https_url(value: Any, where: str) -> None:
    try:
        parsed = urlparse(value) if isinstance(value, str) else None
        host = parsed.hostname if parsed else None
    except ValueError:
        parsed, host = None, None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or host == "localhost"
        or _is_ip_literal(host)
    ):
        raise ConfigError(f"{where}: url must be a plain https URL to a public host name")


def _validate_feed(feed: Any, where: str, seen: set[str]) -> None:
    if not isinstance(feed, dict):
        raise ConfigError(f"{where}: must be an object")
    feed_id = feed.get("id")
    if not isinstance(feed_id, str) or not feed_id or feed_id in seen:
        raise ConfigError(f"{where}: id must be a unique non-empty string")
    seen.add(feed_id)
    if feed.get("type") not in FEED_TYPES:
        raise ConfigError(f"{where}: type must be one of {sorted(FEED_TYPES)}")
    if feed.get("lang") not in LANGS:
        raise ConfigError(f"{where}: lang must be 'en' or 'zh'")
    if feed["type"] == "google_news":
        if not isinstance(feed.get("query"), str) or not feed["query"].strip():
            raise ConfigError(f"{where}: query is required for google_news feeds")
    else:
        _public_https_url(feed.get("url"), where)


def validate_news(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError("news.json must be an object")
    feeds = data.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ConfigError("news.json: feeds must be a non-empty list")
    seen: set[str] = set()
    for index, feed in enumerate(feeds):
        _validate_feed(feed, f"news.json feeds[{index}]", seen)
    categories = data.get("categories")
    if not isinstance(categories, dict) or "holdings" not in categories:
        raise ConfigError("news.json: categories.holdings is required")
    for pattern in data.get("exclude_patterns") or []:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"news.json: invalid exclude pattern {pattern!r}: {exc}") from exc
    return data


def _load(path: Path) -> Any:
    if not path.is_file():
        raise ConfigError(f"missing config file: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path.name}: invalid JSON ({exc})") from exc


def load_config(config_dir: Path) -> Config:
    raw = {name: _load(config_dir / name) for name in CONFIG_FILES}
    market, extra, pairs, watch, tradingview = parse_watchlist(raw["watchlist.json"])
    events, terms = raw["events.json"], raw["macro_terms.json"]
    if not isinstance(events, dict) or not isinstance(terms, dict):
        raise ConfigError("events.json and macro_terms.json must be JSON objects")
    return Config(
        holdings=parse_portfolio(raw["portfolio.json"]),
        market=market,
        extra_symbols=extra,
        adr_pairs=pairs,
        earnings_watch=watch,
        tradingview=tradingview,
        news=validate_news(raw["news.json"]),
        events=events,
        macro_terms=terms,
    )
