from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUN_ROOT = PROJECT_DIR / "outputs" / "subject_agent_runs"
LOG_DIR = PROJECT_DIR / "logs"

# 不使用命令行参数；默认审计最新一次 subject agent run。
RUN_DIR = None


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_run_dir(run_dir_override: Path | None = None) -> Path:
    if run_dir_override is not None:
        return run_dir_override
    if RUN_DIR:
        return Path(RUN_DIR)
    candidates = [path for path in RUN_ROOT.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"未找到 subject agent run 目录：{RUN_ROOT}")
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def count_csv_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return len(pd.read_csv(path))
    except Exception:
        return None


def image_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "width": 0, "height": 0, "size_bytes": 0}
    with Image.open(path) as image:
        width, height = image.size
    return {"exists": True, "width": width, "height": height, "size_bytes": path.stat().st_size}


def audit_artifact(result: dict[str, Any]) -> dict[str, Any]:
    artifact_id = result["artifact_id"]
    artifact_dir = Path(result["output_dir"])
    is_chart = artifact_id.startswith("figure")
    primary = artifact_dir / ("chart_data.csv" if is_chart else "table_data.csv")
    spec = artifact_dir / ("chart_spec.json" if is_chart else "table_spec.json")
    image = artifact_dir / ("chart.png" if is_chart else "table.png")
    source_trace = artifact_dir / "source_trace.csv"
    narrative = artifact_dir / "narrative.md"
    run_log = artifact_dir / "run_log.md"
    errors: list[str] = []
    for path in [primary, spec, image, source_trace, narrative, run_log]:
        if not path.exists():
            errors.append(f"missing {path.name}")
        elif path.stat().st_size == 0:
            errors.append(f"empty {path.name}")
    primary_rows = count_csv_rows(primary)
    trace_rows = count_csv_rows(source_trace)
    if primary_rows is None or primary_rows == 0:
        errors.append("primary data has zero/read error")
    if trace_rows is None or trace_rows == 0:
        errors.append("source_trace has zero/read error")
    img = image_status(image)
    if not img["exists"] or img["width"] < 400 or img["height"] < 300:
        errors.append("image missing or too small")
    return {
        "artifact_id": artifact_id,
        "status": "pass" if not errors else "fail",
        "primary_rows": primary_rows,
        "source_trace_rows": trace_rows,
        "image_width": img["width"],
        "image_height": img["height"],
        "image_size_bytes": img["size_bytes"],
        "errors": "; ".join(errors),
    }


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_visual_contact_sheet(generated_results: list[dict[str, Any]], audit_dir: Path) -> Path:
    font = load_font(16)
    thumb_w, thumb_h = 330, 198
    cols = 4
    rows = max(1, (len(generated_results) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * 390, rows * 275), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, result in enumerate(generated_results):
        artifact_id = result["artifact_id"]
        artifact_dir = Path(result["output_dir"])
        image_path = artifact_dir / ("chart.png" if artifact_id.startswith("figure") else "table.png")
        if not image_path.exists():
            continue
        image = Image.open(image_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = (idx % cols) * 390 + 26
        y = (idx // cols) * 275 + 28
        sheet.paste(image, (x, y))
        draw.text((x, y + thumb_h + 10), artifact_id, font=font, fill=(30, 41, 59))
    output_path = audit_dir / "visual_contact_sheet.png"
    sheet.save(output_path)
    return output_path


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_audit(run_dir_override: Path | None = None) -> dict[str, Any]:
    run_dir = resolve_run_dir(run_dir_override)
    summary_path = run_dir / "artifacts" / "artifact_generation_summary.json"
    if not summary_path.exists():
        raise RuntimeError(f"缺少 artifact generation summary：{summary_path}")
    generation_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    generated_results = [row for row in generation_summary.get("results", []) if row.get("status") == "generated"]
    audit_rows = [audit_artifact(row) for row in generated_results]
    pass_count = sum(1 for row in audit_rows if row["status"] == "pass")
    fail_count = len(audit_rows) - pass_count
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = build_visual_contact_sheet(generated_results, audit_dir)
    report = {
        "generated_at": now_text(),
        "run_dir": str(run_dir),
        "artifact_count": len(audit_rows),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "visual_contact_sheet": str(contact_sheet_path),
        "results": audit_rows,
    }
    (audit_dir / "subject_artifact_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    write_csv(
        audit_dir / "subject_artifact_audit.csv",
        audit_rows,
        ["artifact_id", "status", "primary_rows", "source_trace_rows", "image_width", "image_height", "image_size_bytes", "errors"],
    )
    lines = [
        "# Subject Artifact Audit",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- run_dir: `{run_dir}`",
        f"- artifact_count: {len(audit_rows)}",
        f"- pass_count: {pass_count}",
        f"- fail_count: {fail_count}",
        f"- visual_contact_sheet: `{contact_sheet_path}`",
        "",
        "| artifact | status | rows | trace rows | image | errors |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in audit_rows:
        lines.append(
            f"| {row['artifact_id']} | {row['status']} | {row['primary_rows']} | {row['source_trace_rows']} | "
            f"{row['image_width']}x{row['image_height']} | {row['errors']} |"
        )
    (audit_dir / "subject_artifact_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "subject_agent_audit_log.md"
    if not log_path.exists():
        log_path.write_text("# Subject Agent 审计留档\n", encoding="utf-8", newline="\n")
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"\n## {report['generated_at']}\n\n"
            f"- run_dir: `{run_dir}`\n"
            f"- artifact_count: {len(audit_rows)}\n"
            f"- pass_count: {pass_count}\n"
            f"- fail_count: {fail_count}\n"
        )
    print(json.dumps({"run_dir": str(run_dir), "artifact_count": len(audit_rows), "pass_count": pass_count, "fail_count": fail_count}, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    build_audit()
