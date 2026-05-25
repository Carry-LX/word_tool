from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
LINEAGE_DIR = PROJECT_DIR / "outputs" / "subject_49_full_lineage_audit"
DATA_AUDIT_DIR = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit"
PUBLIC_PLAN_CSV = PROJECT_DIR / "outputs" / "public_gap_supplements" / "public_gap_supplement_plan.csv"
FACT_RANKING_CSV = PROJECT_DIR / "processed" / "fact_ranking.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "missing_data_lineage_review"

SUBJECT_MATRIX_CSV = LINEAGE_DIR / "subject_49_full_lineage_subject_matrix.csv"
SOURCE_MATRIX_CSV = LINEAGE_DIR / "subject_49_full_lineage_source_matrix.csv"
RAW_UTIL_ISSUES_CSV = DATA_AUDIT_DIR / "subject_49_raw_utilization_issues.csv"


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


def bool_value(value: Any) -> bool:
    return clean_text(value).lower() in {"true", "1", "yes"}


def int_value(value: Any) -> int:
    try:
        text = clean_text(value)
        return int(float(text)) if text else 0
    except (TypeError, ValueError):
        return 0


def split_aliases(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [item.strip() for item in text.split(" | ") if item.strip()]


def source_latest_years(facts: pd.DataFrame) -> dict[str, str]:
    if facts.empty or "ranking_year" not in facts.columns:
        return {}
    rows = facts.copy()
    rows["_year_num"] = pd.to_numeric(rows["ranking_year"], errors="coerce")
    latest: dict[str, str] = {}
    for source, group in rows.groupby("ranking_source", dropna=False):
        years = group["_year_num"].dropna()
        if years.empty:
            continue
        latest[clean_text(source)] = str(int(years.max()))
    return latest


def build_alias_lookup(alias_df: pd.DataFrame) -> dict[tuple[str, str], set[str]]:
    lookup: dict[tuple[str, str], set[str]] = {}
    if alias_df.empty:
        return lookup
    for _, row in alias_df.iterrows():
        subject_id = clean_text(row.get("subject_id"))
        source = clean_text(row.get("ranking_source"))
        raw_alias = clean_text(row.get("ranking_subject_alias"))
        norm_alias = clean_text(row.get("ranking_subject_norm"))
        for alias in {raw_alias, norm_alias}:
            key = normalize_key(alias)
            if subject_id and source and key:
                lookup.setdefault((subject_id, source), set()).add(key)
    return lookup


def subject_source_fact_rows(
    facts: pd.DataFrame,
    alias_lookup: dict[tuple[str, str], set[str]],
    subject_id: str,
    source: str,
    aliases_text: str,
) -> pd.DataFrame:
    if facts.empty:
        return pd.DataFrame()
    keys = set(alias_lookup.get((subject_id, source), set()))
    keys.update(normalize_key(value) for value in split_aliases(aliases_text))
    keys = {key for key in keys if key}
    if not keys:
        return pd.DataFrame()
    rows = facts[facts["ranking_source"].map(clean_text) == source].copy()
    if rows.empty:
        return rows
    tongji = rows.get("is_tongji", pd.Series(dtype=str)).astype(str).str.lower().isin(["true", "1"])
    raw_keys = rows.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_key)
    norm_keys = rows.get("ranking_subject_norm", pd.Series(dtype=str)).map(normalize_key)
    return rows[tongji & (raw_keys.isin(keys) | norm_keys.isin(keys))].copy()


def classify_ranking_gap(row: pd.Series, local_rows: pd.DataFrame, latest_year: str) -> str:
    if bool_value(row.get("final_ranking_ready")):
        return "ready"
    raw_rows = int_value(row.get("raw_standard_matched_rows"))
    local_count = len(local_rows)
    latest_count = 0
    if latest_year and not local_rows.empty:
        latest_count = int((local_rows.get("ranking_year", pd.Series(dtype=str)).map(clean_text) == latest_year).sum())
    if latest_count > 0:
        return "pipeline_issue_latest_fact_not_used"
    if local_count > 0:
        return "latest_year_gap_has_history"
    if raw_rows > 0:
        return "pipeline_issue_raw_match_not_in_fact"
    diagnosis = clean_text(row.get("mapping_diagnosis"))
    if diagnosis in {"no_local_weight_or_ranking_fact", "weight_only_no_local_ranking_fact"}:
        return "confirmed_no_raw_or_local_tongji_ranking"
    return "needs_manual_review"


