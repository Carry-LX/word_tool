from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import agent_runtime


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = agent_runtime.load_runtime_profile()
SUBJECT_REQUEST = agent_runtime.load_subject_request(RUNTIME_PROFILE)

PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
AUDIT_DIR = agent_runtime.profile_path(
    RUNTIME_PROFILE,
    "paths.agent_system_audit_dir",
    PROJECT_DIR / "outputs" / "agent_system_audit",
)
LATEST_AUDIT_DIR = AUDIT_DIR / "latest"

CORE_TABLES = [
    "dim_subject",
    "dim_subject_alias",
    "dim_university",
    "fact_ranking",
    "fact_indicator_weight",
    "fact_ranking_indicator",
    "fact_paper_metric",
    "mapping_registry",
    "external_source_registry",
    "artifact_data_contract",
]

GOVERNANCE_FILES = [
    CONFIG_DIR / "runtime" / "agent_runtime_profile.json",
    CONFIG_DIR / "runtime" / "current_subject_request.json",
    CONFIG_DIR / "runtime" / "subject_request_schema.yaml",
    CONFIG_DIR / "runtime" / "query_contract.md",
    CONFIG_DIR / "runtime" / "manual_subject_aliases.json",
    CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json",
    CONFIG_DIR / "runtime" / "legacy_script_registry.json",
    CONFIG_DIR / "data_governance" / "data_layer_maintainability_audit.md",
]

