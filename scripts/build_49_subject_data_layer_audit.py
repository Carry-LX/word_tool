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
PUBLIC_PLAN_CSV = PROJECT_DIR / "outputs" / "public_gap_supplements" / "public_gap_supplement_plan.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
FACT_INDICATOR_CSV = PROJECT_DIR / "processed" / "fact_ranking_indicator.csv"
WOS_CSV = PROJECT_DIR / "external_data" / "processed" / "wos_37_university_subject_paper_metrics_20260511.csv"
CWTS_CSV = PROJECT_DIR / "external_data" / "processed" / "cwts_subject_field_crosswalk.csv"
ARWU_PUBLIC_CSV = PROJECT_DIR / "external_data" / "processed" / "arwu_gras_public_tongji_history_2023_2025_long.csv"
USNEWS_HISTORY_CSV = PROJECT_DIR / "external_data" / "processed" / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit"
RANKING_SOURCES = ["软科", "QS", "US News", "THE"]


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


def subject_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "subject_id": clean_text(row.get("subject_id")),
        "target_subject": clean_text(row.get("source_subject_name") or row.get("ministry_subject_name")),
        "target_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
        "ministry_subject_name": clean_text(row.get("ministry_subject_name")),
        "ministry_category_name": clean_text(row.get("ministry_category_name")),
        "arwu_subject_name": clean_text(row.get("arwu_mapping")),
        "qs_subject_name": clean_text(row.get("qs_mapping")),
        "usnews_subject_name": clean_text(row.get("usnews_mapping")),
        "the_subject_area": clean_text(row.get("the_mapping")),
        "alias_summary": {},
    }


def load_alias_summary(alias_df: pd.DataFrame, subject: dict[str, Any]) -> dict[str, list[str]]:
    rows = alias_df[alias_df["subject_id"] == subject["subject_id"]].copy() if not alias_df.empty else pd.DataFrame()
    summary: dict[str, list[str]] = {}
    if not rows.empty:
        for source, group in rows.groupby("ranking_source"):
            values = sorted({clean_text(value) for value in group["ranking_subject_alias"].tolist() if clean_text(value)})
            if values:
                summary[clean_text(source)] = values
    if public_supplements.qs_proxy(subject):
        summary["QS"] = sorted(set(summary.get("QS", []) + public_supplements.qs_proxy_aliases(subject)))
    arwu_aliases = public_supplements.arwu_public_aliases(subject)
    if arwu_aliases:
        summary["软科"] = sorted(set(summary.get("软科", []) + arwu_aliases))
    for source in RANKING_SOURCES:
        aliases = public_supplements.source_aliases(subject, source)
        if aliases:
            summary[source] = sorted(set(summary.get(source, []) + aliases))
    return summary


def subject_source_keys(subject: dict[str, Any], source: str) -> set[str]:
    field = {
        "软科": "arwu_subject_name",
        "QS": "qs_subject_name",
        "US News": "usnews_subject_name",
        "THE": "the_subject_area",
    }.get(source, "")
    values = set(subject.get("alias_summary", {}).get(source, []))
    values.add(subject.get("target_subject", ""))
    if field:
        values.add(subject.get(field, ""))
    return {normalize_key(value) for value in values if public_supplements.valid_mapping_value(value)}


def build_indicator_key_index(indicators: pd.DataFrame) -> dict[str, set[str]]:
    if indicators.empty:
        return {}
    index: dict[str, set[str]] = {}
    tongji_rows = indicators[indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    for source in RANKING_SOURCES:
        rows = tongji_rows[tongji_rows["ranking_source"] == source].copy()
        keys = set(rows.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key))
        keys.update(rows.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key))
        index[source] = {key for key in keys if key}
    return index


def indicator_source_available(indicator_index: dict[str, set[str]], subject: dict[str, Any], source: str) -> bool:
    keys = subject_source_keys(subject, source)
    if not keys:
        return False
    return bool(keys & indicator_index.get(source, set()))


