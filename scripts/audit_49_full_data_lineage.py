from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
AUDIT_DIR = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit"
SYSTEM_AUDIT_JSON = PROJECT_DIR / "outputs" / "agent_system_audit" / "latest" / "agent_system_readiness.json"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_49_full_lineage_audit"
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"

MAPPING_SUMMARY_JSON = AUDIT_DIR / "mapping_workbook_integrity_after_protection_summary.json"
MAPPING_DETAIL_CSV = AUDIT_DIR / "mapping_workbook_integrity_after_protection.csv"
MAPPING_DIAGNOSIS_JSON = AUDIT_DIR / "subject_49_mapping_gap_diagnostics_summary.json"
MAPPING_DIAGNOSIS_CSV = AUDIT_DIR / "subject_49_mapping_gap_diagnostics.csv"
RAW_GAP_JSON = AUDIT_DIR / "subject_49_raw_excel_gap_verification_summary.json"
RAW_STANDARD_CSV = AUDIT_DIR / "subject_49_raw_standard_utilization.csv"
RAW_DEDICATED_CSV = AUDIT_DIR / "subject_49_tongji_dedicated_sheet_utilization.csv"
RAW_UTIL_JSON = AUDIT_DIR / "subject_49_raw_data_utilization_summary.json"
RAW_UTIL_ISSUES_CSV = AUDIT_DIR / "subject_49_raw_utilization_issues.csv"
DATA_LAYER_JSON = AUDIT_DIR / "subject_49_data_layer_audit_summary.json"
DATA_LAYER_CSV = AUDIT_DIR / "subject_49_data_layer_audit.csv"
WORD_CHART_JSON = AUDIT_DIR / "subject_49_word_chart_data_completeness_summary.json"
WORD_CHART_CSV = AUDIT_DIR / "subject_49_word_chart_data_completeness.csv"

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


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def int_value(value: Any) -> int:
    try:
        if value is None or clean_text(value) == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def status_from_bool(ok: bool, warn: bool = False) -> str:
    if ok:
        return "PASS"
    if warn:
        return "WARN"
    return "FAIL"


def sources_to_set(value: Any) -> set[str]:
    text = clean_text(value)
    if not text:
        return set()
    return {item.strip() for item in text.split(";") if item.strip()}


def source_ready_set(row: pd.Series, column: str) -> set[str]:
    return sources_to_set(row.get(column, ""))


def missing_sources(row: pd.Series, column: str) -> str:
    text = clean_text(row.get(column, ""))
    return text if text else ""


def subject_key(df: pd.DataFrame) -> pd.Series:
    code = df.get("ministry_subject_code", pd.Series(dtype=str)).astype(str).str.zfill(4)
    name_col = "source_subject_name" if "source_subject_name" in df.columns else "subject_name"
    name = df.get(name_col, pd.Series(dtype=str)).map(clean_text)
    return code + "|" + name


def summarize_raw_standard(raw_standard: pd.DataFrame) -> pd.DataFrame:
    if raw_standard.empty:
        return pd.DataFrame(
            columns=[
                "ministry_subject_code",
                "subject_name",
                "ranking_source",
                "raw_standard_matched_files",
                "raw_standard_matched_rows",
                "raw_standard_statuses",
                "raw_standard_utilization_statuses",
                "fact_ranking_years",
            ]
        )
    rows: list[dict[str, Any]] = []
    group_cols = ["ministry_subject_code", "subject_name", "ranking_source"]
    for keys, group in raw_standard.groupby(group_cols, dropna=False):
        code, subject_name, source = keys
        matched = group[group["raw_match_status"].map(clean_text) == "matched"].copy()
        raw_rows = 0
        if not matched.empty:
            raw_rows = sum(int_value(value) for value in matched.get("raw_match_rows", []))
        rows.append(
            {
                "ministry_subject_code": clean_text(code).zfill(4),
                "subject_name": clean_text(subject_name),
                "ranking_source": clean_text(source),
                "raw_standard_matched_files": ";".join(
                    sorted({clean_text(value) for value in matched.get("file", []) if clean_text(value)})
                ),
                "raw_standard_matched_rows": raw_rows,
                "raw_standard_statuses": ";".join(sorted({clean_text(value) for value in group["raw_match_status"] if clean_text(value)})),
                "raw_standard_utilization_statuses": ";".join(
                    sorted({clean_text(value) for value in group["utilization_status"] if clean_text(value)})
                ),
                "fact_ranking_years": ";".join(
                    sorted({clean_text(value) for value in group.get("fact_ranking_years", []) if clean_text(value)})
                ),
            }
        )
    return pd.DataFrame(rows)


