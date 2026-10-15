"""Quote snapshots (Yahoo Finance via yfinance) plus ADR premium indicators."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from pipeline.config import AdrPair
import re

from pipeline.io_utils import num, to_iso
from pipeline.text import clean_text

HISTORY_POINTS = 66  # about three months of trading days
STATIC_FIELDS = ("name", "currency", "high_52w", "low_52w")
STATE_MAP = {
    "PRE": "PRE",
    "REGULAR": "REGULAR",
    "POST": "POST",
    "PREPRE": "CLOSED",
    "POSTPOST": "CLOSED",
    "CLOSED": "CLOSED",
}

History = Sequence[tuple[str, float]]
InfoFetcher = Callable[[str], Mapping[str, Any]]
HistoryFetcher = Callable[[Sequence[str]], Mapping[str, History]]


def fetch_info(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    return dict(yf.Ticker(symbol).info or {})


def extract_history(frame: Any, symbol: str) -> list[tuple[str, float]]:
    """Daily closes for one symbol out of a yfinance download frame."""
    if frame is None or getattr(frame, "empty", True):
        return []
    try:
        if getattr(frame.columns, "nlevels", 1) > 1:
            series = frame[(symbol, "Close")]
        else:
            series = frame["Close"]
    except KeyError:
        return []
    closes = []
    for index, value in series.items():
        close = num(value)
        if close is not None:
            closes.append((index.strftime("%Y-%m-%d"), round(close, 4)))
    return closes


def fetch_history(symbols: Sequence[str], period: str = "3mo") -> dict[str, list[tuple[str, float]]]:
    import yfinance as yf

    frame = yf.download(
        list(symbols),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    return {symbol: extract_history(frame, symbol) for symbol in symbols}


def _extended_quote(state: str | None, info: Mapping[str, Any], price: float) -> dict[str, Any] | None:
    if state == "PRE":
        label, ext_price = "盤前", num(info.get("preMarketPrice"))
    elif state in ("POST", "CLOSED"):
        label, ext_price = "盤後", num(info.get("postMarketPrice"))
    else:
        return None
    if ext_price is None or not price:
        return None
    return {"label": label, "price": round(ext_price, 4), "change_pct": round((ext_price - price) / price * 100, 2)}


def _as_of(info: Mapping[str, Any], fallback: datetime) -> str | None:
    epoch = num(info.get("regularMarketTime"))
    if epoch is None:
        return to_iso(fallback)
    return to_iso(datetime.fromtimestamp(epoch, tz=timezone.utc))


def build_quote(symbol: str, info: Mapping[str, Any] | None, history: History | None, fetched_at: datetime) -> dict[str, Any] | None:
    info = info or {}
    closes = list(history or [])
    price = num(info.get("regularMarketPrice")) or num(info.get("currentPrice"))
    source = "info" if price is not None else "history"
    if price is None and closes:
        price = closes[-1][1]
    if price is None:
        return None
    prev_close = num(info.get("regularMarketPreviousClose")) or num(info.get("previousClose"))
    if prev_close is None and len(closes) >= 2:
        prev_close = closes[-2][1]
    raw_state = str(info.get("marketState") or "").upper()
    state = STATE_MAP.get(raw_state, "CLOSED") if raw_state else None
    return {
        "symbol": symbol,
        "name": clean_text(info.get("shortName") or info.get("longName"), 80) or symbol,
        "price": round(price, 4),
        "prev_close": round(prev_close, 4) if prev_close else None,
        "change": round(price - prev_close, 4) if prev_close else None,
        "change_pct": round((price - prev_close) / prev_close * 100, 2) if prev_close else None,
        "currency": info.get("currency") if re.fullmatch(r"[A-Z]{3}", str(info.get("currency") or "")) else None,
        "market_state": state,
        "ext": _extended_quote(state, info, price),
        "as_of": _as_of(info, fetched_at),
        "high_52w": num(info.get("fiftyTwoWeekHigh")),
        "low_52w": num(info.get("fiftyTwoWeekLow")),
        "history": [{"d": day, "c": close} for day, close in closes[-HISTORY_POINTS:]],
        "source": source,
        "stale": False,
    }


def adr_premium(adr_price: Any, local_price: Any, ratio: Any, fx_rate: Any) -> float | None:
    """Premium (%) of an ADR over the local share it represents, converted to USD."""
    values = [num(v) for v in (adr_price, local_price, ratio, fx_rate)]
    if any(v is None or v <= 0 for v in values):
        return None
    adr, local, shares_per_adr, fx = values
    implied = local * shares_per_adr / fx
    return round((adr / implied - 1) * 100, 2)


def _premium_history(adr: Mapping, local: Mapping, fx: Mapping, ratio: float) -> list[dict[str, Any]]:
    local_by_day = {p["d"]: p["c"] for p in local.get("history", [])}
    fx_by_day = {p["d"]: p["c"] for p in fx.get("history", [])}
    points = []
    for point in adr.get("history", []):
        day = point["d"]
        premium = adr_premium(point["c"], local_by_day.get(day), ratio, fx_by_day.get(day))
        if premium is not None:
            points.append({"d": day, "c": premium})
    return points[-30:]


def build_indicators(quotes: Mapping[str, Mapping[str, Any]], adr_pairs: Sequence[AdrPair]) -> list[dict[str, Any]]:
    indicators = []
    for pair in adr_pairs:
        adr, local, fx = quotes.get(pair.adr), quotes.get(pair.local), quotes.get(pair.fx)
        if not (adr and local and fx):
            continue
        premium = adr_premium(adr.get("price"), local.get("price"), pair.ratio, fx.get("price"))
        if premium is None:
            continue
        indicators.append(
            {
                "id": f"adr-{pair.adr}",
                "label": pair.label,
                "note": pair.note,
                "value": premium,
                "unit": "%",
                "adr_price": adr["price"],
                "implied_price": round(local["price"] * pair.ratio / fx["price"], 2),
                "history": _premium_history(adr, local, fx, pair.ratio),
            }
        )
    return indicators


def _with_static_fields(fresh: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    """A history-only quote (Yahoo info rate-limited) keeps the previous name / currency / 52-week range."""
    if fresh.get("source") != "history" or not isinstance(previous, Mapping):
        return dict(fresh)
    carried = {field: previous.get(field) for field in STATIC_FIELDS if previous.get(field) is not None}
    return {**fresh, **carried, "degraded": True}


def merge_quotes(previous: Mapping[str, Mapping], fresh: Mapping[str, Mapping], symbols: Sequence[str]) -> dict[str, dict]:
    """Prefer fresh quotes; fall back to the previous snapshot marked as stale."""
    merged: dict[str, dict] = {}
    for symbol in symbols:
        if symbol in fresh:
            merged[symbol] = _with_static_fields(fresh[symbol], previous.get(symbol))
        elif isinstance(previous.get(symbol), Mapping):
            merged[symbol] = {**previous[symbol], "stale": True}
    return merged


def _info_with_retry(fetcher: InfoFetcher, symbol: str, retry_delay: float) -> tuple[Mapping[str, Any], str | None]:
    last_error = None
    for attempt in range(2):
        try:
            return fetcher(symbol) or {}, None
        except Exception as exc:  # network/parsing errors from yfinance are not typed
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 0 and retry_delay:
                time.sleep(retry_delay)
    return {}, last_error


def collect_quotes(
    symbols: Sequence[str],
    now: datetime,
    *,
    info_fetcher: InfoFetcher = fetch_info,
    history_fetcher: HistoryFetcher = fetch_history,
    retry_delay: float = 1.0,
    max_workers: int = 6,
) -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    try:
        histories = history_fetcher(symbols)
    except Exception as exc:  # keep going with info-only quotes
        histories = {}
        errors.append(f"history download failed: {type(exc).__name__}: {exc}")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(lambda s: _info_with_retry(info_fetcher, s, retry_delay), symbols))
    quotes: dict[str, dict] = {}
    for symbol, (info, error) in zip(symbols, results):
        if error:
            errors.append(f"{symbol}: {error}")
        quote = build_quote(symbol, info, histories.get(symbol, []), now)
        if quote is None:
            errors.append(f"{symbol}: no data")
        else:
            quotes[symbol] = quote
    return quotes, errors
