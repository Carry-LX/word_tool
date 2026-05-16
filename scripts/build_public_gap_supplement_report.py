from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import ranking_public_supplements as public_supplements


PROJECT_DIR = Path(__file__).resolve().parent.parent
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
FACT_RANKING_CSV = PROJECT_DIR / "processed" / "fact_ranking.csv"
FACT_WEIGHT_CSV = PROJECT_DIR / "processed" / "fact_indicator_weight.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
ARWU_PUBLIC_CSV = PROJECT_DIR / "external_data" / "processed" / "arwu_gras_public_tongji_history_2023_2025_long.csv"
USNEWS_HISTORY_CSV = PROJECT_DIR / "external_data" / "processed" / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "public_gap_supplements"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def normalize_ascii_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).lower().replace("&", " and "))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def subject_from_coverage(row: pd.Series) -> dict[str, Any]:
    return {
        "subject_id": clean_text(row.get("subject_id")),
        "target_subject": clean_text(row.get("source_subject_name") or row.get("ministry_subject_name")),
        "target_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
        "ministry_subject_name": clean_text(row.get("ministry_subject_name")),
        "arwu_subject_name": clean_text(row.get("arwu_mapping")),
        "qs_subject_name": clean_text(row.get("qs_mapping")),
        "usnews_subject_name": clean_text(row.get("usnews_mapping")),
        "the_subject_area": clean_text(row.get("the_mapping")),
        "alias_summary": {},
    }


def load_alias_summary(subject_id: str) -> dict[str, list[str]]:
    aliases = read_csv(DIM_ALIAS_CSV)
    if aliases.empty:
        return {}
    rows = aliases[aliases["subject_id"] == subject_id].copy()
    summary: dict[str, list[str]] = {}
    for source, group in rows.groupby("ranking_source"):
        values = sorted({clean_text(value) for value in group["ranking_subject_alias"].tolist() if clean_text(value)})
        if values:
            summary[clean_text(source)] = values
    return summary


def add_public_aliases(subject: dict[str, Any]) -> None:
    alias_summary = subject.setdefault("alias_summary", {})
    if public_supplements.qs_proxy(subject):
        alias_summary["QS"] = sorted(set(alias_summary.get("QS", []) + public_supplements.qs_proxy_aliases(subject)))
    arwu_aliases = public_supplements.arwu_public_aliases(subject)
    if arwu_aliases:
        alias_summary["软科"] = sorted(set(alias_summary.get("软科", []) + arwu_aliases))
    for source in ["软科", "QS", "US News", "THE"]:
        aliases = public_supplements.source_aliases(subject, source)
        if aliases:
            alias_summary[source] = sorted(set(alias_summary.get(source, []) + aliases))


def alias_keys(subject: dict[str, Any], source: str) -> set[str]:
    values = set(subject.get("alias_summary", {}).get(source, []))
    source_field = {
        "软科": "arwu_subject_name",
        "QS": "qs_subject_name",
        "US News": "usnews_subject_name",
        "THE": "the_subject_area",
    }.get(source, "")
    if source_field:
        values.add(clean_text(subject.get(source_field)))
    values.add(clean_text(subject.get("target_subject")))
    return {normalize_key(value) for value in values if public_supplements.valid_mapping_value(value)}


def source_latest_year(facts: pd.DataFrame, source: str) -> str:
    if facts.empty or "ranking_year" not in facts.columns:
        return ""
    rows = facts[(facts["ranking_source"] == source) & (facts.get("is_tongji", pd.Series(dtype=str)).astype(str).str.lower().isin(["true", "1"]))].copy()
    years = sorted(clean_text(value) for value in rows["ranking_year"].drop_duplicates().tolist() if clean_text(value))
    return years[-1] if years else ""


def source_has_ranking(facts: pd.DataFrame, subject: dict[str, Any], source: str, latest_only: bool = False) -> bool:
    keys = alias_keys(subject, source)
    if not keys or facts.empty:
        return False
    rows = facts[facts["ranking_source"] == source].copy()
    if latest_only:
        latest_year = source_latest_year(facts, source)
        if latest_year:
            rows = rows[rows.get("ranking_year", pd.Series(dtype=str)).map(clean_text) == latest_year].copy()
    raw_keys = rows.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key)
    norm_keys = rows.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key)
    tongji = rows.get("is_tongji", pd.Series(dtype=str)).astype(str).str.lower().isin(["true", "1"])
    return bool((tongji & (raw_keys.isin(keys) | norm_keys.isin(keys))).any())


