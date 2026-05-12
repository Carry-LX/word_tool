from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
SLOT_MAPPING_CSV = PROJECT_DIR / "configs" / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"
NARRATIVE_MAPPING_JSON = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_paragraph_mapping.json"
SUBJECT_RUNS_ROOT = PROJECT_DIR / "outputs" / "subject_agent_runs"


def latest_subject_run_dir() -> Path:
    return max((path for path in SUBJECT_RUNS_ROOT.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_slot_mapping() -> list[dict[str, str]]:
    return read_csv_rows(SLOT_MAPPING_CSV)


def read_narrative_mapping() -> list[dict[str, Any]]:
    payload = json.loads(NARRATIVE_MAPPING_JSON.read_text(encoding="utf-8"))
    return payload.get("paragraph_mappings", [])


def artifact_preview_rows(artifact_dir: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for filename in ("chart_data.csv", "table_data.csv", "chart_plot_data.csv", "peer_indicator_long.csv"):
        path = artifact_dir / filename
        if not path.exists():
            continue
        rows = read_csv_rows(path)
        result[filename] = rows[:5]
    return result


def artifact_narrative_text(artifact_dir: Path) -> str:
    path = artifact_dir / "narrative.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def build_bundle(subject_run_dir: Path | None = None) -> Path:
    subject_run_dir = subject_run_dir or latest_subject_run_dir()
    artifact_root = subject_run_dir / "artifacts"
    output_dir = subject_run_dir / "narrative_generation"
    output_dir.mkdir(parents=True, exist_ok=True)

    slot_mapping_by_id = {row["logical_slot_id"]: row for row in read_slot_mapping()}
    tasks: list[dict[str, Any]] = []

    for slot_item in read_narrative_mapping():
        slot_id = str(slot_item.get("logical_slot_id", "")).strip()
        if not slot_id or str(slot_item.get("replace_decision", "replace")) != "replace":
            continue
        slot_row = slot_mapping_by_id.get(slot_id, {})
        artifact_id = str(slot_item.get("artifact_id", "")).strip()
        artifact_dir = artifact_root / artifact_id
        preview = artifact_preview_rows(artifact_dir)
        narrative = artifact_narrative_text(artifact_dir)
        source_files = []
        for filename in ("chart_data.csv", "table_data.csv", "chart_spec.json", "table_spec.json", "source_trace.csv", "narrative.md"):
            path = artifact_dir / filename
            if path.exists():
                source_files.append(str(path))
        for paragraph in slot_item.get("paragraphs", []):
            tasks.append(
                {
                    "logical_slot_id": slot_id,
                    "artifact_id": artifact_id,
                    "slot_kind": slot_row.get("slot_kind", ""),
                    "segment_key": paragraph.get("segment_key", ""),
                    "reference_caption": slot_item.get("reference_caption", ""),
                    "template_paragraph_index": paragraph.get("template_paragraph_index", ""),
                    "position_relative_to_caption": paragraph.get("position_relative_to_caption", ""),
                    "generation_hint": paragraph.get("generation_hint", ""),
                    "template_text": paragraph.get("template_text", ""),
                    "artifact_narrative": narrative,
                    "data_preview": preview,
                    "source_files": source_files,
                }
            )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subject_run_dir": str(subject_run_dir),
        "prompt_template": str(PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_llm_prompt_template.md"),
        "output_template": str(PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_llm_output_template.json"),
        "task_count": len(tasks),
        "tasks": tasks,
    }

    output_path = output_dir / "narrative_generation_bundle.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(output_path)
    return output_path


if __name__ == "__main__":
    build_bundle()