SCRIPT_RISK_PATTERNS = {
    "hardcoded_subject": re.compile(r'^\s*TARGET_SUBJECT\s*=\s*"[^"]+"', re.MULTILINE),
    "hardcoded_subject_code": re.compile(r'^\s*TARGET_SUBJECT_CODE\s*=\s*"[^"]+"', re.MULTILINE),
    "math_only_branch": re.compile(r'数学|0701|math', re.IGNORECASE),
    "direct_project_excel_read": re.compile(r"data[\\/].+\.(xlsx|xls|csv)", re.IGNORECASE),
    "absolute_local_path": re.compile(r"[A-Z]:[\\/][^\"')\s]+"),
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def add_issue(issues: list[dict[str, Any]], severity: str, area: str, item: str, message: str, recommendation: str) -> None:
    issues.append(
        {
            "severity": severity,
            "area": area,
            "item": item,
            "message": message,
            "recommendation": recommendation,
        }
    )


def audit_runtime_config(issues: list[dict[str, Any]]) -> dict[str, Any]:
    request_issues = agent_runtime.validate_subject_request(SUBJECT_REQUEST)
    for issue in request_issues:
        add_issue(
            issues,
            issue["severity"],
            "runtime_config",
            issue["field"],
            issue["message"],
            "Update configs/runtime/current_subject_request.json before running the report agent.",
        )
    render_qa = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.run_render_qa", False)
    if not render_qa:
        add_issue(
            issues,
            "P2",
            "qa",
            "word_pipeline.run_render_qa",
            "Render QA is disabled in the runtime profile.",
            "Keep it disabled on machines without LibreOffice, but enable it in delivery environments so DOCX pages are visually checked automatically.",
        )
    return {
        "profile_path": RUNTIME_PROFILE.get("_profile_path", ""),
        "subject_request_path": SUBJECT_REQUEST.get("_request_path", ""),
        "target_university": SUBJECT_REQUEST.get("target_university", ""),
        "target_subject": SUBJECT_REQUEST.get("target_subject", ""),
        "target_subject_code": SUBJECT_REQUEST.get("target_subject_code", ""),
        "report_year": SUBJECT_REQUEST.get("report_year", ""),
        "ranking_sources": SUBJECT_REQUEST.get(
            "ranking_sources",
            agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", []),
        ),
    }


def sqlite_row_counts(sqlite_path: Path, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sqlite_path.exists():
        add_issue(
            issues,
            "P0",
            "data_layer",
            "ranking.sqlite",
            "Processed ranking database is missing.",
            "Run the data ingestion pipeline before any subject report generation.",
        )
        return []
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(sqlite_path) as conn:
        for table in CORE_TABLES:
            csv_path = PROCESSED_DIR / f"{table}.csv"
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                status = "ok" if count > 0 else "empty"
            except sqlite3.Error as exc:
                if csv_path.exists():
                    count = max(sum(1 for _ in csv_path.open("r", encoding="utf-8-sig", errors="ignore")) - 1, 0)
                    status = f"csv_fallback_ok: {exc}"
                else:
                    count = 0
                    status = f"missing_or_invalid: {exc}"
            rows.append({"table": table, "row_count": count, "status": status})
            if count == 0:
                add_issue(
                    issues,
                    "P0" if table.startswith("fact_") or table in {"dim_subject", "dim_subject_alias"} else "P1",
                    "data_layer",
                    table,
                    f"{table} has no queryable rows.",
                    "Regenerate processed data and confirm this table is populated.",
                )
            elif status.startswith("csv_fallback_ok"):
                add_issue(
                    issues,
                    "P2",
                    "data_layer",
                    table,
                    f"{table} is available as CSV but not queryable in ranking.sqlite.",
                    "This is acceptable for current scripts, but production deployment should either document the CSV fallback or load the table into SQLite.",
                )
    return rows


def audit_governance_files(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for path in GOVERNANCE_FILES:
        exists = path.exists()
        rows.append({"path": str(path), "exists": exists, "bytes": path.stat().st_size if exists else 0})
        if not exists:
            add_issue(
                issues,
                "P1",
                "governance",
                str(path.relative_to(PROJECT_DIR)),
                "Expected governance/configuration file is missing.",
                "Restore or recreate this file so new users can understand the data and runtime contract.",
            )
    return rows


def audit_subject_mapping(issues: list[dict[str, Any]]) -> dict[str, Any]:
    dim_subject = PROCESSED_DIR / "dim_subject.csv"
    alias = PROCESSED_DIR / "dim_subject_alias.csv"
    if not dim_subject.exists() or not alias.exists():
        add_issue(
            issues,
            "P0",
            "cross_subject",
            "subject_mapping",
            "Subject dimension or alias table is missing.",
            "Regenerate processed subject mapping tables.",
        )
        return {"subject_count": 0, "alias_count": 0, "subjects_without_alias": 0}
    subjects = pd.read_csv(dim_subject, dtype=str).fillna("")
    aliases = pd.read_csv(alias, dtype=str).fillna("")
    subject_ids = set(subjects.get("subject_id", pd.Series(dtype=str)).astype(str))
    alias_ids = set(aliases.get("subject_id", pd.Series(dtype=str)).astype(str))
    missing = sorted(subject_ids - alias_ids)
    if missing:
        add_issue(
            issues,
            "P1",
            "cross_subject",
            "subjects_without_alias",
            f"{len(missing)} subjects have no ranking alias rows.",
            "Add scoped aliases in the alias registry before promising these subjects to external users.",
        )
    registry_path = PROCESSED_DIR / "mapping_registry.csv"
    confidence_columns: list[str] = []
    if registry_path.exists():
        registry = pd.read_csv(registry_path, dtype=str).fillna("")
        confidence_columns = [col for col in registry.columns if "confidence" in col.lower() or "evidence" in col.lower()]
        if not confidence_columns:
            add_issue(
                issues,
                "P1",
                "mapping_governance",
                "mapping_registry",
                "Mapping registry exists but no confidence/evidence column was detected.",
                "Add confidence/evidence/scope fields so cross-discipline mappings can be disclosed and audited.",
            )
    return {
        "subject_count": len(subjects),
        "alias_count": len(aliases),
        "subjects_without_alias": len(missing),
        "sample_subjects_without_alias": missing[:10],
        "mapping_confidence_columns": confidence_columns,
    }


def latest_run_summary() -> dict[str, Any]:
    runs_dir = agent_runtime.profile_path(
        RUNTIME_PROFILE,
        "paths.subject_agent_runs_dir",
        PROJECT_DIR / "outputs" / "subject_agent_runs",
    )
    summaries = sorted(runs_dir.glob("*/agent_run_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not summaries:
        return {}
    payload = json.loads(summaries[0].read_text(encoding="utf-8"))
    payload["_summary_path"] = str(summaries[0])
    return payload


def audit_latest_run(issues: list[dict[str, Any]]) -> dict[str, Any]:
    summary = latest_run_summary()
    if not summary:
        add_issue(
            issues,
            "P1",
            "operations",
            "latest_subject_run",
            "No subject agent run summary was found.",
            "Run scripts/run_subject_agent.py once after changing the runtime profile.",
        )
        return {}
    artifact_count = int(summary.get("artifact_count", 0) or 0)
    ready_count = int(summary.get("ready_artifact_count", 0) or 0)
    fail_count = int(summary.get("subject_artifact_audit", {}).get("fail_count", 0) or 0)
    if artifact_count and ready_count < artifact_count:
        add_issue(
            issues,
            "P1",
            "artifact_pipeline",
            "artifact_readiness",
            f"Only {ready_count}/{artifact_count} artifacts were marked ready in the latest run.",
            "Use the generated data_gap_report.csv to decide whether to supplement data or disable the corresponding slot.",
        )
    if fail_count:
        add_issue(
            issues,
            "P0",
            "artifact_pipeline",
            "artifact_visual_audit",
            f"{fail_count} generated artifacts failed audit in the latest run.",
            "Fix artifact builders before generating a delivery DOCX.",
        )
    return {
        "summary_path": summary.get("_summary_path", ""),
        "run_dir": summary.get("run_dir", ""),
        "request": summary.get("request", {}),
        "ready_artifact_count": ready_count,
        "artifact_count": artifact_count,
        "artifact_audit": summary.get("subject_artifact_audit", {}),
    }


def audit_script_risks(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry_path = CONFIG_DIR / "runtime" / "legacy_script_registry.json"
    registry = {}
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8")).get("scripts", {})
    rows: list[dict[str, Any]] = []
    for path in sorted((PROJECT_DIR / "scripts").glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = {name: len(pattern.findall(text)) for name, pattern in SCRIPT_RISK_PATTERNS.items()}
        total = sum(counts.values())
        if total:
            rel_path = path.relative_to(PROJECT_DIR).as_posix()
            legacy = registry.get(rel_path, {})
            rows.append(
                {
                    "path": str(path),
                    "registered_legacy_status": legacy.get("status", ""),
                    "replacement": legacy.get("replacement", ""),
                    **counts,
                    "total_risk_hits": total,
                }
            )
    severe = [
        row
        for row in rows
        if (row.get("hardcoded_subject", 0) or row.get("hardcoded_subject_code", 0))
        and not row.get("registered_legacy_status")
    ]
    if severe:
        add_issue(
            issues,
            "P1",
            "maintainability",
            "script_hardcoding",
            f"{len(severe)} unregistered scripts still look like they contain subject constants.",
            "Move remaining subject and code constants behind the runtime profile or a typed subject request loader.",
        )
    registered_legacy = [row for row in rows if row.get("registered_legacy_status")]
    if registered_legacy:
        add_issue(
            issues,
            "P2",
            "maintainability",
            "registered_legacy_scripts",
            f"{len(registered_legacy)} legacy scripts are registered and excluded from default cross-subject entrypoints.",
            "Keep them for traceability, but migrate useful logic into scripts/subject_artifact_builders.py before reusing it.",
        )
    math_hits = sum(row.get("math_only_branch", 0) for row in rows)
    if math_hits:
        add_issue(
            issues,
            "P2",
            "cross_subject",
            "math_only_branches",
            f"Detected {math_hits} possible mathematics-specific branches across scripts.",
            "Keep verified branches gated, but progressively replace them with source-driven artifact builders.",
        )
    return rows


def audit_coverage_outputs(issues: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        OUTPUTS_DIR / "subject_coverage_audit",
        PROCESSED_DIR / "qa",
    ]
    files: list[Path] = []
    for directory in candidates:
        if directory.exists():
            files.extend(directory.glob("*.csv"))
    latest_files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    if not latest_files:
        add_issue(
            issues,
            "P2",
            "cross_subject",
            "coverage_audit",
            "No reusable cross-subject coverage CSV was found.",
            "Maintain a 49-subject coverage audit output so onboarding users know which subjects are production-ready.",
        )
    return {"latest_coverage_files": [str(path) for path in latest_files]}


def build_markdown(payload: dict[str, Any]) -> str:
    issues = payload["issues"]
    severity_counts = Counter(issue["severity"] for issue in issues)
    lines = [
        "# Agent System Readiness Audit",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- profile: {payload['runtime_config']['profile_path']}",
        f"- subject_request: {payload['runtime_config']['subject_request_path']}",
        f"- target: {payload['runtime_config']['target_university']} / {payload['runtime_config']['target_subject']} ({payload['runtime_config']['target_subject_code']})",
        f"- issue_counts: {dict(severity_counts)}",
        "",
        "## Priority Issues",
        "",
        "| severity | area | item | message | recommendation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for issue in sorted(issues, key=lambda row: row["severity"]):
        lines.append(
            f"| {issue['severity']} | {issue['area']} | {issue['item']} | {issue['message']} | {issue['recommendation']} |"
        )
    lines.extend(
        [
            "",
            "## Data Layer",
            "",
            "| table | row_count | status |",
            "| --- | ---: | --- |",
        ]
    )
    for row in payload["data_layer"]["sqlite_tables"]:
        lines.append(f"| {row['table']} | {row['row_count']} | {row['status']} |")
    mapping = payload["cross_subject_mapping"]
    lines.extend(
        [
            "",
            "## Cross Subject Mapping",
            "",
            f"- subject_count: {mapping['subject_count']}",
            f"- alias_count: {mapping['alias_count']}",
            f"- subjects_without_alias: {mapping['subjects_without_alias']}",
            f"- mapping_confidence_columns: {mapping['mapping_confidence_columns']}",
            "",
            "## Latest Run",
            "",
            f"- summary_path: {payload['latest_run'].get('summary_path', '')}",
            f"- run_dir: {payload['latest_run'].get('run_dir', '')}",
            f"- ready_artifacts: {payload['latest_run'].get('ready_artifact_count', 0)}/{payload['latest_run'].get('artifact_count', 0)}",
            "",
            "## Generated Files",
            "",
            f"- JSON: {payload['outputs']['json']}",
            f"- CSV: {payload['outputs']['issues_csv']}",
            f"- script_risk_csv: {payload['outputs']['script_risk_csv']}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_audit() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    runtime_config = audit_runtime_config(issues)
    data_rows = sqlite_row_counts(PROCESSED_DIR / "ranking.sqlite", issues)
    governance_files = audit_governance_files(issues)
    mapping = audit_subject_mapping(issues)
    latest_run = audit_latest_run(issues)
    script_risks = audit_script_risks(issues)
    coverage = audit_coverage_outputs(issues)

    payload = {
        "generated_at": now_text(),
        "runtime_config": runtime_config,
        "data_layer": {"sqlite_tables": data_rows},
        "governance_files": governance_files,
        "cross_subject_mapping": mapping,
        "latest_run": latest_run,
        "script_risks": script_risks,
        "coverage_outputs": coverage,
        "issues": issues,
        "outputs": {
            "json": str(LATEST_AUDIT_DIR / "agent_system_readiness.json"),
            "markdown": str(LATEST_AUDIT_DIR / "agent_system_readiness.md"),
            "issues_csv": str(LATEST_AUDIT_DIR / "agent_system_issues.csv"),
            "script_risk_csv": str(LATEST_AUDIT_DIR / "script_risk_scan.csv"),
        },
    }
    LATEST_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(LATEST_AUDIT_DIR / "agent_system_readiness.json", payload)
    write_csv(
        LATEST_AUDIT_DIR / "agent_system_issues.csv",
        issues,
        ["severity", "area", "item", "message", "recommendation"],
    )
    risk_fields = [
        "path",
        "registered_legacy_status",
        "replacement",
        "hardcoded_subject",
        "hardcoded_subject_code",
        "math_only_branch",
        "direct_project_excel_read",
        "absolute_local_path",
        "total_risk_hits",
    ]
    write_csv(LATEST_AUDIT_DIR / "script_risk_scan.csv", script_risks, risk_fields)
    (LATEST_AUDIT_DIR / "agent_system_readiness.md").write_text(build_markdown(payload), encoding="utf-8", newline="\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_audit(), ensure_ascii=False, indent=2))
