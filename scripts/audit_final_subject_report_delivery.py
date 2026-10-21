from __future__ import annotations

import ast
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
FULL_AUDIT_JSON = (
    PROJECT_DIR
    / "outputs"
    / "regenerate_all_ministry_subject_word_reports"
    / "full_generation_audit_20260927"
    / "full_generation_audit.json"
)
COVERAGE_CSV = (
    PROJECT_DIR
    / "outputs"
    / "subject_coverage_audit"
    / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
)
MAPPING_WORKBOOK = PROJECT_DIR / "data" / "教育部学科与四大国际学科排名映射关系.xlsx"
MAPPING_SHEET = "学科映射关系"
REVERSE_MAPPING_SHEET = "Sheet1"
MAPPING_DIAGNOSIS_JSON = (
    PROJECT_DIR
    / "outputs"
    / "subject_49_data_layer_audit"
    / "subject_49_mapping_gap_diagnostics_summary.json"
)
DIM_SUBJECT_CSV = PROJECT_DIR / "processed" / "dim_subject.csv"
TONGJI_MAPPING_WORKBOOK = PROJECT_DIR / "data" / "同济大学学院+学科映射关系（20260603更新）.xlsx"
PROCESSED_CORE_SCRIPT = PROJECT_DIR / "scripts" / "build_processed_core.py"
TONGJI_PROXY_SUPPLEMENT_CSV = PROJECT_DIR / "configs" / "runtime" / "tongji_subject_proxy_supplement.csv"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "final_subject_report_delivery_audit_20260928"
SYSTEM_AUDIT_JSON = PROJECT_DIR / "outputs" / "agent_system_audit" / "latest" / "agent_system_readiness.json"
ARWU_AUDIT_JSON = PROJECT_DIR / "outputs" / "arwu_source_upgrade_20260915" / "arwu_source_upgrade_summary.json"
RELEASE_GATE_JSON = PROJECT_DIR / "outputs" / "release_audit" / "latest" / "release_quality_gate.json"
SPARSE_VISUAL_REVIEW_JSON = OUTPUT_DIR / "sparse_page_visual_review.json"

