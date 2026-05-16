from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUT_DIR = PROJECT_DIR / "outputs"
SLOT_MAPPING_CSV = CONFIG_DIR / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"
WORD_TEMPLATE_POLICY_JSON = CONFIG_DIR / "runtime" / "word_template_policy.json"
SUBJECT_PROXY_SUPPLEMENT_CSV = CONFIG_DIR / "runtime" / "tongji_subject_proxy_supplement.csv"
TONGJI_49_COVERAGE_CSV = OUTPUT_DIR / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"


# 显式变量，避免命令行参数成为唯一入口。
SUBJECT_RUN_DIR: Path | None = None


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_artifact_generation(run_dir: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(run_dir / "artifacts" / "artifact_generation_summary.json")
    return {
        clean_text(row.get("artifact_id")): row
        for row in payload.get("results", [])
        if clean_text(row.get("artifact_id"))
    }


def load_artifact_readiness(run_dir: Path) -> dict[str, dict[str, str]]:
    return {
        clean_text(row.get("artifact_id")): row
        for row in read_csv_rows(run_dir / "artifact_readiness.csv")
        if clean_text(row.get("artifact_id"))
    }


def subject_generation_status(summary: dict[str, Any]) -> dict[str, Any]:
    request = summary.get("request", {})
    subject_name = clean_text(request.get("target_subject"))
    subject_code = clean_text(request.get("target_subject_code")).zfill(4)

    for row in read_csv_rows(TONGJI_49_COVERAGE_CSV):
        if clean_text(row.get("source_subject_name")) == subject_name or clean_text(row.get("ministry_subject_code")).zfill(4) == subject_code:
            return {
                "source": str(TONGJI_49_COVERAGE_CSV),
                "generation_status_code": clean_text(row.get("generation_status_code_after_supplement")) or "fallback_full",
                "is_proxy_subject_code": clean_text(row.get("is_proxy_subject_code")).lower() == "true",
                "supplement_proxy_note": clean_text(row.get("supplement_proxy_note")),
                "readiness_status": clean_text(row.get("readiness_status")),
            }

    for row in read_csv_rows(SUBJECT_PROXY_SUPPLEMENT_CSV):
        if clean_text(row.get("source_subject_name")) == subject_name or clean_text(row.get("proxy_ministry_subject_code")).zfill(4) == subject_code:
            return {
                "source": str(SUBJECT_PROXY_SUPPLEMENT_CSV),
                "generation_status_code": "full_ready_via_subject_proxy",
                "is_proxy_subject_code": True,
                "supplement_proxy_note": clean_text(row.get("proxy_scope_note")),
                "readiness_status": "agent_ready",
            }

    blocked = int(summary.get("blocked_or_partial_count") or 0)
    return {
        "source": "agent_run_summary",
        "generation_status_code": "fallback_full" if blocked == 0 else "fallback_partial",
        "is_proxy_subject_code": False,
        "supplement_proxy_note": "",
        "readiness_status": "agent_ready" if blocked == 0 else "partial",
    }


def resolve_template_policy(generation_status: dict[str, Any]) -> dict[str, Any]:
    policy = read_json(WORD_TEMPLATE_POLICY_JSON)
    status_code = clean_text(generation_status.get("generation_status_code")) or "fallback_partial"
    status_policy = policy.get("status_policy", {})
    selected = status_policy.get(status_code) or status_policy.get("fallback_partial") or {}
    template_mode = clean_text(selected.get("template_mode")) or "partial"
    template_rel = policy.get("templates", {}).get(f"{template_mode}_template_docx") or policy.get("templates", {}).get("default_template_docx")
    template_path = PROJECT_DIR / template_rel if template_rel else PROJECT_DIR / "data" / "同济大学XX学科的国际排名发展分析-2026年5月.docx"
    disclosure_text = policy.get("disclosure_text", {}).get(template_mode, "")
    return {
        "status_code": status_code,
        "template_mode": template_mode,
        "template_docx": str(template_path),
        "allow_all_ready_artifacts": bool(selected.get("allow_all_ready_artifacts")),
        "requires_disclosure": bool(selected.get("requires_disclosure")),
        "narrative_tone": clean_text(selected.get("narrative_tone")),
        "disclosure_text": disclosure_text,
        "partial_mode_allowed_sections": policy.get("partial_mode_allowed_sections", []),
        "partial_mode_allowed_artifacts": policy.get("partial_mode_allowed_artifacts", []),
    }


def artifact_output_files(run_dir: Path, artifact_id: str) -> dict[str, str]:
    artifact_dir = run_dir / "artifacts" / artifact_id
    files = {}
    for filename in ["chart.png", "table.png", "chart_data.csv", "table_matrix.csv", "table_data.csv", "source_trace.csv", "chart_spec.json", "table_spec.json", "narrative.md"]:
        path = artifact_dir / filename
        if path.exists():
            files[filename] = str(path)
    return files


def build_slot_decisions(
    run_dir: Path,
    template_policy: dict[str, Any],
    slot_rows: list[dict[str, str]],
    artifact_generation: dict[str, dict[str, Any]],
    artifact_readiness: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    allow_all = bool(template_policy.get("allow_all_ready_artifacts"))
    partial_allowed_sections = set(template_policy.get("partial_mode_allowed_sections", []))
    partial_allowed_artifacts = set(template_policy.get("partial_mode_allowed_artifacts", []))
    decisions = []
    for index, row in enumerate(slot_rows, start=1):
        artifact_id = clean_text(row.get("artifact_id"))
        section = clean_text(row.get("section"))
        generated = artifact_generation.get(artifact_id, {})
        readiness = artifact_readiness.get(artifact_id, {})
        status = clean_text(generated.get("status")) or clean_text(readiness.get("readiness_status")) or "missing"
        source_files = artifact_output_files(run_dir, artifact_id)
        has_visual = "chart.png" in source_files or "table.png" in source_files or "table_matrix.csv" in source_files
        include = status == "generated" and has_visual
        if not allow_all:
            include = include and (artifact_id in partial_allowed_artifacts or section in partial_allowed_sections)
        decisions.append(
            {
                "order": index,
                "logical_slot_id": clean_text(row.get("logical_slot_id")),
                "section": section,
                "slot_kind": clean_text(row.get("slot_kind")),
                "reference_caption": clean_text(row.get("reference_caption")),
                "reference_object": clean_text(row.get("reference_object")),
                "artifact_id": artifact_id,
                "artifact_status": status,
                "readiness_status": clean_text(readiness.get("readiness_status")),
                "include_in_word": include,
                "skip_reason": "" if include else "not_generated_or_excluded_by_template_policy",
                "source_files": source_files,
                "llm_narrative": {
                    "enabled": False,
                    "prompt_template": "configs/template_slot_inventory/narrative_llm_prompt_template.md",
                    "placeholder_mode": True,
                },
            }
        )
    return decisions


def build_manifest(run_dir: Path) -> dict[str, Any]:
    summary = read_json(run_dir / "agent_run_summary.json")
    if not summary:
        raise FileNotFoundError(f"缺少 agent_run_summary.json: {run_dir}")
    generation_status = subject_generation_status(summary)
    template_policy = resolve_template_policy(generation_status)
    slot_rows = read_csv_rows(SLOT_MAPPING_CSV)
    artifact_generation = load_artifact_generation(run_dir)
    artifact_readiness = load_artifact_readiness(run_dir)
    decisions = build_slot_decisions(run_dir, template_policy, slot_rows, artifact_generation, artifact_readiness)
    included = [row for row in decisions if row["include_in_word"]]
    excluded = [row for row in decisions if not row["include_in_word"]]
    subject = summary.get("resolved_subject", {})
    supplement_requires_disclosure = any(
        bool(row.get("requires_disclosure")) for row in subject.get("public_supplements", [])
    ) or any(
        bool(row.get("requires_disclosure")) for row in subject.get("source_runtime_overrides", {}).values()
    )
    if excluded or supplement_requires_disclosure:
        template_policy["requires_disclosure"] = True
        if not clean_text(template_policy.get("disclosure_text")):
            template_policy["disclosure_text"] = "本报告按当前可核验数据生成；缺失图表槽位会移除模板占位内容并写明数据缺口，不套用其他学科图表。"
    payload = {
        "generated_at": now_text(),
        "run_dir": str(run_dir),
        "request": summary.get("request", {}),
        "subject": subject,
        "generation_status": generation_status,
        "template_policy": template_policy,
        "assembly_counts": {
            "slot_count": len(decisions),
            "included_slot_count": len(included),
            "excluded_slot_count": len(excluded),
        },
        "slot_decisions": decisions,
        "maintenance_contract": {
            "single_source_of_truth": "word_assembly_manifest.json",
            "artifact_source": "run_dir/artifacts/<artifact_id>",
            "narrative_generation": "deferred_llm_call",
            "word_writer": "scripts/build_subject_word_report.py",
            "qa_script": "scripts/audit_word_report.py",
        },
    }
    out_path = run_dir / "word_assembly" / "word_assembly_manifest.json"
    write_json(out_path, payload)
    return payload


def main() -> dict[str, Any]:
    if SUBJECT_RUN_DIR is None:
        raise ValueError("请先显式设置 SUBJECT_RUN_DIR，或通过 scripts/build_subject_word_report.py 调用本模块。")
    payload = build_manifest(SUBJECT_RUN_DIR)
    print(json.dumps({"manifest": payload["run_dir"], "assembly_counts": payload["assembly_counts"], "template_mode": payload["template_policy"]["template_mode"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