def source_has_weight(weights: pd.DataFrame, subject: dict[str, Any], source: str) -> tuple[bool, str]:
    values = list(subject.get("alias_summary", {}).get(source, []))
    field = {
        "软科": "arwu_subject_name",
        "QS": "qs_subject_name",
        "US News": "usnews_subject_name",
        "THE": "the_subject_area",
    }.get(source, "")
    if field:
        values.insert(0, subject.get(field))
    if source == "QS":
        values = public_supplements.qs_proxy_aliases(subject) + values
    weight_rows = weights[weights["ranking_source"] == source].copy()
    weight_key_to_area = {
        normalize_key(value): value
        for value in weight_rows.get("ranking_subject_or_area", pd.Series(dtype=str)).drop_duplicates().tolist()
        if clean_text(value)
    }
    for value in values:
        text = public_supplements.valid_mapping_value(value)
        if normalize_key(text) in weight_key_to_area:
            return True, weight_key_to_area[normalize_key(text)]
    return False, ""


def build_arwu_external_key_index(arwu_public: pd.DataFrame, latest_only: bool = False) -> set[str]:
    if arwu_public.empty:
        return set()
    rows = arwu_public.copy()
    if latest_only and "ranking_year" in rows.columns:
        years = sorted(clean_text(value) for value in rows["ranking_year"].drop_duplicates().tolist() if clean_text(value))
        if years:
            rows = rows[rows["ranking_year"].map(clean_text) == years[-1]].copy()
    return {key for key in rows.get("arwu_subject_name_en", pd.Series(dtype=str)).map(normalize_ascii_key).tolist() if key}


def arwu_external_history_available(arwu_public_keys: set[str], subject: dict[str, Any]) -> bool:
    keys = {normalize_ascii_key(value) for value in public_supplements.arwu_public_aliases(subject)}
    for value in subject.get("alias_summary", {}).get("软科", []):
        if re.search(r"[A-Za-z]", clean_text(value)):
            keys.add(normalize_ascii_key(value))
    return bool(keys and (keys & arwu_public_keys))


def build_usnews_external_key_index(usnews_history: pd.DataFrame, latest_only: bool = False) -> set[str]:
    if usnews_history.empty:
        return set()
    rows = usnews_history.copy()
    if latest_only and "ranking_year" in rows.columns:
        years = sorted(clean_text(value) for value in rows["ranking_year"].drop_duplicates().tolist() if clean_text(value))
        if years:
            rows = rows[rows["ranking_year"].map(clean_text) == years[-1]].copy()
    keys = set(rows.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key))
    keys.update(rows.get("ranking_subject_en", pd.Series(dtype=str)).map(normalize_key))
    keys.update(rows.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key))
    return {key for key in keys if key}


def usnews_external_history_available(usnews_history_keys: set[str], subject: dict[str, Any]) -> bool:
    keys = alias_keys(subject, "US News")
    return bool(keys and (keys & usnews_history_keys))


def external_history_available(source: str, subject: dict[str, Any], arwu_keys: set[str], usnews_keys: set[str]) -> bool:
    if source == "软科":
        return arwu_external_history_available(arwu_keys, subject)
    if source == "US News":
        return usnews_external_history_available(usnews_keys, subject)
    return False


