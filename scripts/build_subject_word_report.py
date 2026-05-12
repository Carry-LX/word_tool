from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import audit_word_report
import build_narrative_generation_bundle as narrative_bundle
import build_word_assembly_manifest as assembly_manifest
import build_word_replacement_trial as word_trial
import run_subject_agent as subject_agent


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
NARRATIVE_DEMO_RESULT_JSON = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_generated_demo_20260511.json"

# 显式变量，避免命令行参数成为唯一入口。
RUN_SUBJECT_AGENT_FIRST = True
SUBJECT_RUN_DIR: Path | None = None
BUILD_NARRATIVE_BUNDLE = True
USE_DEMO_NARRATIVE_RESULT = False
RUN_WORD_QA = True
RUN_RENDER_QA = True
TABLE_REPLACEMENT_MODE = "native"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def resolve_run_dir() -> tuple[Path, dict[str, Any]]:
    if RUN_SUBJECT_AGENT_FIRST:
        summary = subject_agent.run_subject_agent()
        return Path(summary["run_dir"]), summary
    if SUBJECT_RUN_DIR is None:
        raise ValueError("RUN_SUBJECT_AGENT_FIRST=False 时必须设置 SUBJECT_RUN_DIR")
    summary_path = SUBJECT_RUN_DIR / "agent_run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    return SUBJECT_RUN_DIR, summary


def prepare_narrative_assets(run_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"bundle_path": "", "result_path": "", "llm_called": False, "demo_result_used": False}
    narrative_dir = run_dir / "narrative_generation"
    narrative_dir.mkdir(parents=True, exist_ok=True)
    if BUILD_NARRATIVE_BUNDLE:
        bundle_path = narrative_bundle.build_bundle(run_dir)
        result["bundle_path"] = str(bundle_path)
    result_path = narrative_dir / "narrative_generation_result.json"
    result["result_path"] = str(result_path)
    if USE_DEMO_NARRATIVE_RESULT and not result_path.exists() and NARRATIVE_DEMO_RESULT_JSON.exists():
        shutil.copyfile(NARRATIVE_DEMO_RESULT_JSON, result_path)
        result["demo_result_used"] = True
    return result


def configure_word_writer(run_dir: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> Path:
    request = summary.get("request") or manifest.get("request", {})
    subject_name = clean_text(request.get("target_subject")) or clean_text(manifest.get("subject", {}).get("target_subject")) or "未命名学科"
    template_docx = Path(manifest.get("template_policy", {}).get("template_docx", ""))
    if not template_docx.is_absolute():
        template_docx = PROJECT_DIR / template_docx
    output_dir = OUTPUT_ROOT / run_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_docx = output_dir / f"同济大学{subject_name}_学科国际排名发展分析.docx"

    word_trial.TEMPLATE_DOCX = template_docx
    word_trial.SUBJECT_RUN_DIR = run_dir
    word_trial.OUTPUT_DIR = output_dir
    word_trial.OUTPUT_DOCX = output_docx
    word_trial.REPLACEMENT_LOG_JSON = output_dir / "replacement_log.json"
    word_trial.REPLACEMENT_AUDIT_JSON = output_dir / "replacement_audit.json"
    word_trial.REPLACEMENT_AUDIT_MD = output_dir / "replacement_audit.md"
    word_trial.TABLE_REPLACEMENT_MODE = TABLE_REPLACEMENT_MODE
    return output_docx


def build_subject_word_report() -> dict[str, Any]:
    run_dir, subject_summary = resolve_run_dir()
    manifest = assembly_manifest.build_manifest(run_dir)
    narrative_assets = prepare_narrative_assets(run_dir)
    output_docx = configure_word_writer(run_dir, manifest, subject_summary)
    word_trial.main()

    qa_result = {}
    if RUN_WORD_QA:
        qa_result = audit_word_report.audit_docx(
            output_docx,
            output_docx.parent / "qa",
            render=RUN_RENDER_QA,
        )

    payload = {
        "generated_at": now_text(),
        "run_dir": str(run_dir),
        "request": subject_summary.get("request", manifest.get("request", {})),
        "word_output_dir": str(output_docx.parent),
        "word_output_docx": str(output_docx),
        "assembly_manifest": str(run_dir / "word_assembly" / "word_assembly_manifest.json"),
        "template_mode": manifest.get("template_policy", {}).get("template_mode"),
        "requires_disclosure": manifest.get("template_policy", {}).get("requires_disclosure"),
        "narrative_assets": narrative_assets,
        "artifact_summary": subject_summary.get("parameterized_artifacts", {}),
        "artifact_audit": subject_summary.get("subject_artifact_audit", {}),
        "word_replacement_audit": str(word_trial.REPLACEMENT_AUDIT_JSON),
        "word_qa": qa_result,
    }
    write_json(output_docx.parent / "subject_word_report_summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    build_subject_word_report()
