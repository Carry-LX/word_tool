from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from docx import Document
from PIL import Image, ImageStat


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_RENDER_SCRIPT = Path(r"C:\Users\李鑫\.codex\plugins\cache\openai-primary-runtime\documents\26.430.10722\skills\documents\render_docx.py")

# 显式变量，避免只能靠命令行参数。
DOCX_PATH = PROJECT_DIR / "outputs" / "full_word_reports" / "latest.docx"
QA_OUTPUT_DIR = PROJECT_DIR / "outputs" / "word_qa"
ENABLE_RENDER_QA = True
EMIT_PDF = True


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def inspect_zip(docx_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "ok", "media_count": 0, "warnings": []}
    try:
        with ZipFile(docx_path) as zip_file:
            members = set(zip_file.namelist())
            required = {"[Content_Types].xml", "word/document.xml", "word/_rels/document.xml.rels"}
            missing = sorted(required - members)
            result["member_count"] = len(members)
            result["media_count"] = sum(1 for member in members if member.startswith("word/media/"))
            result["has_document_xml"] = "word/document.xml" in members
            result["missing_required_members"] = missing
            if missing:
                result["status"] = "fail"
            if "word/document.xml" in members:
                document_xml = zip_file.read("word/document.xml").decode("utf-8", errors="ignore")
                result["odd_page_section_break_count"] = document_xml.count('w:val="oddPage"')
                if result["odd_page_section_break_count"]:
                    result["warnings"].append("document_contains_odd_page_section_breaks")
    except BadZipFile as exc:
        result["status"] = "fail"
        result["error"] = f"BadZipFile: {exc}"
    return result


def inspect_docx_structure(docx_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "ok", "warnings": []}
    document = Document(str(docx_path))
    result["paragraph_count"] = len(document.paragraphs)
    result["table_count"] = len(document.tables)
    result["section_count"] = len(document.sections)
    result["inline_shape_count"] = len(document.inline_shapes)
    empty_table_count = 0
    texts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        if not table.rows or not table.columns:
            empty_table_count += 1
        for row in table.rows:
            for cell in row.cells:
                value = cell.text.strip()
                if value:
                    texts.append(value)
    result["empty_table_count"] = empty_table_count
    if empty_table_count:
        result["warnings"].append("empty_tables_present")
    bad_patterns = {
        "debug_narrative_placeholder": "自动说明占位",
        "debug_slot_marker": "slot=",
        "debug_artifact_marker": "artifact=",
        "unresolved_xx_subject": r"(?i)xx\s*学",
        "unresolved_update_marker": "待更新",
        "subject_typo": "计算机科学于技术",
    }
    pattern_hits: dict[str, list[str]] = {}
    for name, pattern in bad_patterns.items():
        hits = []
        for text in texts:
            matched = re.search(pattern, text) if pattern.startswith("(?i)") else pattern in text
            if matched:
                hits.append(text[:240])
        if hits:
            pattern_hits[name] = hits[:8]
    result["bad_text_pattern_counts"] = {name: len(items) for name, items in pattern_hits.items()}
    result["bad_text_pattern_samples"] = pattern_hits
    if pattern_hits:
        result["status"] = "fail"
        result["warnings"].append("unresolved_template_or_debug_text_present")
    return result


def image_blankness(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        stat = ImageStat.Stat(rgb)
        extrema = rgb.getextrema()
        channel_ranges = [high - low for low, high in extrema]
        return {
            "file": str(path),
            "width": image.width,
            "height": image.height,
            "mean": [round(value, 2) for value in stat.mean],
            "channel_ranges": channel_ranges,
            "looks_blank": max(channel_ranges) < 8,
        }


def run_render(docx_path: Path, output_dir: Path) -> dict[str, Any]:
    render_dir = output_dir / "rendered_pages"
    render_dir.mkdir(parents=True, exist_ok=True)
    if not DOCUMENTS_RENDER_SCRIPT.exists():
        return {"status": "skipped", "reason": "documents_render_script_missing", "script": str(DOCUMENTS_RENDER_SCRIPT)}
    command = [sys.executable, str(DOCUMENTS_RENDER_SCRIPT), str(docx_path), "--output_dir", str(render_dir)]
    if EMIT_PDF:
        command.append("--emit_pdf")
    completed = subprocess.run(command, cwd=str(PROJECT_DIR), text=True, capture_output=True, timeout=180)
    pngs = sorted(render_dir.glob("page-*.png"))
    page_checks = []
    for png in pngs:
        try:
            page_checks.append(image_blankness(png))
        except Exception as exc:
            page_checks.append({"file": str(png), "error": str(exc), "looks_blank": True})
    pdfs = sorted(render_dir.glob("*.pdf"))
    status = "ok" if pngs and completed.returncode == 0 and not any(row.get("looks_blank") for row in page_checks) else "fail"
    if pngs and completed.returncode != 0:
        status = "warning"
    return {
        "status": status,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "render_dir": str(render_dir),
        "page_count": len(pngs),
        "pdf_files": [str(path) for path in pdfs],
        "page_checks": page_checks,
    }


def audit_docx(docx_path: Path, output_dir: Path | None = None, render: bool = ENABLE_RENDER_QA) -> dict[str, Any]:
    output_dir = output_dir or QA_OUTPUT_DIR / docx_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": now_text(),
        "docx_path": str(docx_path),
        "qa_output_dir": str(output_dir),
        "exists": docx_path.exists(),
        "python_executable": sys.executable,
    }
    if not docx_path.exists():
        payload["overall_status"] = "fail"
        payload["error"] = "docx_missing"
        write_json(output_dir / "word_qa_report.json", payload)
        return payload

    payload["zip"] = inspect_zip(docx_path)
    payload["structure"] = inspect_docx_structure(docx_path)
    if render:
        payload["render"] = run_render(docx_path, output_dir)
    else:
        payload["render"] = {"status": "skipped", "reason": "render_disabled"}
    hard_fail = payload["zip"]["status"] == "fail" or payload["structure"]["status"] == "fail" or payload["render"]["status"] == "fail"
    payload["overall_status"] = "fail" if hard_fail else "pass_with_warnings" if payload["render"]["status"] in {"warning", "skipped"} else "pass"
    write_json(output_dir / "word_qa_report.json", payload)
    lines = [
        "# Word QA Report",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- docx_path: `{docx_path}`",
        f"- overall_status: {payload['overall_status']}",
        f"- paragraph_count: {payload['structure'].get('paragraph_count', '')}",
        f"- table_count: {payload['structure'].get('table_count', '')}",
        f"- media_count: {payload['zip'].get('media_count', '')}",
        f"- render_status: {payload['render'].get('status', '')}",
        f"- page_count: {payload['render'].get('page_count', '')}",
        "",
    ]
    (output_dir / "word_qa_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return payload


def main() -> dict[str, Any]:
    payload = audit_docx(DOCX_PATH, QA_OUTPUT_DIR / DOCX_PATH.stem)
    print(json.dumps({"overall_status": payload["overall_status"], "qa_output_dir": payload["qa_output_dir"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