def build_arwu_public_key_index(arwu_public: pd.DataFrame) -> set[str]:
    if arwu_public.empty:
        return set()
    return {key for key in arwu_public["arwu_subject_name_en"].map(normalize_ascii_key).tolist() if key}


def arwu_public_history_available(arwu_public_keys: set[str], subject: dict[str, Any]) -> bool:
    keys = {normalize_ascii_key(value) for value in public_supplements.arwu_public_aliases(subject)}
    for value in subject.get("alias_summary", {}).get("软科", []):
        if re.search(r"[A-Za-z]", clean_text(value)):
            keys.add(normalize_ascii_key(value))
    if not keys:
        return False
    return bool(keys & arwu_public_keys)


def build_usnews_history_key_index(usnews_history: pd.DataFrame) -> set[str]:
    if usnews_history.empty:
        return set()
    keys = set(usnews_history.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key))
    keys.update(usnews_history.get("ranking_subject_en", pd.Series(dtype=str)).map(normalize_key))
    keys.update(usnews_history.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key))
    return {key for key in keys if key}


def usnews_external_history_available(usnews_history_keys: set[str], subject: dict[str, Any]) -> bool:
    keys = subject_source_keys(subject, "US News")
    if not keys:
        return False
    return bool(keys & usnews_history_keys)


