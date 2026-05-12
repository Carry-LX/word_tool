from __future__ import annotations

import csv
import json
import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.shared import Emu, Pt, RGBColor


PROJECT_DIR = Path(r"E:\projects\water\word_tool")

TEMPLATE_DOCX = PROJECT_DIR / "data" / "同济大学XX学科的国际排名发展分析-2026年5月.docx"
SLOT_MAPPING_CSV = PROJECT_DIR / "configs" / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"
NARRATIVE_MAPPING_JSON = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_paragraph_mapping.json"

# 这里显式指定本次试跑使用哪一次学科产物。后续换学科时只改这一行即可。
SUBJECT_RUN_DIR = PROJECT_DIR / "outputs" / "subject_agent_runs" / "20260511_154304_0812_计算机科学与技术"

OUTPUT_DIR = PROJECT_DIR / "outputs" / "word_replacement_trial"
OUTPUT_DOCX = OUTPUT_DIR / "同济大学计算机科学与技术_模板式图形修正版.docx"
REPLACEMENT_LOG_JSON = OUTPUT_DIR / "replacement_log.json"
REPLACEMENT_AUDIT_JSON = OUTPUT_DIR / "replacement_audit.json"
REPLACEMENT_AUDIT_MD = OUTPUT_DIR / "replacement_audit.md"

# 第一版已验证“图表产物能否进入 Word 原槽位”。
# 现在默认使用原生 Word 表格，保留可编辑性。
TABLE_REPLACEMENT_MODE = "native"  # native / image
INSERT_CAPTION_ONLY_FIGURES = True

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


def read_slot_mapping() -> list[dict[str, str]]:
    with SLOT_MAPPING_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_narrative_mapping() -> dict[str, dict[str, Any]]:
    payload = json.loads(NARRATIVE_MAPPING_JSON.read_text(encoding="utf-8"))
    items = payload.get("paragraph_mappings", [])
    return {str(item.get("logical_slot_id", "")): item for item in items if item.get("logical_slot_id")}


def read_narrative_content() -> dict[tuple[str, str], str]:
    path = SUBJECT_RUN_DIR / "narrative_generation" / "narrative_generation_result.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("segment_texts", [])
        result: dict[tuple[str, str], str] = {}
        for item in items:
            slot_id = str(item.get("logical_slot_id", "")).strip()
            segment_key = str(item.get("segment_key", "")).strip()
            text = str(item.get("text", "")).strip()
            if slot_id and segment_key and text:
                result[(slot_id, segment_key)] = text
        if result:
            return result
    return {}


def read_target_subject_name() -> str:
    summary_path = SUBJECT_RUN_DIR / "agent_run_summary.json"
    if summary_path.exists():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        request = payload.get("request", {})
        subject_name = str(request.get("target_subject", "")).strip()
        if subject_name:
            return subject_name

    name_parts = SUBJECT_RUN_DIR.name.split("_")
    if name_parts:
        subject_name = name_parts[-1].strip()
        if subject_name:
            return subject_name
    return "计算机科学与技术"


def artifact_png_path(artifact_id: str) -> Path | None:
    artifact_dir = SUBJECT_RUN_DIR / "artifacts" / artifact_id
    for filename in ("chart.png", "table.png"):
        path = artifact_dir / filename
        if path.exists():
            return path
    return None


def artifact_matrix_path(artifact_id: str) -> Path | None:
    path = SUBJECT_RUN_DIR / "artifacts" / artifact_id / "table_matrix.csv"
    return path if path.exists() else None


