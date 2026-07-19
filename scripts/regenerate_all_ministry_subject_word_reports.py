from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import subprocess
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
RUN_SUBJECT_REPORT_SCRIPT = PROJECT_DIR / "scripts" / "run_subject_report.py"

# Keep this empty for all unique ministry subjects from COVERAGE_CSV.
ONLY_CODES: list[str] = []

RUN_RENDER_QA = True
RUN_WORD_QA = True
RUN_SUBJECT_AGENT_FIRST = True
BUILD_NARRATIVE_BUNDLE = True
GENERATE_NARRATIVE_WITH_LLM = False
USE_DEMO_NARRATIVE_RESULT = False
UPDATE_WORD_FIELDS_WITH_COM = False
NORMALIZE_DOCX_FOR_WORD_OPEN = False
BATCH_PROGRESS_EVERY = 5


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def slug_text(value: Any) -> str:
    text = clean_text(value).lower()
    chars = [char if char.isalnum() else "_" for char in text]
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "subject"


def read_ministry_subjects() -> list[dict[str, str]]:
    with COVERAGE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    subjects: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        code = clean_text(row.get("ministry_subject_code")).zfill(4)
        subject = clean_text(row.get("ministry_subject_name")) or clean_text(row.get("source_subject_name"))
        if not code or not subject:
            continue
        subjects.setdefault(
            (code, subject),
            {
                "code": code,
                "subject": subject,
                "college": clean_text(row.get("college")),
                "source_subject_name": clean_text(row.get("source_subject_name")),
                "source_generation_status": clean_text(row.get("generation_status_code_after_supplement")),
                "source_proxy_note": clean_text(row.get("supplement_proxy_note")),
            },
        )
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


def print_progress(message: str) -> None:
    print(f"[{now_text()}] {message}", flush=True)


def request_payload_for_subject(row: dict[str, str]) -> dict[str, Any]:
    target_subject = clean_text(row.get("subject")) or clean_text(row.get("source_subject_name"))
    source_subject = clean_text(row.get("source_subject_name")) or target_subject
    return {
        "generated_at": now_text(),
        "request": {
            "target_university": "同济大学",
            "target_subject": target_subject,
            "target_subject_code": clean_text(row.get("code")).zfill(4),
            "target_college": clean_text(row.get("college")),
            "report_year": 2026,
            "peer_scope": "mainland_top200_by_ranking",
            "ranking_sources": ["软科", "QS", "US News", "THE"],
            "allow_area_mapping": True,
            "proxy_policy": "allow_with_disclosure",
            "source_subject_name": source_subject,
            "source_generation_status": clean_text(row.get("source_generation_status")),
            "source_proxy_note": clean_text(row.get("source_proxy_note")),
        },
    }


def parse_child_payload(stdout_path: Path) -> dict[str, Any]:
    text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return {}
    decoder = json.JSONDecoder()
    payloads: list[dict[str, Any]] = []
    for match in re.finditer(r"(?m)^\{", text):
        try:
            payload, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    for payload in reversed(payloads):
        if payload.get("word_output_docx"):
            return payload
    return payloads[-1] if payloads else {}


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


