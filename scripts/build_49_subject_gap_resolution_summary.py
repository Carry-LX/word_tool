from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit"
PUBLIC_PLAN_CSV = PROJECT_DIR / "outputs" / "public_gap_supplements" / "public_gap_supplement_plan.csv"
AUDIT_CSV = OUTPUT_DIR / "subject_49_data_layer_audit.csv"
DIAGNOSTICS_CSV = OUTPUT_DIR / "subject_49_mapping_gap_diagnostics.csv"
RAW_VERIFY_CSV = OUTPUT_DIR / "subject_49_raw_excel_gap_verification.csv"
MATRIX_CSV = OUTPUT_DIR / "subject_49_gap_resolution_matrix.csv"
CONFIRMED_GAPS_CSV = OUTPUT_DIR / "subject_49_confirmed_ranking_gaps.csv"
SUMMARY_JSON = OUTPUT_DIR / "subject_49_gap_resolution_summary.json"
SUMMARY_MD = OUTPUT_DIR / "subject_49_gap_resolution_summary.md"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def bool_text(value: Any) -> bool:
    return clean_text(value).lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def gap_class(row: pd.Series) -> str:
    if bool_text(row.get("latest_ranking_after_all_supplements")):
        if bool_text(row.get("latest_local_ranking_after_supplement")):
            return "ready_latest_local_fact"
        return "ready_latest_external_history"
    if bool_text(row.get("ranking_after_all_supplements")):
        return "historical_only_no_latest_ranking"
    if bool_text(row.get("local_weight_after_supplement")):
        if clean_text(row.get("supplement_proxy_level")):
            return "weight_or_proxy_only_no_ranking"
        return "weight_only_no_ranking"
    return "confirmed_no_ranking_or_weight"


