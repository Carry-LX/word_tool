from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
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
OUTPUT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
BATCH_ROOT = PROJECT_DIR / "outputs" / "missing_ministry_subject_reports"
BATCH_LIMIT = 12
TARGET_UNIVERSITY = "\u540c\u6d4e\u5927\u5b66"
REPORT_YEAR = 2026


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def batch_dir() -> Path:
    return BATCH_ROOT / ("batch_" + datetime.now().strftime("%Y%m%d_%H%M%S"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def split_sources(value: str) -> list[str]:
    sources = [item.strip() for item in re.split(r"[;\uff1b]", clean_text(value)) if item.strip()]
    return sources or ["\u8f6f\u79d1", "QS", "US News", "THE"]


def existing_output_codes() -> dict[str, list[str]]:
    outputs: dict[str, list[str]] = {}
    if not OUTPUT_ROOT.exists():
        return outputs
    for directory in OUTPUT_ROOT.iterdir():
        if not directory.is_dir():
            continue
        match = re.search(r"_(\d{4})_", directory.name)
        if match:
            outputs.setdefault(match.group(1), []).append(directory.name)
    return outputs


def select_missing_ministry_subjects(limit: int = BATCH_LIMIT) -> list[dict[str, str]]:
    existing_codes = set(existing_output_codes())
    selected: list[dict[str, str]] = []
    seen_codes = set(existing_codes)
    for row_index, row in enumerate(read_csv_rows(COVERAGE_CSV), start=1):
        code = clean_text(row.get("ministry_subject_code"))
        subject = clean_text(row.get("ministry_subject_name"))
        if not code or not subject or code in seen_codes:
            continue
        selected.append(
            {
                "coverage_row": str(row_index),
                "code": code,
                "subject": subject,
                "source_subject": clean_text(row.get("source_subject_name")),
                "college": clean_text(row.get("college")),
                "ranking_sources": clean_text(row.get("ranking_sources")),
                "coverage_ready": clean_text(row.get("full_ready_after_supplement")),
                "coverage_status": clean_text(row.get("generation_status_code_after_supplement")),
                "is_proxy_subject_code": clean_text(row.get("is_proxy_subject_code")),
                "supplement_proxy_note": clean_text(row.get("supplement_proxy_note")),
            }
        )
        seen_codes.add(code)
        if len(selected) >= limit:
            break
    return selected


def render_path_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    path_key = next((key for key in env if key.lower() == "path"), "Path")
    parts = [
        item
        for item in env.get(path_key, "").split(";")
        if item and item.rstrip("\\").lower() != r"e:\tools\libreoffice\program"
    ]
    env[path_key] = r"E:\tools\codex-bin;" + ";".join(parts)
    return env


def request_payload(candidate: dict[str, str]) -> dict[str, Any]:
    return {
        "generated_at": now_text(),
        "request": {
            "target_university": TARGET_UNIVERSITY,
            "target_subject": candidate["subject"],
            "target_subject_code": candidate["code"],
            "target_college": candidate.get("college", ""),
            "report_year": REPORT_YEAR,
            "peer_scope": "mainland_top200_by_ranking",
            "ranking_sources": split_sources(candidate.get("ranking_sources", "")),
            "allow_area_mapping": True,
            "proxy_policy": "allow_with_disclosure",
            "source_subject_name": candidate.get("source_subject", ""),
            "source_coverage_row": candidate.get("coverage_row", ""),
            "source_generation_status": candidate.get("coverage_status", ""),
            "source_proxy_note": candidate.get("supplement_proxy_note", ""),
        },
    }


def find_latest_docx_for_code(code: str) -> Path | None:
    candidates = sorted(
        [path for path in OUTPUT_ROOT.glob(f"*_{code}_*") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for directory in candidates:
        docx_files = sorted(directory.glob("*.docx"), key=lambda path: path.stat().st_mtime, reverse=True)
        if docx_files:
            return docx_files[0]
    return None


def run_one(candidate: dict[str, str], request_dir: Path, log_dir: Path) -> dict[str, Any]:
    code = candidate["code"]
    request_path = request_dir / f"request_{code}.json"
    write_json(request_path, request_payload(candidate))

    inline = (
        "from pathlib import Path; import sys; "
        "sys.path.insert(0, str(Path('scripts').resolve())); "
        "import build_subject_word_report as b; "
        "b.RUN_WORD_QA=True; b.RUN_RENDER_QA=True; "
        "b.GENERATE_NARRATIVE_WITH_LLM=False; b.USE_DEMO_NARRATIVE_RESULT=False; "
        "b.UPDATE_WORD_FIELDS_WITH_COM=True; "
        "b.build_subject_word_report()"
    )
    env = render_path_environment()
    env["SUBJECT_REQUEST_PATH"] = str(request_path)
    started = time.time()
    result = subprocess.run(
        [sys.executable, "-c", inline],
        cwd=str(PROJECT_DIR),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=1800,
    )
    stdout_path = log_dir / f"{code}_stdout.log"
    stderr_path = log_dir / f"{code}_stderr.log"
    stdout_path.write_text(result.stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(result.stderr, encoding="utf-8", newline="\n")
    docx_path = find_latest_docx_for_code(code)
    return {
        **candidate,
        "request_path": str(request_path),
        "returncode": result.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "docx": str(docx_path) if docx_path else "",
    }


def audit_generated(generated: list[dict[str, Any]], audit_dir: Path) -> list[dict[str, Any]]:
    sys.path.insert(0, str((PROJECT_DIR / "scripts").resolve()))
    import audit_word_report

    rows: list[dict[str, Any]] = []
    for item in generated:
        docx_path = Path(clean_text(item.get("docx")))
        if not docx_path.exists():
            rows.append({**item, "audit_status": "missing_docx"})
            continue
        qa = audit_word_report.audit_docx(docx_path, docx_path.parent / "qa_final_rerun", render=True)
        rows.append(
            {
                **item,
                "audit_status": qa.get("overall_status"),
                "warnings": qa.get("warnings", []),
                "zip_status": (qa.get("zip") or {}).get("status"),
                "zip_warnings": (qa.get("zip") or {}).get("warnings", []),
                "bad_xml": (qa.get("zip") or {}).get("bad_text_xml_counts", {}),
                "bad_text": (qa.get("structure") or {}).get("bad_text_pattern_counts", {}),
                "page_count": (qa.get("render") or {}).get("page_count"),
                "blank_pages": (qa.get("render") or {}).get("blank_pages", []),
                "sparse_pages": (qa.get("render") or {}).get("sparse_pages", []),
            }
        )
    write_json(audit_dir / "manual_final_audit.json", {"rows": rows})
    return rows


def write_csv_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "coverage_row",
        "code",
        "subject",
        "source_subject",
        "coverage_ready",
        "coverage_status",
        "is_proxy_subject_code",
        "docx",
        "returncode",
        "audit_status",
        "warnings",
        "zip_status",
        "bad_xml",
        "bad_text",
        "page_count",
        "blank_pages",
        "sparse_pages",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row.get(key), ensure_ascii=False)
                    if isinstance(row.get(key), (dict, list))
                    else row.get(key, "")
                    for key in fieldnames
                }
            )


def main() -> dict[str, Any]:
    current_batch_dir = batch_dir()
    request_dir = current_batch_dir / "requests"
    log_dir = current_batch_dir / "logs"
    audit_dir = current_batch_dir / "manual_final_audit"
    for directory in [request_dir, log_dir, audit_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    selected = select_missing_ministry_subjects()
    write_json(current_batch_dir / "selected_missing_ministry_subjects.json", selected)
    print(f"[{now_text()}] selected {len(selected)} missing ministry subjects", flush=True)

    generated: list[dict[str, Any]] = []
    for candidate in selected:
        print(
            f"[{now_text()}] start {candidate['code']} {candidate['subject']} "
            f"status={candidate.get('coverage_status')}",
            flush=True,
        )
        item = run_one(candidate, request_dir, log_dir)
        generated.append(item)
        write_json(current_batch_dir / "generation_progress.json", generated)
        print(
            f"[{now_text()}] done {item['code']} rc={item['returncode']} "
            f"elapsed={item['elapsed_seconds']} docx={item.get('docx','')}",
            flush=True,
        )

    audit_rows = audit_generated(generated, audit_dir)
    write_csv_summary(audit_dir / "manual_final_audit.csv", audit_rows)
    payload = {
        "batch_dir": str(current_batch_dir),
        "selected_count": len(selected),
        "generated": generated,
        "audit_rows": audit_rows,
    }
    write_json(current_batch_dir / "batch_summary.json", payload)
    print(f"[{now_text()}] complete {current_batch_dir}", flush=True)
    return payload


if __name__ == "__main__":
    main()
