"""Pipeline entry point.

    python -m pipeline.main --mode quotes          # quote snapshot only (intraday)
    python -m pipeline.main --mode full            # quotes + news + earnings + macro + AI brief
    python -m pipeline.main --mode full --no-summary
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline import earnings, macro, news_fetch, quotes, summary
from pipeline.config import Config, ConfigError, load_config
from pipeline.io_utils import parse_iso, read_json, to_iso, utc_now, write_json_atomic
from pipeline.log import LOGGER, configure, warn
from pipeline.news_rank import build_rules, merge_news, rank_items, sanitize_items

DATA_DIR = Path("site") / "data"
EXIT_CONFIG_ERROR = 2
EXIT_NO_FRESH_QUOTES = 3  # quote run fetched nothing: the workflow skips the deploy


@dataclass(frozen=True)
class Deps:
    collect_quotes: Callable[..., Any] = quotes.collect_quotes
    fetch_news: Callable[..., Any] = news_fetch.fetch_all
    collect_earnings: Callable[..., Any] = earnings.collect_earnings
    collect_macro: Callable[..., Any] = macro.collect_macro
    generate_summary: Callable[..., Any] = summary.generate_summary


@dataclass(frozen=True)
class StageResult:
    ok: bool
    message: str

    def to_dict(self, now: datetime) -> dict[str, Any]:
        return {"ok": self.ok, "message": self.message, "at": to_iso(now)}


def _doc(data_dir: Path, name: str) -> dict[str, Any]:
    loaded = read_json(data_dir / name, {})
    return loaded if isinstance(loaded, dict) else {}


def _quotes_stage(cfg: Config, data_dir: Path, now: datetime, deps: Deps) -> StageResult:
    symbols = cfg.quote_symbols
    fresh, errors = deps.collect_quotes(symbols, now)
    previous_doc = _doc(data_dir, "quotes.json")
    previous = previous_doc.get("quotes")
    merged = quotes.merge_quotes(previous if isinstance(previous, dict) else {}, fresh, symbols)
    write_json_atomic(
        data_dir / "quotes.json",
        {
            # Keep the old timestamp when nothing was fetched so stale prices never look fresh.
            "generated_at": to_iso(now) if fresh else previous_doc.get("generated_at", to_iso(now)),
            "holdings": [h.to_public() for h in cfg.holdings],
            "market": [dict(m) for m in cfg.market],
            "tradingview": [dict(t) for t in cfg.tradingview],
            "quotes": merged,
            "indicators": quotes.build_indicators(merged, cfg.adr_pairs),
            "fx": {"USDTWD": (merged.get("TWD=X") or {}).get("price")},
            "errors": errors[:30],
        },
    )
    message = f"{len(fresh)}/{len(symbols)} symbols updated" + (f"; {len(errors)} issues" if errors else "")
    return StageResult(bool(fresh), message)


def _news_stage(cfg: Config, data_dir: Path, now: datetime, deps: Deps) -> tuple[StageResult, list[dict[str, Any]]]:
    settings = {key: cfg.news.get(key) for key in ("per_feed_limit", "google_window")}
    raw, feed_errors = deps.fetch_news(list(cfg.news["feeds"]), now, settings)
    rules = build_rules(cfg.news, cfg.holdings)
    ranked = rank_items(raw, rules, now)
    previous = _doc(data_dir, "news.json")
    items = merge_news(
        previous.get("items", []),
        ranked,
        now,
        retention_hours=float(cfg.news.get("retention_hours", 96)),
        max_items=int(cfg.news.get("max_items", 400)),
        threshold=float(cfg.news.get("dedupe_threshold", 0.6)),
        min_score=float(cfg.news.get("min_score", 0)),
        low_score=float(cfg.news.get("low_score", 0)),
        low_score_hours=cfg.news.get("low_score_hours"),
    )
    write_json_atomic(
        data_dir / "news.json",
        {
            # Only claim freshness when something was actually fetched.
            "generated_at": to_iso(now) if raw else previous.get("generated_at"),
            "categories": dict(rules.labels),
            "items": items,
            "feed_errors": feed_errors,
        },
    )
    message = f"{len(ranked)} relevant of {len(raw)} fetched, {len(items)} kept"
    if feed_errors:
        message += f"; failed feeds: {', '.join(sorted(feed_errors))}"
    return StageResult(bool(raw), message), items


def _earnings_stage(cfg: Config, data_dir: Path, now: datetime, deps: Deps) -> StageResult:
    doc, errors = deps.collect_earnings(list(cfg.earnings_watch), now)
    failed_calendar, failed_history = set(doc.get("failed_calendar", [])), set(doc.get("failed_history", []))
    merged = earnings.merge_earnings(doc, _doc(data_dir, "earnings.json"), failed_calendar, failed_history, now)
    has_data = bool(merged.get("upcoming") or merged.get("recent"))
    if has_data:
        write_json_atomic(data_dir / "earnings.json", {**merged, "errors": errors[:30]})
    failed_holdings = sorted((failed_calendar | failed_history) & {h.symbol for h in cfg.holdings})
    message = f"{len(merged.get('upcoming', []))} upcoming, {len(merged.get('recent', []))} recent" + (f"; {len(errors)} issues" if errors else "")
    if failed_holdings:
        message += f"; holdings using previous data: {', '.join(failed_holdings)}"
    if not has_data:
        message = f"no data, kept previous file; {message}"
    return StageResult(has_data and not failed_holdings, message)


def _macro_stage(cfg: Config, data_dir: Path, now: datetime, deps: Deps) -> StageResult:
    doc, errors = deps.collect_macro(cfg.events, cfg.macro_terms, now)
    if not doc.get("week"):
        week_start = now - timedelta(days=7)
        previous_week = [e for e in _doc(data_dir, "macro.json").get("week", []) if (parse_iso(e.get("datetime")) or week_start) > week_start]
        doc = {**doc, "week": previous_week}
    write_json_atomic(data_dir / "macro.json", {**doc, "errors": errors})
    return StageResult(not errors, f"{len(doc['week'])} events this week, {len(doc['upcoming'])} upcoming" + (f"; {'; '.join(errors)}" if errors else ""))


def _summary_stage(cfg: Config, data_dir: Path, now: datetime, deps: Deps, news_items: list[dict[str, Any]]) -> StageResult:
    ctx = summary.SummaryContext(
        news=news_items,
        quotes_doc=_doc(data_dir, "quotes.json"),
        earnings_doc=_doc(data_dir, "earnings.json"),
        macro_doc=_doc(data_dir, "macro.json"),
        holdings=cfg.holdings,
    )
    brief, status = deps.generate_summary(ctx, now)
    if brief:
        write_json_atomic(data_dir / "summary.json", brief)
    return StageResult(not status.startswith("error"), status)


def _guard(action: Callable[[], StageResult]) -> StageResult:
    try:
        return action()
    except Exception as exc:  # one broken stage must never block the others
        return StageResult(False, f"{type(exc).__name__}: {exc}")


def _run_full(cfg: Config, data_dir: Path, now: datetime, deps: Deps, with_summary: bool) -> dict[str, StageResult]:
    stages: dict[str, StageResult] = {}
    news_items: list[dict[str, Any]] = []

    def news_action() -> StageResult:
        nonlocal news_items
        result, news_items = _news_stage(cfg, data_dir, now, deps)
        return result

    stages["news"] = _guard(news_action)
    if not news_items:
        news_items = sanitize_items(_doc(data_dir, "news.json").get("items", []))
    stages["earnings"] = _guard(lambda: _earnings_stage(cfg, data_dir, now, deps))
    stages["macro"] = _guard(lambda: _macro_stage(cfg, data_dir, now, deps))
    if with_summary:
        stages["summary"] = _guard(lambda: _summary_stage(cfg, data_dir, now, deps, news_items))
    else:
        stages["summary"] = StageResult(True, "skipped: disabled for this run")
    return stages


def run(mode: str, root: Path, now: datetime | None = None, summary: bool = True, deps: Deps | None = None) -> int:
    configure()
    now = now or utc_now()
    deps = deps or Deps()
    try:
        cfg = load_config(root / "config")
    except ConfigError as exc:
        warn(f"config error: {exc}")
        return EXIT_CONFIG_ERROR
    data_dir = root / DATA_DIR
    quotes_result = _guard(lambda: _quotes_stage(cfg, data_dir, now, deps))
    stages = {"quotes": quotes_result}
    if mode == "full":
        stages.update(_run_full(cfg, data_dir, now, deps, summary))
        write_json_atomic(
            data_dir / "meta.json",
            {"last_full_run": to_iso(now), "stages": {name: result.to_dict(now) for name, result in stages.items()}},
        )
    for name, result in stages.items():
        if result.ok:
            LOGGER.info("%s: %s", name, result.message)
        else:
            warn(f"{name}: {result.message}")
    if mode == "quotes" and not quotes_result.ok:
        return EXIT_NO_FRESH_QUOTES
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="美股持股觀測站資料管線")
    parser.add_argument("--mode", choices=("full", "quotes"), default="full")
    parser.add_argument("--no-summary", action="store_true", help="skip the AI brief for this run")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    return run(args.mode, args.root, summary=not args.no_summary)


if __name__ == "__main__":
    raise SystemExit(main())
