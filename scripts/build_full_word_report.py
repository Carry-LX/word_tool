from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import build_narrative_generation_bundle as narrative_bundle
import build_word_replacement_trial as word_trial
import run_subject_agent as subject_agent


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
FULL_OUTPUT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
SUMMARY_JSON_NAME = "full_word_report_summary.json"
NARRATIVE_DEMO_RESULT_JSON = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_generated_demo_20260511.json"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def safe_slug(value: str) -> str:
    cleaned = clean_text(value)
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in cleaned) or "subject"


def configure_word_trial(summary: dict[str, Any]) -> Path:
    run_dir = Path(summary["run_dir"])
    request = summary.get("request", {})
    subject_name = clean_text(request.get("target_subject")) or "未命名学科"
    run_slug = run_dir.name

    output_dir = FULL_OUTPUT_ROOT / run_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    output_docx = output_dir / f"同济大学{subject_name}_已替换报告.docx"

    word_trial.SUBJECT_RUN_DIR = run_dir
    word_trial.OUTPUT_DIR = output_dir
    word_trial.OUTPUT_DOCX = output_docx
    word_trial.REPLACEMENT_LOG_JSON = output_dir / "replacement_log.json"
    word_trial.REPLACEMENT_AUDIT_JSON = output_dir / "replacement_audit.json"
    word_trial.REPLACEMENT_AUDIT_MD = output_dir / "replacement_audit.md"

    return output_docx


def prepare_narrative_generation_assets(run_dir: Path) -> Path:
    narrative_dir = run_dir / "narrative_generation"
    narrative_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = narrative_bundle.build_bundle(run_dir)
    result_path = narrative_dir / "narrative_generation_result.json"
    if not result_path.exists() and NARRATIVE_DEMO_RESULT_JSON.exists():
        shutil.copyfile(NARRATIVE_DEMO_RESULT_JSON, result_path)
    return bundle_path


def build_full_report() -> dict[str, Any]:
    subject_summary = subject_agent.run_subject_agent()
    prepare_narrative_generation_assets(Path(subject_summary["run_dir"]))
    output_docx = configure_word_trial(subject_summary)
    word_trial.main()

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "request": subject_summary.get("request", {}),
        "run_dir": subject_summary.get("run_dir", ""),
        "word_output_dir": str(word_trial.OUTPUT_DIR),
        "word_output_docx": str(output_docx),
        "artifact_ready_count": subject_summary.get("ready_artifact_count", 0),
        "artifact_total_count": subject_summary.get("artifact_count", 0),
        "audit": subject_summary.get("subject_artifact_audit", {}),
    }
    summary_path = word_trial.OUTPUT_DIR / SUMMARY_JSON_NAME
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(output_docx)
    return payload


if __name__ == "__main__":
    build_full_report()