def run_subject_report_child(request_path: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["SUBJECT_REQUEST_PATH"] = str(request_path)
    env["PYTHONIOENCODING"] = "utf-8"
    env["RUN_SUBJECT_AGENT_FIRST"] = "1" if RUN_SUBJECT_AGENT_FIRST else "0"
    env["BUILD_NARRATIVE_BUNDLE"] = "1" if BUILD_NARRATIVE_BUNDLE else "0"
    env["GENERATE_NARRATIVE_WITH_LLM"] = "1" if GENERATE_NARRATIVE_WITH_LLM else "0"
    env["USE_DEMO_NARRATIVE_RESULT"] = "1" if USE_DEMO_NARRATIVE_RESULT else "0"
    env["RUN_WORD_QA"] = "1" if RUN_WORD_QA else "0"
    env["RUN_RENDER_QA"] = "1" if RUN_RENDER_QA else "0"
    env["UPDATE_WORD_FIELDS_WITH_COM"] = "1" if UPDATE_WORD_FIELDS_WITH_COM else "0"
    env["NORMALIZE_DOCX_FOR_WORD_OPEN"] = "1" if NORMALIZE_DOCX_FOR_WORD_OPEN else "0"
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout_handle:
        with stderr_path.open("w", encoding="utf-8", newline="\n") as stderr_handle:
            completed = subprocess.run(
                [sys.executable, str(RUN_SUBJECT_REPORT_SCRIPT)],
                cwd=str(PROJECT_DIR),
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
            )
    if completed.returncode != 0:
        raise RuntimeError(f"run_subject_report.py exited with code {completed.returncode}")
    return parse_child_payload(stdout_path)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    prepend_soffice_wrapper_to_path()
    sys.path.insert(0, str((PROJECT_DIR / "scripts").resolve()))

    word_report = None
    if not RUN_SUBJECT_AGENT_FIRST:
        import build_subject_word_report as word_report

    batch_dir = BATCH_OUTPUT_ROOT / ("batch_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_dir = batch_dir / "logs"
    request_dir = batch_dir / "requests"
    batch_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    request_dir.mkdir(parents=True, exist_ok=True)

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
    print_progress(f"batch started: total={len(subjects)}, batch_dir={batch_dir}")

    for index, row in enumerate(subjects, start=1):
        code = row["code"]
        subject = row["subject"]
        run_dir = run_dirs_by_subject.get((code, subject)) or run_dirs_by_code.get(code)
        progress["current_code"] = code
        progress["current_subject"] = subject
        progress["current_index"] = index
        progress["completed"] = index - 1
        write_json(batch_dir / "progress.json", progress)
        print_progress(f"start {index}/{len(subjects)} {code} {subject}")
        if not RUN_SUBJECT_AGENT_FIRST and run_dir is None:
            item = {"code": code, "subject": subject, "status": "missing_subject_run_dir"}
            progress["failed"] += 1
            progress["results"].append(item)
            write_json(batch_dir / "progress.json", progress)
            continue

        stdout_path = log_dir / f"{code}_stdout.log"
        stderr_path = log_dir / f"{code}_stderr.log"
        try:
            if RUN_SUBJECT_AGENT_FIRST:
                request_path = request_dir / f"current_request_{code}.json"
                write_json(request_path, request_payload_for_subject(row))
                payload = run_subject_report_child(request_path, stdout_path, stderr_path)
                run_dir = Path(clean_text(payload.get("run_dir")))
            else:
                if word_report is None:
                    raise RuntimeError("word_report module was not loaded for existing-run mode.")
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
            item["request_path"] = str(request_path) if RUN_SUBJECT_AGENT_FIRST else ""
            item["stdout_log"] = str(stdout_path)
            item["stderr_log"] = str(stderr_path)
            progress["results"].append(item)
            print_progress(
                f"done {index}/{len(subjects)} {code} {subject}: "
                f"status={item.get('overall_status') or item.get('status')}, docx={bool(item.get('docx'))}"
            )
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
            print_progress(f"error {index}/{len(subjects)} {code} {subject}: {exc}")
        progress["completed"] = index
        progress["last_progress_at"] = now_text()
        write_json(batch_dir / "progress.json", progress)
        if index % BATCH_PROGRESS_EVERY == 0 or index == len(subjects):
            ok_count = sum(1 for item in progress["results"] if item.get("status") == "ok")
            print_progress(
                f"batch progress: completed={index}/{len(subjects)}, ok={ok_count}, "
                f"failed={progress['failed']}"
            )

    progress["finished_at"] = now_text()
    progress["current_code"] = ""
    progress["current_subject"] = ""
    write_json(batch_dir / "progress.json", progress)
    write_json(batch_dir / "summary.json", progress)
    print_progress(f"batch finished: completed={progress['completed']}/{progress['total']}, failed={progress['failed']}")
    print(json.dumps(progress, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
