from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{str(key): clean_text(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def data_file_index() -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    if not DATA_DIR.exists():
        return index
    for path in DATA_DIR.rglob("*"):
        if path.is_file():
            index.setdefault(path.name, []).append(path)
    return index


def relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_DIR.resolve()))
    except ValueError:
        return str(path)


def is_under_data(path: Path) -> bool:
    try:
        path.resolve().relative_to(DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def resolve_raw_data_path(source_file: str, index: dict[str, list[Path]], source_url: str = "") -> dict[str, str]:
    source = clean_text(source_file)
    url = clean_text(source_url)
    if not source:
        if url:
            return {
                "raw_data_file": "",
                "raw_data_path": "",
                "raw_data_status": "public_url_no_local_raw_file",
                "intermediate_source_path": url,
            }
        return {
            "raw_data_file": "",
            "raw_data_path": "",
            "raw_data_status": "missing_source_file",
            "intermediate_source_path": "",
        }

    source_path = Path(source)
    candidates: list[Path] = []
    if source_path.is_absolute():
        candidates.append(source_path)
    else:
        candidates.extend([PROJECT_DIR / source_path, DATA_DIR / source_path])

    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and is_under_data(candidate):
            return {
                "raw_data_file": candidate.name,
                "raw_data_path": str(candidate.resolve()),
                "raw_data_status": "data_path_exact",
                "intermediate_source_path": "",
            }

    basename_matches = index.get(source_path.name, [])
    if len(basename_matches) == 1:
        path = basename_matches[0]
        return {
            "raw_data_file": path.name,
            "raw_data_path": str(path.resolve()),
            "raw_data_status": "data_path_by_filename",
            "intermediate_source_path": "",
        }
    if len(basename_matches) > 1:
        paths = [str(path.resolve()) for path in basename_matches]
        return {
            "raw_data_file": source_path.name,
            "raw_data_path": ";".join(paths),
            "raw_data_status": "ambiguous_data_filename",
            "intermediate_source_path": "",
        }

    existing = next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)
    if existing:
        return {
            "raw_data_file": "",
            "raw_data_path": "",
            "raw_data_status": "source_exists_outside_data",
            "intermediate_source_path": str(existing.resolve()),
        }
    return {
        "raw_data_file": "",
        "raw_data_path": "",
        "raw_data_status": "raw_data_file_not_found",
        "intermediate_source_path": source,
    }


def key_for_trace_row(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        clean_text(row.get("source_file")),
        clean_text(row.get("source_sheet")),
        clean_text(row.get("source_row")),
        clean_text(row.get("source_column") or row.get("source_columns")),
        clean_text(row.get("source_url")),
    )


def build_lineage_for_artifact(artifact_dir: Path, artifact_id: str, index: dict[str, list[Path]]) -> list[dict[str, Any]]:
    rows = read_csv_rows(artifact_dir / "source_trace.csv")
    if not rows:
        return []
    counts = Counter(key_for_trace_row(row) for row in rows)
    first_rows: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = key_for_trace_row(row)
        first_rows.setdefault(key, row)

    lineage_rows: list[dict[str, Any]] = []
    for key, trace_count in sorted(counts.items(), key=lambda item: item[0]):
        source_file, source_sheet, source_row, source_column, source_url = key
        example = first_rows[key]
        resolved = resolve_raw_data_path(source_file, index, source_url)
        lineage_rows.append(
            {
                "artifact_id": artifact_id,
                "artifact_dir": str(artifact_dir),
                "trace_row_count": trace_count,
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_row": source_row,
                "source_column": source_column,
                "source_url": source_url,
                "raw_data_file": resolved["raw_data_file"],
                "raw_data_path": resolved["raw_data_path"],
                "raw_data_status": resolved["raw_data_status"],
                "intermediate_source_path": resolved["intermediate_source_path"],
                "ranking_source": clean_text(example.get("ranking_source")),
                "ranking_subject_or_area": clean_text(
                    example.get("ranking_subject_or_area")
                    or example.get("ranking_subject_raw")
                    or example.get("ranking_subject_alias")
                    or example.get("paper_field")
                ),
                "indicator_name": clean_text(example.get("indicator_name")),
                "metric_name": clean_text(example.get("metric_name") or example.get("metric_type")),
                "university_name_cn": clean_text(example.get("university_name_cn")),
                "evidence_level": clean_text(example.get("evidence_level")),
                "requires_disclosure": clean_text(example.get("requires_disclosure")),
                "proxy_scope_note": clean_text(example.get("proxy_scope_note")),
            }
        )
    return lineage_rows


