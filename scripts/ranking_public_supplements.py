from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
SUPPLEMENT_PATH = PROJECT_DIR / "configs" / "runtime" / "public_ranking_source_supplements.json"
INVALID_ALIAS_VALUES = {"", "无", "暂无", "无对应", "未发布", "未收录", "-", "none", "nan"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def subject_code(subject: dict[str, Any]) -> str:
    return clean_text(subject.get("target_subject_code") or subject.get("ministry_subject_code")).zfill(4)


def load_public_supplements() -> dict[str, Any]:
    if not SUPPLEMENT_PATH.exists():
        return {}
    return json.loads(SUPPLEMENT_PATH.read_text(encoding="utf-8"))


def valid_mapping_value(value: Any) -> str:
    text = clean_text(value)
    return "" if text.lower() in INVALID_ALIAS_VALUES else text


def qs_proxy(subject: dict[str, Any]) -> dict[str, Any]:
    payload = load_public_supplements()
    name = clean_text(subject.get("target_subject") or subject.get("ministry_subject_name"))
    by_name = payload.get("qs_proxy_subject_names", {})
    if name in by_name:
        return dict(by_name[name])
    return dict(payload.get("qs_proxy_subjects", {}).get(subject_code(subject), {}))


def arwu_public_alias(subject: dict[str, Any]) -> dict[str, Any]:
    payload = load_public_supplements()
    return dict(payload.get("arwu_public_aliases", {}).get(subject_code(subject), {}))


def source_alias_supplement(subject: dict[str, Any], source: str) -> dict[str, Any]:
    payload = load_public_supplements()
    source_rows = payload.get("source_alias_supplements", {}).get(source, {})
    name = clean_text(subject.get("target_subject") or subject.get("ministry_subject_name"))
    if name in source_rows:
        return dict(source_rows[name])
    return dict(source_rows.get(subject_code(subject), {}))


def usnews_weight_strategy() -> dict[str, Any]:
    payload = load_public_supplements()
    return dict(payload.get("usnews_weight_strategy", {}))


def qs_proxy_aliases(subject: dict[str, Any]) -> list[str]:
    proxy = qs_proxy(subject)
    values = [
        valid_mapping_value(proxy.get("proxy_subject_or_area")),
        valid_mapping_value(proxy.get("proxy_subject_en")),
    ]
    return [value for value in values if value]


def arwu_public_aliases(subject: dict[str, Any]) -> list[str]:
    alias = arwu_public_alias(subject)
    return [valid_mapping_value(value) for value in alias.get("aliases", []) if valid_mapping_value(value)]


def source_aliases(subject: dict[str, Any], source: str) -> list[str]:
    alias = source_alias_supplement(subject, source)
    return [valid_mapping_value(value) for value in alias.get("aliases", []) if valid_mapping_value(value)]


def public_supplement_records(subject: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    qs = qs_proxy(subject)
    if qs:
        records.append(
            {
                "ranking_source": "QS",
                "supplement_type": "proxy_subject_or_area",
                "subject_or_area": valid_mapping_value(qs.get("proxy_subject_or_area")),
                "subject_or_area_en": valid_mapping_value(qs.get("proxy_subject_en")),
                "proxy_level": clean_text(qs.get("proxy_level")),
                "requires_disclosure": bool(qs.get("requires_disclosure")),
                "reason": clean_text(qs.get("reason")),
                "source_key": clean_text(qs.get("source_key")),
            }
        )
    arwu = arwu_public_alias(subject)
    for alias in arwu_public_aliases(subject):
        records.append(
            {
                "ranking_source": "软科",
                "supplement_type": "public_english_alias",
                "subject_or_area": alias,
                "subject_or_area_en": alias,
                "proxy_level": clean_text(arwu.get("proxy_level")),
                "requires_disclosure": bool(arwu.get("requires_disclosure")),
                "reason": clean_text(arwu.get("reason")),
                "source_key": clean_text(arwu.get("source_key")),
            }
        )
    payload = load_public_supplements()
    for source in payload.get("source_alias_supplements", {}):
        supplement = source_alias_supplement(subject, source)
        for alias in source_aliases(subject, source):
            records.append(
                {
                    "ranking_source": source,
                    "supplement_type": "public_source_alias",
                    "subject_or_area": alias,
                    "subject_or_area_en": alias,
                    "proxy_level": clean_text(supplement.get("proxy_level")),
                    "requires_disclosure": bool(supplement.get("requires_disclosure")),
                    "reason": clean_text(supplement.get("reason")),
                    "source_key": clean_text(supplement.get("source_key")),
                }
            )
    return records
