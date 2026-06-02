from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import audit_word_report
import agent_runtime
import build_artifact_lineage_manifest
import build_narrative_generation_bundle as narrative_bundle
import generate_narrative_with_llm as narrative_llm
import build_word_assembly_manifest as assembly_manifest
import build_word_replacement_trial as word_trial
import run_subject_agent as subject_agent


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = agent_runtime.load_runtime_profile()
OUTPUT_ROOT = agent_runtime.profile_path(
    RUNTIME_PROFILE,
    "paths.full_word_reports_dir",
    PROJECT_DIR / "outputs" / "full_word_reports",
)
NARRATIVE_DEMO_RESULT_JSON = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_generated_demo_20260511.json"

# 显式变量仍然保留，但默认值来自 configs/runtime/agent_runtime_profile.json。
RUN_SUBJECT_AGENT_FIRST = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.run_subject_agent_first", True)
configured_subject_run_dir = agent_runtime.deep_get(RUNTIME_PROFILE, "word_pipeline.subject_run_dir", "")
SUBJECT_RUN_DIR: Path | None = (
    agent_runtime.resolve_project_path(configured_subject_run_dir)
    if str(configured_subject_run_dir).strip()
    else None
)
BUILD_NARRATIVE_BUNDLE = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.build_narrative_bundle", True)
GENERATE_NARRATIVE_WITH_LLM = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.narrative_llm.enabled", False)
USE_DEMO_NARRATIVE_RESULT = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.use_demo_narrative_result", False)
RUN_WORD_QA = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.run_word_qa", True)
RUN_RENDER_QA = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.run_render_qa", False)
UPDATE_WORD_FIELDS_WITH_COM = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.update_word_fields_with_com", True)
NORMALIZE_DOCX_FOR_WORD_OPEN = agent_runtime.profile_bool(RUNTIME_PROFILE, "word_pipeline.normalize_docx_for_word_open", True)
TABLE_REPLACEMENT_MODE = agent_runtime.profile_str(RUNTIME_PROFILE, "word_pipeline.table_replacement_mode", "native")
ARTIFACT_DATA_BUNDLE_DIRNAME = "artifact_source_bundle"
ARTIFACT_DATA_BUNDLE_INDEX_CSV = "artifact_source_bundle_index.csv"
ARTIFACT_DATA_BUNDLE_INDEX_JSON = "artifact_source_bundle_index.json"
DOCX_NORMALIZATION_TIMEOUT_SECONDS = 420
WORD_FIELD_UPDATE_TIMEOUT_SECONDS = 180


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
    return slug or "artifact"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_json_from_text(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def append_stage_log(output_dir: Path, stage: str, status: str, extra: dict[str, Any] | None = None) -> None:
    row = {"time": now_text(), "stage": stage, "status": status}
    if extra:
        row.update(extra)
    path = output_dir / "build_stage_log.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_docx_normalization(docx_path: Path) -> dict[str, Any]:
    if not NORMALIZE_DOCX_FOR_WORD_OPEN:
        return {"status": "skipped", "reason": "disabled_by_runtime_profile", "docx_path": str(docx_path)}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NORMALIZE_DOCX_PATH"] = str(docx_path.resolve())
    try:
        completed = subprocess.run(
            [sys.executable, str(PROJECT_DIR / "scripts" / "normalize_docx_for_word_open.py")],
            cwd=str(PROJECT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=DOCX_NORMALIZATION_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "docx_path": str(docx_path),
            "timeout_seconds": DOCX_NORMALIZATION_TIMEOUT_SECONDS,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
    payload = parse_json_from_text(completed.stdout)
    if not payload:
        payload = {"status": "failed", "docx_path": str(docx_path), "reason": "missing_json_stdout"}
    payload["returncode"] = completed.returncode
    payload["stderr"] = completed.stderr[-2000:]
    return payload


def run_word_field_update(docx_path: Path) -> dict[str, Any]:
    if not UPDATE_WORD_FIELDS_WITH_COM:
        return {"status": "skipped", "reason": "disabled_by_runtime_profile", "docx_path": str(docx_path)}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["UPDATE_WORD_FIELDS_DOCX_PATH"] = str(docx_path.resolve())
    try:
        completed = subprocess.run(
            [sys.executable, str(PROJECT_DIR / "scripts" / "update_word_fields.py")],
            cwd=str(PROJECT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=WORD_FIELD_UPDATE_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "docx_path": str(docx_path),
            "timeout_seconds": WORD_FIELD_UPDATE_TIMEOUT_SECONDS,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
    payload = parse_json_from_text(completed.stdout)
    if not payload:
        payload = {"status": "failed", "docx_path": str(docx_path), "reason": "missing_json_stdout"}
    payload["returncode"] = completed.returncode
    payload["stderr"] = completed.stderr[-2000:]
    return payload


def relative_project_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_DIR.resolve()))
    except Exception:
        return str(path)


def artifact_caption(slot: dict[str, Any]) -> str:
    return (
        clean_text(slot.get("reference_caption"))
        or clean_text(slot.get("reference_object"))
        or clean_text(slot.get("logical_slot_id"))
        or clean_text(slot.get("artifact_id"))
    )


def figure_caption_prefix(caption: str) -> str:
    text = clean_text(caption)
    if "、" in text and text.startswith("图"):
        return text.split("、", 1)[0] + "、"
    return "图、"


def source_display_name(source: str) -> str:
    normalized = clean_text(source)
    if normalized in {"US News", "U.S.News", "U.S. News"}:
        return "U.S. News"
    return normalized


def spec_subject_label(spec_payload: dict[str, Any]) -> str:
    source = clean_text(spec_payload.get("ranking_source"))
    candidates = [clean_text(item) for item in spec_payload.get("candidate_subject_or_areas", []) if clean_text(item)]
    if source == "THE" and candidates:
        return candidates[-1]
    return clean_text(spec_payload.get("ranking_subject_or_area")) or (candidates[-1] if candidates else "")


def display_artifact_caption(slot: dict[str, Any], source_files: dict[str, str]) -> str:
    caption = artifact_caption(slot)
    artifact_id = clean_text(slot.get("artifact_id"))
    spec_path_text = clean_text(source_files.get("chart_spec.json") or source_files.get("table_spec.json"))
    spec_payload = read_json(Path(spec_path_text)) if spec_path_text else {}
    source = source_display_name(spec_payload.get("ranking_source"))
    subject_label = spec_subject_label(spec_payload)
    if "indicator_weight" in artifact_id and source and subject_label:
        prefix = figure_caption_prefix(caption)
        if source == "软科":
            return f"{prefix}软科世界一流学科{subject_label}口径指标权重"
        if source == "QS":
            return f"{prefix}QS学科排名{subject_label}口径指标权重"
        if source == "U.S. News":
            return f"{prefix}U.S. News学科排名{subject_label}口径指标权重"
        if source == "THE":
            return f"{prefix}THE世界学科排名{subject_label}口径指标权重"
    return caption


def bundle_file_role(filename: str) -> str:
    roles = {
        "chart_data.csv": "final_chart_data",
        "chart_plot_data.csv": "plot_level_intermediate_data",
        "chart_tree_data.csv": "tree_layout_intermediate_data",
        "peer_indicator_long.csv": "peer_indicator_long_form_data",
        "table_data.csv": "final_table_long_data",
        "table_matrix.csv": "final_table_matrix_data",
        "source_trace.csv": "source_trace_data",
        "latest_peer_records.csv": "selected_peer_scope_snapshot",
        "latest_peer_records_full_top200.csv": "full_top200_peer_scope_snapshot",
        "peer_records_top200.csv": "top200_peer_scope_snapshot",
        "deduped_duplicate_records.csv": "deduped_rows_reference",
        "chart_spec.json": "chart_metadata",
        "table_spec.json": "table_metadata",
        "run_log.md": "generation_log",
        "narrative.md": "artifact_usage_note",
        "table.md": "table_markdown_preview",
        "chart.png": "rendered_chart_reference",
        "chart.svg": "rendered_chart_reference_vector",
        "table.png": "rendered_table_reference",
    }
    return roles.get(filename, "supporting_file")


def primary_data_filename(source_files: dict[str, str]) -> str:
    for filename in [
        "chart_data.csv",
        "table_matrix.csv",
        "table_data.csv",
        "chart_plot_data.csv",
        "peer_indicator_long.csv",
        "source_trace.csv",
    ]:
        if filename in source_files:
            return filename
    return ""


def spec_filename(source_files: dict[str, str]) -> str:
    for filename in ["chart_spec.json", "table_spec.json"]:
        if filename in source_files:
            return filename
    return ""


def csv_source_summary(path: Path) -> list[dict[str, Any]]:
    rows = read_csv_rows(path)
    if not rows:
        return []
    if not any(field in rows[0] for field in ["source_file", "source_sheet", "source_row"]):
        return []
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        source_file = clean_text(row.get("source_file"))
        source_sheet = clean_text(row.get("source_sheet"))
        source_row = clean_text(row.get("source_row"))
        key = (source_file, source_sheet)
        item = counts.setdefault(
            key,
            {
                "source_file": source_file,
                "source_sheet": source_sheet,
                "row_count": 0,
                "source_row_examples": [],
            },
        )
        item["row_count"] += 1
        if source_row and source_row not in item["source_row_examples"] and len(item["source_row_examples"]) < 8:
            item["source_row_examples"].append(source_row)
    ordered = sorted(counts.values(), key=lambda item: (-int(item["row_count"]), item["source_file"], item["source_sheet"]))
    for item in ordered:
        item["source_row_examples"] = ",".join(item["source_row_examples"])
    return ordered


def artifact_lineage_defaults(artifact_id: str) -> dict[str, Any]:
    ranking_artifacts = {
        "figure_01_tongji_subject_ranking_overview",
        "figure_07_all_rankings_history",
        "table_04_mainland_rank_band_distribution",
        "table_05_arwu_mainland_peer_ranking",
        "table_06_usnews_mainland_peer_ranking",
        "table_07_qs_mainland_peer_ranking",
        "table_08_the_mainland_peer_ranking",
        "table_09_peer_full_ranking_history_appendix",
    }
    weight_artifacts = {
        "figure_03_arwu_indicator_weight",
        "figure_04_qs_indicator_weight",
        "figure_05_usnews_indicator_weight",
        "figure_05_usnews_indicator_weight_candidate",
        "figure_06_the_indicator_weight",
    }
    indicator_history_artifacts = {
        "table_01_arwu_tongji_indicator_history",
        "table_02_usnews_tongji_indicator_history",
        "table_03_the_tongji_indicator_history",
        "figure_10_usnews_indicator_history_trend",
    }
    peer_indicator_artifacts = {
        "figure_09_arwu_peer_indicator_relative_rank",
        "figure_10_qs_peer_indicator_relative_rank",
        "figure_11_usnews_peer_indicator_relative_rank",
        "figure_12_the_peer_indicator_relative_rank",
    }
    paper_artifacts = {
        "figure_13_paper_output_citation_relative_rank",
        "figure_14_paper_cnci_cpp_relative_rank",
        "figure_15_paper_highly_cited_relative_rank",
        "figure_16_paper_international_collab_relative_rank",
    }

    if artifact_id in ranking_artifacts:
        return {
            "upstream_inputs": [
                {"path": "processed/ranking.sqlite", "object": "fact_ranking", "role": "ranking_history_source"},
                {"path": "processed/dim_subject_alias.csv", "object": "subject_alias_scope", "role": "subject_matching_rule"},
                {"path": "run_dir/public_ranking_source_supplements.csv", "object": "runtime_public_supplements", "role": "supplemental_scope_if_any"},
            ],
            "derivation_steps": [
                "Filter ranking records by the current subject aliases, then aggregate by ranking_source.",
                "Deduplicate rows when needed and restrict the scope to Tongji or mainland top-200 peers.",
                "Write the final plotting table into chart_data.csv or table_matrix.csv.",
            ],
        }
    if artifact_id == "figure_02_ranking_indicator_commonality":
        return {
            "upstream_inputs": [
                {"path": "processed/fact_indicator_weight.csv", "object": "indicator_weight", "role": "preferred_weight_source"},
                {"path": "processed/fact_ranking_indicator.csv", "object": "indicator_coverage", "role": "fallback_when_weight_missing"},
            ],
            "derivation_steps": [
                "Prefer weight data to aggregate indicator groups.",
                "When weight data is missing, fall back to the latest Tongji indicator coverage rows.",
                "Keep the pre-aggregation long-form rows in source_trace.csv.",
            ],
        }
    if artifact_id in weight_artifacts:
        default_path = "processed/fact_indicator_weight.csv"
        if artifact_id == "figure_05_usnews_indicator_weight_candidate":
            default_path = "external_data/processed/usnews_math_weight_candidate_indirect.csv"
        return {
            "upstream_inputs": [
                {"path": default_path, "object": "indicator_weight", "role": "weight_source"},
                {"path": "processed/dim_subject_alias.csv", "object": "subject_alias_scope", "role": "area_matching_rule"},
            ],
            "derivation_steps": [
                "Match weight rows by ranking_source and subject or subject-area aliases.",
                "The rendered visual usually uses only first-level indicators or tree summary rows.",
                "Keep the full weight table in chart_data.csv and the plotting intermediate table in chart_plot_data.csv or chart_tree_data.csv.",
            ],
        }
    if artifact_id in indicator_history_artifacts:
        external_defaults = {
            "table_01_arwu_tongji_indicator_history": "external_data/processed/arwu_gras_public_tongji_history_2023_2025_long.csv",
            "table_02_usnews_tongji_indicator_history": "external_data/processed/usnews_tongji_subject_indicator_history_2022_2026_long.csv",
            "figure_10_usnews_indicator_history_trend": "external_data/processed/usnews_tongji_subject_indicator_history_2022_2026_long.csv",
        }
        default_path = external_defaults.get(artifact_id, "processed/fact_ranking_indicator.csv")
        return {
            "upstream_inputs": [
                {"path": default_path, "object": "indicator_history", "role": "indicator_history_source"},
                {"path": "processed/dim_subject_alias.csv", "object": "subject_alias_scope", "role": "subject_matching_rule"},
            ],
            "derivation_steps": [
                "Filter to the current subject and Tongji University first.",
                "Expand the data by year and indicator name into a trend chart or matrix table.",
                "Keep the pre-aggregation long table in table_data.csv and source_trace.csv.",
            ],
        }
    if artifact_id in peer_indicator_artifacts:
        return {
            "upstream_inputs": [
                {"path": "processed/fact_ranking_indicator.csv", "object": "peer_indicator_source", "role": "peer_indicator_history"},
                {"path": "run_dir/artifacts/<peer_artifact_id>/latest_peer_records.csv", "object": "peer_scope", "role": "selected_peer_set"},
            ],
            "derivation_steps": [
                "Use the peer table to determine the comparison university set first.",
                "Then extract comparable indicator rows for those peers and Tongji from the long-form indicator table.",
                "Keep the final summary in chart_data.csv and the expanded detail in peer_indicator_long.csv and source_trace.csv.",
            ],
        }
    if artifact_id in paper_artifacts:
        return {
            "upstream_inputs": [
                {"path": "external_data/processed/wos_37_university_subject_paper_metrics_20260511.csv", "object": "wos_subject_metrics", "role": "preferred_subject_level_source"},
                {"path": "external_data/processed/cwts_traditional_2025_china_latest_all_fields.csv", "object": "cwts_field_metrics", "role": "fallback_broad_field_source"},
                {"path": "external_data/processed/cwts_subject_field_crosswalk.csv", "object": "cwts_subject_field_mapping", "role": "subject_to_field_mapping"},
            ],
            "derivation_steps": [
                "Prefer subject-level WOS paper metrics and fall back to the broader CWTS proxy when needed.",
                "Compute relative_rank fields required by the visual.",
                "Keep the final replot fields in chart_data.csv and the full comparison base table in source_trace.csv.",
            ],
        }
    return {
        "upstream_inputs": [],
        "derivation_steps": [
            "The raw data for this artifact has been exported with the bundle.",
            "Use the primary data file, the spec file, and source_trace.csv to understand the plotting scope.",
        ],
    }


def build_artifact_source_overview(
    artifact_id: str,
    slot: dict[str, Any],
    copied_files: list[dict[str, Any]],
    source_files: dict[str, str],
    bundle_dir: Path,
    caption: str,
) -> dict[str, Any]:
    spec_name = spec_filename(source_files)
    spec_payload = read_json(Path(source_files[spec_name])) if spec_name else {}
    source_trace_summary = []
    if "source_trace.csv" in source_files:
        source_trace_summary = csv_source_summary(Path(source_files["source_trace.csv"]))
    defaults = artifact_lineage_defaults(artifact_id)
    upstream_inputs = list(defaults.get("upstream_inputs", []))
    if spec_payload.get("external_source"):
        upstream_inputs.insert(
            0,
            {
                "path": clean_text(spec_payload.get("external_source")),
                "object": clean_text(spec_payload.get("source_system") or spec_payload.get("source_kind") or "external_source"),
                "role": "explicit_spec_external_source",
            },
        )
    if spec_payload.get("peer_artifact_id"):
        upstream_inputs.append(
            {
                "path": f"run_dir/artifacts/{clean_text(spec_payload['peer_artifact_id'])}/latest_peer_records.csv",
                "object": "peer_scope",
                "role": "peer_scope_from_peer_table",
            }
        )
    overview = {
        "artifact_id": artifact_id,
        "logical_slot_id": clean_text(slot.get("logical_slot_id")),
        "artifact_caption": caption,
        "artifact_status": clean_text(slot.get("artifact_status")),
        "primary_data_file": primary_data_filename(source_files),
        "spec_file": spec_name,
        "copied_files": copied_files,
        "upstream_inputs": upstream_inputs,
        "derivation_steps": defaults.get("derivation_steps", []),
        "source_trace_summary": source_trace_summary,
        "spec_summary": spec_payload,
        "bundle_dir": str(bundle_dir),
    }
    return overview


def build_replot_request_text(overview: dict[str, Any]) -> str:
    lines = [
        f"# Replot Request: {overview['artifact_id']}",
        "",
        "## Goal",
        f"- Recreate the chart/table for: {overview['artifact_caption']}",
        f"- Artifact id: {overview['artifact_id']}",
        "",
        "## Files To Send",
    ]
    copied_files = overview.get("copied_files", [])
    primary_name = clean_text(overview.get("primary_data_file"))
    spec_name = clean_text(overview.get("spec_file"))
    preferred = []
    for name in [primary_name, spec_name, "source_trace.csv", "chart_plot_data.csv", "chart_tree_data.csv", "peer_indicator_long.csv", "chart.png", "table.png"]:
        if name and any(item["filename"] == name for item in copied_files) and name not in preferred:
            preferred.append(name)
    if preferred:
        for name in preferred:
            lines.append(f"- {name}")
    else:
        lines.append("- Send all files in this folder.")
    lines.extend(["", "## Intent", "- Use the primary data file as the direct plotting table.", "- Use source_trace.csv to understand the upstream rows before aggregation/filtering when it exists.", "- Use the spec json to preserve chart type, metric scope, source system, and subject/peer matching assumptions.", "", "## Derivation Notes"])
    derivation_steps = overview.get("derivation_steps", [])
    if derivation_steps:
        for step in derivation_steps:
            lines.append(f"- {step}")
    else:
        lines.append("- The direct plotting data is already materialized in the exported csv files.")
    lines.extend(["", "## Output Expectation", "- Return a rebuilt figure/table plus a short explanation of how the data fields map to the visual encoding.", ""])
    return "\n".join(lines)


def export_artifact_source_bundle(run_dir: Path, manifest: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    bundle_root = output_dir / ARTIFACT_DATA_BUNDLE_DIRNAME
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    slot_rows = [row for row in manifest.get("slot_decisions", []) if row.get("include_in_word")]
    index_rows: list[dict[str, Any]] = []

    for order, slot in enumerate(slot_rows, start=1):
        artifact_id = clean_text(slot.get("artifact_id"))
        source_files = slot.get("source_files", {}) or {}
        if not artifact_id or not source_files:
            continue
        caption = display_artifact_caption(slot, source_files)
        bundle_name = f"{order:02d}_{artifact_id}_{slug_text(caption)[:48]}"
        artifact_bundle_dir = bundle_root / bundle_name
        artifact_bundle_dir.mkdir(parents=True, exist_ok=True)

        copied_files: list[dict[str, Any]] = []
        for filename, source_path_text in sorted(source_files.items()):
            source_path = Path(source_path_text)
            if not source_path.exists():
                continue
            target_path = artifact_bundle_dir / filename
            shutil.copyfile(source_path, target_path)
            copied_files.append(
                {
                    "filename": filename,
                    "role": bundle_file_role(filename),
                    "source_path": str(source_path),
                    "bundle_path": str(target_path),
                }
            )

        overview = build_artifact_source_overview(artifact_id, slot, copied_files, source_files, artifact_bundle_dir, caption)
        write_json(artifact_bundle_dir / "source_overview.json", overview)
        write_text(artifact_bundle_dir / "replot_request.md", build_replot_request_text(overview))

        source_lines = [
            f"# {artifact_id}",
            "",
            f"- logical_slot_id: {overview['logical_slot_id']}",
            f"- caption: {overview['artifact_caption']}",
            f"- primary_data_file: {overview['primary_data_file']}",
            f"- spec_file: {overview['spec_file']}",
            "",
            "## Upstream Inputs",
        ]
        upstream_inputs = overview.get("upstream_inputs", [])
        if upstream_inputs:
            for item in upstream_inputs:
                source_lines.append(
                    f"- {clean_text(item.get('path'))} | {clean_text(item.get('object'))} | {clean_text(item.get('role'))}"
                )
        else:
            source_lines.append("- none")
        source_lines.extend(["", "## Derivation Steps"])
        for step in overview.get("derivation_steps", []):
            source_lines.append(f"- {step}")
        trace_summary = overview.get("source_trace_summary", [])
        source_lines.extend(["", "## Source Trace Summary"])
        if trace_summary:
            for item in trace_summary:
                source_lines.append(
                    f"- {clean_text(item.get('source_file'))} | {clean_text(item.get('source_sheet'))} | rows={item.get('row_count')} | sample_rows={clean_text(item.get('source_row_examples'))}"
                )
        else:
            source_lines.append("- source_trace.csv does not expose source_file/source_sheet/source_row columns, so use the upstream input list and spec json as provenance.")
        write_text(artifact_bundle_dir / "source_overview.md", "\n".join(source_lines) + "\n")

        index_rows.append(
            {
                "order": order,
                "artifact_id": artifact_id,
                "logical_slot_id": clean_text(slot.get("logical_slot_id")),
                "section": clean_text(slot.get("section")),
                "caption": caption,
                "bundle_dir": str(artifact_bundle_dir),
                "primary_data_file": overview.get("primary_data_file", ""),
                "spec_file": overview.get("spec_file", ""),
                "replot_request_file": str(artifact_bundle_dir / "replot_request.md"),
                "source_overview_file": str(artifact_bundle_dir / "source_overview.json"),
                "copied_file_count": len(copied_files),
            }
        )

    write_json(bundle_root / ARTIFACT_DATA_BUNDLE_INDEX_JSON, {"generated_at": now_text(), "artifacts": index_rows})
    write_csv_rows(
        bundle_root / ARTIFACT_DATA_BUNDLE_INDEX_CSV,
        index_rows,
        [
            "order",
            "artifact_id",
            "logical_slot_id",
            "section",
            "caption",
            "bundle_dir",
            "primary_data_file",
            "spec_file",
            "replot_request_file",
            "source_overview_file",
            "copied_file_count",
        ],
    )
    readme_lines = [
        "# Artifact Source Bundle",
        "",
        "- Each subfolder corresponds to one artifact that was actually included in the Word report.",
        "- The main data file is usually chart_data.csv, table_matrix.csv, or table_data.csv.",
        "- source_trace.csv keeps pre-aggregation detail, source_overview.json explains provenance, and replot_request.md can be sent to another AI directly.",
        "",
        "## Included Artifacts",
    ]
    for row in index_rows:
        readme_lines.append(
            f"- {row['order']:02d} | {row['artifact_id']} | {row['caption']} | primary={row['primary_data_file']}"
        )
    write_text(bundle_root / "README.md", "\n".join(readme_lines) + "\n")
    return {
        "bundle_dir": str(bundle_root),
        "artifact_count": len(index_rows),
        "index_json": str(bundle_root / ARTIFACT_DATA_BUNDLE_INDEX_JSON),
        "index_csv": str(bundle_root / ARTIFACT_DATA_BUNDLE_INDEX_CSV),
        "readme": str(bundle_root / "README.md"),
    }


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
    result: dict[str, Any] = {
        "bundle_path": "",
        "result_path": "",
        "validation_path": "",
        "llm_called": False,
        "demo_result_used": False,
    }
    narrative_dir = run_dir / "narrative_generation"
    narrative_dir.mkdir(parents=True, exist_ok=True)
    if BUILD_NARRATIVE_BUNDLE:
        bundle_path = narrative_bundle.build_bundle(run_dir)
        result["bundle_path"] = str(bundle_path)
    result_path = narrative_dir / "narrative_generation_result.json"
    result["result_path"] = str(result_path)
    if GENERATE_NARRATIVE_WITH_LLM:
        llm_result = narrative_llm.generate_narrative_for_run(run_dir, RUNTIME_PROFILE)
        result.update(llm_result)
        result["llm_called"] = bool(llm_result.get("llm_called"))
        result["result_path"] = str(result_path)
        return result
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
    append_stage_log(output_docx.parent, "word_replacement", "start")
    word_trial.main()
    append_stage_log(output_docx.parent, "word_replacement", "done")
    append_stage_log(output_docx.parent, "word_open_normalization", "start")
    word_open_normalization = run_docx_normalization(output_docx)
    append_stage_log(
        output_docx.parent,
        "word_open_normalization",
        clean_text(word_open_normalization.get("status")) or "unknown",
    )
    append_stage_log(output_docx.parent, "word_field_update", "start")
    field_update_result = run_word_field_update(output_docx)
    append_stage_log(output_docx.parent, "word_field_update", clean_text(field_update_result.get("status")) or "unknown")
    append_stage_log(output_docx.parent, "post_field_media_refresh", "start")
    rows, _ = word_trial.split_slot_rows_by_manifest(word_trial.read_all_slot_mapping())
    post_field_media_log = word_trial.refresh_visible_figure_media(rows, output_docx)
    post_field_layout_log = [
        {
            "slot": "post_field_trailing_table_empty_paragraph_xml",
            "artifact_id": "",
            "operation": "remove_trailing_table_empty_paragraph_in_docx_xml",
            "status": "ok",
            "removed_paragraphs": word_trial.remove_trailing_table_empty_paragraph_in_docx_xml(output_docx),
        }
    ]
    append_stage_log(output_docx.parent, "post_field_media_refresh", "done")
    append_stage_log(output_docx.parent, "post_field_audit", "start")
    post_field_audit_rows = word_trial.audit_replacements(rows, output_docx)
    word_trial.write_audit_files(post_field_audit_rows)
    word_trial.append_replacement_log(post_field_media_log + post_field_layout_log, post_field_audit_rows)
    append_stage_log(output_docx.parent, "post_field_audit", "done")

    qa_result = {}
    if RUN_WORD_QA:
        append_stage_log(output_docx.parent, "word_qa", "start")
        qa_result = audit_word_report.audit_docx(
            output_docx,
            output_docx.parent / "qa",
            render=RUN_RENDER_QA,
        )
        append_stage_log(output_docx.parent, "word_qa", clean_text(qa_result.get("overall_status")) or "unknown")
    append_stage_log(output_docx.parent, "artifact_source_bundle", "start")
    artifact_source_bundle = export_artifact_source_bundle(run_dir, manifest, output_docx.parent)
    append_stage_log(output_docx.parent, "artifact_source_bundle", "done")
    append_stage_log(output_docx.parent, "artifact_lineage_manifest", "start")
    try:
        artifact_lineage = build_artifact_lineage_manifest.build_lineage_manifests(run_dir, output_docx.parent)
        artifact_lineage["status"] = "generated"
        append_stage_log(output_docx.parent, "artifact_lineage_manifest", "generated")
    except Exception as exc:
        artifact_lineage = {"status": "error", "error": str(exc)}
        append_stage_log(output_docx.parent, "artifact_lineage_manifest", "error", {"error": str(exc)})

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
        "artifact_source_bundle": artifact_source_bundle,
        "artifact_lineage": artifact_lineage,
        "word_replacement_audit": str(word_trial.REPLACEMENT_AUDIT_JSON),
        "word_open_normalization": word_open_normalization,
        "word_field_update": field_update_result,
        "word_qa": qa_result,
    }
    write_json(output_docx.parent / "subject_word_report_summary.json", payload)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    build_subject_word_report()
