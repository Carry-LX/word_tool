from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree as ET


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "configs" / "template_slot_inventory"
REFERENCE_DOCX_NAME_CONTAINS = "国际排名发展分析"
TARGET_TEMPLATE_NAME_CONTAINS = "【标黄】"
ARTIFACT_REGISTRY_PATH = PROJECT_DIR / "configs" / "artifact_registry.yaml"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def choose_docx(name_contains: str, fallback_largest: bool = False) -> Path:
    files = list(DATA_DIR.glob("*.docx"))
    matched = [p for p in files if name_contains in p.name]
    if matched:
        return matched[0]
    if fallback_largest:
        return max(files, key=lambda p: p.stat().st_size)
    raise FileNotFoundError(f"未找到包含 {name_contains!r} 的 docx")


def qname(tag: str) -> str:
    return f"{{{NS['w']}}}{tag}"


def para_text(element: ET.Element) -> str:
    return "".join((t.text or "") for t in element.findall(".//w:t", NS)).strip()


def table_text_preview(tbl: ET.Element, max_cells: int = 10) -> str:
    cells = []
    for tc in tbl.findall(".//w:tc", NS):
        text = para_text(tc)
        if text:
            cells.append(text)
        if len(cells) >= max_cells:
            break
    return " | ".join(cells)


def table_shape(tbl: ET.Element) -> tuple[int, int]:
    rows = tbl.findall(".//w:tr", NS)
    max_cols = 0
    for tr in rows:
        max_cols = max(max_cols, len(tr.findall("./w:tc", NS)))
    return len(rows), max_cols


def extract_relationships(zip_file: ZipFile) -> dict[str, str]:
    rel_path = "word/_rels/document.xml.rels"
    if rel_path not in zip_file.namelist():
        return {}
    root = ET.fromstring(zip_file.read(rel_path))
    rels = {}
    for rel in root:
        rel_id = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        rels[rel_id] = target
    return rels


def drawing_info(p: ET.Element, rels: dict[str, str]) -> list[dict[str, Any]]:
    infos = []
    for drawing in p.findall(".//w:drawing", NS):
        blip = drawing.find(".//a:blip", NS)
        rid = blip.attrib.get(f"{{{NS['r']}}}embed", "") if blip is not None else ""
        extent = drawing.find(".//wp:extent", NS)
        cx = int(extent.attrib.get("cx", "0")) if extent is not None else 0
        cy = int(extent.attrib.get("cy", "0")) if extent is not None else 0
        infos.append(
            {
                "relationship_id": rid,
                "target": rels.get(rid, ""),
                "width_emu": cx,
                "height_emu": cy,
            }
        )
    return infos


