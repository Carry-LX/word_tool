from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
COVERAGE_CSV = (
    PROJECT_DIR
    / "outputs"
    / "subject_coverage_audit"
    / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
)
SUBJECT_RUN_ROOT = PROJECT_DIR / "outputs" / "subject_agent_runs"
BATCH_OUTPUT_ROOT = PROJECT_DIR / "outputs" / "regenerate_all_ministry_subject_word_reports"
SOFFICE_WRAPPER_DIR = Path("E:/tools/codex-bin")

# Keep this empty for all unique ministry subjects from COVERAGE_CSV.
ONLY_CODES: list[str] = []

RUN_RENDER_QA = True
RUN_WORD_QA = True
RUN_SUBJECT_AGENT_FIRST = False
BUILD_NARRATIVE_BUNDLE = True
GENERATE_NARRATIVE_WITH_LLM = False
USE_DEMO_NARRATIVE_RESULT = False
UPDATE_WORD_FIELDS_WITH_COM = True


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def read_ministry_subjects() -> list[dict[str, str]]:
    with COVERAGE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    subjects: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        code = clean_text(row.get("ministry_subject_code")).zfill(4)
        subject = clean_text(row.get("ministry_subject_name")) or clean_text(row.get("source_subject_name"))
        if not code or not subject:
            continue
        subjects.setdefault((code, subject), {"code": code, "subject": subject})
    result = [subjects[key] for key in sorted(subjects)]
    if ONLY_CODES:
        wanted = {code.zfill(4) for code in ONLY_CODES}
        result = [row for row in result if row["code"] in wanted]
    return result


def subject_name_from_dir(path: Path) -> str:
    match = re.match(r"^\d{8}_\d{6}_(\d{4})_(.+)$", path.name)
    return match.group(2).strip() if match else ""


def latest_run_dirs_by_subject() -> tuple[dict[str, Path], dict[tuple[str, str], Path]]:
    by_code: dict[str, Path] = {}
    by_subject: dict[tuple[str, str], Path] = {}
    for run_dir in SUBJECT_RUN_ROOT.glob("*"):
        if not run_dir.is_dir():
            continue
        match = re.search(r"_(\d{4})_", run_dir.name)
        if not match:
            continue
        if not (run_dir / "agent_run_summary.json").exists():
            continue
        code = match.group(1)
        if code not in by_code or run_dir.stat().st_mtime > by_code[code].stat().st_mtime:
            by_code[code] = run_dir
        subject = subject_name_from_dir(run_dir)
        if subject:
            key = (code, subject)
            if key not in by_subject or run_dir.stat().st_mtime > by_subject[key].stat().st_mtime:
                by_subject[key] = run_dir
    return by_code, by_subject


def prepend_soffice_wrapper_to_path() -> None:
    existing = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    filtered = [item for item in existing if Path(item).as_posix().lower() != "e:/tools/libreoffice/program"]
    os.environ["PATH"] = str(SOFFICE_WRAPPER_DIR) + os.pathsep + os.pathsep.join(filtered)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def compact_summary(code: str, run_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    qa = payload.get("word_qa") or {}
    render = qa.get("render") or {}
    return {
        "code": code,
        "run_dir": str(run_dir),
        "docx": clean_text(payload.get("word_output_docx")),
        "overall_status": clean_text(qa.get("overall_status")),
        "warnings": qa.get("warnings") or [],
        "render_status": clean_text(render.get("status")),
        "page_count": render.get("page_count"),
        "blank_pages": render.get("blank_pages") or [],
        "sparse_pages": render.get("sparse_pages") or [],
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    prepend_soffice_wrapper_to_path()
    sys.path.insert(0, str((PROJECT_DIR / "scripts").resolve()))

    import build_subject_word_report as word_report

    batch_dir = BATCH_OUTPUT_ROOT / ("batch_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_dir = batch_dir / "logs"
    batch_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    subjects = read_ministry_subjects()
    run_dirs_by_code, run_dirs_by_subject = latest_run_dirs_by_subject()
    selected = [
        {
            "code": row["code"],
            "subject": row["subject"],
            "run_dir": str(run_dirs_by_subject.get((row["code"], row["subject"])) or run_dirs_by_code.get(row["code"], "")),
        }
        for row in subjects
    ]
    write_json(batch_dir / "selected_subject_runs.json", selected)

    progress = {
        "started_at": now_text(),
        "batch_dir": str(batch_dir),
        "total": len(subjects),
        "completed": 0,
        "failed": 0,
        "current_code": "",
        "results": [],
    }
    write_json(batch_dir / "progress.json", progress)

    for index, row in enumerate(subjects, start=1):
        code = row["code"]
        subject = row["subject"]
        run_dir = run_dirs_by_subject.get((code, subject)) or run_dirs_by_code.get(code)
        progress["current_code"] = code
        progress["completed"] = index - 1
        write_json(batch_dir / "progress.json", progress)
        if run_dir is None:
            item = {"code": code, "subject": subject, "status": "missing_subject_run_dir"}
            progress["failed"] += 1
            progress["results"].append(item)
            write_json(batch_dir / "progress.json", progress)
            continue

        stdout_path = log_dir / f"{code}_stdout.log"
        stderr_path = log_dir / f"{code}_stderr.log"
        try:
            word_report.RUN_SUBJECT_AGENT_FIRST = RUN_SUBJECT_AGENT_FIRST
            word_report.SUBJECT_RUN_DIR = run_dir
            word_report.BUILD_NARRATIVE_BUNDLE = BUILD_NARRATIVE_BUNDLE
            word_report.GENERATE_NARRATIVE_WITH_LLM = GENERATE_NARRATIVE_WITH_LLM
            word_report.USE_DEMO_NARRATIVE_RESULT = USE_DEMO_NARRATIVE_RESULT
            word_report.RUN_WORD_QA = RUN_WORD_QA
            word_report.RUN_RENDER_QA = RUN_RENDER_QA
            word_report.UPDATE_WORD_FIELDS_WITH_COM = UPDATE_WORD_FIELDS_WITH_COM
            with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout_handle:
                with stderr_path.open("w", encoding="utf-8", newline="\n") as stderr_handle:
                    with contextlib.redirect_stdout(stdout_handle), contextlib.redirect_stderr(stderr_handle):
                        payload = word_report.build_subject_word_report()
            item = compact_summary(code, run_dir, payload)
            item["subject"] = subject
            item["status"] = "ok"
            item["stdout_log"] = str(stdout_path)
            item["stderr_log"] = str(stderr_path)
            progress["results"].append(item)
        except Exception as exc:
            stderr_path.write_text(traceback.format_exc(), encoding="utf-8", newline="\n")
            progress["failed"] += 1
            progress["results"].append(
                {
                    "code": code,
                    "run_dir": str(run_dir),
                    "status": "error",
                    "error": str(exc),
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                }
            )
        progress["completed"] = index
        write_json(batch_dir / "progress.json", progress)

    progress["finished_at"] = now_text()
    progress["current_code"] = ""
    write_json(batch_dir / "progress.json", progress)
    write_json(batch_dir / "summary.json", progress)
    print(json.dumps(progress, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
