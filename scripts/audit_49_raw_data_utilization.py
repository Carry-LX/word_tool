from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import ranking_public_supplements as public_supplements
import verify_49_gaps_against_raw_excels as raw_verify


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
SQLITE_PATH = PROJECT_DIR / "processed" / "ranking.sqlite"
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


def alias_values(subject: dict[str, Any], source: str) -> list[str]:
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
    rows = []
    seen = set()
    for value in values:
        text = public_supplements.valid_mapping_value(value)
        key = normalize_key(text)
        if key and key not in seen:
            rows.append(text)
            seen.add(key)
    return sorted(rows, key=lambda value: (len(value), value), reverse=True)


def fact_tongji_rows(subject_id: str, source: str) -> pd.DataFrame:
    if not SQLITE_PATH.exists():
        return pd.DataFrame()
    query = """
    SELECT
      f.ranking_source,
      f.release_year,
      f.ranking_year,
      f.ranking_subject_raw,
      f.rank_raw,
      f.source_file,
      f.source_sheet,
      f.source_row,
      f.is_tongji
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
      AND f.ranking_source = ?
      AND lower(cast(f.is_tongji as text)) IN ('true', '1')
    """
    try:
        with sqlite3.connect(SQLITE_PATH) as conn:
            return pd.read_sql_query(query, conn, params=[subject_id, source]).fillna("")
    except Exception:
        return pd.DataFrame()