def build_report() -> dict[str, Any]:
    coverage = read_csv(COVERAGE_CSV)
    facts = read_csv(FACT_RANKING_CSV)
    weights = read_csv(FACT_WEIGHT_CSV)
    arwu_public = read_csv(ARWU_PUBLIC_CSV)
    usnews_history = read_csv(USNEWS_HISTORY_CSV)
    arwu_external_keys = build_arwu_external_key_index(arwu_public)
    usnews_external_keys = build_usnews_external_key_index(usnews_history)
    latest_arwu_external_keys = build_arwu_external_key_index(arwu_public, latest_only=True)
    latest_usnews_external_keys = build_usnews_external_key_index(usnews_history, latest_only=True)
    source_latest_years = {source: source_latest_year(facts, source) for source in ["软科", "QS", "US News", "THE"]}
    rows: list[dict[str, Any]] = []
    for _, coverage_row in coverage.iterrows():
        subject = subject_from_coverage(coverage_row)
        subject["alias_summary"] = load_alias_summary(clean_text(subject.get("subject_id")))
        original_qs_mapping = public_supplements.valid_mapping_value(subject.get("qs_subject_name"))
        original_arwu_mapping = public_supplements.valid_mapping_value(subject.get("arwu_subject_name"))
        add_public_aliases(subject)
        supplements = public_supplements.public_supplement_records(subject)
        for source in ["软科", "QS", "US News", "THE"]:
            has_ranking = source_has_ranking(facts, subject, source)
            has_latest_ranking = source_has_ranking(facts, subject, source, latest_only=True)
            has_external_history = external_history_available(source, subject, arwu_external_keys, usnews_external_keys)
            has_latest_external_history = external_history_available(source, subject, latest_arwu_external_keys, latest_usnews_external_keys)
            has_weight, matched_weight_area = source_has_weight(weights, subject, source)
            source_supplements = [row for row in supplements if row["ranking_source"] == source]
            rows.append(
                {
                    "ministry_subject_code": subject["target_subject_code"],
                    "subject_name": subject["target_subject"],
                    "ranking_source": source,
                    "original_mapping": clean_text(
                        {
                            "软科": subject.get("arwu_subject_name"),
                            "QS": subject.get("qs_subject_name"),
                            "US News": subject.get("usnews_subject_name"),
                            "THE": subject.get("the_subject_area"),
                        }.get(source)
                    ),
                    "original_direct_mapping_valid": bool(
                        {
                            "软科": original_arwu_mapping,
                            "QS": original_qs_mapping,
                            "US News": public_supplements.valid_mapping_value(subject.get("usnews_subject_name")),
                            "THE": public_supplements.valid_mapping_value(subject.get("the_subject_area")),
                        }.get(source)
                    ),
                    "supplement_subject_or_area": " | ".join(clean_text(row.get("subject_or_area")) for row in source_supplements),
                    "supplement_proxy_level": " | ".join(clean_text(row.get("proxy_level")) for row in source_supplements),
                    "requires_disclosure": any(bool(row.get("requires_disclosure")) for row in source_supplements),
                    "local_ranking_after_supplement": has_ranking,
                    "external_history_after_supplement": has_external_history,
                    "ranking_after_all_supplements": has_ranking or has_external_history,
                    "latest_source_year": source_latest_years.get(source, ""),
                    "latest_local_ranking_after_supplement": has_latest_ranking,
                    "latest_external_history_after_supplement": has_latest_external_history,
                    "latest_ranking_after_all_supplements": has_latest_ranking or has_latest_external_history,
                    "local_weight_after_supplement": has_weight,
                    "matched_weight_area": matched_weight_area,
                    "supplement_source_key": " | ".join(clean_text(row.get("source_key")) for row in source_supplements),
                }
            )
    plan = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plan_path = OUTPUT_DIR / "public_gap_supplement_plan.csv"
    plan.to_csv(plan_path, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": now_text(),
        "generation_subject_count": int(len(coverage)),
        "unique_ministry_subject_code_count": int(coverage["ministry_subject_code"].nunique()) if not coverage.empty else 0,
        "row_count": len(plan),
        "sources": public_supplements.load_public_supplements().get("public_sources", {}),
        "qs_original_missing_subjects": int(
            plan[(plan["ranking_source"] == "QS") & (~plan["original_direct_mapping_valid"])].shape[0]
        ),
        "qs_supplemented_subjects": int(
            plan[(plan["ranking_source"] == "QS") & (plan["supplement_subject_or_area"].astype(str).str.len() > 0)].shape[0]
        ),
        "arwu_public_alias_subjects": int(
            plan[(plan["ranking_source"] == "软科") & (plan["supplement_subject_or_area"].astype(str).str.len() > 0)].shape[0]
        ),
        "local_weight_available_after_supplement": int(plan[plan["local_weight_after_supplement"]].shape[0]),
        "local_ranking_available_after_supplement": int(plan[plan["local_ranking_after_supplement"]].shape[0]),
        "external_history_available_after_supplement": int(plan[plan["external_history_after_supplement"]].shape[0]),
        "ranking_available_after_all_supplements": int(plan[plan["ranking_after_all_supplements"]].shape[0]),
        "latest_local_ranking_available_after_supplement": int(plan[plan["latest_local_ranking_after_supplement"]].shape[0]),
        "latest_external_history_available_after_supplement": int(plan[plan["latest_external_history_after_supplement"]].shape[0]),
        "latest_ranking_available_after_all_supplements": int(plan[plan["latest_ranking_after_all_supplements"]].shape[0]),
    }
    (OUTPUT_DIR / "public_gap_supplement_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 49 学科公开来源补充报告",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- generation_subject_count: {summary['generation_subject_count']}",
        f"- unique_ministry_subject_code_count: {summary['unique_ministry_subject_code_count']}",
        f"- qs_original_missing_subjects: {summary['qs_original_missing_subjects']}",
        f"- qs_supplemented_subjects: {summary['qs_supplemented_subjects']}",
        f"- arwu_public_alias_subjects: {summary['arwu_public_alias_subjects']}",
        f"- local_weight_available_after_supplement: {summary['local_weight_available_after_supplement']}/{summary['row_count']}",
        f"- local_ranking_available_after_supplement: {summary['local_ranking_available_after_supplement']}/{summary['row_count']}",
        f"- external_history_available_after_supplement: {summary['external_history_available_after_supplement']}/{summary['row_count']}",
        f"- ranking_available_after_all_supplements: {summary['ranking_available_after_all_supplements']}/{summary['row_count']}",
        f"- latest_ranking_available_after_all_supplements: {summary['latest_ranking_available_after_all_supplements']}/{summary['row_count']}",
        "",
        "## 说明",
        "",
        "本报告只登记可复用的公开来源补充口径。close_subject_proxy 和 broad_faculty_proxy 进入 Word 时必须披露，不能写成目标学科直接排名。",
        "",
        f"- 结构化明细：{plan_path}",
    ]
    (OUTPUT_DIR / "public_gap_supplement_summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
