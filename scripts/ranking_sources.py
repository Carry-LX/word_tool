from __future__ import annotations

import re
from typing import Any


CANONICAL_KEYS = ("arwu", "qs", "usnews", "the")

DISPLAY_LABELS = {
    "arwu": "\u8f6f\u79d1",
    "qs": "QS",
    "usnews": "US News",
    "the": "THE",
}

# Historical outputs may contain mojibake for the ARWU display label. The exact
# broken bytes vary by console/codepage, so source_key also handles the common
# first-character signature instead of relying on a single corrupted spelling.
LEGACY_ARWU_PREFIX = "\u675e"

ALIASES = {
    "arwu": "arwu",
    "gras": "arwu",
    "shanghairanking": "arwu",
    "shanghai ranking": "arwu",
    "\u8f6f\u79d1": "arwu",
    "\u8f6f\u79d1\u6392\u540d": "arwu",
    "qs": "qs",
    "usnews": "usnews",
    "us news": "usnews",
    "u.s.news": "usnews",
    "u.s. news": "usnews",
    "the": "the",
    "timeshighereducation": "the",
    "times higher education": "the",
}


def normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff. ]+", "", text)


def source_key(value: Any, default: str = "") -> str:
    if value in CANONICAL_KEYS:
        return str(value)
    text = str(value or "").strip()
    if not text:
        return default
    if text.startswith(LEGACY_ARWU_PREFIX):
        return "arwu"
    return ALIASES.get(normalize_token(text), default)


def require_source_key(value: Any) -> str:
    key = source_key(value)
    if not key:
        raise ValueError(f"Unsupported ranking source: {value!r}")
    return key


def display_label(value: Any) -> str:
    key = source_key(value)
    return DISPLAY_LABELS.get(key, str(value or "").strip())


def legacy_label(value: Any) -> str:
    return display_label(value)


def normalize_sources(values: Any, default: list[str] | None = None, *, display: bool = True) -> list[str]:
    source_values = values if isinstance(values, list) else default
    if not source_values:
        source_values = list(CANONICAL_KEYS)
    seen: set[str] = set()
    normalized: list[str] = []
    for value in source_values:
        key = source_key(value)
        if key and key not in seen:
            seen.add(key)
            normalized.append(display_label(key) if display else key)
    return normalized or [display_label(key) if display else key for key in CANONICAL_KEYS]


def source_sort_key(value: Any) -> int:
    key = source_key(value)
    try:
        return list(CANONICAL_KEYS).index(key)
    except ValueError:
        return len(CANONICAL_KEYS)
