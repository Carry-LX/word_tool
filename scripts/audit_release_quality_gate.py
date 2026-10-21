from __future__ import annotations

import json
import re
import csv
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
FULL_WORD_REPORTS_DIR = PROJECT_DIR / "outputs" / "full_word_reports"
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
LINEAGE_REVIEW_JSON = PROJECT_DIR / "outputs" / "missing_data_lineage_review" / "missing_data_lineage_review_summary.json"
SYSTEM_AUDIT_JSON = PROJECT_DIR / "outputs" / "agent_system_audit" / "latest" / "agent_system_readiness.json"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "release_audit" / "latest"
SPARSE_PAGE_VISUAL_REVIEW_JSON = (
    PROJECT_DIR
    / "outputs"
    / "final_subject_report_delivery_audit_20260928"
    / "sparse_page_visual_review.json"
)

# Explicit variables. Keep empty to check all latest report directories.
ONLY_CODES: list[str] = []
ALLOW_PASS_WITH_WARNINGS = True
REPORT_BASIS = "ministry_subject"  # ministry_subject or coverage_subject


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_coverage_subjects() -> list[dict[str, str]]:
    if not COVERAGE_CSV.exists():
        return []
    subjects: list[dict[str, str]] = []
    with COVERAGE_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            code = clean_text(row.get("ministry_subject_code")).zfill(4)
            source_name = clean_text(row.get("source_subject_name"))
            ministry_name = clean_text(row.get("ministry_subject_name")) or source_name
            if not code:
                continue
            if ONLY_CODES and code not in {item.zfill(4) for item in ONLY_CODES}:
                continue
            subjects.append(
                {
                    "code": code,
                    "name": source_name or ministry_name,
                    "source_subject_name": source_name,
                    "ministry_subject_name": ministry_name,
                    "readiness_status": clean_text(row.get("readiness_status")),
                    "generation_status": clean_text(row.get("generation_status_code_after_supplement")),
                    "is_proxy_subject_code": clean_text(row.get("is_proxy_subject_code")),
                }
            )
    return subjects


def expected_subjects_from_coverage(coverage_subjects: list[dict[str, str]]) -> list[dict[str, Any]]:
    if REPORT_BASIS == "coverage_subject":
        return [dict(row, report_basis="coverage_subject") for row in coverage_subjects]
    if REPORT_BASIS != "ministry_subject":
        raise ValueError("REPORT_BASIS must be 'ministry_subject' or 'coverage_subject'.")

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in coverage_subjects:
        name = row["ministry_subject_name"] or row["source_subject_name"] or row["name"]
        key = (row["code"], name)
        item = by_key.setdefault(
            key,
            {
                **row,
                "name": name,
                "report_basis": "ministry_subject",
                "proxy_source_subjects": [],
            },
        )
        source_name = row["source_subject_name"]
        if source_name and source_name != name:
            item["proxy_source_subjects"].append(source_name)
    return sorted(by_key.values(), key=lambda item: (item["code"], item["name"]))


def code_from_dir(path: Path) -> str:
    match = re.search(r"_(\d{4})_", path.name)
    return match.group(1) if match else ""


def subject_name_from_dir(path: Path) -> str:
    match = re.match(r"^\d{8}_\d{6}_(\d{4})_(.+)$", path.name)
    return match.group(2).strip() if match else ""


def is_newer_report(path: Path, current: Path | None) -> bool:
    return current is None or path.stat().st_mtime > current.stat().st_mtime


def page_number_from_path(value: str) -> int:
    match = re.search(r"page-(\d+)", Path(value).stem)
    return int(match.group(1)) if match else 0


def split_sparse_pages(render: dict[str, Any]) -> tuple[list[str], list[str]]:
    page_count = int(render.get("page_count") or 0)
    frontmatter_sparse: list[str] = []
    blocking_sparse: list[str] = []
    for page in render.get("sparse_pages") or []:
        page_number = page_number_from_path(page)
        if page_number and page_number <= 3:
            frontmatter_sparse.append(page)
        elif page_count and page_number == page_count:
            blocking_sparse.append(page)
        else:
            blocking_sparse.append(page)
    return frontmatter_sparse, blocking_sparse


