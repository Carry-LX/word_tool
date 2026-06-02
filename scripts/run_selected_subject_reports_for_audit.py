from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Explicit audit batch. Keep values as ASCII subject codes; names are read from UTF-8 project data.
SUBJECT_CODES = ["0202", "0710", "0805"]

# Full Word is still generated and render-QA checked. These two post-processing steps are skipped
# because they only affect local Word/COM normalization and often time out in the agent session.
RUN_WORD_QA = True
RUN_RENDER_QA = True
UPDATE_WORD_FIELDS_WITH_COM = False
NORMALIZE_DOCX_FOR_WORD_OPEN = False
GENERATE_NARRATIVE_WITH_LLM = False
USE_DEMO_NARRATIVE_RESULT = False


def configure_word_builder(module: Any) -> None:
    module.RUN_SUBJECT_AGENT_FIRST = True
    module.BUILD_NARRATIVE_BUNDLE = True
    module.GENERATE_NARRATIVE_WITH_LLM = GENERATE_NARRATIVE_WITH_LLM
    module.USE_DEMO_NARRATIVE_RESULT = USE_DEMO_NARRATIVE_RESULT
    module.RUN_WORD_QA = RUN_WORD_QA
    module.RUN_RENDER_QA = RUN_RENDER_QA
    module.UPDATE_WORD_FIELDS_WITH_COM = UPDATE_WORD_FIELDS_WITH_COM
    module.NORMALIZE_DOCX_FOR_WORD_OPEN = NORMALIZE_DOCX_FOR_WORD_OPEN


def run_one(code: str) -> dict[str, Any]:
    import run_subject_report

    request_path = run_subject_report.write_request_from_code(code)
    os.environ["SUBJECT_REQUEST_PATH"] = str(request_path.resolve())

    # These modules read SUBJECT_REQUEST_PATH at import time.
    if "run_subject_agent" in sys.modules:
        importlib.reload(sys.modules["run_subject_agent"])
    else:
        import run_subject_agent  # noqa: F401

    if "build_subject_word_report" in sys.modules:
        build_subject_word_report = importlib.reload(sys.modules["build_subject_word_report"])
    else:
        import build_subject_word_report

    configure_word_builder(build_subject_word_report)
    payload = build_subject_word_report.build_subject_word_report()
    return {
        "code": code,
        "request_path": str(request_path),
        "run_dir": payload.get("run_dir", ""),
        "word_output_dir": payload.get("word_output_dir", ""),
        "word_output_docx": payload.get("word_output_docx", ""),
        "word_qa": (payload.get("word_qa") or {}).get("overall_status", ""),
        "replacement_audit": payload.get("word_replacement_audit", ""),
        "lineage_status": (payload.get("artifact_lineage") or {}).get("status", ""),
    }


def main() -> list[dict[str, Any]]:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    rows = [run_one(code) for code in SUBJECT_CODES]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


if __name__ == "__main__":
    main()