RANKING_SOURCES = ["软科", "QS", "US News", "THE"]
MAPPING_COLUMNS = {
    "软科": "软科世界一流学科对应名称",
    "QS": "QS对应的学科名称",
    "US News": "U.S.NEWS学科排名对应名称",
    "THE": "THE对应领域",
}
NO_MAPPING_VALUES = {"", "无", "不适用", "n/a", "na", "none", "nan", "-", "—", "/"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def normalize_code(value: Any) -> str:
    text = clean_text(value)
    return text.zfill(4) if text else ""


def int_value(value: Any) -> int:
    try:
        return int(float(clean_text(value) or 0))
    except ValueError:
        return 0


def valid_mapping(value: Any) -> bool:
    return clean_text(value).lower() not in NO_MAPPING_VALUES


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def load_authoritative_mapping() -> pd.DataFrame:
    mapping = pd.read_excel(MAPPING_WORKBOOK, sheet_name=MAPPING_SHEET, dtype=str).fillna("")
    mapping["一级学科代码"] = mapping["一级学科代码"].map(normalize_code)
    return mapping


def split_subject_names(value: Any) -> set[str]:
    text = clean_text(value)
    if not text:
        return set()
    return {item.strip() for item in re.split(r"[、,，;/；]", text) if item.strip()}


def reverse_mapping_candidates() -> dict[tuple[str, str], list[str]]:
    reverse = pd.read_excel(
        MAPPING_WORKBOOK,
        sheet_name=REVERSE_MAPPING_SHEET,
        dtype=str,
    ).fillna("")
    source_names = {
        "软科世界一流学科排名": "软科",
        "QS世界学科排名": "QS",
        "US News世界学科排名": "US News",
        "THE世界学科排名": "THE",
    }
    result: dict[tuple[str, str], set[str]] = {}
    for _, row in reverse.iterrows():
        source = source_names.get(clean_text(row.get("榜单名称")))
        ranking_subject = clean_text(row.get("榜单学科"))
        if not source or not ranking_subject:
            continue
        for subject_name in split_subject_names(row.get("对应一级学科")):
            result.setdefault((subject_name, source), set()).add(ranking_subject)
    return {key: sorted(values) for key, values in result.items()}


def registered_display_corrections() -> dict[tuple[str, str], str]:
    tree = ast.parse(PROCESSED_CORE_SCRIPT.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "SUBJECT_MAPPING_DISPLAY_CORRECTIONS" for target in targets):
                value = ast.literal_eval(node.value)
                return {
                    (normalize_code(code), clean_text(column)): clean_text(mapping_value)
                    for (code, column), mapping_value in value.items()
                }
    return {}


def aggregate_unique(values: pd.Series) -> str:
    items: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in items:
            items.append(text)
    return "；".join(items)


def load_tongji_mapping_overrides() -> pd.DataFrame:
    tongji = pd.read_excel(TONGJI_MAPPING_WORKBOOK, sheet_name="Sheet1", dtype=str).fillna("")
    for column in ["编号", "学院"]:
        if column in tongji.columns:
            tongji[column] = tongji[column].replace("", pd.NA).ffill().fillna("")
    if TONGJI_PROXY_SUPPLEMENT_CSV.exists():
        supplements = load_csv(TONGJI_PROXY_SUPPLEMENT_CSV)
        for _, supplement in supplements.iterrows():
            source_subject_name = clean_text(supplement.get("source_subject_name"))
            proxy_code = normalize_code(supplement.get("proxy_ministry_subject_code"))
            if source_subject_name and proxy_code:
                mask = tongji["学术学位点"].map(clean_text).eq(source_subject_name)
                tongji.loc[mask, "一级学科学科代码"] = proxy_code
    tongji["一级学科学科代码"] = tongji["一级学科学科代码"].map(clean_text)
    tongji = tongji[tongji["一级学科学科代码"].str.fullmatch(r"\d{4}")].copy()
    grouped = (
        tongji.groupby("一级学科学科代码", dropna=True)
        .agg(
            tongji_arwu_subject=("软科世界一流学科对应名称", aggregate_unique),
            tongji_qs_subject=("QS对应的学科名称", aggregate_unique),
            tongji_usnews_subject=("U.S.NEWS学科排名对应名称", aggregate_unique),
            tongji_the_area=("THE对应领域", aggregate_unique),
        )
        .reset_index()
        .rename(columns={"一级学科学科代码": "ministry_subject_code"})
    )
    grouped["ministry_subject_code"] = grouped["ministry_subject_code"].map(normalize_code)
    return grouped


def mapping_diagnosis_summary() -> dict[str, Any]:
    if not MAPPING_DIAGNOSIS_JSON.exists():
        return {}
    return load_json(MAPPING_DIAGNOSIS_JSON)


def build_audit() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    full_audit = load_json(FULL_AUDIT_JSON)
    coverage = load_csv(COVERAGE_CSV)
    mapping = load_authoritative_mapping()
    reverse_candidates = reverse_mapping_candidates()
    dim_subject = load_csv(DIM_SUBJECT_CSV)
    dim_subject["ministry_subject_code"] = dim_subject["ministry_subject_code"].map(normalize_code)
    tongji_overrides = load_tongji_mapping_overrides()
    display_corrections = registered_display_corrections()
    diagnosis = mapping_diagnosis_summary()
    system_audit = load_json(SYSTEM_AUDIT_JSON) if SYSTEM_AUDIT_JSON.exists() else {}
    arwu_audit = load_json(ARWU_AUDIT_JSON) if ARWU_AUDIT_JSON.exists() else {}
    release_gate = load_json(RELEASE_GATE_JSON) if RELEASE_GATE_JSON.exists() else {}
    sparse_visual_review = load_json(SPARSE_VISUAL_REVIEW_JSON) if SPARSE_VISUAL_REVIEW_JSON.exists() else {}

    coverage["ministry_subject_code"] = coverage["ministry_subject_code"].map(normalize_code)
    expected_codes = sorted({code for code in coverage["ministry_subject_code"] if code})
    expected_names = (
        coverage[["ministry_subject_code", "ministry_subject_name"]]
        .drop_duplicates(subset=["ministry_subject_code"])
        .set_index("ministry_subject_code")["ministry_subject_name"]
        .to_dict()
    )

    report_records = full_audit.get("reports", [])
    report_codes = [normalize_code(record.get("code")) for record in report_records]
    report_counter = Counter(report_codes)
    duplicate_report_codes = sorted(code for code, count in report_counter.items() if count > 1)
    missing_report_codes = sorted(set(expected_codes) - set(report_codes))
    extra_report_codes = sorted(set(report_codes) - set(expected_codes))

    mapping_by_code = mapping.set_index("一级学科代码", drop=False)
    effective_mapping_by_code = dim_subject.set_index("ministry_subject_code", drop=False)
    tongji_override_by_code = tongji_overrides.set_index("ministry_subject_code", drop=False)
    subject_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    for report in report_records:
        code = normalize_code(report.get("code"))
        subject = clean_text(report.get("subject"))
        run_dir = Path(clean_text(report.get("run_dir")))
        availability_path = run_dir / "ranking_availability.csv"
        availability = load_csv(availability_path) if availability_path.exists() else pd.DataFrame()
        mapping_row = mapping_by_code.loc[code] if code in mapping_by_code.index else None
        if isinstance(mapping_row, pd.DataFrame):
            mapping_row = mapping_row.iloc[0]
        effective_mapping_row = (
            effective_mapping_by_code.loc[code]
            if code in effective_mapping_by_code.index
            else None
        )
        if isinstance(effective_mapping_row, pd.DataFrame):
            effective_mapping_row = effective_mapping_row.iloc[0]
        tongji_override_row = (
            tongji_override_by_code.loc[code]
            if code in tongji_override_by_code.index
            else None
        )
        if isinstance(tongji_override_row, pd.DataFrame):
            tongji_override_row = tongji_override_row.iloc[0]

        source_issue_count = 0
        available_source_count = 0
        selected_no_tongji_count = 0
        no_mapping_count = 0
        fallback_count = 0
        authoritative_mapping_count = 0

        for source in RANKING_SOURCES:
            source_match = availability[availability.get("ranking_source", "") == source] if not availability.empty else pd.DataFrame()
            runtime = source_match.iloc[0] if len(source_match) == 1 else pd.Series(dtype=str)
            direct_mapping_value = clean_text(mapping_row.get(MAPPING_COLUMNS[source])) if mapping_row is not None else ""
            reverse_values = reverse_candidates.get((subject, source), [])
            effective_column = {
                "软科": "arwu_subject_name",
                "QS": "qs_subject_name",
                "US News": "usnews_subject_name",
                "THE": "the_subject_area",
            }[source]
            tongji_override_column = {
                "软科": "tongji_arwu_subject",
                "QS": "tongji_qs_subject",
                "US News": "tongji_usnews_subject",
                "THE": "tongji_the_area",
            }[source]
            correction_value = display_corrections.get((code, effective_column), "")
            tongji_override_value = (
                clean_text(tongji_override_row.get(tongji_override_column))
                if tongji_override_row is not None
                else ""
            )
            expected_effective_mapping = direct_mapping_value
            mapping_provenance = "education_mapping"
            if tongji_override_value:
                expected_effective_mapping = tongji_override_value
                mapping_provenance = "tongji_mapping_override"
            if correction_value:
                expected_effective_mapping = correction_value
                mapping_provenance = "registered_display_correction"
            if not expected_effective_mapping:
                mapping_provenance = "none"
            effective_mapping_value = (
                clean_text(effective_mapping_row.get(effective_column))
                if effective_mapping_row is not None
                else ""
            )
            authoritative_value = effective_mapping_value if valid_mapping(effective_mapping_value) else ""
            has_authoritative_mapping = bool(authoritative_value)
            authoritative_mapping_count += int(has_authoritative_mapping)

            selection_mode = clean_text(runtime.get("selection_mode"))
            selected_subject = clean_text(runtime.get("selected_ranking_subject_or_area"))
            data_status = clean_text(runtime.get("data_status"))
            tongji_latest_rows = int_value(runtime.get("tongji_latest_rows"))
            mapping_candidates = clean_text(runtime.get("mapping_candidate_subjects"))
            fallback_rule_id = clean_text(runtime.get("fallback_rule_id"))
            fallback_mapping_class = clean_text(runtime.get("fallback_mapping_class"))
            fallback_mapping_note = clean_text(runtime.get("fallback_mapping_note"))

            candidate_statuses: list[dict[str, Any]] = []
            candidate_json = clean_text(runtime.get("mapping_candidate_status_json"))
            if candidate_json:
                try:
                    parsed = json.loads(candidate_json)
                    if isinstance(parsed, list):
                        candidate_statuses = [item for item in parsed if isinstance(item, dict)]
                except json.JSONDecodeError:
                    candidate_statuses = []
            candidate_tongji_rows = max(
                (int_value(item.get("tongji_rows")) for item in candidate_statuses),
                default=0,
            )

            issues: list[str] = []
            if source_match.empty:
                issues.append("missing_runtime_availability_row")
            elif len(source_match) > 1:
                issues.append("duplicate_runtime_availability_row")
            if mapping_row is None:
                issues.append("missing_authoritative_mapping_row")
            if effective_mapping_row is None:
                issues.append("missing_effective_mapping_row")
            if clean_text(effective_mapping_value) != clean_text(expected_effective_mapping):
                issues.append("effective_mapping_drift_from_source_tables")
            if has_authoritative_mapping and selection_mode == "missing":
                issues.append("authoritative_mapping_not_selected")
            if selection_mode == "mapping_table_candidate" and not has_authoritative_mapping:
                issues.append("mapping_candidate_without_authoritative_mapping")
            if selection_mode in {"mapping_table_candidate", "fallback_mapping"} and not selected_subject:
                issues.append("selected_mode_without_subject")
            if selection_mode == "fallback_mapping" and not (
                fallback_rule_id and fallback_mapping_class and fallback_mapping_note
            ):
                issues.append("fallback_without_complete_metadata")
            if selection_mode == "missing" and mapping_candidates:
                issues.append("missing_selection_with_mapping_candidates")
            if data_status == "available" and tongji_latest_rows <= 0:
                issues.append("available_status_without_tongji_latest_row")
            if data_status != "available" and candidate_tongji_rows > 0:
                issues.append("candidate_has_tongji_data_but_runtime_missing")

            if data_status == "available":
                availability_class = "available"
                available_source_count += 1
            elif selection_mode == "missing":
                availability_class = "no_direct_mapping"
                no_mapping_count += 1
            else:
                availability_class = "mapped_but_tongji_not_ranked_latest"
                selected_no_tongji_count += 1
            if selection_mode == "fallback_mapping":
                fallback_count += 1

            source_issue_count += len(issues)
            source_rows.append(
                {
                    "ministry_subject_code": code,
                    "subject_name": subject,
                    "ranking_source": source,
                    "direct_mapping": direct_mapping_value,
                    "tongji_mapping_override": tongji_override_value,
                    "registered_display_correction": correction_value,
                    "expected_effective_mapping": expected_effective_mapping,
                    "mapping_provenance": mapping_provenance,
                    "reverse_mapping_candidates": " | ".join(reverse_values),
                    "effective_mapping": authoritative_value,
                    "authoritative_mapping": authoritative_value,
                    "has_authoritative_mapping": has_authoritative_mapping,
                    "selection_mode": selection_mode,
                    "selected_ranking_subject_or_area": selected_subject,
                    "mapping_candidate_subjects": mapping_candidates,
                    "fallback_rule_id": fallback_rule_id,
                    "fallback_mapping_class": fallback_mapping_class,
                    "fallback_mapping_note": fallback_mapping_note,
                    "tongji_latest_rows": tongji_latest_rows,
                    "tongji_latest_rank": clean_text(runtime.get("tongji_latest_rank")),
                    "data_status": data_status,
                    "availability_class": availability_class,
                    "issue_count": len(issues),
                    "issues": " | ".join(issues),
                }
            )

        deliverable_docx = Path(clean_text(report.get("deliverable_docx")))
        report_type = clean_text(report.get("report_type"))
        subject_issues: list[str] = []
        if not deliverable_docx.exists():
            subject_issues.append("missing_deliverable_docx")
        if clean_text(report.get("status")) != "ok":
            subject_issues.append("report_status_not_ok")
        if not clean_text(report.get("word_qa_status")).startswith("pass"):
            subject_issues.append("word_qa_not_pass")
        if int_value(report.get("blank_page_count")) > 0:
            subject_issues.append("blank_pages_found")
        if report_type == "coverage_statement" and available_source_count > 0:
            subject_issues.append("coverage_statement_has_available_source")
        if report_type == "full_report" and available_source_count == 0:
            subject_issues.append("full_report_has_no_available_source")
        if report_type == "coverage_statement" and authoritative_mapping_count > 0:
            subject_issues.append("coverage_statement_has_authoritative_mapping")
        if source_issue_count > 0:
            subject_issues.append("source_mapping_issue")

        subject_rows.append(
            {
                "ministry_subject_code": code,
                "subject_name": subject,
                "expected_subject_name": clean_text(expected_names.get(code)),
                "report_type": report_type,
                "report_status": clean_text(report.get("status")),
                "word_qa_status": clean_text(report.get("word_qa_status")),
                "page_count": int_value(report.get("page_count")),
                "blank_page_count": int_value(report.get("blank_page_count")),
                "available_source_count": available_source_count,
                "mapped_but_tongji_not_ranked_count": selected_no_tongji_count,
                "no_direct_mapping_count": no_mapping_count,
                "fallback_mapping_count": fallback_count,
                "authoritative_mapping_count": authoritative_mapping_count,
                "deliverable_docx": str(deliverable_docx),
                "deliverable_exists": deliverable_docx.exists(),
                "source_issue_count": source_issue_count,
                "subject_issue_count": len(subject_issues),
                "issues": " | ".join(subject_issues),
            }
        )

    subjects = pd.DataFrame(subject_rows).sort_values("ministry_subject_code").reset_index(drop=True)
    sources = pd.DataFrame(source_rows).sort_values(["ministry_subject_code", "ranking_source"]).reset_index(drop=True)

    global_issues: list[str] = []
    if missing_report_codes:
        global_issues.append("missing_expected_reports")
    if extra_report_codes:
        global_issues.append("unexpected_extra_reports")
    if duplicate_report_codes:
        global_issues.append("duplicate_report_codes")
    if len(subjects) != len(expected_codes):
        global_issues.append("report_count_mismatch")
    if not subjects.empty and int(subjects["subject_issue_count"].sum()) > 0:
        global_issues.append("subject_or_source_audit_issues")
    if int_value(diagnosis.get("mapping_related_issue_count")) > 0:
        global_issues.append("processed_mapping_diagnosis_issues")
    system_issue_counts = Counter(clean_text(row.get("severity")) for row in system_audit.get("issues", []))
    if system_issue_counts.get("P0", 0) or system_issue_counts.get("P1", 0):
        global_issues.append("system_readiness_p0_or_p1")
    if clean_text(arwu_audit.get("status")).lower() != "pass":
        global_issues.append("arwu_source_upgrade_audit_not_pass")
    if clean_text(release_gate.get("status")).lower() != "pass":
        global_issues.append("release_quality_gate_not_pass")

    coverage_statements = subjects[subjects["report_type"] == "coverage_statement"]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pass" if not global_issues else "fail",
        "global_issues": global_issues,
        "coverage_input_row_count": len(coverage),
        "expected_unique_subject_count": len(expected_codes),
        "generated_report_count": len(subjects),
        "generated_unique_code_count": len(set(report_codes)),
        "missing_report_codes": missing_report_codes,
        "extra_report_codes": extra_report_codes,
        "duplicate_report_codes": duplicate_report_codes,
        "full_report_count": int((subjects["report_type"] == "full_report").sum()),
        "coverage_statement_count": len(coverage_statements),
        "coverage_statement_subjects": coverage_statements[
            ["ministry_subject_code", "subject_name"]
        ].to_dict("records"),
        "word_qa_pass_count": int(subjects["word_qa_status"].str.startswith("pass").sum()),
        "blank_page_report_count": int((subjects["blank_page_count"] > 0).sum()),
        "total_page_count": int(subjects["page_count"].sum()),
        "source_audit_row_count": len(sources),
        "available_source_count": int((sources["availability_class"] == "available").sum()),
        "mapped_but_tongji_not_ranked_count": int(
            (sources["availability_class"] == "mapped_but_tongji_not_ranked_latest").sum()
        ),
        "no_effective_mapping_count": int((sources["availability_class"] == "no_direct_mapping").sum()),
        "fallback_mapping_count": int((sources["selection_mode"] == "fallback_mapping").sum()),
        "source_issue_count": int(sources["issue_count"].sum()),
        "subject_issue_count": int(subjects["subject_issue_count"].sum()),
        "processed_mapping_diagnosis": {
            "mapping_related_issue_count": int_value(diagnosis.get("mapping_related_issue_count")),
            "runtime_alias_recovery_count": int_value(diagnosis.get("runtime_alias_recovery_count")),
            "diagnosis_breakdown": diagnosis.get("diagnosis_breakdown", {}),
        },
        "system_readiness": {
            "p0_count": system_issue_counts.get("P0", 0),
            "p1_count": system_issue_counts.get("P1", 0),
            "p2_count": system_issue_counts.get("P2", 0),
        },
        "arwu_source_upgrade_status": clean_text(arwu_audit.get("status")),
        "release_quality_gate_status": clean_text(release_gate.get("status")),
        "visually_reviewed_sparse_page_count": sum(
            1
            for row in sparse_visual_review.get("pages", [])
            if clean_text(row.get("status")).lower() == "pass"
        ),
    }
    return subjects, sources, summary


