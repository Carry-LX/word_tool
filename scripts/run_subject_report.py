from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
REQUEST_OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_report_requests"
SOFFICE_WRAPPER_DIR = Path("E:/tools/codex-bin")

# Explicit variables. Leave SUBJECT_CODE empty to use configs/runtime/current_subject_request.json.
SUBJECT_CODE = ""
TARGET_UNIVERSITY = "同济大学"
REPORT_YEAR = 2026
RANKING_SOURCES = ["软科", "QS", "US News", "THE"]
ALLOW_AREA_MAPPING = True
PROXY_POLICY = "allow_with_disclosure"
PEER_SCOPE = "mainland_top200_by_ranking"

RUN_SUBJECT_AGENT_FIRST = True
BUILD_NARRATIVE_BUNDLE = True
GENERATE_NARRATIVE_WITH_LLM = False
USE_DEMO_NARRATIVE_RESULT = False
RUN_WORD_QA = True
RUN_RENDER_QA = True
UPDATE_WORD_FIELDS_WITH_COM = True


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def prepend_soffice_wrapper_to_path() -> None:
    existing = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    filtered = [item for item in existing if Path(item).as_posix().lower() != "e:/tools/libreoffice/program"]
    os.environ["PATH"] = str(SOFFICE_WRAPPER_DIR) + os.pathsep + os.pathsep.join(filtered)


def coverage_row_for_code(code: str) -> dict[str, Any]:
    rows = pd.read_csv(COVERAGE_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    matches = rows[rows["ministry_subject_code"].astype(str).str.zfill(4) == code.zfill(4)]
    if matches.empty:
        raise ValueError(f"Subject code not found in coverage table: {code}")
    return matches.iloc[0].to_dict()


def write_request_from_code(code: str) -> Path:
    row = coverage_row_for_code(code)
    subject = clean_text(row.get("source_subject_name") or row.get("ministry_subject_name"))
    payload = {
        "generated_at": now_text(),
        "request": {
            "target_university": TARGET_UNIVERSITY,
            "target_subject": subject,
            "target_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
            "target_college": clean_text(row.get("college")),
            "report_year": REPORT_YEAR,
            "peer_scope": PEER_SCOPE,
            "ranking_sources": RANKING_SOURCES,
            "allow_area_mapping": ALLOW_AREA_MAPPING,
            "proxy_policy": PROXY_POLICY,
            "source_subject_name": subject,
            "source_generation_status": clean_text(row.get("generation_status_code_after_supplement")),
            "source_proxy_note": clean_text(row.get("supplement_proxy_note")),
        },
    }
    REQUEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = REQUEST_OUTPUT_DIR / f"current_request_{code.zfill(4)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return path


def configure_word_report_module(module: Any) -> None:
    module.RUN_SUBJECT_AGENT_FIRST = RUN_SUBJECT_AGENT_FIRST
    module.BUILD_NARRATIVE_BUNDLE = BUILD_NARRATIVE_BUNDLE
    module.GENERATE_NARRATIVE_WITH_LLM = GENERATE_NARRATIVE_WITH_LLM
    module.USE_DEMO_NARRATIVE_RESULT = USE_DEMO_NARRATIVE_RESULT
    module.RUN_WORD_QA = RUN_WORD_QA
    module.RUN_RENDER_QA = RUN_RENDER_QA
    module.UPDATE_WORD_FIELDS_WITH_COM = UPDATE_WORD_FIELDS_WITH_COM


def main() -> None:
    prepend_soffice_wrapper_to_path()
    if SUBJECT_CODE:
        os.environ["SUBJECT_REQUEST_PATH"] = str(write_request_from_code(SUBJECT_CODE))

    import build_subject_word_report

    configure_word_report_module(build_subject_word_report)
    payload = build_subject_word_report.build_subject_word_report()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