def bool_text(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def plan_bool(plan_rows: pd.DataFrame, source: str, column: str) -> bool:
    rows = plan_rows[plan_rows["ranking_source"] == source]
    if rows.empty or column not in rows.columns:
        return False
    return bool_text(rows[column].iloc[0])


def build_audit() -> dict[str, Any]:
    coverage = read_csv(COVERAGE_CSV)
    public_plan = read_csv(PUBLIC_PLAN_CSV)
    alias_df = read_csv(DIM_ALIAS_CSV)
    indicators = read_csv(FACT_INDICATOR_CSV)
    wos = read_csv(WOS_CSV)
    cwts = read_csv(CWTS_CSV)
    arwu_public = read_csv(ARWU_PUBLIC_CSV)
    usnews_history = read_csv(USNEWS_HISTORY_CSV)
    indicator_index = build_indicator_key_index(indicators)
    arwu_public_keys = build_arwu_public_key_index(arwu_public)
    usnews_history_keys = build_usnews_history_key_index(usnews_history)
    rows: list[dict[str, Any]] = []
    for _, coverage_row in coverage.iterrows():
        subject = subject_from_row(coverage_row)
        subject["alias_summary"] = load_alias_summary(alias_df, subject)
        code = subject["target_subject_code"]
        plan_rows = public_plan[
            (public_plan["ministry_subject_code"].astype(str).str.zfill(4) == code)
            & (public_plan["subject_name"].astype(str).map(clean_text) == subject["target_subject"])
        ].copy()
        if plan_rows.empty:
            plan_rows = public_plan[public_plan["ministry_subject_code"].astype(str).str.zfill(4) == code].copy()
        ranking_ready = {
            source: plan_bool(plan_rows, source, "latest_ranking_after_all_supplements")
            or (
                "latest_ranking_after_all_supplements" not in public_plan.columns
                and (
                    plan_bool(plan_rows, source, "ranking_after_all_supplements")
                    or plan_bool(plan_rows, source, "local_ranking_after_supplement")
                )
            )
            for source in RANKING_SOURCES
        }
        weight_ready = {
            source: plan_bool(plan_rows, source, "local_weight_after_supplement")
            for source in RANKING_SOURCES
        }
        indicator_ready = {source: indicator_source_available(indicator_index, subject, source) for source in RANKING_SOURCES}
        wos_rows = 0
        if not wos.empty and "ministry_subject_code" in wos.columns:
            wos_rows = len(wos[wos["ministry_subject_code"].astype(str).str.zfill(4) == code])
        cwts_row = pd.DataFrame()
        if not cwts.empty and "ministry_subject_code" in cwts.columns:
            cwts_row = cwts[cwts["ministry_subject_code"].astype(str).str.zfill(4) == code].copy()
        supplements = public_supplements.public_supplement_records(subject)
        rows.append(
            {
                "ministry_subject_code": code,
                "subject_name": subject["target_subject"],
                "ranking_ready_count": sum(ranking_ready.values()),
                "ranking_ready_sources": ";".join(source for source, ok in ranking_ready.items() if ok),
                "weight_ready_count": sum(weight_ready.values()),
                "weight_ready_sources": ";".join(source for source, ok in weight_ready.items() if ok),
                "indicator_ready_count": sum(indicator_ready.values()),
                "indicator_ready_sources": ";".join(source for source, ok in indicator_ready.items() if ok),
                "wos_subject_rows": wos_rows,
                "wos_available": wos_rows > 0,
                "cwts_available": not cwts_row.empty and bool_text(cwts_row.iloc[0].get("tongji_has_field_record", "")),
                "cwts_field": clean_text(cwts_row.iloc[0].get("cwts_field", "")) if not cwts_row.empty else "",
                "arwu_public_history_available": arwu_public_history_available(arwu_public_keys, subject),
                "usnews_external_history_available": usnews_external_history_available(usnews_history_keys, subject),
                "public_supplement_count": len(supplements),
                "requires_disclosure_count": sum(1 for row in supplements if row.get("requires_disclosure")),
                "remaining_missing_ranking_sources": ";".join(source for source, ok in ranking_ready.items() if not ok),
                "remaining_missing_weight_sources": ";".join(source for source, ok in weight_ready.items() if not ok),
                "remaining_missing_indicator_sources": ";".join(source for source, ok in indicator_ready.items() if not ok),
            }
        )
    audit = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = OUTPUT_DIR / "subject_49_data_layer_audit.csv"
    audit.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": now_text(),
        "generation_subject_count": len(audit),
        "all_four_ranking_ready_count": int((audit["ranking_ready_count"] == 4).sum()),
        "all_four_weight_ready_count": int((audit["weight_ready_count"] == 4).sum()),
        "all_four_indicator_ready_count": int((audit["indicator_ready_count"] == 4).sum()),
        "wos_available_count": int(audit["wos_available"].sum()),
        "cwts_available_count": int(audit["cwts_available"].sum()),
        "arwu_public_history_available_count": int(audit["arwu_public_history_available"].sum()),
        "usnews_external_history_available_count": int(audit["usnews_external_history_available"].sum()),
        "subjects_with_public_supplement_count": int((audit["public_supplement_count"] > 0).sum()),
        "subjects_requiring_disclosure_count": int((audit["requires_disclosure_count"] > 0).sum()),
        "detail_csv": str(detail_path),
    }
    (OUTPUT_DIR / "subject_49_data_layer_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 49 学科数据层体检",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- all_four_ranking_ready_count: {summary['all_four_ranking_ready_count']}/{summary['generation_subject_count']}",
        f"- all_four_weight_ready_count: {summary['all_four_weight_ready_count']}/{summary['generation_subject_count']}",
        f"- all_four_indicator_ready_count: {summary['all_four_indicator_ready_count']}/{summary['generation_subject_count']}",
        f"- wos_available_count: {summary['wos_available_count']}/{summary['generation_subject_count']}",
        f"- cwts_available_count: {summary['cwts_available_count']}/{summary['generation_subject_count']}",
        f"- arwu_public_history_available_count: {summary['arwu_public_history_available_count']}/{summary['generation_subject_count']}",
        f"- usnews_external_history_available_count: {summary['usnews_external_history_available_count']}/{summary['generation_subject_count']}",
        f"- subjects_with_public_supplement_count: {summary['subjects_with_public_supplement_count']}/{summary['generation_subject_count']}",
        f"- subjects_requiring_disclosure_count: {summary['subjects_requiring_disclosure_count']}/{summary['generation_subject_count']}",
        "",
        f"- 明细：{detail_path}",
    ]
    (OUTPUT_DIR / "subject_49_data_layer_audit_summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    build_audit()