def classify_weight_gap(row: pd.Series) -> str:
    if bool_value(row.get("final_weight_ready")):
        return "ready"
    weight_rows = int_value(row.get("weight_rows_by_runtime_alias"))
    if weight_rows > 0:
        return "pipeline_issue_weight_rows_not_used"
    return "confirmed_no_weight_mapping"


def classify_indicator_gap(row: pd.Series) -> str:
    if bool_value(row.get("final_indicator_ready")):
        return "ready"
    if not bool_value(row.get("final_ranking_ready")):
        return "blocked_by_missing_latest_ranking_or_alias"
    return "indicator_source_missing"


def build_subject_priority(subjects: pd.DataFrame) -> pd.DataFrame:
    if subjects.empty:
        return pd.DataFrame()
    rows = subjects.copy()
    for column in [
        "ranking_ready_count",
        "weight_ready_count",
        "indicator_ready_count",
        "requires_disclosure_count",
        "public_supplement_count",
    ]:
        rows[column] = rows.get(column, pd.Series(dtype=str)).map(int_value)
    rows["missing_score"] = (
        (4 - rows["ranking_ready_count"]) * 3
        + (4 - rows["indicator_ready_count"]) * 2
        + (4 - rows["weight_ready_count"])
        + rows["requires_disclosure_count"]
    )
    rows["review_priority"] = "low"
    rows.loc[~rows.get("usable_partial_sources", "").map(bool_value), "review_priority"] = "critical"
    rows.loc[(rows["review_priority"] == "low") & (rows["missing_score"] >= 12), "review_priority"] = "high"
    rows.loc[(rows["review_priority"] == "low") & (rows["missing_score"] >= 7), "review_priority"] = "medium"
    sort_cols = ["review_priority", "missing_score", "ranking_ready_count"]
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows["_priority_order"] = rows["review_priority"].map(priority_order).fillna(9)
    return rows.sort_values(["_priority_order", "missing_score", "ranking_ready_count"], ascending=[True, False, True]).drop(columns=["_priority_order"])


