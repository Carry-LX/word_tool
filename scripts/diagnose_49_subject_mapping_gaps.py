from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import ranking_public_supplements as public_supplements


PROJECT_DIR = Path(__file__).resolve().parent.parent
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
FACT_RANKING_CSV = PROJECT_DIR / "processed" / "fact_ranking.csv"
FACT_WEIGHT_CSV = PROJECT_DIR / "processed" / "fact_indicator_weight.csv"
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


def alias_values(subject: dict[str, Any], source: str) -> set[str]:
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
    return {value for value in values if public_supplements.valid_mapping_value(value)}


def latest_tongji_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rows = df[df["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    if rows.empty:
        return rows
    rows["release_year_num"] = pd.to_numeric(rows.get("release_year", ""), errors="coerce")
    rows["ranking_year_num"] = pd.to_numeric(rows.get("ranking_year", ""), errors="coerce")
    latest_release = rows["release_year_num"].max()
    rows = rows[rows["release_year_num"] == latest_release].copy()
    latest_ranking = rows["ranking_year_num"].max()
    return rows[rows["ranking_year_num"] == latest_ranking].copy()


def sqlite_join_count(subject_id: str, source: str) -> tuple[int, str]:
    if not SQLITE_PATH.exists():
        return 0, ""
    query = """
    SELECT f.ranking_subject_raw, f.ranking_year, f.release_year, f.rank_raw, f.is_tongji
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
            df = pd.read_sql_query(query, conn, params=[subject_id, source]).fillna("")
    except Exception:
        return 0, ""
    latest = latest_tongji_rows(df)
    subjects = ";".join(sorted(latest.get("ranking_subject_raw", pd.Series(dtype=str)).drop_duplicates().tolist())[:6])
    return len(latest), subjects


def diagnose() -> dict[str, Any]:
    coverage = read_csv(COVERAGE_CSV)
    aliases = read_csv(DIM_ALIAS_CSV)
    facts = read_csv(FACT_RANKING_CSV)
    weights = read_csv(FACT_WEIGHT_CSV)
    facts["_raw_key"] = facts.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key)
    facts["_norm_key"] = facts.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key)
    rows: list[dict[str, Any]] = []
    for _, coverage_row in coverage.iterrows():
        subject = subject_from_row(coverage_row)
        subject["alias_summary"] = load_alias_summary(aliases, subject)
        for source in RANKING_SOURCES:
            values = alias_values(subject, source)
            keys = {normalize_key(value) for value in values if normalize_key(value)}
            source_facts = facts[facts["ranking_source"] == source].copy()
            by_subject_id = latest_tongji_rows(source_facts[source_facts["subject_id"] == subject["subject_id"]].copy())
            by_alias = latest_tongji_rows(source_facts[source_facts["_raw_key"].isin(keys) | source_facts["_norm_key"].isin(keys)].copy())
            sqlite_count, sqlite_subjects = sqlite_join_count(subject["subject_id"], source)
            weight_rows = pd.DataFrame()
            if not weights.empty:
                weight_keys = weights[weights["ranking_source"] == source].get("ranking_subject_or_area", pd.Series(dtype=str)).map(normalize_key)
                weight_rows = weights[(weights["ranking_source"] == source) & weight_keys.isin(keys)].copy()
            if len(by_subject_id) > 0 and len(by_alias) == 0:
                diagnosis = "subject_id_fact_alias_miss"
            elif len(by_alias) > 0 and sqlite_count == 0:
                diagnosis = "runtime_alias_recovers_local_fact"
            elif len(weight_rows) > 0 and len(by_alias) == 0:
                diagnosis = "weight_only_no_local_ranking_fact"
            elif len(weight_rows) == 0 and len(by_alias) == 0:
                diagnosis = "no_local_weight_or_ranking_fact"
            else:
                diagnosis = "ok"
            rows.append(
                {
                    "ministry_subject_code": subject["target_subject_code"],
                    "subject_name": subject["target_subject"],
                    "subject_id": subject["subject_id"],
                    "ranking_source": source,
                    "alias_values": " | ".join(sorted(values)[:14]),
                    "fact_tongji_latest_by_subject_id": len(by_subject_id),
                    "fact_tongji_latest_by_runtime_alias": len(by_alias),
                    "sqlite_join_latest_tongji_rows": sqlite_count,
                    "weight_rows_by_runtime_alias": len(weight_rows),
                    "subject_id_subjects": ";".join(sorted(by_subject_id.get("ranking_subject_raw", pd.Series(dtype=str)).drop_duplicates().tolist())[:6]),
                    "runtime_alias_subjects": ";".join(sorted(by_alias.get("ranking_subject_raw", pd.Series(dtype=str)).drop_duplicates().tolist())[:6]),
                    "sqlite_join_subjects": sqlite_subjects,
                    "diagnosis": diagnosis,
                }
            )
    out = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = OUTPUT_DIR / "subject_49_mapping_gap_diagnostics.csv"
    out.to_csv(detail_path, index=False, encoding="utf-8-sig")
    issue_rows = out[out["diagnosis"].isin(["subject_id_fact_alias_miss"])].copy()
    runtime_recovery_rows = out[out["diagnosis"].isin(["runtime_alias_recovers_local_fact"])].copy()
    issue_path = OUTPUT_DIR / "subject_49_possible_mapping_issues.csv"
    issue_rows.to_csv(issue_path, index=False, encoding="utf-8-sig")
    runtime_recovery_path = OUTPUT_DIR / "subject_49_runtime_alias_recoveries.csv"
    runtime_recovery_rows.to_csv(runtime_recovery_path, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": now_text(),
        "row_count": len(out),
        "mapping_related_issue_count": len(issue_rows),
        "runtime_alias_recovery_count": len(runtime_recovery_rows),
        "detail_csv": str(detail_path),
        "mapping_related_issue_csv": str(issue_path),
        "runtime_alias_recovery_csv": str(runtime_recovery_path),
        "diagnosis_breakdown": out.groupby("diagnosis").size().to_dict(),
        "mapping_issue_breakdown": issue_rows.groupby("ranking_source").size().to_dict() if not issue_rows.empty else {},
        "runtime_alias_recovery_breakdown": runtime_recovery_rows.groupby("ranking_source").size().to_dict() if not runtime_recovery_rows.empty else {},
    }
    (OUTPUT_DIR / "subject_49_mapping_gap_diagnostics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 49 学科映射缺口诊断",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- row_count: {summary['row_count']}",
        f"- mapping_related_issue_count: {summary['mapping_related_issue_count']}",
        f"- runtime_alias_recovery_count: {summary['runtime_alias_recovery_count']}",
        f"- detail_csv: {detail_path}",
        f"- mapping_related_issue_csv: {issue_path}",
        f"- runtime_alias_recovery_csv: {runtime_recovery_path}",
        "",
        "## 诊断分类",
        "",
    ]
    for key, value in summary["diagnosis_breakdown"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 映射相关问题来源分布", ""])
    for key, value in summary["mapping_issue_breakdown"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 运行时别名补充恢复来源分布", ""])
    for key, value in summary["runtime_alias_recovery_breakdown"].items():
        lines.append(f"- {key}: {value}")
    (OUTPUT_DIR / "subject_49_mapping_gap_diagnostics_summary.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    diagnose()