def extract_docx_blocks(docx_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    with ZipFile(docx_path) as z:
        xml = z.read("word/document.xml")
        rels = extract_relationships(z)
    root = ET.fromstring(xml)
    body = root.find("w:body", NS)
    if body is None:
        return blocks, slots

    block_index = 0
    image_index = 0
    table_index = 0
    caption_pattern = re.compile(r"^\s*([图表]\s*\d*|表\s*\d+|图\s*\d+|表[：:、]|图[：:、])")
    for child in list(body):
        if child.tag == qname("p"):
            text = para_text(child)
            drawings = drawing_info(child, rels)
            block_type = "paragraph"
            if drawings:
                block_type = "image_paragraph"
            blocks.append(
                {
                    "block_index": block_index,
                    "block_type": block_type,
                    "text": text,
                    "drawing_count": len(drawings),
                    "table_rows": "",
                    "table_cols": "",
                }
            )
            if text and caption_pattern.search(text):
                slots.append(
                    {
                        "slot_id": f"caption_{len(slots)+1:03d}",
                        "slot_type": "caption_or_heading",
                        "block_index": block_index,
                        "caption_text": text,
                        "media_target": "",
                        "table_rows": "",
                        "table_cols": "",
                        "style_hint": infer_style_hint(text),
                        "artifact_candidate": infer_artifact_candidate(text),
                    }
                )
            for info in drawings:
                image_index += 1
                slots.append(
                    {
                        "slot_id": f"image_{image_index:03d}",
                        "slot_type": "image",
                        "block_index": block_index,
                        "caption_text": text,
                        "media_target": info["target"],
                        "table_rows": "",
                        "table_cols": "",
                        "style_hint": "embedded_reference_image",
                        "artifact_candidate": infer_artifact_candidate(text),
                    }
                )
            block_index += 1
        elif child.tag == qname("tbl"):
            table_index += 1
            rows, cols = table_shape(child)
            preview = table_text_preview(child)
            blocks.append(
                {
                    "block_index": block_index,
                    "block_type": "table",
                    "text": preview,
                    "drawing_count": "",
                    "table_rows": rows,
                    "table_cols": cols,
                }
            )
            slots.append(
                {
                    "slot_id": f"table_{table_index:03d}",
                    "slot_type": "table",
                    "block_index": block_index,
                    "caption_text": preview,
                    "media_target": "",
                    "table_rows": rows,
                    "table_cols": cols,
                    "style_hint": infer_table_style_hint(rows, cols, preview),
                    "artifact_candidate": infer_artifact_candidate(preview),
                }
            )
            block_index += 1
    return blocks, slots


def infer_table_style_hint(rows: int, cols: int, preview: str) -> str:
    if rows <= 2 and cols <= 5:
        return "compact_summary_table_or_card"
    if rows >= 10 and cols >= 5:
        return "wide_peer_ranking_table"
    if "权重" in preview or "指标" in preview:
        return "indicator_weight_table"
    return "word_table"


def infer_style_hint(text: str) -> str:
    if "趋势" in text or "历史" in text:
        return "line_chart"
    if "分项指标" in text or "指标" in text:
        return "multi_indicator_chart"
    if "位次分布" in text or "前200" in text:
        return "rank_distribution_table"
    if "排名" in text:
        return "ranking_chart_or_table"
    return "caption_or_text_slot"


def infer_artifact_candidate(text: str) -> str:
    if not text:
        return ""
    if "四大" in text and ("历史" in text or "趋势" in text):
        return "figure_07_all_rankings_history"
    if "四大" in text and "排名" in text:
        return "figure_01_tongji_subject_ranking_overview"
    if "位次分布" in text:
        return "table_04_mainland_rank_band_distribution"
    if "软科" in text and "分项" in text:
        return "figure_09_arwu_peer_indicator_relative_rank"
    if ("U.S" in text or "US News" in text or "U.S.News" in text) and "分项" in text:
        return "figure_11_usnews_peer_indicator_relative_rank"
    if "THE" in text and "分项" in text:
        return "figure_12_the_peer_indicator_relative_rank"
    if "软科" in text:
        return "table_05_arwu_mainland_peer_ranking"
    if "U.S" in text or "US News" in text or "U.S.News" in text:
        return "table_06_usnews_mainland_peer_ranking"
    if "QS" in text:
        return "table_07_qs_mainland_peer_ranking"
    if "THE" in text:
        return "table_08_the_mainland_peer_ranking"
    return ""


def read_artifacts() -> set[str]:
    if not ARTIFACT_REGISTRY_PATH.exists():
        return set()
    data = json.loads(ARTIFACT_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["artifact_id"] for item in data.get("artifacts", [])}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reference_docx = choose_docx(REFERENCE_DOCX_NAME_CONTAINS, fallback_largest=True)
    target_docx = choose_docx(TARGET_TEMPLATE_NAME_CONTAINS)
    artifacts = read_artifacts()

    reference_blocks, reference_slots = extract_docx_blocks(reference_docx)
    target_blocks, target_slots = extract_docx_blocks(target_docx)
    for slot in reference_slots:
        candidate = clean_text(slot.get("artifact_candidate"))
        slot["artifact_exists"] = bool(candidate and candidate in artifacts)
        slot["coverage_status"] = "covered_by_existing_artifact" if slot["artifact_exists"] else "needs_mapping_or_new_artifact"
    for slot in target_slots:
        candidate = clean_text(slot.get("artifact_candidate"))
        slot["artifact_exists"] = bool(candidate and candidate in artifacts)
        slot["coverage_status"] = "covered_by_existing_artifact" if slot["artifact_exists"] else "needs_mapping_or_new_artifact"

    write_csv(OUTPUT_DIR / "reference_blocks.csv", reference_blocks)
    write_csv(OUTPUT_DIR / "reference_slots.csv", reference_slots)
    write_csv(OUTPUT_DIR / "target_template_blocks.csv", target_blocks)
    write_csv(OUTPUT_DIR / "target_template_slots.csv", target_slots)

    summary = {
        "reference_docx": str(reference_docx),
        "target_template_docx": str(target_docx),
        "reference_blocks": len(reference_blocks),
        "reference_slots": len(reference_slots),
        "reference_images": sum(1 for s in reference_slots if s["slot_type"] == "image"),
        "reference_tables": sum(1 for s in reference_slots if s["slot_type"] == "table"),
        "reference_caption_or_heading_slots": sum(1 for s in reference_slots if s["slot_type"] == "caption_or_heading"),
        "target_blocks": len(target_blocks),
        "target_slots": len(target_slots),
        "covered_reference_slots": sum(1 for s in reference_slots if s["coverage_status"] == "covered_by_existing_artifact"),
        "uncovered_reference_slots": sum(1 for s in reference_slots if s["coverage_status"] != "covered_by_existing_artifact"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Template Slot Inventory",
        "",
        f"- reference_docx: `{reference_docx}`",
        f"- target_template_docx: `{target_docx}`",
        f"- reference_blocks: {summary['reference_blocks']}",
        f"- reference_slots: {summary['reference_slots']}",
        f"- reference_images: {summary['reference_images']}",
        f"- reference_tables: {summary['reference_tables']}",
        f"- target_slots: {summary['target_slots']}",
        f"- covered_reference_slots_by_current_artifacts: {summary['covered_reference_slots']}",
        f"- uncovered_reference_slots: {summary['uncovered_reference_slots']}",
        "",
        "## 判断",
        "",
        "当前 10 个 artifact 覆盖的是核心分析链路，不等于覆盖了参考 Word 的全部图表槽位。下一步需要人工/规则结合地筛掉装饰性表格、拆分正文表格与图表，并形成最终 `slot -> artifact_id -> visual_style` 映射。",
        "",
        "## 输出文件",
        "",
        "- `reference_blocks.csv`：参考报告按文档顺序抽取的段落/表格/图片段落。",
        "- `reference_slots.csv`：参考报告中候选图、表、标题槽位及初步 artifact 候选。",
        "- `target_template_blocks.csv`：标黄模板按文档顺序抽取的段落/表格/图片段落。",
        "- `target_template_slots.csv`：标黄模板候选槽位。",
        "- `summary.json`：数量摘要。",
    ]
    (OUTPUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
