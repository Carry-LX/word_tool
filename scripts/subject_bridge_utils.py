from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text


def read_alias_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["subject_id", "ranking_source", "ranking_subject_norm"])
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def build_subject_lookup(subject_aliases: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    lookup: dict[tuple[str, str], list[str]] = {}
    if subject_aliases.empty:
        return lookup
    for _, row in subject_aliases.iterrows():
        key = (clean_text(row.get("ranking_source")), clean_text(row.get("ranking_subject_norm")))
        subject_id = clean_text(row.get("subject_id"))
        if not key[0] or not key[1] or not subject_id:
            continue
        lookup.setdefault(key, [])
        if subject_id not in lookup[key]:
            lookup[key].append(subject_id)
    return lookup


def subject_ids_for(source: Any, subject_value: Any, lookup: dict[tuple[str, str], list[str]]) -> list[str]:
    key = normalize_key(subject_value)
    return lookup.get((clean_text(source), key), [])


def build_subject_bridge(
    facts: pd.DataFrame,
    subject_aliases: pd.DataFrame,
    *,
    fact_id_col: str,
    subject_raw_col: str = "ranking_subject_raw",
    subject_norm_col: str = "ranking_subject_norm",
    subject_id_col: str = "subject_id",
    bridge_id_prefix: str = "bridge",
) -> pd.DataFrame:
    lookup = build_subject_lookup(subject_aliases)
    rows: list[dict[str, Any]] = []
    if facts.empty:
        return pd.DataFrame(
            columns=[
                "bridge_id",
                fact_id_col,
                "ranking_source",
                "ranking_subject_raw",
                "ranking_subject_norm",
                "subject_id",
                "alias_match_count",
                "candidate_order",
                "match_policy",
                "is_direct_subject_id",
            ]
        )

    for _, fact in facts.iterrows():
        source = clean_text(fact.get("ranking_source"))
        raw = clean_text(fact.get(subject_raw_col))
        norm = clean_text(fact.get(subject_norm_col)) or normalize_key(raw)
        candidate_ids = subject_ids_for(source, norm, lookup) or subject_ids_for(source, raw, lookup)
        direct_subject_id = clean_text(fact.get(subject_id_col)) if subject_id_col in facts.columns else ""
        if direct_subject_id and direct_subject_id not in candidate_ids:
            candidate_ids = [direct_subject_id, *candidate_ids]
        match_count = len(candidate_ids)
        if match_count == 0:
            continue
        match_policy = "unique_alias" if match_count == 1 else "multi_alias_bridge"
        for order, subject_id in enumerate(candidate_ids, start=1):
            rows.append(
                {
                    fact_id_col: clean_text(fact.get(fact_id_col)),
                    "ranking_source": source,
                    "ranking_subject_raw": raw,
                    "ranking_subject_norm": norm,
                    "subject_id": subject_id,
                    "alias_match_count": match_count,
                    "candidate_order": order,
                    "match_policy": match_policy,
                    "is_direct_subject_id": bool(direct_subject_id and direct_subject_id == subject_id),
                }
            )

    bridge = pd.DataFrame(rows)
    if bridge.empty:
        bridge.insert(0, "bridge_id", [])
        return bridge
    bridge = bridge.drop_duplicates(
        subset=[fact_id_col, "ranking_source", "ranking_subject_norm", "subject_id"],
        keep="first",
    ).reset_index(drop=True)
    bridge.insert(0, "bridge_id", [f"{bridge_id_prefix}_{idx + 1:08d}" for idx in range(len(bridge))])
    return bridge
