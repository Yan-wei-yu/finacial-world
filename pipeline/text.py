"""Text helpers shared by the news fetcher and ranker."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

# [^<>]* keeps these linear: a run of "<" characters can no longer cause quadratic backtracking.
_BLOCK_TAG_RE = re.compile(r"</?(?:br|p|div|li|ul|ol|tr|td|h[1-6])\b[^<>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^<>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_URL_LENGTH = 2048
INPUT_FACTOR = 20  # raw markup examined per output character
_WS_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")
_LATIN_WORD_RE = re.compile(r"[a-z0-9][a-z0-9.&'\-]*")
_SUFFIX_SEPARATORS = (" - ", " | ", " — ", " – ")

STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "as", "at", "by", "from",
        "is", "are", "was", "were", "be", "been", "its", "it", "this", "that", "after", "amid", "over",
        "into", "new", "says", "say", "said", "will", "could", "may", "than", "more", "about", "how",
        "why", "what", "has", "have", "had", "not",
    }
)


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def clean_text(value: object, limit: int) -> str:
    """Strip HTML, decode entities, collapse whitespace and cap the length."""
    if not isinstance(value, str):
        return ""
    text = _TAG_RE.sub("", _BLOCK_TAG_RE.sub(" ", value[: limit * INPUT_FACTOR]))
    text = _TAG_RE.sub("", html.unescape(text))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def sanitize_url(value: object) -> str | None:
    """Only allow absolute http(s) links; anything else (javascript:, data:, relative) is dropped."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > MAX_URL_LENGTH or _CONTROL_RE.search(candidate):
        return None
    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not hostname or parsed.username or parsed.password:
        return None
    return candidate


def strip_source_suffix(title: str, source: str) -> str:
    """Google News appends " - Source" to titles; remove it when it matches the known source."""
    if not source:
        return title
    for separator in _SUFFIX_SEPARATORS:
        suffix = f"{separator}{source}"
        if title.endswith(suffix) and len(title) > len(suffix):
            return title[: -len(suffix)].rstrip()
    return title


def tokenize(text: str) -> frozenset[str]:
    """Words for Latin text, character bigrams for CJK text (used for duplicate detection)."""
    lowered = text.lower()
    tokens: set[str] = set()
    for word in _LATIN_WORD_RE.findall(lowered):
        stripped = word.strip(".'-&")
        if len(stripped) >= 2 and stripped not in STOPWORDS:
            tokens.add(stripped)
    for run in _CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i : i + 2] for i in range(len(run) - 1))
    return frozenset(tokens)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0