def build_review() -> dict[str, Any]:
    subjects = read_csv(SUBJECT_MATRIX_CSV)
    sources = read_csv(SOURCE_MATRIX_CSV)
    raw_issues = read_csv(RAW_UTIL_ISSUES_CSV)
    facts = read_csv(FACT_RANKING_CSV)
    aliases = read_csv(DIM_ALIAS_CSV)
    public_plan = read_csv(PUBLIC_PLAN_CSV)

    latest_by_source = source_latest_years(facts)
    alias_lookup = build_alias_lookup(aliases)
    source_rows: list[dict[str, Any]] = []
    for _, row in sources.iterrows():
        subject_id = ""
        code = clean_text(row.get("ministry_subject_code")).zfill(4)
        if not public_plan.empty:
            matches = public_plan[
                (public_plan["ministry_subject_code"].astype(str).str.zfill(4) == code)
                & (public_plan["subject_name"].map(clean_text) == clean_text(row.get("subject_name")))
            ]
            if not matches.empty:
                # subject_id is not stored in the plan; keep lookup from dim aliases by code-like suffix when possible.
                pass
        if not aliases.empty:
            candidates = aliases[aliases["subject_id"].astype(str).str.endswith("_" + code)]
            if not candidates.empty:
                subject_id = clean_text(candidates["subject_id"].iloc[0])
        source = clean_text(row.get("ranking_source"))
        local_rows = subject_source_fact_rows(facts, alias_lookup, subject_id, source, clean_text(row.get("alias_values")))
        years = sorted({clean_text(value) for value in local_rows.get("ranking_year", pd.Series(dtype=str)).tolist() if clean_text(value)})
        latest_year = latest_by_source.get(source, "")
        latest_count = int((local_rows.get("ranking_year", pd.Series(dtype=str)).map(clean_text) == latest_year).sum()) if latest_year and not local_rows.empty else 0
        review = dict(row)
        review.update(
            {
                "subject_id_inferred": subject_id,
                "source_latest_year": latest_year,
                "local_fact_years_by_alias": ";".join(years),
                "local_fact_rows_by_alias": len(local_rows),
                "latest_local_fact_rows_by_alias": latest_count,
                "ranking_gap_class": classify_ranking_gap(row, local_rows, latest_year),
                "weight_gap_class": classify_weight_gap(row),
                "indicator_gap_class": classify_indicator_gap(row),
            }
        )
        source_rows.append(review)

    source_review = pd.DataFrame(source_rows)
    subject_priority = build_subject_priority(subjects)
    potential_issues = source_review[
        source_review["ranking_gap_class"].astype(str).str.startswith("pipeline_issue_")
        | source_review["weight_gap_class"].astype(str).str.startswith("pipeline_issue_")
    ].copy()
    true_ranking_gaps = source_review[
        source_review["ranking_gap_class"].isin(
            [
                "confirmed_no_raw_or_local_tongji_ranking",
                "latest_year_gap_has_history",
            ]
        )
    ].copy()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    subject_path = OUTPUT_DIR / "missing_data_subject_priority.csv"
    source_path = OUTPUT_DIR / "source_gap_lineage_review.csv"
    issues_path = OUTPUT_DIR / "potential_pipeline_issues.csv"
    true_gap_path = OUTPUT_DIR / "confirmed_or_latest_gap_rows.csv"
    subject_priority.to_csv(subject_path, index=False, encoding="utf-8-sig")
    source_review.to_csv(source_path, index=False, encoding="utf-8-sig")
    potential_issues.to_csv(issues_path, index=False, encoding="utf-8-sig")
    true_ranking_gaps.to_csv(true_gap_path, index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "inputs": {
            "subject_matrix": str(SUBJECT_MATRIX_CSV),
            "source_matrix": str(SOURCE_MATRIX_CSV),
            "fact_ranking_csv": str(FACT_RANKING_CSV),
            "public_plan_csv": str(PUBLIC_PLAN_CSV),
        },
        "subject_count": int(len(subject_priority)),
        "critical_subject_count": int((subject_priority["review_priority"] == "critical").sum()) if not subject_priority.empty else 0,
        "high_subject_count": int((subject_priority["review_priority"] == "high").sum()) if not subject_priority.empty else 0,
        "medium_subject_count": int((subject_priority["review_priority"] == "medium").sum()) if not subject_priority.empty else 0,
        "ranking_gap_class_counts": source_review["ranking_gap_class"].value_counts().astype(int).to_dict() if not source_review.empty else {},
        "weight_gap_class_counts": source_review["weight_gap_class"].value_counts().astype(int).to_dict() if not source_review.empty else {},
        "indicator_gap_class_counts": source_review["indicator_gap_class"].value_counts().astype(int).to_dict() if not source_review.empty else {},
        "potential_pipeline_issue_count": int(len(potential_issues)),
        "raw_utilization_issue_count": int(len(raw_issues)),
        "source_latest_years": latest_by_source,
        "outputs": {
            "subject_priority_csv": str(subject_path),
            "source_gap_lineage_csv": str(source_path),
            "potential_pipeline_issues_csv": str(issues_path),
            "confirmed_or_latest_gap_rows_csv": str(true_gap_path),
        },
    }
    summary_path = OUTPUT_DIR / "missing_data_lineage_review_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    lines = [
        "# Missing Data Lineage Review",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- subject_count: {summary['subject_count']}",
        f"- critical_subject_count: {summary['critical_subject_count']}",
        f"- high_subject_count: {summary['high_subject_count']}",
        f"- potential_pipeline_issue_count: {summary['potential_pipeline_issue_count']}",
        f"- raw_utilization_issue_count: {summary['raw_utilization_issue_count']}",
        "",
        "## Ranking Gap Classes",
        "",
        *[f"- {key}: {value}" for key, value in summary["ranking_gap_class_counts"].items()],
        "",
        "## Outputs",
        "",
        *[f"- {key}: {value}" for key, value in summary["outputs"].items()],
    ]
    (OUTPUT_DIR / "missing_data_lineage_review_summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    build_review()