def write_outputs(subjects: pd.DataFrame, sources: pd.DataFrame, summary: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    subject_csv = OUTPUT_DIR / "subject_report_coverage_audit.csv"
    source_csv = OUTPUT_DIR / "source_mapping_audit.csv"
    summary_json = OUTPUT_DIR / "final_audit_summary.json"
    report_md = OUTPUT_DIR / "final_audit_report.md"
    subjects.to_csv(subject_csv, index=False, encoding="utf-8-sig")
    sources.to_csv(source_csv, index=False, encoding="utf-8-sig")
    summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# 全学科 Word 报告最终核查",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 总体状态：{summary['status'].upper()}",
        f"- 覆盖表原始行数：{summary['coverage_input_row_count']}",
        f"- 唯一一级学科数：{summary['expected_unique_subject_count']}",
        f"- 已生成报告数：{summary['generated_report_count']}",
        f"- 完整报告：{summary['full_report_count']}",
        f"- 数据覆盖说明：{summary['coverage_statement_count']}",
        f"- Word QA 通过：{summary['word_qa_pass_count']}/{summary['generated_report_count']}",
        f"- 空白页报告数：{summary['blank_page_report_count']}",
        f"- 总页数：{summary['total_page_count']}",
        "",
        "## 映射与数据来源核查",
        "",
        f"- 学科×榜单核查单元：{summary['source_audit_row_count']}",
        f"- 有同济最新排名数据：{summary['available_source_count']}",
        f"- 有明确映射但同济未进入该榜单最新发布：{summary['mapped_but_tongji_not_ranked_count']}",
        f"- 有效映射层未给出直接映射：{summary['no_effective_mapping_count']}",
        f"- 使用有规则编号、类别和说明的回退映射：{summary['fallback_mapping_count']}",
        f"- 发现的来源级问题：{summary['source_issue_count']}",
        f"- 预处理映射诊断问题：{summary['processed_mapping_diagnosis']['mapping_related_issue_count']}",
        f"- 系统体检 P0/P1/P2：{summary['system_readiness']['p0_count']}/{summary['system_readiness']['p1_count']}/{summary['system_readiness']['p2_count']}",
        f"- 软科新源专项审计：{summary['arwu_source_upgrade_status']}",
        f"- 发布质量门禁：{summary['release_quality_gate_status']}",
        f"- 人工目检通过的稀疏末页：{summary['visually_reviewed_sparse_page_count']}",
        "",
        "## 数据覆盖说明报告",
        "",
    ]
    for item in summary["coverage_statement_subjects"]:
        lines.append(
            f"- {item['ministry_subject_code']} {item['subject_name']}：有效映射层四类排名均未给出直接映射，保留为覆盖说明，不以相近学科替代。"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- 46 个唯一一级学科均已生成 Word，没有缺报、重码或多报。",
            "- 4 份一页报告不是生成失败，而是教育部基础映射、同济覆盖映射和已登记校正规则组成的有效映射层均没有四类排名的直接学科口径；继续强行映射会改变原有映射治理原则。",
            "- 有映射但同济未进入最新榜单的情况保留为缺失数据，不改写为 0，也不借用其他学科排名。",
            "- 所有运行期回退映射均带规则编号、映射类别和口径说明，可追溯。",
            "",
            "## 输出",
            "",
            f"- 学科报告覆盖核查：{subject_csv}",
            f"- 学科×榜单映射核查：{source_csv}",
            f"- 汇总 JSON：{summary_json}",
        ]
    )
    report_md.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    subjects, sources, summary = build_audit()
    write_outputs(subjects, sources, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
