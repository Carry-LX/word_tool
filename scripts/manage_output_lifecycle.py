from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs"
OUTPUT_DIR = OUTPUTS_DIR / "cleanup_reports"

# Safe defaults: write a deletion plan only. Set APPLY_CHANGES=True after reviewing the plan.
APPLY_CHANGES = False
KEEP_LATEST_SUBJECT_RUNS_PER_CODE = 2
KEEP_LATEST_WORD_REPORTS_PER_CODE = 2
DROP_RENDERED_PAGE_IMAGES_FROM_OLDER_WORD_REPORTS = True


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def code_from_name(name: str) -> str:
    match = re.search(r"_(\d{4})_", name)
    return match.group(1) if match else ""


def grouped_dirs(root: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    if not root.exists():
        return groups
    for path in root.iterdir():
        if not path.is_dir():
            continue
        code = code_from_name(path.name)
        if code:
            groups.setdefault(code, []).append(path)
    for paths in groups.values():
        paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return groups


def dir_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def plan_old_dirs(root: Path, keep: int, reason: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, paths in grouped_dirs(root).items():
        for path in paths[keep:]:
            rows.append(
                {
                    "action": "delete_dir",
                    "reason": reason,
                    "code": code,
                    "path": str(path),
                    "bytes": dir_size(path),
                }
            )
    return rows


def plan_old_rendered_pages() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    report_root = OUTPUTS_DIR / "full_word_reports"
    for code, paths in grouped_dirs(report_root).items():
        for report_dir in paths[KEEP_LATEST_WORD_REPORTS_PER_CODE:]:
            rendered = report_dir / "qa" / "rendered_pages"
            if rendered.exists():
                rows.append(
                    {
                        "action": "delete_dir",
                        "reason": "drop_rendered_page_images_from_older_word_reports",
                        "code": code,
                        "path": str(rendered),
                        "bytes": dir_size(rendered),
                    }
                )
    return rows


def apply_plan(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        path = Path(str(row["path"]))
        try:
            resolved = path.resolve()
            resolved.relative_to(PROJECT_DIR.resolve())
        except Exception as exc:
            raise RuntimeError(f"Refusing to delete outside project: {path}") from exc
        if row["action"] == "delete_dir" and path.exists():
            shutil.rmtree(path)


def build_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        plan_old_dirs(
            OUTPUTS_DIR / "subject_agent_runs",
            KEEP_LATEST_SUBJECT_RUNS_PER_CODE,
            "keep_latest_subject_agent_runs_per_code",
        )
    )
    rows.extend(
        plan_old_dirs(
            OUTPUTS_DIR / "full_word_reports",
            KEEP_LATEST_WORD_REPORTS_PER_CODE,
            "keep_latest_full_word_reports_per_code",
        )
    )
    if DROP_RENDERED_PAGE_IMAGES_FROM_OLDER_WORD_REPORTS:
        rows.extend(plan_old_rendered_pages())
    payload = {
        "generated_at": now_text(),
        "apply_changes": APPLY_CHANGES,
        "row_count": len(rows),
        "planned_bytes": sum(int(row["bytes"]) for row in rows),
        "planned_mb": round(sum(int(row["bytes"]) for row in rows) / 1024 / 1024, 2),
        "rows": rows,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"output_lifecycle_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    if APPLY_CHANGES:
        apply_plan(rows)
    print(json.dumps({"plan": str(path), **{k: payload[k] for k in ["apply_changes", "row_count", "planned_mb"]}}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    build_plan()
