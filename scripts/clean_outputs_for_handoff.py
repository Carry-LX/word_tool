from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs"
CLEANUP_DIR = OUTPUTS_DIR / "handoff_cleanup"

# Explicit variables.
DRY_RUN = False
KEEP_LATEST_FULL_WORD_REPORTS = True
KEEP_REPORT_ARTIFACT_SOURCE_BUNDLES = False
KEEP_REPORT_RENDERED_PAGES = False

ROOT_DIRS_TO_KEEP = {
    "full_word_reports",
    "release_audit",
    "word_openability_audit",
    "agent_system_audit",
    "subject_coverage_audit",
    "missing_data_lineage_review",
    "handoff_cleanup",
}
ROOT_AUDIT_DIRS_KEEP_LATEST_ONLY = {
    "release_audit",
    "word_openability_audit",
    "agent_system_audit",
}
REPORT_FILES_TO_KEEP = {
    "subject_word_report_summary.json",
    "replacement_audit.json",
    "replacement_audit.md",
}
QA_FILES_TO_KEEP = {
    "word_qa_report.json",
    "word_qa_report.md",
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_inside_outputs(path: Path) -> bool:
    resolved_outputs = OUTPUTS_DIR.resolve()
    resolved_path = path.resolve()
    return resolved_path == resolved_outputs or resolved_outputs in resolved_path.parents


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 3)


def remove_path(path: Path, reason: str, removed: list[dict[str, Any]]) -> None:
    if not path.exists():
        return
    if not is_inside_outputs(path):
        raise RuntimeError(f"Refusing to remove outside outputs: {path}")
    size = path_size(path)
    row = {
        "path": str(path),
        "reason": reason,
        "bytes": size,
        "mb": mb(size),
        "dry_run": DRY_RUN,
    }
    removed.append(row)
    if DRY_RUN:
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def code_from_report_dir(path: Path) -> str:
    match = re.search(r"_(\d{4})_", path.name)
    return match.group(1) if match else ""


def latest_report_dirs_by_code() -> dict[str, Path]:
    report_root = OUTPUTS_DIR / "full_word_reports"
    latest: dict[str, Path] = {}
    if not report_root.exists():
        return latest
    for path in report_root.iterdir():
        if not path.is_dir():
            continue
        code = code_from_report_dir(path)
        if not code:
            continue
        if code not in latest or path.stat().st_mtime > latest[code].stat().st_mtime:
            latest[code] = path
    return latest


def clean_full_word_reports(removed: list[dict[str, Any]], kept: list[dict[str, Any]]) -> None:
    report_root = OUTPUTS_DIR / "full_word_reports"
    if not report_root.exists():
        return
    latest_by_code = latest_report_dirs_by_code()
    latest_paths = {path.resolve() for path in latest_by_code.values()} if KEEP_LATEST_FULL_WORD_REPORTS else set()
    for report_dir in sorted([path for path in report_root.iterdir() if path.is_dir()]):
        if KEEP_LATEST_FULL_WORD_REPORTS and report_dir.resolve() not in latest_paths:
            remove_path(report_dir, "old_duplicate_full_word_report_directory", removed)
            continue
        clean_single_report_dir(report_dir, removed)
        docx_count = len([path for path in report_dir.glob("*.docx") if not path.name.startswith("~$")])
        kept.append(
            {
                "path": str(report_dir),
                "kind": "latest_full_word_report",
                "code": code_from_report_dir(report_dir),
                "docx_count": docx_count,
                "mb_after": mb(path_size(report_dir)) if report_dir.exists() else 0,
            }
        )


def clean_single_report_dir(report_dir: Path, removed: list[dict[str, Any]]) -> None:
    for item in list(report_dir.iterdir()):
        if item.is_dir():
            if item.name == "qa":
                clean_qa_dir(item, removed)
            elif item.name == "artifact_source_bundle" and KEEP_REPORT_ARTIFACT_SOURCE_BUNDLES:
                continue
            else:
                remove_path(item, "nonessential_report_subdirectory", removed)
            continue
        if item.name.startswith("~$") or item.name.endswith(".tmp.docx") or item.name.endswith(".pre_normalize.docx"):
            remove_path(item, "temporary_docx_file", removed)
        elif item.suffix.lower() == ".docx":
            continue
        elif item.name in REPORT_FILES_TO_KEEP:
            continue
        else:
            remove_path(item, "nonessential_report_file", removed)


def clean_qa_dir(qa_dir: Path, removed: list[dict[str, Any]]) -> None:
    for item in list(qa_dir.iterdir()):
        if item.is_dir():
            if item.name == "rendered_pages" and KEEP_REPORT_RENDERED_PAGES:
                continue
            remove_path(item, "nonessential_qa_render_artifacts", removed)
        elif item.name not in QA_FILES_TO_KEEP:
            remove_path(item, "nonessential_qa_file", removed)


def clean_root_outputs(removed: list[dict[str, Any]]) -> None:
    if not OUTPUTS_DIR.exists():
        return
    CLEANUP_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted([item for item in OUTPUTS_DIR.iterdir() if item.is_dir()]):
        if path.name not in ROOT_DIRS_TO_KEEP:
            remove_path(path, "nonessential_output_root_directory", removed)


def clean_audit_dirs(removed: list[dict[str, Any]], kept: list[dict[str, Any]]) -> None:
    for name in ROOT_AUDIT_DIRS_KEEP_LATEST_ONLY:
        root = OUTPUTS_DIR / name
        if not root.exists():
            continue
        latest = root / "latest"
        for item in list(root.iterdir()):
            if item.is_dir() and item.resolve() != latest.resolve():
                remove_path(item, "old_audit_subdirectory", removed)
        kept.append({"path": str(root), "kind": "audit_directory", "mb_after": mb(path_size(root))})


def write_cleanup_summary(payload: dict[str, Any]) -> None:
    CLEANUP_DIR.mkdir(parents=True, exist_ok=True)
    (CLEANUP_DIR / "cleanup_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# Handoff Output Cleanup",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- dry_run: {payload['dry_run']}",
        f"- bytes_before: {payload['bytes_before']}",
        f"- bytes_after: {payload['bytes_after']}",
        f"- mb_before: {payload['mb_before']}",
        f"- mb_after: {payload['mb_after']}",
        f"- removed_count: {payload['removed_count']}",
        f"- removed_mb: {payload['removed_mb']}",
        f"- kept_report_count: {payload['kept_report_count']}",
    ]
    (CLEANUP_DIR / "cleanup_summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> dict[str, Any]:
    if not OUTPUTS_DIR.exists():
        raise FileNotFoundError(OUTPUTS_DIR)
    bytes_before = path_size(OUTPUTS_DIR)
    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    clean_root_outputs(removed)
    clean_full_word_reports(removed, kept)
    clean_audit_dirs(removed, kept)
    bytes_after = path_size(OUTPUTS_DIR)
    payload = {
        "generated_at": now_text(),
        "dry_run": DRY_RUN,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "mb_before": mb(bytes_before),
        "mb_after": mb(bytes_after),
        "removed_count": len(removed),
        "removed_bytes": sum(row["bytes"] for row in removed),
        "removed_mb": mb(sum(row["bytes"] for row in removed)),
        "kept_report_count": sum(1 for row in kept if row.get("kind") == "latest_full_word_report"),
        "kept": kept,
        "removed": removed,
    }
    write_cleanup_summary(payload)
    print(json.dumps({key: payload[key] for key in ["mb_before", "mb_after", "removed_count", "removed_mb", "kept_report_count"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