def visually_reviewed_sparse_pages() -> set[tuple[str, str]]:
    review = read_json(SPARSE_PAGE_VISUAL_REVIEW_JSON)
    return {
        (clean_text(row.get("code")).zfill(4), Path(clean_text(row.get("page"))).name)
        for row in review.get("pages", [])
        if clean_text(row.get("status")).lower() == "pass"
    }


def latest_report_dirs() -> tuple[dict[str, Path], dict[tuple[str, str], Path]]:
    latest_by_code: dict[str, Path] = {}
    latest_by_subject: dict[tuple[str, str], Path] = {}
    if not FULL_WORD_REPORTS_DIR.exists():
        return latest_by_code, latest_by_subject
    for path in FULL_WORD_REPORTS_DIR.iterdir():
        if not path.is_dir():
            continue
        code = code_from_dir(path)
        if not code:
            continue
        if ONLY_CODES and code not in {item.zfill(4) for item in ONLY_CODES}:
            continue
        subject_name = subject_name_from_dir(path)
        if is_newer_report(path, latest_by_code.get(code)):
            latest_by_code[code] = path
        if subject_name:
            key = (code, subject_name)
            if is_newer_report(path, latest_by_subject.get(key)):
                latest_by_subject[key] = path
    return latest_by_code, latest_by_subject


def report_status(code: str, report_dir: Path, expected_subject_name: str = "") -> dict[str, Any]:
    docx_files = sorted(report_dir.glob("*.docx"), key=lambda item: item.stat().st_mtime, reverse=True)
    qa = read_json(report_dir / "qa" / "word_qa_report.json")
    qa_source = "qa/word_qa_report.json"
    if not qa:
        summary = read_json(report_dir / "subject_word_report_summary.json")
        qa = summary.get("word_qa") or {}
        qa_source = "subject_word_report_summary.json:word_qa" if qa else "missing"
    render = qa.get("render") or {}
    status = str(qa.get("overall_status") or "missing_qa")
    acceptable_statuses = {"pass"}
    if ALLOW_PASS_WITH_WARNINGS:
        acceptable_statuses.add("pass_with_warnings")
    blocking = []
    if not docx_files:
        blocking.append("missing_docx")
    if status not in acceptable_statuses:
        blocking.append(f"qa_status_{status}")
    if render.get("blank_pages"):
        blocking.append("blank_pages")
    frontmatter_sparse_pages, blocking_sparse_pages = split_sparse_pages(render)
    reviewed_keys = visually_reviewed_sparse_pages()
    visually_reviewed_pages = [
        page
        for page in blocking_sparse_pages
        if (code, Path(page).name) in reviewed_keys
    ]
    blocking_sparse_pages = [
        page
        for page in blocking_sparse_pages
        if (code, Path(page).name) not in reviewed_keys
    ]
    if blocking_sparse_pages:
        blocking.append("sparse_pages")
    return {
        "code": code,
        "expected_subject_name": expected_subject_name,
        "report_subject_name": subject_name_from_dir(report_dir),
        "report_dir": str(report_dir),
        "docx": str(docx_files[0]) if docx_files else "",
        "qa_source": qa_source,
        "qa_status": status,
        "warnings": qa.get("warnings") or [],
        "page_count": render.get("page_count"),
        "blank_pages": render.get("blank_pages") or [],
        "sparse_pages": render.get("sparse_pages") or [],
        "frontmatter_sparse_pages": frontmatter_sparse_pages,
        "visually_reviewed_sparse_pages": visually_reviewed_pages,
        "blocking_sparse_pages": blocking_sparse_pages,
        "blocking_issues": blocking,
        "pass": not blocking,
    }


