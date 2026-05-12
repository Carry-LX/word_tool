from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
REGISTRY_PATH = PROJECT_DIR / "configs" / "artifact_registry.yaml"
AUDIT_DIR = PROJECT_DIR / "configs" / "artifact_audit"
LOG_DIR = PROJECT_DIR / "logs"

AUDIT_JSON_PATH = AUDIT_DIR / "artifact_audit_report.json"
AUDIT_CSV_PATH = AUDIT_DIR / "artifact_audit_report.csv"
AUDIT_MD_PATH = AUDIT_DIR / "artifact_audit_report.md"
RUN_LOG_PATH = LOG_DIR / "artifact_audit_run_log.md"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_is_nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def count_csv_rows(path: Path) -> int | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
        return max(0, len(rows) - 1)
    except Exception:
        return None


def audit_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_id = artifact["artifact_id"]
    script_path = PROJECT_DIR / artifact["script_path"]
    output_dir = PROJECT_DIR / artifact["output_dir"]
    spec_path = output_dir / artifact["spec_file"]

    errors: list[str] = []
    warnings: list[str] = []
    file_status: list[dict[str, Any]] = []

    if not script_path.exists():
        errors.append(f"missing script: {artifact['script_path']}")
    if not output_dir.exists():
        errors.append(f"missing output_dir: {artifact['output_dir']}")

    for required_file in artifact.get("required_outputs", []):
        path = output_dir / required_file
        exists = path.exists()
        nonempty = file_is_nonempty(path)
        row_count = count_csv_rows(path) if required_file.endswith(".csv") else None
        file_status.append(
            {
                "file": required_file,
                "required": True,
                "exists": exists,
                "nonempty": nonempty,
                "size_bytes": path.stat().st_size if exists else 0,
                "csv_rows": row_count,
            }
        )
        if not exists:
            errors.append(f"missing required output: {required_file}")
        elif not nonempty:
            errors.append(f"empty required output: {required_file}")

    for optional_file in artifact.get("optional_outputs", []):
        path = output_dir / optional_file
        exists = path.exists()
        file_status.append(
            {
                "file": optional_file,
                "required": False,
                "exists": exists,
                "nonempty": file_is_nonempty(path) if exists else False,
                "size_bytes": path.stat().st_size if exists else 0,
                "csv_rows": count_csv_rows(path) if optional_file.endswith(".csv") and exists else None,
            }
        )
        if not exists:
            warnings.append(f"missing optional output: {optional_file}")

    spec = {}
    if spec_path.exists():
        try:
            spec = read_json_file(spec_path)
            if spec.get("artifact_id") != artifact_id:
                errors.append(f"spec artifact_id mismatch: {spec.get('artifact_id')}")
        except Exception as exc:
            errors.append(f"spec parse failed: {exc}")
    else:
        errors.append(f"missing spec file: {artifact['spec_file']}")

    source_trace_path = output_dir / "source_trace.csv"
    source_trace_rows = count_csv_rows(source_trace_path)
    if source_trace_rows is None:
        errors.append("source_trace.csv is not readable")
    elif source_trace_rows == 0:
        errors.append("source_trace.csv has zero data rows")

    primary_data_file = "chart_data.csv" if artifact["artifact_type"] == "chart" else "table_data.csv"
    primary_data_rows = count_csv_rows(output_dir / primary_data_file)
    if primary_data_rows is None:
        errors.append(f"{primary_data_file} is not readable")
    elif primary_data_rows == 0:
        errors.append(f"{primary_data_file} has zero data rows")

    dependency_status = []
    for dependency in artifact.get("data_dependencies", []):
        dep_path = PROJECT_DIR / dependency
        exists = dep_path.exists()
        dependency_status.append({"path": dependency, "exists": exists, "size_bytes": dep_path.stat().st_size if exists else 0})
        if not exists:
            errors.append(f"missing dependency: {dependency}")

    status = "pass" if not errors else "fail"
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact["artifact_type"],
        "registry_status": artifact.get("status", ""),
        "audit_status": status,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "script_exists": script_path.exists(),
        "output_dir_exists": output_dir.exists(),
        "spec_file": artifact["spec_file"],
        "primary_data_file": primary_data_file,
        "primary_data_rows": primary_data_rows,
        "source_trace_rows": source_trace_rows,
        "file_status": file_status,
        "dependency_status": dependency_status,
        "spec_summary": {
            "generated_at": spec.get("generated_at", ""),
            "target_subject": spec.get("target_subject", ""),
            "target_university": spec.get("target_university", ""),
            "raw_match_rows_before_alias_dedup": spec.get("raw_match_rows_before_alias_dedup", ""),
        },
    }


def write_csv_report(results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "artifact_id",
        "artifact_type",
        "registry_status",
        "audit_status",
        "error_count",
        "warning_count",
        "primary_data_file",
        "primary_data_rows",
        "source_trace_rows",
        "script_exists",
        "output_dir_exists",
    ]
    with AUDIT_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({field: result.get(field, "") for field in fieldnames})


def write_markdown_report(results: list[dict[str, Any]], generated_at: str) -> None:
    pass_count = sum(1 for result in results if result["audit_status"] == "pass")
    fail_count = len(results) - pass_count
    lines = [
        "# Artifact 输出审计报告",
        "",
        f"- generated_at: {generated_at}",
        f"- registry: `{REGISTRY_PATH}`",
        f"- artifact_count: {len(results)}",
        f"- pass: {pass_count}",
        f"- fail: {fail_count}",
        "",
        "## 总览",
        "",
        "| artifact_id | type | status | data_rows | source_trace_rows | errors | warnings |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result["artifact_id"],
                    result["artifact_type"],
                    result["audit_status"],
                    str(result["primary_data_rows"]),
                    str(result["source_trace_rows"]),
                    str(result["error_count"]),
                    str(result["warning_count"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 详情", ""])
    for result in results:
        lines.extend(
            [
                f"### {result['artifact_id']}",
                "",
                f"- audit_status: {result['audit_status']}",
                f"- script_exists: {result['script_exists']}",
                f"- output_dir_exists: {result['output_dir_exists']}",
                f"- primary_data_file: {result['primary_data_file']}",
                f"- primary_data_rows: {result['primary_data_rows']}",
                f"- source_trace_rows: {result['source_trace_rows']}",
            ]
        )
        if result["errors"]:
            lines.append(f"- errors: {'; '.join(result['errors'])}")
        if result["warnings"]:
            lines.append(f"- warnings: {'; '.join(result['warnings'])}")
        lines.append("")

    AUDIT_MD_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def build_audit() -> dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = now_text()

    registry = read_json_file(REGISTRY_PATH)
    results = [audit_artifact(artifact) for artifact in registry.get("artifacts", [])]
    pass_count = sum(1 for result in results if result["audit_status"] == "pass")
    fail_count = len(results) - pass_count

    report = {
        "generated_at": generated_at,
        "registry_path": str(REGISTRY_PATH),
        "artifact_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "results": results,
    }
    AUDIT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    write_csv_report(results)
    write_markdown_report(results, generated_at)

    if not RUN_LOG_PATH.exists():
        RUN_LOG_PATH.write_text("# Artifact 审计过程留档\n", encoding="utf-8", newline="\n")
    with RUN_LOG_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"\n## {generated_at}\n\n"
            f"- artifact_count: {len(results)}\n"
            f"- pass_count: {pass_count}\n"
            f"- fail_count: {fail_count}\n"
            f"- report: `{AUDIT_MD_PATH}`\n"
        )

    return {
        "artifact_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "report_dir": str(AUDIT_DIR),
    }


def main() -> None:
    summary = build_audit()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