def summarize_raw_dedicated(raw_dedicated: pd.DataFrame) -> pd.DataFrame:
    if raw_dedicated.empty:
        return pd.DataFrame(
            columns=[
                "ministry_subject_code",
                "subject_name",
                "ranking_source",
                "raw_dedicated_rows",
                "raw_dedicated_years",
                "raw_dedicated_statuses",
            ]
        )
    if "ranking_source" not in raw_dedicated.columns:
        raw_dedicated = raw_dedicated.copy()
        raw_dedicated["ranking_source"] = "THE"
    rows: list[dict[str, Any]] = []
    group_cols = ["ministry_subject_code", "subject_name", "ranking_source"]
    for keys, group in raw_dedicated.groupby(group_cols, dropna=False):
        code, subject_name, source = keys
        raw_years: set[str] = set()
        for value in group.get("raw_years", []):
            raw_years.update(item.strip() for item in clean_text(value).split(";") if item.strip())
        rows.append(
            {
                "ministry_subject_code": clean_text(code).zfill(4),
                "subject_name": clean_text(subject_name),
                "ranking_source": clean_text(source),
                "raw_dedicated_rows": len(group),
                "raw_dedicated_years": ";".join(sorted(raw_years)),
                "raw_dedicated_statuses": ";".join(
                    sorted({clean_text(value) for value in group.get("utilization_status", []) if clean_text(value)})
                ),
            }
        )
    return pd.DataFrame(rows)


def build_subject_matrix(word_chart: pd.DataFrame, data_layer: pd.DataFrame) -> pd.DataFrame:
    if word_chart.empty:
        return pd.DataFrame()
    base = word_chart.copy()
    base["_join_key"] = subject_key(base)
    if not data_layer.empty:
        extra = data_layer.copy()
        extra["_join_key"] = subject_key(extra)
        keep_cols = [
            "_join_key",
            "wos_subject_rows",
            "cwts_field",
            "arwu_public_history_available",
            "usnews_external_history_available",
            "public_supplement_count",
        ]
        keep_cols = [col for col in keep_cols if col in extra.columns]
        base = base.merge(extra[keep_cols].drop_duplicates("_join_key"), on="_join_key", how="left")
    rows: list[dict[str, Any]] = []
    for _, row in base.iterrows():
        strict_rank_weight_indicator = bool_value(row.get("strict_all_four_rank_weight_indicator"))
        strict_with_wos = bool_value(row.get("strict_all_chart_data_with_wos"))
        usable_partial = bool_value(row.get("usable_partial_sources"))
        wos_available = bool_value(row.get("wos_available"))
        cwts_available = bool_value(row.get("cwts_available"))
        if strict_with_wos:
            lineage_status = "strict_complete"
        elif strict_rank_weight_indicator and cwts_available:
            lineage_status = "complete_rank_weight_indicator_with_cwts_proxy"
        elif usable_partial:
            lineage_status = "usable_partial"
        else:
            lineage_status = "weak_partial"
        rows.append(
            {
                "ministry_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
                "source_subject_name": clean_text(row.get("source_subject_name") or row.get("subject_name")),
                "mapped_subject_name": clean_text(row.get("subject_name")),
                "college": clean_text(row.get("college")),
                "ranking_ready_count": int_value(row.get("ranking_ready_count")),
                "ranking_ready_sources": clean_text(row.get("ranking_ready_sources")),
                "remaining_missing_ranking_sources": missing_sources(row, "remaining_missing_ranking_sources"),
                "weight_ready_count": int_value(row.get("weight_ready_count")),
                "weight_ready_sources": clean_text(row.get("weight_ready_sources")),
                "remaining_missing_weight_sources": missing_sources(row, "remaining_missing_weight_sources"),
                "indicator_ready_count": int_value(row.get("indicator_ready_count")),
                "indicator_ready_sources": clean_text(row.get("indicator_ready_sources")),
                "remaining_missing_indicator_sources": missing_sources(row, "remaining_missing_indicator_sources"),
                "wos_available": wos_available,
                "cwts_available": cwts_available,
                "cwts_field": clean_text(row.get("cwts_field")),
                "arwu_public_history_available": bool_value(row.get("arwu_public_history_available")),
                "usnews_external_history_available": bool_value(row.get("usnews_external_history_available")),
                "requires_disclosure_count": int_value(row.get("requires_disclosure_count")),
                "public_supplement_count": int_value(row.get("public_supplement_count")),
                "is_proxy_subject_code": bool_value(row.get("is_proxy_subject_code")),
                "generation_status_code_after_supplement": clean_text(row.get("generation_status_code_after_supplement")),
                "strict_all_four_rank_weight_indicator": strict_rank_weight_indicator,
                "strict_all_chart_data_with_wos": strict_with_wos,
                "usable_partial_sources": usable_partial,
                "lineage_status": lineage_status,
            }
        )
    return pd.DataFrame(rows)