def build_gate() -> dict[str, Any]:
    latest_by_code, latest_by_subject = latest_report_dirs()
    coverage_subjects = load_coverage_subjects()
    expected_subjects = expected_subjects_from_coverage(coverage_subjects)
    expected_code_counts: dict[str, int] = {}
    for row in expected_subjects:
        expected_code_counts[row["code"]] = expected_code_counts.get(row["code"], 0) + 1
    if expected_subjects:
        reports = []
        missing_report_subjects = []
        for row in sorted(expected_subjects, key=lambda item: (item["code"], item["name"])):
            code = row["code"]
            name = row["name"]
            report_dir = latest_by_subject.get((code, name))
            if report_dir is None and expected_code_counts.get(code, 0) == 1:
                report_dir = latest_by_code.get(code)
            if report_dir is None:
                missing_report_subjects.append(row)
                continue
            reports.append(report_status(code, report_dir, name))
    else:
        reports = [report_status(code, path) for code, path in sorted(latest_by_code.items())]
        missing_report_subjects = []
    lineage = read_json(LINEAGE_REVIEW_JSON)
    system_audit = read_json(SYSTEM_AUDIT_JSON)
    blocking_reports = [row for row in reports if not row["pass"]]
    expected_subject_keys = {(row["code"], row["name"]) for row in expected_subjects}
    unexpected_report_subjects = [
        {"code": code, "name": name, "report_dir": str(path)}
        for (code, name), path in sorted(latest_by_subject.items())
        if expected_subjects and (code, name) not in expected_subject_keys
    ]
    pipeline_issue_count = int(lineage.get("potential_pipeline_issue_count") or 0)
    raw_issue_count = int(lineage.get("raw_utilization_issue_count") or 0)
    status = "pass"
    blockers = []
    if blocking_reports:
        blockers.append("word_report_failures")
    if missing_report_subjects:
        blockers.append("missing_expected_word_reports")
    if pipeline_issue_count:
        blockers.append("potential_pipeline_issues")
    if raw_issue_count:
        blockers.append("raw_utilization_issues")
    if blockers:
        status = "fail"
    payload = {
        "generated_at": now_text(),
        "status": status,
        "blockers": blockers,
        "report_basis": REPORT_BASIS,
        "coverage_row_count": len(coverage_subjects),
        "expected_report_count": len(expected_subjects),
        "report_count": len(reports),
        "missing_report_count": len(missing_report_subjects),
        "proxy_source_subject_count": sum(len(row.get("proxy_source_subjects") or []) for row in expected_subjects),
        "blocking_report_count": len(blocking_reports),
        "potential_pipeline_issue_count": pipeline_issue_count,
        "raw_utilization_issue_count": raw_issue_count,
        "system_audit_generated_at": system_audit.get("generated_at", ""),
        "missing_report_subjects": missing_report_subjects,
        "unexpected_report_subjects": unexpected_report_subjects,
        "reports": reports,
        "inputs": {
            "full_word_reports_dir": str(FULL_WORD_REPORTS_DIR),
            "coverage_csv": str(COVERAGE_CSV),
            "lineage_review_json": str(LINEAGE_REVIEW_JSON),
            "system_audit_json": str(SYSTEM_AUDIT_JSON),
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "release_quality_gate.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# Release Quality Gate",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- status: {payload['status']}",
        f"- report_basis: {payload['report_basis']}",
        f"- coverage_row_count: {payload['coverage_row_count']}",
        f"- expected_report_count: {payload['expected_report_count']}",
        f"- report_count: {payload['report_count']}",
        f"- missing_report_count: {payload['missing_report_count']}",
        f"- proxy_source_subject_count: {payload['proxy_source_subject_count']}",
        f"- blocking_report_count: {payload['blocking_report_count']}",
        f"- potential_pipeline_issue_count: {pipeline_issue_count}",
        f"- raw_utilization_issue_count: {raw_issue_count}",
    ]
    if missing_report_subjects:
        lines.extend(["", "## Missing Reports", ""])
        for row in missing_report_subjects:
            lines.append(f"- {row['code']} {row['name']} ({row['generation_status']})")
    (OUTPUT_DIR / "release_quality_gate.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    build_gate()