def summarize_lineage(artifact_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(clean_text(row.get("raw_data_status")) for row in rows)
    raw_paths = sorted({clean_text(row.get("raw_data_path")) for row in rows if clean_text(row.get("raw_data_path"))})
    return {
        "artifact_id": artifact_id,
        "lineage_rows": len(rows),
        "raw_data_file_count": len(raw_paths),
        "raw_data_paths": raw_paths,
        "raw_data_status_counts": dict(sorted(statuses.items())),
    }


def build_lineage_manifests(run_dir: Path | str, output_dir: Path | str | None = None) -> dict[str, Any]:
    run_path = Path(run_dir)
    output_path = Path(output_dir) if output_dir is not None else run_path
    artifact_lineage_root = output_path / "artifact_lineage"
    artifacts_dir = run_path / "artifacts"
    index = data_file_index()
    all_rows: list[dict[str, Any]] = []
    artifact_summaries: list[dict[str, Any]] = []
    if artifacts_dir.exists():
        for artifact_dir in sorted(path for path in artifacts_dir.iterdir() if path.is_dir()):
            artifact_id = artifact_dir.name
            rows = build_lineage_for_artifact(artifact_dir, artifact_id, index)
            if not rows:
                continue
            fieldnames = list(rows[0].keys())
            artifact_output_dir = artifact_lineage_root / artifact_id
            write_csv(artifact_output_dir / "lineage_manifest.csv", rows, fieldnames)
            write_json(
                artifact_output_dir / "lineage_manifest.json",
                {
                    "generated_at": now_text(),
                    "artifact_id": artifact_id,
                    "source_trace": str(artifact_dir / "source_trace.csv"),
                    "lineage_rows": rows,
                    "summary": summarize_lineage(artifact_id, rows),
                },
            )
            all_rows.extend(rows)
            artifact_summaries.append(summarize_lineage(artifact_id, rows))

    status_counts = Counter(clean_text(row.get("raw_data_status")) for row in all_rows)
    payload = {
        "generated_at": now_text(),
        "run_dir": str(run_path),
        "output_dir": str(output_path),
        "artifact_count": len(artifact_summaries),
        "lineage_row_count": len(all_rows),
        "raw_data_status_counts": dict(sorted(status_counts.items())),
        "artifact_summaries": artifact_summaries,
        "outputs": {
            "csv": str(output_path / "artifact_lineage_manifest.csv"),
            "json": str(output_path / "artifact_lineage_manifest.json"),
            "artifact_lineage_dir": str(artifact_lineage_root),
        },
    }
    if all_rows:
        write_csv(output_path / "artifact_lineage_manifest.csv", all_rows, list(all_rows[0].keys()))
    else:
        write_csv(
            output_path / "artifact_lineage_manifest.csv",
            [],
            [
                "artifact_id",
                "artifact_dir",
                "trace_row_count",
                "source_file",
                "source_sheet",
                "source_row",
                "raw_data_path",
                "raw_data_status",
            ],
        )
    write_json(output_path / "artifact_lineage_manifest.json", payload)
    return payload


if __name__ == "__main__":
    latest_runs = sorted(
        (PROJECT_DIR / "outputs" / "subject_agent_runs").glob("*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    target = next((path for path in latest_runs if path.is_dir()), PROJECT_DIR)
    print(json.dumps(build_lineage_manifests(target), ensure_ascii=False, indent=2))