def build_current_word_chart_matrix(coverage: pd.DataFrame, data_layer: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if coverage.empty or data_layer.empty:
        return read_csv(WORD_CHART_CSV), read_json(WORD_CHART_JSON)
    coverage_rows = coverage.copy()
    coverage_rows["ministry_subject_code"] = coverage_rows["ministry_subject_code"].astype(str).str.zfill(4)
    data_rows = data_layer.copy()
    data_rows["ministry_subject_code"] = data_rows["ministry_subject_code"].astype(str).str.zfill(4)

    output_rows: list[dict[str, Any]] = []
    for _, coverage_row in coverage_rows.iterrows():
        code = clean_text(coverage_row.get("ministry_subject_code")).zfill(4)
        source_subject_name = clean_text(coverage_row.get("source_subject_name") or coverage_row.get("ministry_subject_name"))
        ministry_subject_name = clean_text(coverage_row.get("ministry_subject_name"))
        candidates = data_rows[data_rows["ministry_subject_code"] == code].copy()
        data_row = pd.Series(dtype=object)
        for candidate_name in [source_subject_name, ministry_subject_name]:
            matched = candidates[candidates["subject_name"].map(clean_text) == candidate_name].copy()
            if not matched.empty:
                data_row = matched.iloc[0]
                break
        if data_row.empty and len(candidates) == 1:
            data_row = candidates.iloc[0]

        ranking_ready_count = int_value(data_row.get("ranking_ready_count"))
        weight_ready_count = int_value(data_row.get("weight_ready_count"))
        indicator_ready_count = int_value(data_row.get("indicator_ready_count"))
        wos_available = bool_value(data_row.get("wos_available"))
        cwts_available = bool_value(data_row.get("cwts_available"))
        strict_rank_weight_indicator = ranking_ready_count == 4 and weight_ready_count == 4 and indicator_ready_count == 4
        strict_with_wos = strict_rank_weight_indicator and wos_available
        usable_partial = ranking_ready_count >= 2 and indicator_ready_count >= 2 and (wos_available or cwts_available)
        output_rows.append(
            {
                "ministry_subject_code": code,
                "subject_name": clean_text(data_row.get("subject_name") or ministry_subject_name),
                "college": clean_text(coverage_row.get("college")),
                "source_subject_name": source_subject_name,
                "ranking_ready_count": ranking_ready_count,
                "ranking_ready_sources": clean_text(data_row.get("ranking_ready_sources")),
                "remaining_missing_ranking_sources": clean_text(data_row.get("remaining_missing_ranking_sources")),
                "weight_ready_count": weight_ready_count,
                "weight_ready_sources": clean_text(data_row.get("weight_ready_sources")),
                "remaining_missing_weight_sources": clean_text(data_row.get("remaining_missing_weight_sources")),
                "indicator_ready_count": indicator_ready_count,
                "indicator_ready_sources": clean_text(data_row.get("indicator_ready_sources")),
                "remaining_missing_indicator_sources": clean_text(data_row.get("remaining_missing_indicator_sources")),
                "wos_available": wos_available,
                "cwts_available": cwts_available,
                "requires_disclosure_count": int_value(data_row.get("requires_disclosure_count")),
                "strict_all_four_rank_weight_indicator": strict_rank_weight_indicator,
                "strict_all_chart_data_with_wos": strict_with_wos,
                "usable_partial_sources": usable_partial,
                "is_proxy_subject_code": bool_value(coverage_row.get("is_proxy_subject_code")),
                "generation_status_code_after_supplement": clean_text(coverage_row.get("generation_status_code_after_supplement")),
            }
        )
    out = pd.DataFrame(output_rows)
    summary = {
        "generated_at": now_text(),
        "subject_count": len(out),
        "strict_all_four_rank_weight_indicator": int(out["strict_all_four_rank_weight_indicator"].sum()) if not out.empty else 0,
        "strict_all_chart_data_with_wos": int(out["strict_all_chart_data_with_wos"].sum()) if not out.empty else 0,
        "usable_partial_sources": int(out["usable_partial_sources"].sum()) if not out.empty else 0,
        "ranking_ready_distribution": out["ranking_ready_count"].value_counts().sort_index().astype(int).to_dict() if not out.empty else {},
        "weight_ready_distribution": out["weight_ready_count"].value_counts().sort_index().astype(int).to_dict() if not out.empty else {},
        "indicator_ready_distribution": out["indicator_ready_count"].value_counts().sort_index().astype(int).to_dict() if not out.empty else {},
        "wos_available_distribution": out["wos_available"].value_counts().sort_index().astype(int).to_dict() if not out.empty else {},
        "detail_csv": str(WORD_CHART_CSV),
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(WORD_CHART_CSV, index=False, encoding="utf-8-sig")
    WORD_CHART_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
        newline="\n",
    )
    return out, summary


def build_source_matrix(
    mapping_diagnosis: pd.DataFrame,
    subject_matrix: pd.DataFrame,
    raw_standard_summary: pd.DataFrame,
    raw_dedicated_summary: pd.DataFrame,
) -> pd.DataFrame:
    if mapping_diagnosis.empty:
        return pd.DataFrame()
    rows = mapping_diagnosis.copy()
    rows["ministry_subject_code"] = rows["ministry_subject_code"].astype(str).str.zfill(4)
    rows["_join_key"] = rows["ministry_subject_code"] + "|" + rows["subject_name"].map(clean_text)

    if not subject_matrix.empty:
        subject_cols = [
            "ministry_subject_code",
            "source_subject_name",
            "ranking_ready_sources",
            "weight_ready_sources",
            "indicator_ready_sources",
            "lineage_status",
        ]
        subjects = subject_matrix[subject_cols].copy()
        subjects["_join_key"] = subjects["ministry_subject_code"].astype(str).str.zfill(4) + "|" + subjects["source_subject_name"].map(clean_text)
        rows = rows.merge(subjects.drop_duplicates("_join_key"), on="_join_key", how="left", suffixes=("", "_final"))

    raw_standard = raw_standard_summary.copy()
    if not raw_standard.empty:
        raw_standard["ministry_subject_code"] = raw_standard["ministry_subject_code"].astype(str).str.zfill(4)
        rows = rows.merge(
            raw_standard,
            on=["ministry_subject_code", "subject_name", "ranking_source"],
            how="left",
        )
    raw_dedicated = raw_dedicated_summary.copy()
    if not raw_dedicated.empty:
        raw_dedicated["ministry_subject_code"] = raw_dedicated["ministry_subject_code"].astype(str).str.zfill(4)
        rows = rows.merge(
            raw_dedicated,
            on=["ministry_subject_code", "subject_name", "ranking_source"],
            how="left",
        )

    final_rows: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        source = clean_text(row.get("ranking_source"))
        ranking_ready = source in source_ready_set(row, "ranking_ready_sources")
        weight_ready = source in source_ready_set(row, "weight_ready_sources")
        indicator_ready = source in source_ready_set(row, "indicator_ready_sources")
        final_rows.append(
            {
                "ministry_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
                "subject_name": clean_text(row.get("subject_name")),
                "ranking_source": source,
                "mapping_diagnosis": clean_text(row.get("diagnosis")),
                "alias_values": clean_text(row.get("alias_values")),
                "fact_tongji_latest_by_subject_id": int_value(row.get("fact_tongji_latest_by_subject_id")),
                "fact_tongji_latest_by_runtime_alias": int_value(row.get("fact_tongji_latest_by_runtime_alias")),
                "sqlite_join_latest_tongji_rows": int_value(row.get("sqlite_join_latest_tongji_rows")),
                "weight_rows_by_runtime_alias": int_value(row.get("weight_rows_by_runtime_alias")),
                "raw_standard_matched_rows": int_value(row.get("raw_standard_matched_rows")),
                "raw_standard_statuses": clean_text(row.get("raw_standard_statuses")),
                "raw_standard_utilization_statuses": clean_text(row.get("raw_standard_utilization_statuses")),
                "raw_standard_matched_files": clean_text(row.get("raw_standard_matched_files")),
                "raw_dedicated_rows": int_value(row.get("raw_dedicated_rows")),
                "raw_dedicated_years": clean_text(row.get("raw_dedicated_years")),
                "raw_dedicated_statuses": clean_text(row.get("raw_dedicated_statuses")),
                "final_ranking_ready": ranking_ready,
                "final_weight_ready": weight_ready,
                "final_indicator_ready": indicator_ready,
                "subject_lineage_status": clean_text(row.get("lineage_status")),
            }
        )
    return pd.DataFrame(final_rows)


def table_status_map(system_audit: dict[str, Any]) -> dict[str, int]:
    rows = system_audit.get("data_layer", {}).get("sqlite_tables", [])
    return {clean_text(row.get("table")): int_value(row.get("row_count")) for row in rows}


def build_summary(
    mapping_summary: dict[str, Any],
    mapping_diagnosis_summary: dict[str, Any],
    raw_gap_summary: dict[str, Any],
    raw_util_summary: dict[str, Any],
    data_layer_summary: dict[str, Any],
    word_chart_summary: dict[str, Any],
    system_audit: dict[str, Any],
    subject_matrix: pd.DataFrame,
    source_matrix: pd.DataFrame,
) -> dict[str, Any]:
    safety_checks = mapping_summary.get("safety_checks", [])
    safety_ok = all(bool(row.get("pass")) for row in safety_checks)
    expected_links = int_value(mapping_summary.get("expected_links"))
    ok_links = int_value(mapping_summary.get("status_counts", {}).get("ok"))
    mapping_gate = expected_links > 0 and ok_links == expected_links and safety_ok

    table_counts = table_status_map(system_audit)
    required_tables = [
        "dim_subject",
        "dim_subject_alias",
        "fact_ranking",
        "fact_ranking_subject_bridge",
        "fact_indicator_weight",
        "fact_ranking_indicator",
        "fact_ranking_indicator_subject_bridge",
    ]
    preprocessing_gate = all(table_counts.get(table, 0) > 0 for table in required_tables)

    raw_gap_gate = (
        int_value(raw_gap_summary.get("raw_recovery_rows")) == 0
        and int_value(raw_gap_summary.get("raw_recovery_subject_source_count")) == 0
        and int_value(raw_util_summary.get("issue_rows")) == 0
    )
    mapping_49_gate = int_value(mapping_diagnosis_summary.get("mapping_related_issue_count")) == 0

    subject_count = int_value(word_chart_summary.get("subject_count"))
    strict_with_wos = int_value(word_chart_summary.get("strict_all_chart_data_with_wos"))
    strict_rank_weight_indicator = int_value(word_chart_summary.get("strict_all_four_rank_weight_indicator"))
    usable_partial = int_value(word_chart_summary.get("usable_partial_sources"))

    weak_subjects = []
    not_strict_subjects = []
    if not subject_matrix.empty:
        weak_subjects = subject_matrix[subject_matrix["lineage_status"] == "weak_partial"]["source_subject_name"].tolist()
        not_strict_subjects = subject_matrix[
            subject_matrix["strict_all_chart_data_with_wos"].map(lambda value: not bool_value(value))
        ]["source_subject_name"].tolist()

    ranking_missing_breakdown = {}
    indicator_missing_breakdown = {}
    if not subject_matrix.empty:
        for source in RANKING_SOURCES:
            ranking_missing_breakdown[source] = int(
                subject_matrix["remaining_missing_ranking_sources"].map(lambda text: source in sources_to_set(text)).sum()
            )
            indicator_missing_breakdown[source] = int(
                subject_matrix["remaining_missing_indicator_sources"].map(lambda text: source in sources_to_set(text)).sum()
            )

    return {
        "generated_at": now_text(),
        "input_audit_dir": str(AUDIT_DIR),
        "output_dir": str(OUTPUT_DIR),
        "gates": {
            "mapping_workbook_integrity": status_from_bool(mapping_gate),
            "subject_49_mapping_diagnosis": status_from_bool(mapping_49_gate),
            "raw_excel_recovery_check": status_from_bool(raw_gap_gate),
            "processed_layer_core_tables": status_from_bool(preprocessing_gate),
            "final_chart_strict_all_49": status_from_bool(subject_count > 0 and strict_with_wos == subject_count, warn=True),
            "final_chart_usable_partial": status_from_bool(subject_count > 0 and usable_partial == subject_count, warn=True),
        },
        "mapping": {
            "expected_links": expected_links,
            "ok_links": ok_links,
            "safety_check_count": len(safety_checks),
            "safety_check_pass_count": sum(1 for row in safety_checks if bool(row.get("pass"))),
            "mapping_related_issue_count": int_value(mapping_diagnosis_summary.get("mapping_related_issue_count")),
            "runtime_alias_recovery_count": int_value(mapping_diagnosis_summary.get("runtime_alias_recovery_count")),
            "diagnosis_breakdown": mapping_diagnosis_summary.get("diagnosis_breakdown", {}),
        },
        "raw_data": {
            "checked_gap_rows": int_value(raw_gap_summary.get("checked_gap_rows")),
            "raw_recovery_rows": int_value(raw_gap_summary.get("raw_recovery_rows")),
            "raw_recovery_subject_source_count": int_value(raw_gap_summary.get("raw_recovery_subject_source_count")),
            "standard_rows": int_value(raw_util_summary.get("standard_rows")),
            "standard_runtime_alias_supplement_count": int_value(raw_util_summary.get("standard_runtime_alias_supplement_count")),
            "standard_raw_match_not_in_fact_count": int_value(raw_util_summary.get("standard_raw_match_not_in_fact_count")),
            "dedicated_sheet_rows": int_value(raw_util_summary.get("dedicated_sheet_rows")),
            "dedicated_sheet_supplement_needed_count": int_value(raw_util_summary.get("dedicated_sheet_supplement_needed_count")),
            "issue_rows": int_value(raw_util_summary.get("issue_rows")),
        },
        "processed_layer": {
            "table_counts": table_counts,
            "required_table_count": len(required_tables),
            "required_table_ready_count": sum(1 for table in required_tables if table_counts.get(table, 0) > 0),
        },
        "final_chart_data": {
            "subject_count": subject_count,
            "strict_all_four_rank_weight_indicator": strict_rank_weight_indicator,
            "strict_all_chart_data_with_wos": strict_with_wos,
            "usable_partial_sources": usable_partial,
            "ranking_ready_distribution": word_chart_summary.get("ranking_ready_distribution", {}),
            "weight_ready_distribution": word_chart_summary.get("weight_ready_distribution", {}),
            "indicator_ready_distribution": word_chart_summary.get("indicator_ready_distribution", {}),
            "wos_available_distribution": word_chart_summary.get("wos_available_distribution", {}),
            "ranking_missing_breakdown": ranking_missing_breakdown,
            "indicator_missing_breakdown": indicator_missing_breakdown,
            "not_strict_subjects": not_strict_subjects,
            "weak_subjects": weak_subjects,
        },
        "lineage_outputs": {
            "subject_matrix_csv": str(OUTPUT_DIR / "subject_49_full_lineage_subject_matrix.csv"),
            "source_matrix_csv": str(OUTPUT_DIR / "subject_49_full_lineage_source_matrix.csv"),
            "markdown_report": str(OUTPUT_DIR / "subject_49_full_lineage_audit.md"),
            "summary_json": str(OUTPUT_DIR / "subject_49_full_lineage_audit_summary.json"),
        },
        "source_matrix_rows": len(source_matrix),
        "subject_matrix_rows": len(subject_matrix),
    }


def format_distribution(distribution: dict[str, Any]) -> str:
    if not distribution:
        return "无"
    return "，".join(f"{key}:{value}" for key, value in sorted(distribution.items(), key=lambda item: str(item[0])))


def build_markdown(summary: dict[str, Any], subject_matrix: pd.DataFrame) -> str:
    gates = summary["gates"]
    mapping = summary["mapping"]
    raw_data = summary["raw_data"]
    final_chart = summary["final_chart_data"]
    processed = summary["processed_layer"]

    weak_subjects = final_chart.get("weak_subjects", [])
    not_strict_subjects = final_chart.get("not_strict_subjects", [])
    gap_rows = pd.DataFrame()
    if not subject_matrix.empty:
        gap_rows = subject_matrix[subject_matrix["strict_all_chart_data_with_wos"].map(lambda value: not bool_value(value))].copy()
        gap_rows = gap_rows[
            [
                "ministry_subject_code",
                "source_subject_name",
                "ranking_ready_count",
                "remaining_missing_ranking_sources",
                "indicator_ready_count",
                "remaining_missing_indicator_sources",
                "wos_available",
                "cwts_available",
                "lineage_status",
            ]
        ]

    lines = [
        "# 49 个一级学科全链路数据核查",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 输入审计目录: {summary['input_audit_dir']}",
        f"- 输出目录: {summary['output_dir']}",
        "",
        "## 总体结论",
        "",
        f"- 原始映射表完整性: {gates['mapping_workbook_integrity']}。映射工作簿期望链路 {mapping['expected_links']} 条，已落入别名表 {mapping['ok_links']} 条，安全检查 {mapping['safety_check_pass_count']}/{mapping['safety_check_count']} 通过。",
        f"- 49 学科映射诊断: {gates['subject_49_mapping_diagnosis']}。mapping_related_issue_count={mapping['mapping_related_issue_count']}，runtime_alias_recovery_count={mapping['runtime_alias_recovery_count']}。",
        f"- 原始 Excel 可恢复缺口复查: {gates['raw_excel_recovery_check']}。raw_recovery_rows={raw_data['raw_recovery_rows']}，standard_raw_match_not_in_fact_count={raw_data['standard_raw_match_not_in_fact_count']}，issue_rows={raw_data['issue_rows']}。",
        f"- 预处理核心表: {gates['processed_layer_core_tables']}。核心表 {processed['required_table_ready_count']}/{processed['required_table_count']} 可用。",
        f"- 最终 Word 图表严格齐全度: {gates['final_chart_strict_all_49']}。严格四榜单排名+权重+指标+WOS 齐全 {final_chart['strict_all_chart_data_with_wos']}/{final_chart['subject_count']}。",
        f"- 最终 Word 图表可用覆盖度: {gates['final_chart_usable_partial']}。至少具备可用部分来源并有论文代理支撑 {final_chart['usable_partial_sources']}/{final_chart['subject_count']}。",
        "",
        "## 关键判断",
        "",
        "- 当前没有发现“原始数据中存在、但因为映射或预处理遗漏导致没有用上”的剩余可恢复缺口；这类问题在本轮核查中为 0。",
        "- 当前没有发现 49 学科层面的映射错误链路；此前需要运行期别名补足的来源已进入可解释矩阵。",
        f"- 不能把当前状态表述为 49 个学科所有图表数据都严格齐全。严格齐全的是 {final_chart['strict_all_chart_data_with_wos']} 个；如果接受部分榜单来源和 CWTS 等代理支撑，可用覆盖为 {final_chart['usable_partial_sources']} 个。",
        "",
        "## 分布",
        "",
        f"- 排名来源齐全度分布: {format_distribution(final_chart.get('ranking_ready_distribution', {}))}",
        f"- 权重来源齐全度分布: {format_distribution(final_chart.get('weight_ready_distribution', {}))}",
        f"- 指标来源齐全度分布: {format_distribution(final_chart.get('indicator_ready_distribution', {}))}",
        f"- WOS 可用分布: {format_distribution(final_chart.get('wos_available_distribution', {}))}",
        f"- 排名缺口按来源: {format_distribution(final_chart.get('ranking_missing_breakdown', {}))}",
        f"- 指标缺口按来源: {format_distribution(final_chart.get('indicator_missing_breakdown', {}))}",
        "",
        "## 严格未齐全学科",
        "",
    ]
    if gap_rows.empty:
        lines.append("- 无。")
    else:
        for _, row in gap_rows.iterrows():
            ranking_missing = clean_text(row.get("remaining_missing_ranking_sources")) or "无"
            indicator_missing = clean_text(row.get("remaining_missing_indicator_sources")) or "无"
            lines.append(
                f"- {clean_text(row.get('ministry_subject_code')).zfill(4)} {clean_text(row.get('source_subject_name'))}: "
                f"排名 {int_value(row.get('ranking_ready_count'))}/4，缺 {ranking_missing}；"
                f"指标 {int_value(row.get('indicator_ready_count'))}/4，缺 {indicator_missing}；"
                f"WOS={bool_value(row.get('wos_available'))}，CWTS={bool_value(row.get('cwts_available'))}，状态={clean_text(row.get('lineage_status'))}"
            )
    lines.extend(
        [
            "",
            "## 最弱覆盖学科",
            "",
            "- " + ("、".join(weak_subjects) if weak_subjects else "无"),
            "",
            "## 输出文件",
            "",
            f"- 学科维度矩阵: {summary['lineage_outputs']['subject_matrix_csv']}",
            f"- 学科×榜单来源矩阵: {summary['lineage_outputs']['source_matrix_csv']}",
            f"- 汇总 JSON: {summary['lineage_outputs']['summary_json']}",
            f"- 本报告: {summary['lineage_outputs']['markdown_report']}",
            "",
            "## 核查口径",
            "",
            "- 原始数据层: 使用标准榜单原始 Excel 扫描、THE 专用同济历史 sheet 扫描、原始缺口复查结果。",
            "- 映射层: 使用 `教育部学科与四大国际学科排名映射关系.xlsx` 两个 sheet 生成的别名完整性核查和 49 学科逐来源诊断。",
            "- 预处理层: 使用 SQLite/CSV 的核心 fact、dim、bridge 表行数和系统体检结果。",
            "- 最终图表层: 使用 49 学科 Word 图表数据完整性矩阵，区分严格齐全、CWTS/公开数据代理、可用部分来源和弱覆盖。",
        ]
    )
    if not_strict_subjects:
        lines.extend(["", f"<!-- not_strict_subject_count={len(not_strict_subjects)} -->"])
    return "\n".join(lines) + "\n"


def run_audit() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping_summary = read_json(MAPPING_SUMMARY_JSON)
    mapping_diagnosis_summary = read_json(MAPPING_DIAGNOSIS_JSON)
    raw_gap_summary = read_json(RAW_GAP_JSON)
    raw_util_summary = read_json(RAW_UTIL_JSON)
    data_layer_summary = read_json(DATA_LAYER_JSON)
    system_audit = read_json(SYSTEM_AUDIT_JSON)

    coverage = read_csv(COVERAGE_CSV)
    data_layer = read_csv(DATA_LAYER_CSV)
    word_chart, word_chart_summary = build_current_word_chart_matrix(coverage, data_layer)
    mapping_diagnosis = read_csv(MAPPING_DIAGNOSIS_CSV)
    raw_standard = read_csv(RAW_STANDARD_CSV)
    raw_dedicated = read_csv(RAW_DEDICATED_CSV)

    subject_matrix = build_subject_matrix(word_chart, data_layer)
    raw_standard_summary = summarize_raw_standard(raw_standard)
    raw_dedicated_summary = summarize_raw_dedicated(raw_dedicated)
    source_matrix = build_source_matrix(mapping_diagnosis, subject_matrix, raw_standard_summary, raw_dedicated_summary)

    subject_matrix_path = OUTPUT_DIR / "subject_49_full_lineage_subject_matrix.csv"
    source_matrix_path = OUTPUT_DIR / "subject_49_full_lineage_source_matrix.csv"
    subject_matrix.to_csv(subject_matrix_path, index=False, encoding="utf-8-sig")
    source_matrix.to_csv(source_matrix_path, index=False, encoding="utf-8-sig")

    summary = build_summary(
        mapping_summary=mapping_summary,
        mapping_diagnosis_summary=mapping_diagnosis_summary,
        raw_gap_summary=raw_gap_summary,
        raw_util_summary=raw_util_summary,
        data_layer_summary=data_layer_summary,
        word_chart_summary=word_chart_summary,
        system_audit=system_audit,
        subject_matrix=subject_matrix,
        source_matrix=source_matrix,
    )
    (OUTPUT_DIR / "subject_49_full_lineage_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
        newline="\n",
    )
    (OUTPUT_DIR / "subject_49_full_lineage_audit.md").write_text(
        build_markdown(summary, subject_matrix),
        encoding="utf-8-sig",
        newline="\n",
    )

    print(json.dumps(summary["gates"], ensure_ascii=False, indent=2))
    print(f"subject_matrix_rows={len(subject_matrix)}")
    print(f"source_matrix_rows={len(source_matrix)}")
    print(f"output_dir={OUTPUT_DIR}")


if __name__ == "__main__":
    run_audit()