def scan_standard_raw_matches(subjects: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_row_cache = {source: raw_verify.load_source_tongji_rows(source) for source in RANKING_SOURCES}
    cache_summary = pd.DataFrame(
        [{"ranking_source": source, "raw_tongji_rows": len(df)} for source, df in source_row_cache.items()]
    )
    rows: list[dict[str, Any]] = []
    for subject in subjects:
        for source in RANKING_SOURCES:
            matches = raw_verify.scan_source_subject(source_row_cache[source], source, subject)
            fact_rows = fact_tongji_rows(subject["subject_id"], source)
            fact_years = sorted(pd.to_numeric(fact_rows.get("ranking_year", pd.Series(dtype=str)), errors="coerce").dropna().astype(int).unique().tolist())
            if not matches:
                rows.append(
                    {
                        "ministry_subject_code": subject["target_subject_code"],
                        "subject_name": subject["target_subject"],
                        "subject_id": subject["subject_id"],
                        "ranking_source": source,
                        "raw_match_status": "no_raw_tongji_alias_match",
                        "raw_match_rows": 0,
                        "file": "",
                        "sheet": "",
                        "matched_aliases": "",
                        "fact_tongji_rows": len(fact_rows),
                        "fact_ranking_years": ";".join(str(year) for year in fact_years),
                        "utilization_status": "ok_no_raw_match" if fact_rows.empty else "fact_exists_without_raw_scan_match",
                    }
                )
                continue
            for match in matches:
                utilization = "ok_fact_exists" if not fact_rows.empty else "covered_by_runtime_alias_supplement"
                rows.append(
                    {
                        "ministry_subject_code": subject["target_subject_code"],
                        "subject_name": subject["target_subject"],
                        "subject_id": subject["subject_id"],
                        "ranking_source": source,
                        "raw_match_status": "matched",
                        "raw_match_rows": match.get("raw_tongji_alias_rows", 0),
                        "file": match.get("file", ""),
                        "sheet": match.get("sheet", ""),
                        "matched_aliases": match.get("matched_aliases", ""),
                        "match_scope": match.get("match_scope", ""),
                        "subject_columns": match.get("subject_columns", ""),
                        "sample_subject_text": match.get("sample_subject_text", ""),
                        "fact_tongji_rows": len(fact_rows),
                        "fact_ranking_years": ";".join(str(year) for year in fact_years),
                        "utilization_status": utilization,
                    }
                )
    return pd.DataFrame(rows), cache_summary


def rank_year_columns(columns: list[Any]) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for column in columns:
        text = clean_text(column)
        match = re.search(r"(20\d{2}).*排名", text)
        if match:
            rows.append((text, int(match.group(1))))
    return rows


def scan_the_tongji_history(subjects: list[dict[str, Any]]) -> pd.DataFrame:
    paths = sorted(DATA_DIR.glob("*THE*2023-2026*.xlsx"))
    if not paths:
        return pd.DataFrame()
    try:
        history = pd.read_excel(paths[0], sheet_name="同济历史", dtype=str).fillna("")
    except Exception:
        return pd.DataFrame()
    if history.empty:
        return pd.DataFrame()
    area_col = "THE学科领域" if "THE学科领域" in history.columns else history.columns[0]
    year_cols = rank_year_columns(list(history.columns))
    rows: list[dict[str, Any]] = []
    for subject in subjects:
        aliases = alias_values(subject, "THE")
        alias_keys = {normalize_key(value) for value in aliases if normalize_key(value)}
        matched = history[history[area_col].map(normalize_key).isin(alias_keys)].copy()
        if matched.empty:
            continue
        fact_rows = fact_tongji_rows(subject["subject_id"], "THE")
        fact_years = set(pd.to_numeric(fact_rows.get("ranking_year", pd.Series(dtype=str)), errors="coerce").dropna().astype(int).tolist())
        for _, row in matched.iterrows():
            raw_years = []
            raw_values = []
            missing_years = []
            for column, year in year_cols:
                if year < 2023 or year > 2026:
                    continue
                value = clean_text(row.get(column))
                if not value or value in {"未进入", "滑落"}:
                    continue
                raw_years.append(year)
                raw_values.append(f"{year}:{value}")
                if year not in fact_years:
                    missing_years.append(year)
            rows.append(
                {
                    "ministry_subject_code": subject["target_subject_code"],
                    "subject_name": subject["target_subject"],
                    "subject_id": subject["subject_id"],
                    "ranking_source": "THE",
                    "file": paths[0].name,
                    "sheet": "同济历史",
                    "matched_area": clean_text(row.get(area_col)),
                    "matched_aliases": " | ".join(aliases[:12]),
                    "raw_years": ";".join(str(year) for year in raw_years),
                    "raw_values": " | ".join(raw_values),
                    "fact_years": ";".join(str(year) for year in sorted(fact_years)),
                    "missing_from_fact_years": ";".join(str(year) for year in missing_years),
                    "utilization_status": "covered_by_the_history_builder_supplement" if missing_years else "covered_by_fact",
                }
            )
    return pd.DataFrame(rows)


def write_outputs(
    standard: pd.DataFrame,
    cache_summary: pd.DataFrame,
    supplemental: pd.DataFrame,
) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    standard_path = OUTPUT_DIR / "subject_49_raw_standard_utilization.csv"
    cache_path = OUTPUT_DIR / "subject_49_raw_tongji_cache_summary.csv"
    supplemental_path = OUTPUT_DIR / "subject_49_tongji_dedicated_sheet_utilization.csv"
    issues_path = OUTPUT_DIR / "subject_49_raw_utilization_issues.csv"
    standard.to_csv(standard_path, index=False, encoding="utf-8-sig")
    cache_summary.to_csv(cache_path, index=False, encoding="utf-8-sig")
    supplemental.to_csv(supplemental_path, index=False, encoding="utf-8-sig")

    issue_parts = []
    if not standard.empty:
        issue_parts.append(
            standard[standard["utilization_status"].isin(["raw_match_not_in_fact_join"])].assign(issue_type="standard_raw_match_not_in_fact")
        )
    if not supplemental.empty:
        issue_parts.append(
            supplemental[supplemental["utilization_status"] == "supplement_needed"].assign(issue_type="dedicated_sheet_missing_years")
        )
    issues = pd.concat(issue_parts, ignore_index=True, sort=False) if issue_parts else pd.DataFrame()
    issues.to_csv(issues_path, index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "standard_rows": int(len(standard)),
        "standard_runtime_alias_supplement_count": int((standard.get("utilization_status", pd.Series(dtype=str)) == "covered_by_runtime_alias_supplement").sum()) if not standard.empty else 0,
        "standard_raw_match_not_in_fact_count": int((standard.get("utilization_status", pd.Series(dtype=str)) == "raw_match_not_in_fact_join").sum()) if not standard.empty else 0,
        "dedicated_sheet_rows": int(len(supplemental)),
        "dedicated_sheet_builder_supplement_count": int((supplemental.get("utilization_status", pd.Series(dtype=str)) == "covered_by_the_history_builder_supplement").sum()) if not supplemental.empty else 0,
        "dedicated_sheet_supplement_needed_count": int((supplemental.get("utilization_status", pd.Series(dtype=str)) == "supplement_needed").sum()) if not supplemental.empty else 0,
        "issue_rows": int(len(issues)),
        "standard_csv": str(standard_path),
        "cache_summary_csv": str(cache_path),
        "dedicated_sheet_csv": str(supplemental_path),
        "issues_csv": str(issues_path),
    }
    (OUTPUT_DIR / "subject_49_raw_data_utilization_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 49 学科原始数据利用审计",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- standard_rows: {summary['standard_rows']}",
        f"- standard_runtime_alias_supplement_count: {summary['standard_runtime_alias_supplement_count']}",
        f"- standard_raw_match_not_in_fact_count: {summary['standard_raw_match_not_in_fact_count']}",
        f"- dedicated_sheet_rows: {summary['dedicated_sheet_rows']}",
        f"- dedicated_sheet_builder_supplement_count: {summary['dedicated_sheet_builder_supplement_count']}",
        f"- dedicated_sheet_supplement_needed_count: {summary['dedicated_sheet_supplement_needed_count']}",
        f"- issue_rows: {summary['issue_rows']}",
        f"- standard_csv: {standard_path}",
        f"- dedicated_sheet_csv: {supplemental_path}",
        f"- issues_csv: {issues_path}",
    ]
    (OUTPUT_DIR / "subject_49_raw_data_utilization_summary.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )
    return summary


def audit() -> dict[str, Any]:
    coverage = read_csv(COVERAGE_CSV)
    aliases = read_csv(DIM_ALIAS_CSV)
    subjects = []
    for _, row in coverage.iterrows():
        subject = subject_from_row(row)
        subject["alias_summary"] = load_alias_summary(aliases, subject)
        subjects.append(subject)
    standard, cache_summary = scan_standard_raw_matches(subjects)
    supplemental = scan_the_tongji_history(subjects)
    summary = write_outputs(standard, cache_summary, supplemental)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    audit()