def read_csv_matrix(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [[cell.strip() for cell in row] for row in csv.reader(handle)]
    return [row for row in rows if any(cell for cell in row)]


def parse_slot_index(reference_object: str, prefix: str) -> int | None:
    for part in reference_object.split("+"):
        part = part.strip()
        if part.startswith(prefix):
            try:
                return int(part.split("_", 1)[1])
            except (IndexError, ValueError):
                return None
    return None


def extract_template_image_targets(docx_path: Path) -> dict[int, str]:
    with ZipFile(docx_path) as zip_file:
        document_xml = zip_file.read("word/document.xml")
        rels_xml = zip_file.read("word/_rels/document.xml.rels")

    root = ET.fromstring(document_xml)
    rel_root = ET.fromstring(rels_xml)
    rels = {rel.attrib.get("Id", ""): rel.attrib.get("Target", "") for rel in rel_root}

    image_targets: dict[int, str] = {}
    image_index = 0
    for drawing in root.findall(".//w:drawing", NS):
        blip = drawing.find(".//a:blip", NS)
        if blip is None:
            continue
        rel_id = blip.attrib.get(f"{{{NS['r']}}}embed", "")
        target = rels.get(rel_id, "")
        if target.startswith("media/"):
            image_index += 1
            image_targets[image_index] = f"word/{target}"
    return image_targets


def replace_zip_members(source_docx: Path, target_docx: Path, replacements: dict[str, Path]) -> None:
    temp_docx = target_docx.with_suffix(".tmp.docx")
    with ZipFile(source_docx, "r") as zin, ZipFile(temp_docx, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            replacement = replacements.get(item.filename)
            if replacement is None:
                zout.writestr(item, zin.read(item.filename))
            else:
                zout.writestr(item, replacement.read_bytes())
    temp_docx.replace(target_docx)


def replace_docx_xml_member(docx_path: Path, member_name: str, xml_bytes: bytes) -> None:
    temp_docx = docx_path.with_suffix(".tmp.docx")
    with ZipFile(docx_path, "r") as zin, ZipFile(temp_docx, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == member_name:
                zout.writestr(item, xml_bytes)
            else:
                zout.writestr(item, zin.read(item.filename))
    temp_docx.replace(docx_path)


def content_width_emu(document: Document) -> int:
    section = document.sections[0]
    return int(section.page_width - section.left_margin - section.right_margin)


def insert_image_before_table(document: Document, table_index: int, image_path: Path) -> None:
    table = document.tables[table_index - 1]
    paragraph_element = OxmlElement("w:p")
    table._element.addprevious(paragraph_element)
    paragraph = Paragraph(paragraph_element, table._parent)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = 0
    paragraph.paragraph_format.space_after = 0
    paragraph.add_run().add_picture(str(image_path), width=Emu(content_width_emu(document)))
    table._element.getparent().remove(table._element)


def cell_shading(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_text(cell: Any, text: str, *, bold: bool, font_size: float, header: bool) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if header or len(text) <= 12 else WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = 0
    paragraph.paragraph_format.space_after = 0
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(font_size)
    run.font.name = "Microsoft YaHei" if header else "SimSun"
    run.font.color.rgb = RGBColor(31, 41, 51)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑" if header else "宋体")


def mark_repeat_header(row: Any) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tr_pr.append(tbl_header)
    tbl_header.set(qn("w:val"), "true")


def native_table_font_size(column_count: int) -> float:
    if column_count >= 18:
        return 5.2
    if column_count >= 12:
        return 6.0
    if column_count >= 8:
        return 6.8
    if column_count >= 5:
        return 7.5
    return 8.5


def apply_table_widths(table: Any, column_count: int, total_width_emu: int) -> None:
    if column_count <= 0:
        return
    column_width = int(total_width_emu / column_count)
    table.autofit = True
    for row in table.rows:
        for cell in row.cells:
            cell.width = Emu(column_width)


def build_native_table(document: Document, matrix: list[list[str]]) -> Any:
    row_count = len(matrix)
    column_count = max(len(row) for row in matrix)
    table = document.add_table(rows=row_count, cols=column_count)
    table.style = "Table Grid"
    font_size = native_table_font_size(column_count)
    apply_table_widths(table, column_count, content_width_emu(document))

    decorate_body_rows = column_count <= 10
    for row_index, row in enumerate(matrix):
        cells = table.rows[row_index].cells
        for column_index, cell in enumerate(cells):
            value = row[column_index] if column_index < len(row) else ""
            if decorate_body_rows or row_index == 0:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_text(cell, value, bold=row_index == 0, font_size=font_size, header=row_index == 0)
            if row_index == 0:
                cell_shading(cell, "E9EEF5")
            elif decorate_body_rows and row_index % 2 == 0:
                cell_shading(cell, "F7F9FC")
    if table.rows:
        mark_repeat_header(table.rows[0])
    return table


def replace_table_with_native_table(document: Document, table_index: int, matrix: list[list[str]]) -> None:
    old_table = document.tables[table_index - 1]
    new_table = build_native_table(document, matrix)
    old_table._element.addprevious(new_table._element)
    old_table._element.getparent().remove(old_table._element)


def paragraph_text(paragraph: Paragraph) -> str:
    return "".join(run.text for run in paragraph.runs).strip()


def paragraph_run_style(paragraph: Paragraph) -> dict[str, Any]:
    for run in paragraph.runs:
        if not run.text:
            continue
        rpr = run._element.rPr
        east_asia = None
        if rpr is not None and rpr.rFonts is not None:
            east_asia = rpr.rFonts.get(qn("w:eastAsia"))
        return {
            "font_name": run.font.name,
            "east_asia": east_asia,
            "font_size": run.font.size,
            "bold": run.bold,
            "italic": run.italic,
            "underline": run.underline,
        }
    return {
        "font_name": "仿宋_GB2312",
        "east_asia": "仿宋_GB2312",
        "font_size": Pt(14),
        "bold": False,
        "italic": False,
        "underline": False,
    }


def set_paragraph_text_with_template_style(paragraph: Paragraph, text: str, template_style: dict[str, Any]) -> None:
    for run in list(paragraph.runs):
        paragraph._p.remove(run._element)
    run = paragraph.add_run(text)
    run.font.name = template_style.get("font_name") or "仿宋_GB2312"
    run.font.size = template_style.get("font_size") or Pt(14)
    run.bold = bool(template_style.get("bold"))
    run.italic = bool(template_style.get("italic"))
    run.underline = template_style.get("underline")
    east_asia = template_style.get("east_asia") or run.font.name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)


def replace_subject_placeholder_text(text: str, subject_name: str) -> str:
    subject_label = f"{subject_name}学科"
    title = f"同济大学{subject_label}的国际排名发展分析"
    replacements = {
        "同济大学数学学科的国际排名发展分析": title,
        "同济大学XX学科的国际排名发展分析": title,
        "同济大学 XX 学科的国际排名发展分析": title,
        "同济大学xx学科的国际排名发展分析": title,
        "同济大学 xx 学科的国际排名发展分析": title,
        "XX 学科": subject_label,
        "XX学科": subject_label,
        "xx 学科": subject_label,
        "xx学科": subject_label,
        "数学学科指标权重": f"{subject_label}指标权重",
        "数学指标权重": f"{subject_name}指标权重",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def iter_container_paragraphs(container: Any) -> list[Paragraph]:
    paragraphs = list(getattr(container, "paragraphs", []))
    for table in getattr(container, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(iter_container_paragraphs(cell))
    return paragraphs


def replace_subject_placeholders(document: Document, subject_name: str) -> int:
    changed = 0
    containers: list[Any] = [document]
    for section in document.sections:
        containers.extend(
            [
                section.header,
                section.first_page_header,
                section.even_page_header,
                section.footer,
                section.first_page_footer,
                section.even_page_footer,
            ]
        )

    seen: set[int] = set()
    for container in containers:
        for paragraph in iter_container_paragraphs(container):
            paragraph_id = id(paragraph._p)
            if paragraph_id in seen:
                continue
            seen.add(paragraph_id)
            original_text = paragraph_text(paragraph)
            replaced_text = replace_subject_placeholder_text(original_text, subject_name)
            if replaced_text != original_text:
                set_paragraph_text_with_template_style(paragraph, replaced_text, paragraph_run_style(paragraph))
                changed += 1
    return changed


def is_heading_paragraph(text: str) -> bool:
    value = text.strip()
    return bool(
        re.match(r"^[一二三四五六七八九十]+、", value)
        or re.match(r"^\d+、", value)
        or re.match(r"^附表[:：]", value)
        or re.match(r"^第[一二三四五六七八九十]+", value)
    )


def is_caption_paragraph(text: str) -> bool:
    value = text.strip()
    return value.startswith("图") or value.startswith("表") or value.startswith("附表")


def narrative_placeholder_text(row: dict[str, str], position: str) -> str:
    caption = row.get("reference_caption", "").strip()
    return (
        f"【自动说明占位｜slot={row.get('logical_slot_id', '')}｜artifact={row.get('artifact_id', '')}"
        f"｜position={position}】这里替换为与“{caption}”对应的正文分析描述。"
    )


def find_caption_paragraph_index(document: Document, caption: str) -> int | None:
    if not caption:
        return None
    for idx, paragraph in enumerate(document.paragraphs):
        text = paragraph_text(paragraph)
        if caption in text:
            return idx
    return None


def find_narrative_paragraph_index(document: Document, caption_index: int, direction: int) -> int | None:
    paragraphs = document.paragraphs
    idx = caption_index + direction
    while 0 <= idx < len(paragraphs):
        text = paragraph_text(paragraphs[idx]).strip()
        if not text:
            idx += direction
            continue
        if is_heading_paragraph(text) or is_caption_paragraph(text):
            return None
        return idx
    return None


def ordered_caption_paragraph_indices(document: Document) -> list[int]:
    return [
        idx
        for idx, paragraph in enumerate(document.paragraphs)
        if is_caption_paragraph(paragraph_text(paragraph))
    ]


def looks_like_bridge_paragraph(text: str) -> bool:
    value = text.strip()
    bridge_markers = [
        "如下",
        "如下：",
        "位次分布如下",
        "比较37所高校的数据",
    ]
    return any(marker in value for marker in bridge_markers)


def choose_narrative_target(
    row: dict[str, str],
    document: Document,
    caption_index: int,
) -> tuple[int | None, str]:
    caption = row.get("reference_caption", "").strip()
    if caption.startswith("附表"):
        return None, "appendix_skip"

    before_index = find_narrative_paragraph_index(document, caption_index, -1)
    after_index = find_narrative_paragraph_index(document, caption_index, 1)
    before_text = paragraph_text(document.paragraphs[before_index]).strip() if before_index is not None else ""
    after_text = paragraph_text(document.paragraphs[after_index]).strip() if after_index is not None else ""

    if row.get("slot_kind") == "table" and before_text and looks_like_bridge_paragraph(before_text) and after_index is not None:
        return after_index, "after_caption"
    if before_index is not None and not looks_like_bridge_paragraph(before_text):
        return before_index, "before_caption"
    if after_index is not None:
        return after_index, "after_caption"
    if before_index is not None:
        return before_index, "before_caption"
    return None, "narrative_paragraph_not_found"


def replace_narrative_placeholders(document: Document, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    log_rows: list[dict[str, Any]] = []
    caption_indices_in_order = ordered_caption_paragraph_indices(document)
    for row_index, row in enumerate(rows):
        caption = row.get("reference_caption", "").strip()
        caption_index = find_caption_paragraph_index(document, caption)
        caption_match_mode = "exact"
        if caption_index is None and row_index < len(caption_indices_in_order):
            caption_index = caption_indices_in_order[row_index]
            caption_match_mode = "ordered_fallback"
        if caption_index is None:
            log_rows.append(
                {
                    "slot": row["logical_slot_id"],
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_narrative_placeholder",
                    "status": "skipped",
                    "reason": "caption_not_found",
                }
            )
            continue
        target_index, position = choose_narrative_target(row, document, caption_index)
        if target_index is None:
            log_rows.append(
                {
                    "slot": row["logical_slot_id"],
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_narrative_placeholder",
                    "status": "skipped",
                    "reason": position,
                }
            )
            continue
        paragraph = document.paragraphs[target_index]
        original_text = paragraph_text(paragraph)
        replacement_text = narrative_placeholder_text(row, position)
        paragraph.text = replacement_text
        log_rows.append(
            {
                "slot": row["logical_slot_id"],
                "artifact_id": row["artifact_id"],
                "operation": "replace_narrative_placeholder",
                "status": "ok",
                "target_paragraph": f"P{target_index + 1}",
                "position": position,
                "caption_match_mode": caption_match_mode,
                "original_text": original_text,
                "replacement_text": replacement_text,
            }
        )
    return log_rows


def strict_narrative_placeholder_text(row: dict[str, str], paragraph_spec: dict[str, Any]) -> str:
    caption = row.get("reference_caption", "").strip()
    paragraph_index = paragraph_spec.get("template_paragraph_index", "")
    segment = str(paragraph_spec.get("segment_key", "main"))
    position = str(paragraph_spec.get("position_relative_to_caption", "mapped"))
    return (
        f"【自动说明占位｜slot={row.get('logical_slot_id', '')}｜artifact={row.get('artifact_id', '')}"
        f"｜paragraph=P{paragraph_index}｜segment={segment}｜position={position}】"
        f"这里替换为与“{caption}”对应的正文分析描述。"
    )


def resolve_narrative_text(
    row: dict[str, str],
    paragraph_spec: dict[str, Any],
    narrative_texts: dict[tuple[str, str], str],
) -> tuple[str, str]:
    slot_id = row.get("logical_slot_id", "").strip()
    segment_key = str(paragraph_spec.get("segment_key", "")).strip()
    generated_text = narrative_texts.get((slot_id, segment_key), "").strip()
    if generated_text:
        return generated_text, "generated_text"
    return strict_narrative_placeholder_text(row, paragraph_spec), "placeholder_fallback"


def replace_narrative_placeholders_strict(document: Document, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    log_rows: list[dict[str, Any]] = []
    mapping_by_slot = read_narrative_mapping()
    narrative_texts = read_narrative_content()
    for row in rows:
        slot_id = row["logical_slot_id"]
        mapping = mapping_by_slot.get(slot_id)
        if not mapping:
            log_rows.append(
                {
                    "slot": slot_id,
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_narrative_placeholder",
                    "status": "skipped",
                    "reason": "mapping_not_found",
                }
            )
            continue
        if str(mapping.get("replace_decision", "replace")) != "replace":
            log_rows.append(
                {
                    "slot": slot_id,
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_narrative_placeholder",
                    "status": "skipped",
                    "reason": str(mapping.get("replace_decision", "skip")),
                    "notes": mapping.get("notes", ""),
                }
            )
            continue
        for paragraph_spec in mapping.get("paragraphs", []):
            paragraph_index = int(paragraph_spec["template_paragraph_index"])
            target_index = paragraph_index - 1
            if target_index < 0 or target_index >= len(document.paragraphs):
                log_rows.append(
                    {
                        "slot": slot_id,
                        "artifact_id": row["artifact_id"],
                        "operation": "replace_narrative_placeholder",
                        "status": "skipped",
                        "reason": "paragraph_out_of_range",
                        "target_paragraph": f"P{paragraph_index}",
                    }
                )
                continue
            paragraph = document.paragraphs[target_index]
            original_text = paragraph_text(paragraph)
            expected_text = str(paragraph_spec.get("template_text", "")).strip()
            template_style = paragraph_run_style(paragraph)
            replacement_text, content_mode = resolve_narrative_text(row, paragraph_spec, narrative_texts)
            set_paragraph_text_with_template_style(paragraph, replacement_text, template_style)
            log_rows.append(
                {
                    "slot": slot_id,
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_narrative_placeholder",
                    "status": "ok",
                    "target_paragraph": f"P{paragraph_index}",
                    "segment_key": paragraph_spec.get("segment_key", ""),
                    "position": paragraph_spec.get("position_relative_to_caption", ""),
                    "content_mode": content_mode,
                    "text_match": "exact" if expected_text == original_text else "mismatch",
                    "original_text": original_text,
                    "replacement_text": replacement_text,
                }
            )
    return log_rows


def insert_image_after_paragraph(document: Document, paragraph: Paragraph, image_path: Path) -> None:
    new_element = OxmlElement("w:p")
    paragraph._element.addnext(new_element)
    inserted = Paragraph(new_element, paragraph._parent)
    inserted.alignment = WD_ALIGN_PARAGRAPH.CENTER
    inserted.paragraph_format.space_before = 0
    inserted.paragraph_format.space_after = 0
    inserted.add_run().add_picture(str(image_path), width=Emu(content_width_emu(document)))


def replace_tables_and_caption_only_figures(rows: list[dict[str, str]], source_docx: Path, target_docx: Path) -> list[dict[str, Any]]:
    document = Document(str(source_docx))
    log_rows: list[dict[str, Any]] = []

    table_replacements: list[tuple[int, str, Path | None, list[list[str]] | None]] = []
    for row in rows:
        if row["slot_kind"] != "table":
            continue
        table_index = parse_slot_index(row["reference_object"], "table_")
        image_path = artifact_png_path(row["artifact_id"])
        matrix_path = artifact_matrix_path(row["artifact_id"])
        matrix = read_csv_matrix(matrix_path) if matrix_path and TABLE_REPLACEMENT_MODE == "native" else None
        if table_index is None or (TABLE_REPLACEMENT_MODE == "native" and not matrix) or (
            TABLE_REPLACEMENT_MODE == "image" and image_path is None
        ):
            log_rows.append(
                {
                    "slot": row["logical_slot_id"],
                    "artifact_id": row["artifact_id"],
                    "operation": f"replace_table_as_{TABLE_REPLACEMENT_MODE}",
                    "status": "skipped",
                    "reason": "missing_table_index_or_source",
                }
            )
            continue
        table_replacements.append((table_index, row["artifact_id"], image_path, matrix))

    for table_index, artifact_id, image_path, matrix in sorted(table_replacements, reverse=True):
        if TABLE_REPLACEMENT_MODE == "native":
            replace_table_with_native_table(document, table_index, matrix or [])
            source_path = artifact_matrix_path(artifact_id)
        else:
            insert_image_before_table(document, table_index, image_path)  # type: ignore[arg-type]
            source_path = image_path
        log_rows.append(
            {
                "slot": f"table_{table_index:03d}",
                "artifact_id": artifact_id,
                "operation": f"replace_table_as_{TABLE_REPLACEMENT_MODE}",
                "status": "ok",
                "source": str(source_path),
            }
        )

    log_rows.extend(replace_narrative_placeholders_strict(document, rows))

    if INSERT_CAPTION_ONLY_FIGURES:
        caption_only_rows = [
            row
            for row in rows
            if row["slot_kind"] == "figure_caption_without_embedded_object"
            and artifact_png_path(row["artifact_id"]) is not None
        ]
        for row in caption_only_rows:
            caption = row["reference_caption"]
            image_path = artifact_png_path(row["artifact_id"])
            matched = False
            for paragraph in document.paragraphs:
                text = paragraph_text(paragraph)
                if caption and caption in text:
                    insert_image_after_paragraph(document, paragraph, image_path)
                    matched = True
                    log_rows.append(
                        {
                            "slot": row["logical_slot_id"],
                            "artifact_id": row["artifact_id"],
                            "operation": "insert_caption_only_figure",
                            "status": "ok",
                            "source_png": str(image_path),
                        }
                    )
                    break
            if not matched:
                log_rows.append(
                    {
                        "slot": row["logical_slot_id"],
                        "artifact_id": row["artifact_id"],
                        "operation": "insert_caption_only_figure",
                        "status": "skipped",
                        "reason": "caption_not_found",
                    }
                )

    document.save(str(target_docx))
    return log_rows


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_replacements(rows: list[dict[str, str]], output_docx: Path) -> list[dict[str, Any]]:
    audit_rows: list[dict[str, Any]] = []
    image_targets = extract_template_image_targets(TEMPLATE_DOCX)

    with ZipFile(output_docx) as zip_file:
        docx_members = set(zip_file.namelist())
        docx_media_hashes = {
            member: sha256_bytes(zip_file.read(member))
            for member in docx_members
            if member.startswith("word/media/")
        }

    document = Document(str(output_docx))

    for row in rows:
        artifact_id = row["artifact_id"]
        if row["slot_kind"] == "figure" and row["reference_media"]:
            image_index = parse_slot_index(row["reference_object"], "image_")
            target_member = image_targets.get(image_index or -1, "")
            source_png = artifact_png_path(artifact_id)
            source_hash = sha256_bytes(source_png.read_bytes()) if source_png else ""
            docx_hash = docx_media_hashes.get(target_member, "")
            status = "ok" if source_hash and source_hash == docx_hash else "mismatch"
            audit_rows.append(
                {
                    "logical_slot_id": row["logical_slot_id"],
                    "slot_kind": row["slot_kind"],
                    "artifact_id": artifact_id,
                    "expected_source": str(source_png) if source_png else "",
                    "docx_target": target_member,
                    "check": "media_hash_equal",
                    "status": status,
                }
            )
        elif row["slot_kind"] == "figure_caption_without_embedded_object":
            source_png = artifact_png_path(artifact_id)
            source_hash = sha256_bytes(source_png.read_bytes()) if source_png else ""
            status = "ok" if source_hash in docx_media_hashes.values() else "mismatch"
            audit_rows.append(
                {
                    "logical_slot_id": row["logical_slot_id"],
                    "slot_kind": row["slot_kind"],
                    "artifact_id": artifact_id,
                    "expected_source": str(source_png) if source_png else "",
                    "docx_target": "new media relationship after caption",
                    "check": "media_hash_present",
                    "status": status,
                }
            )
        elif row["slot_kind"] == "table":
            table_index = parse_slot_index(row["reference_object"], "table_")
            matrix_path = artifact_matrix_path(artifact_id)
            expected_matrix = read_csv_matrix(matrix_path) if matrix_path else []
            actual_table = document.tables[(table_index or 1) - 1] if table_index and len(document.tables) >= table_index else None
            actual_matrix = []
            if actual_table is not None:
                actual_matrix = [[cell.text.strip() for cell in table_row.cells] for table_row in actual_table.rows]
            expected_header = expected_matrix[0] if expected_matrix else []
            actual_header = actual_matrix[0][: len(expected_header)] if actual_matrix else []
            row_count_ok = len(actual_matrix) == len(expected_matrix)
            header_ok = expected_header == actual_header
            status = "ok" if row_count_ok and header_ok else "mismatch"
            audit_rows.append(
                {
                    "logical_slot_id": row["logical_slot_id"],
                    "slot_kind": row["slot_kind"],
                    "artifact_id": artifact_id,
                    "expected_source": str(matrix_path) if matrix_path else "",
                    "docx_target": f"table_{table_index:03d}" if table_index else "",
                    "check": "native_table_header_and_row_count",
                    "status": status,
                    "expected_rows": len(expected_matrix),
                    "actual_rows": len(actual_matrix),
                    "expected_cols": len(expected_header),
                    "actual_cols": len(actual_header),
                }
            )

    return audit_rows


def write_audit_files(audit_rows: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_docx": str(OUTPUT_DOCX),
        "summary": {
            "ok": sum(1 for item in audit_rows if item["status"] == "ok"),
            "mismatch": sum(1 for item in audit_rows if item["status"] != "ok"),
        },
        "checks": audit_rows,
    }
    REPLACEMENT_AUDIT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    lines = [
        "# Word 图表替换审计",
        "",
        f"- output_docx: `{OUTPUT_DOCX}`",
        f"- ok: {payload['summary']['ok']}",
        f"- mismatch: {payload['summary']['mismatch']}",
        "",
        "| slot | kind | artifact | check | status | target |",
        "|---|---|---|---|---|---|",
    ]
    for item in audit_rows:
        lines.append(
            "| {slot} | {kind} | {artifact} | {check} | {status} | {target} |".format(
                slot=item["logical_slot_id"],
                kind=item["slot_kind"],
                artifact=item["artifact_id"],
                check=item["check"],
                status=item["status"],
                target=item["docx_target"],
            )
        )
    REPLACEMENT_AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def replace_embedded_images(rows: list[dict[str, str]], source_docx: Path, target_docx: Path) -> list[dict[str, Any]]:
    image_targets = extract_template_image_targets(source_docx)
    replacements: dict[str, Path] = {}
    log_rows: list[dict[str, Any]] = []

    for row in rows:
        if row["slot_kind"] != "figure" or not row["reference_media"]:
            continue
        image_index = parse_slot_index(row["reference_object"], "image_")
        image_path = artifact_png_path(row["artifact_id"])
        target_member = image_targets.get(image_index or -1)
        if image_index is None or image_path is None or target_member is None:
            log_rows.append(
                {
                    "slot": row["logical_slot_id"],
                    "artifact_id": row["artifact_id"],
                    "operation": "replace_embedded_image",
                    "status": "skipped",
                    "reason": "missing_image_index_or_png_or_target",
                }
            )
            continue
        replacements[target_member] = image_path
        log_rows.append(
            {
                "slot": row["logical_slot_id"],
                "artifact_id": row["artifact_id"],
                "operation": "replace_embedded_image",
                "status": "ok",
                "target_member": target_member,
                "source_png": str(image_path),
            }
        )

    if replacements:
        replace_zip_members(target_docx, target_docx, replacements)
    return log_rows


def normalize_odd_page_sections(docx_path: Path) -> int:
    temp_docx = docx_path.with_suffix(".tmp.docx")
    changed = 0
    with ZipFile(docx_path, "r") as zin, ZipFile(temp_docx, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                changed = data.count(b' w:val="oddPage"')
                data = data.replace(b' w:val="oddPage"', b' w:val="nextPage"')
            zout.writestr(item, data)
    temp_docx.replace(docx_path)
    return changed


def compact_cover_section_break(document: Document) -> int:
    body = document._body._element
    children = list(body)

    first_section_index = None
    for index, child in enumerate(children):
        if child.tag != qn("w:p"):
            continue
        if child.find(".//" + qn("w:sectPr")) is not None:
            first_section_index = index
            break
    if first_section_index is None:
        return 0

    removed = 0
    index = first_section_index - 1
    while index >= 0 and removed < 8:
        paragraph = children[index]
        if paragraph.tag != qn("w:p") or paragraph.find(".//" + qn("w:sectPr")) is not None:
            break
        has_text = bool("".join(text.text or "" for text in paragraph.findall(".//" + qn("w:t"))).strip())
        has_drawing = paragraph.find(".//" + qn("w:drawing")) is not None or paragraph.find(".//" + qn("w:pict")) is not None
        if has_text or has_drawing:
            break
        body.remove(paragraph)
        removed += 1
        index -= 1

    return removed


def is_empty_paragraph_element(paragraph_element: Any) -> bool:
    has_text = bool("".join(text.text or "" for text in paragraph_element.findall(".//" + qn("w:t"))).strip())
    has_drawing = (
        paragraph_element.find(".//" + qn("w:drawing")) is not None
        or paragraph_element.find(".//" + qn("w:pict")) is not None
    )
    has_section = paragraph_element.find(".//" + qn("w:sectPr")) is not None
    return not has_text and not has_drawing and not has_section


def paragraph_element_text(paragraph_element: Any) -> str:
    return "".join(text.text or "" for text in paragraph_element.findall(".//" + qn("w:t"))).strip()


def compact_cover_main_spacing(document: Document) -> int:
    body = document._body._element
    children = [child for child in list(body) if child.tag == qn("w:p")]
    if not children:
        return 0

    text_by_index = {index: paragraph_element_text(child) for index, child in enumerate(children)}
    subtitle_index = next((index for index, text in text_by_index.items() if text == "（第一版）"), None)
    department_index = next((index for index, text in text_by_index.items() if "发展规划与学科建设部" in text), None)
    if subtitle_index is None or department_index is None or department_index <= subtitle_index:
        return 0

    blank_indices = [
        index
        for index in range(subtitle_index + 1, department_index)
        if is_empty_paragraph_element(children[index])
    ]
    keep_blank_count = 4
    remove_indices = blank_indices[: max(0, len(blank_indices) - keep_blank_count)]

    leading_blank_indices = [
        index
        for index in range(0, subtitle_index)
        if is_empty_paragraph_element(children[index])
    ]
    if len(leading_blank_indices) > 1:
        remove_indices.extend(leading_blank_indices[: len(leading_blank_indices) - 1])

    for index in sorted(remove_indices, reverse=True):
        body.remove(children[index])
    return len(remove_indices)


def replace_subject_placeholders_in_xml_parts(docx_path: Path, subject_name: str) -> int:
    temp_docx = docx_path.with_suffix(".tmp.docx")
    changed_members = 0
    with ZipFile(docx_path, "r") as zin, ZipFile(temp_docx, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                text = data.decode("utf-8", errors="ignore")
                replaced_text = replace_subject_placeholder_text(text, subject_name)
                if replaced_text != text:
                    data = replaced_text.encode("utf-8")
                    changed_members += 1
            zout.writestr(item, data)
    temp_docx.replace(docx_path)
    return changed_members


def scale_embedded_image(docx_path: Path, target_member: str, scale: float) -> int:
    with ZipFile(docx_path) as zip_file:
        document_xml = zip_file.read("word/document.xml").decode("utf-8")
        rels_xml = zip_file.read("word/_rels/document.xml.rels")

    rel_root = ET.fromstring(rels_xml)
    target_rel_ids = {
        rel.attrib.get("Id", "")
        for rel in rel_root
        if f"word/{rel.attrib.get('Target', '')}" == target_member
    }
    if not target_rel_ids:
        return 0

    changed = 0
    for rel_id in target_rel_ids:
        pattern = re.compile(r"(<w:drawing\b(?:(?!</w:drawing>).)*?r:embed=\"" + re.escape(rel_id) + r"\"(?:(?!</w:drawing>).)*?</w:drawing>)", re.DOTALL)

        def scale_drawing(match: re.Match[str]) -> str:
            nonlocal changed
            drawing_xml = match.group(1)

            def scale_extent(extent_match: re.Match[str]) -> str:
                nonlocal changed
                cx = str(max(1, int(int(extent_match.group(2)) * scale)))
                cy = str(max(1, int(int(extent_match.group(4)) * scale)))
                changed += 1
                return f'{extent_match.group(1)}{cx}{extent_match.group(3)}{cy}{extent_match.group(5)}'

            return re.sub(r'(<(?:wp:extent|a:ext)\b[^>]*?\bcx=")(\d+)(" [^>]*?\bcy=")(\d+)(")', scale_extent, drawing_xml)

        document_xml = pattern.sub(scale_drawing, document_xml, count=1)

    if changed:
        replace_docx_xml_member(docx_path, "word/document.xml", document_xml.encode("utf-8"))
    return changed


def postprocess_final_document(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    subject_name = read_target_subject_name()
    document = Document(str(OUTPUT_DOCX))
    placeholder_changes = replace_subject_placeholders(document, subject_name)
    cover_main_spacing_changes = compact_cover_main_spacing(document)
    cover_spacing_changes = compact_cover_section_break(document)
    document.save(str(OUTPUT_DOCX))

    section_changes = normalize_odd_page_sections(OUTPUT_DOCX)
    xml_placeholder_changes = replace_subject_placeholders_in_xml_parts(OUTPUT_DOCX, subject_name)

    image_targets = extract_template_image_targets(TEMPLATE_DOCX)
    collab_member = ""
    for row in rows:
        if row.get("artifact_id") != "figure_16_paper_international_collab_relative_rank":
            continue
        image_index = parse_slot_index(row.get("reference_object", ""), "image_")
        collab_member = image_targets.get(image_index or -1, "")
        break
    scale_changes = scale_embedded_image(OUTPUT_DOCX, collab_member, 0.86) if collab_member else 0

    return [
        {
            "slot": "document_subject_placeholders",
            "artifact_id": "",
            "operation": "replace_subject_placeholders",
            "status": "ok",
            "subject_name": subject_name,
            "changed_paragraphs": placeholder_changes,
        },
        {
            "slot": "document_sections",
            "artifact_id": "",
            "operation": "normalize_odd_page_sections",
            "status": "ok",
            "changed_sections": section_changes,
        },
        {
            "slot": "cover_section_break",
            "artifact_id": "",
            "operation": "compact_cover_section_break",
            "status": "ok",
            "removed_blank_paragraphs": cover_spacing_changes,
        },
        {
            "slot": "cover_main_spacing",
            "artifact_id": "",
            "operation": "compact_cover_main_spacing",
            "status": "ok",
            "removed_blank_paragraphs": cover_main_spacing_changes,
        },
        {
            "slot": "document_xml_subject_placeholders",
            "artifact_id": "",
            "operation": "replace_subject_placeholders_in_xml_parts",
            "status": "ok",
            "changed_members": xml_placeholder_changes,
        },
        {
            "slot": "figure_16_layout",
            "artifact_id": "figure_16_paper_international_collab_relative_rank",
            "operation": "scale_embedded_image",
            "status": "ok" if collab_member else "skipped",
            "target_member": collab_member,
            "changed_extents": scale_changes,
        },
    ]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_slot_mapping()

    working_docx = OUTPUT_DOCX.with_name(OUTPUT_DOCX.stem + "_tables_first.docx")
    shutil.copy2(TEMPLATE_DOCX, working_docx)

    log_rows: list[dict[str, Any]] = []
    log_rows.extend(replace_tables_and_caption_only_figures(rows, working_docx, OUTPUT_DOCX))
    working_docx.unlink(missing_ok=True)
    log_rows.extend(replace_embedded_images(rows, TEMPLATE_DOCX, OUTPUT_DOCX))
    log_rows.extend(postprocess_final_document(rows))
    audit_rows = audit_replacements(rows, OUTPUT_DOCX)
    write_audit_files(audit_rows)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "template_docx": str(TEMPLATE_DOCX),
        "subject_run_dir": str(SUBJECT_RUN_DIR),
        "output_docx": str(OUTPUT_DOCX),
        "operations": log_rows,
        "summary": {
            "ok": sum(1 for item in log_rows if item["status"] == "ok"),
            "skipped": sum(1 for item in log_rows if item["status"] == "skipped"),
            "audit_ok": sum(1 for item in audit_rows if item["status"] == "ok"),
            "audit_mismatch": sum(1 for item in audit_rows if item["status"] != "ok"),
        },
    }
    REPLACEMENT_LOG_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    print(OUTPUT_DOCX)


if __name__ == "__main__":
    main()