def build_summary() -> dict[str, Any]:
    plan = read_csv(PUBLIC_PLAN_CSV)
    audit = read_csv(AUDIT_CSV)
    diagnostics = read_csv(DIAGNOSTICS_CSV)
    raw_verify = read_csv(RAW_VERIFY_CSV)
    if plan.empty:
        raise FileNotFoundError(f"missing public plan: {PUBLIC_PLAN_CSV}")

    matrix = plan.copy()
    for column in [
        "local_ranking_after_supplement",
        "external_history_after_supplement",
        "ranking_after_all_supplements",
        "latest_local_ranking_after_supplement",
        "latest_external_history_after_supplement",
        "latest_ranking_after_all_supplements",
        "local_weight_after_supplement",
        "requires_disclosure",
    ]:
        if column not in matrix.columns:
            matrix[column] = "False"
    matrix["gap_class"] = matrix.apply(gap_class, axis=1)

    if not diagnostics.empty:
        diag_cols = [
            "ministry_subject_code",
            "subject_name",
            "ranking_source",
            "diagnosis",
            "fact_tongji_latest_by_subject_id",
            "fact_tongji_latest_by_runtime_alias",
            "weight_rows_by_runtime_alias",
        ]
        matrix = matrix.merge(
            diagnostics[[col for col in diag_cols if col in diagnostics.columns]],
            on=["ministry_subject_code", "subject_name", "ranking_source"],
            how="left",
        )
    if not raw_verify.empty:
        raw_status = (
            raw_verify.groupby(["ministry_subject_code", "subject_name", "ranking_source"], dropna=False)
            .agg(
                raw_excel_subject_field_recovery=("raw_scan_status", lambda values: "matched" if (values == "matched").any() else "no_match"),
                raw_excel_checked_rows=("raw_scan_status", "size"),
            )
            .reset_index()
        )
        matrix = matrix.merge(raw_status, on=["ministry_subject_code", "subject_name", "ranking_source"], how="left")
    matrix["raw_excel_subject_field_recovery"] = matrix.get("raw_excel_subject_field_recovery", "").fillna("")
    matrix["raw_excel_checked_rows"] = matrix.get("raw_excel_checked_rows", "").fillna("")
    matrix.to_csv(MATRIX_CSV, index=False, encoding="utf-8-sig")

    latest_available = matrix["latest_ranking_after_all_supplements"].map(bool_text)
    confirmed = matrix[~latest_available].copy()
    confirmed.to_csv(CONFIRMED_GAPS_CSV, index=False, encoding="utf-8-sig")

    source_summary = []
    for source, group in matrix.groupby("ranking_source", sort=False):
        source_summary.append(
            {
                "ranking_source": source,
                "rows": int(len(group)),
                "local_ranking": int(group["local_ranking_after_supplement"].map(bool_text).sum()),
                "external_history": int(group["external_history_after_supplement"].map(bool_text).sum()),
                "ranking_after_all": int(group["ranking_after_all_supplements"].map(bool_text).sum()),
                "latest_local_ranking": int(group["latest_local_ranking_after_supplement"].map(bool_text).sum()),
                "latest_external_history": int(group["latest_external_history_after_supplement"].map(bool_text).sum()),
                "latest_ranking_after_all": int(group["latest_ranking_after_all_supplements"].map(bool_text).sum()),
                "local_weight": int(group["local_weight_after_supplement"].map(bool_text).sum()),
                "confirmed_ranking_gaps": int((~group["latest_ranking_after_all_supplements"].map(bool_text)).sum()),
            }
        )

    class_summary = matrix["gap_class"].value_counts().to_dict()
    raw_recovery_rows = 0
    if "raw_excel_subject_field_recovery" in matrix.columns:
        raw_recovery_rows = int((matrix["raw_excel_subject_field_recovery"] == "matched").sum())

    subject_all_ready = 0
    if not audit.empty and "ranking_ready_count" in audit.columns:
        subject_all_ready = int((audit["ranking_ready_count"].astype(str) == "4").sum())

    summary = {
        "generated_at": now_text(),
        "subject_count": int(audit.shape[0]) if not audit.empty else int(matrix[["ministry_subject_code", "subject_name"]].drop_duplicates().shape[0]),
        "subject_source_rows": int(matrix.shape[0]),
        "subject_all_four_ranking_ready_after_all_supplements": subject_all_ready,
        "local_ranking_available_rows": int(matrix["local_ranking_after_supplement"].map(bool_text).sum()),
        "external_history_available_rows": int(matrix["external_history_after_supplement"].map(bool_text).sum()),
        "ranking_available_after_all_supplements_rows": int(matrix["ranking_after_all_supplements"].map(bool_text).sum()),
        "latest_local_ranking_available_rows": int(matrix["latest_local_ranking_after_supplement"].map(bool_text).sum()),
        "latest_external_history_available_rows": int(matrix["latest_external_history_after_supplement"].map(bool_text).sum()),
        "latest_ranking_available_after_all_supplements_rows": int(matrix["latest_ranking_after_all_supplements"].map(bool_text).sum()),
        "local_weight_available_rows": int(matrix["local_weight_after_supplement"].map(bool_text).sum()),
        "confirmed_ranking_gap_rows": int(confirmed.shape[0]),
        "raw_excel_subject_field_recovery_rows": raw_recovery_rows,
        "gap_class_summary": {str(key): int(value) for key, value in class_summary.items()},
        "source_summary": source_summary,
        "matrix_csv": str(MATRIX_CSV),
        "confirmed_gaps_csv": str(CONFIRMED_GAPS_CSV),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    source_lines = [
        f"| {row['ranking_source']} | {row['latest_ranking_after_all']}/{row['rows']} | {row['ranking_after_all']} | {row['latest_local_ranking']} | {row['latest_external_history']} | {row['local_weight']} | {row['confirmed_ranking_gaps']} |"
        for row in source_summary
    ]
    confirmed_preview = confirmed[
        [
            "ministry_subject_code",
            "subject_name",
            "ranking_source",
            "gap_class",
            "latest_source_year",
            "supplement_proxy_level",
            "supplement_subject_or_area",
            "raw_excel_subject_field_recovery",
        ]
    ].head(60)
    lines = [
        "# 49 学科数据缺口核查与补源结论",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- subject_count: {summary['subject_count']}",
        f"- subject_source_rows: {summary['subject_source_rows']}",
        f"- subject_all_four_ranking_ready_after_all_supplements: {summary['subject_all_four_ranking_ready_after_all_supplements']}/{summary['subject_count']}",
        f"- historical_ranking_available_after_all_supplements_rows: {summary['ranking_available_after_all_supplements_rows']}/{summary['subject_source_rows']}",
        f"- latest_ranking_available_after_all_supplements_rows: {summary['latest_ranking_available_after_all_supplements_rows']}/{summary['subject_source_rows']}",
        f"- local_weight_available_rows: {summary['local_weight_available_rows']}/{summary['subject_source_rows']}",
        f"- raw_excel_subject_field_recovery_rows: {summary['raw_excel_subject_field_recovery_rows']}",
        "",
        "## 分来源覆盖",
        "",
        "| 来源 | 最新综合排名可用 | 历史综合排名可用 | 最新本地事实表 | 最新外部补源 | 本地权重 | 确认排名缺口 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *source_lines,
        "",
        "## 缺口类别",
        "",
        *[f"- {key}: {value}" for key, value in summary["gap_class_summary"].items()],
        "",
        "## 确认缺口预览",
        "",
        confirmed_preview.to_markdown(index=False),
        "",
        f"- 明细矩阵: {MATRIX_CSV}",
        f"- 确认缺口: {CONFIRMED_GAPS_CSV}",
    ]
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    build_summary()
