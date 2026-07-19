from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "outputs" / "stage_report"
ASSET_DIR = PROJECT_DIR / "outputs" / "stage_report_assets"
PROVIDED_IMAGE_DIR = ASSET_DIR / "provided_images"
POLISHED_ASSET_DIR = ASSET_DIR / "polished"
DOCX_PATH = OUTPUT_DIR / "同济大学学科国际排名报告生成项目阶段性工作报告.docx"

FONT_CN = "微软雅黑"
FONT_BODY = "Calibri"
BLUE = RGBColor(42, 112, 176)
DARK_BLUE = RGBColor(20, 63, 102)
NAVY = RGBColor(11, 37, 69)
GRAY = RGBColor(94, 94, 94)
LIGHT_GRAY = "F4F6F8"
LIGHT_BLUE = "E8F0F7"
PALE_BLUE = "F6FAFD"
CONTENT_WIDTH_IN = 6.5
CONTENT_WIDTH_DXA = 9360
CAPTION_SIZE = 9.6


def set_run_font(
    run,
    name: str = FONT_CN,
    size: float | None = None,
    color: RGBColor | None = None,
    bold: bool | None = None,
) -> None:
    run.font.name = name
    r_fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), FONT_BODY)
    r_fonts.set(qn("w:hAnsi"), FONT_BODY)
    r_fonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.bold = bold


def set_para_font(paragraph, size: float = 10.5, color: RGBColor | None = None, bold: bool | None = None) -> None:
    for run in paragraph.runs:
        set_run_font(run, size=size, color=color, bold=bold)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top: int = 120, start: int = 150, bottom: int = 120, end: int = 150) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_text(
    cell,
    bold: bool = False,
    color: RGBColor | None = None,
    size: float = 9.2,
    align: int | None = None,
) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_margins(cell)
    for p in cell.paragraphs:
        if align is not None:
            p.alignment = align
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.18
        for run in p.runs:
            set_run_font(run, size=size, color=color, bold=bold)


def set_table_widths(table, widths: list[float]) -> None:
    total_dxa = sum(int(width * 1440) for width in widths)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.allow_autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_dxa))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_layout = tbl_pr.find(qn("w:tblLayout"))
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")
    old_grid = table._tbl.tblGrid
    if old_grid is not None:
        table._tbl.remove(old_grid)
    tbl_grid = OxmlElement("w:tblGrid")
    for width in widths:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(int(width * 1440)))
        tbl_grid.append(grid_col)
    table._tbl.insert(1, tbl_grid)
    for row in table.rows:
        for idx, width in enumerate(widths):
            cell = row.cells[idx]
            cell.width = Inches(width)
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(width * 1440)))
            tc_w.set(qn("w:type"), "dxa")


def set_table_indent(table, indent_dxa: int = 0) -> None:
    tbl_pr = table._tbl.tblPr
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")


def set_row_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = tr_pr.find(qn("w:cantSplit"))
    if cant_split is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def apply_document_styles(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.header_distance = Inches(0.49)
    section.footer_distance = Inches(0.49)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT_CN
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT_BODY)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_BODY)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.22
    normal.paragraph_format.space_after = Pt(6)

    for style_name, size, color, before, after in [
        ("Heading 1", 15.5, BLUE, 12, 7),
        ("Heading 2", 12.8, BLUE, 9, 5),
        ("Heading 3", 11.2, DARK_BLUE, 6, 3),
    ]:
        style = styles[style_name]
        style.font.name = FONT_CN
        style._element.rPr.rFonts.set(qn("w:ascii"), FONT_BODY)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_BODY)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for style_name in ["List Bullet", "List Number"]:
        style = styles[style_name]
        style.font.name = FONT_CN
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        style.font.size = Pt(10)
        style.paragraph_format.space_after = Pt(3)

    header = section.header
    hp = header.paragraphs[0]
    hp.text = "同济大学学科国际排名报告生成项目 | 阶段性工作报告"
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_para_font(hp, size=8.5, color=GRAY)

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.text = "内部阶段汇报材料"
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_font(fp, size=8.5, color=GRAY)


def add_para(
    doc: Document,
    text: str = "",
    *,
    style: str | None = None,
    bold: bool = False,
    color: RGBColor | None = None,
    size: float | None = None,
    align: int | None = None,
    before: float | None = None,
    after: float | None = None,
) -> None:
    p = doc.add_paragraph(style=style)
    if align is not None:
        p.alignment = align
    if before is not None:
        p.paragraph_format.space_before = Pt(before)
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    if text:
        r = p.add_run(text)
        set_run_font(r, size=size, color=color, bold=bold)


def add_heading(doc: Document, text: str, level: int = 1) -> None:
    p = doc.add_heading(text, level=level)
    p.paragraph_format.keep_with_next = True


def add_bullets(doc: Document, items: Iterable[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.12)
        r = p.add_run(item)
        set_run_font(r, size=10.2)


def add_numbered(doc: Document, items: Iterable[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.left_indent = Inches(0.32)
        p.paragraph_format.first_line_indent = Inches(-0.14)
        r = p.add_run(item)
        set_run_font(r, size=10.2)



def format_caption_paragraph(paragraph, text: str, *, before: float, after: float, keep_with_next: bool) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.keep_with_next = keep_with_next
    r = paragraph.add_run(text)
    set_run_font(r, size=CAPTION_SIZE, color=DARK_BLUE, bold=True)


def add_figure_caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    format_caption_paragraph(p, text, before=3, after=9, keep_with_next=False)


def add_table_caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    format_caption_paragraph(p, text, before=8, after=4, keep_with_next=True)


def add_picture_if_exists(doc: Document, path: Path, caption: str, width: float = 6.35) -> None:
    if not path.exists():
        add_para(doc, f"（图片缺失：{path.name}）", color=RGBColor(155, 28, 28), size=9)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    add_figure_caption(doc, caption)


def add_image_pair(doc: Document, left: Path, left_caption: str, right: Path, right_caption: str) -> None:
    table = doc.add_table(rows=2, cols=2)
    table.autofit = False
    set_table_widths(table, [3.12, 3.12])
    set_table_indent(table, 0)
    for row in table.rows:
        for cell in row.cells:
            set_cell_margins(cell, 40, 40, 40, 40)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = tc_pr.find(qn("w:tcBorders"))
            if borders is None:
                borders = OxmlElement("w:tcBorders")
                tc_pr.append(borders)
            for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
                node = borders.find(qn(f"w:{edge}"))
                if node is None:
                    node = OxmlElement(f"w:{edge}")
                    borders.append(node)
                node.set(qn("w:val"), "nil")
    for cell, path in [(table.cell(0, 0), left), (table.cell(0, 1), right)]:
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if path.exists():
            p.add_run().add_picture(str(path), width=Inches(2.95))
        else:
            r = p.add_run(f"图片缺失：{path.name}")
            set_run_font(r, size=8.5, color=RGBColor(155, 28, 28))
    for cell, caption in [(table.cell(1, 0), left_caption), (table.cell(1, 1), right_caption)]:
        p = cell.paragraphs[0]
        format_caption_paragraph(p, caption, before=2, after=4, keep_with_next=False)
    doc.add_paragraph()


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float], caption: str | None = None) -> None:
    if caption:
        add_table_caption(doc, caption)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    set_table_widths(table, widths)
    set_table_indent(table, 0)
    header_cells = table.rows[0].cells
    set_row_cant_split(table.rows[0])
    for idx, header in enumerate(headers):
        header_cells[idx].text = header
        set_cell_shading(header_cells[idx], LIGHT_BLUE)
        set_cell_text(header_cells[idx], bold=True, color=NAVY, size=9.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    for row in rows:
        row_obj = table.add_row()
        set_row_cant_split(row_obj)
        cells = row_obj.cells
        for idx, value in enumerate(row):
            cells[idx].text = str(value)
            if idx == 0:
                set_cell_shading(cells[idx], LIGHT_GRAY)
                set_cell_text(cells[idx], bold=True, color=NAVY, size=8.8, align=WD_ALIGN_PARAGRAPH.CENTER)
            else:
                set_cell_text(cells[idx], size=8.8, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph()


def add_compact_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float], caption: str | None = None) -> None:
    if caption:
        add_table_caption(doc, caption)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    set_table_widths(table, widths)
    set_table_indent(table, 0)
    for idx, header in enumerate(headers):
        set_row_cant_split(table.rows[0])
        cell = table.rows[0].cells[idx]
        cell.text = header
        set_cell_shading(cell, LIGHT_BLUE)
        set_cell_margins(cell, 70, 110, 70, 110)
        set_cell_text(cell, bold=True, color=NAVY, size=8.2, align=WD_ALIGN_PARAGRAPH.CENTER)
    for row in rows:
        row_obj = table.add_row()
        set_row_cant_split(row_obj)
        cells = row_obj.cells
        for idx, value in enumerate(row):
            cells[idx].text = str(value)
            set_cell_margins(cells[idx], 60, 100, 60, 100)
            if idx == 0:
                set_cell_shading(cells[idx], LIGHT_GRAY)
                set_cell_text(cells[idx], bold=True, color=NAVY, size=8.0, align=WD_ALIGN_PARAGRAPH.CENTER)
            else:
                set_cell_text(cells[idx], size=8.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph()


def add_callout(doc: Document, title: str, body: str) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    set_table_widths(table, [CONTENT_WIDTH_IN])
    cell = table.cell(0, 0)
    set_cell_shading(cell, PALE_BLUE)
    set_cell_margins(cell, 160, 190, 160, 190)
    p = cell.paragraphs[0]
    r = p.add_run(title)
    set_run_font(r, size=10.5, color=DARK_BLUE, bold=True)
    p.add_run("\n")
    r = p.add_run(body)
    set_run_font(r, size=10.0, color=RGBColor(50, 50, 50))
    doc.add_paragraph()


def normalize_fonts(doc: Document) -> None:
    def apply_to_paragraph(paragraph) -> None:
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name.startswith("Heading 1"):
            size = 15.5
            color = BLUE
            bold = True
        elif style_name.startswith("Heading 2"):
            size = 12.8
            color = BLUE
            bold = True
        elif style_name.startswith("Heading 3"):
            size = 11.2
            color = DARK_BLUE
            bold = True
        else:
            size = None
            color = None
            bold = None
        for run in paragraph.runs:
            set_run_font(run, size=size, color=color, bold=bold)

    for paragraph in doc.paragraphs:
        apply_to_paragraph(paragraph)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    apply_to_paragraph(paragraph)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def subject_label_from_dir(path: Path) -> str:
    match = re.search(r"_(\d{4})_(.+)$", path.name)
    if not match:
        return path.name
    return f"{match.group(1)} {match.group(2)}"


def latest_valid_report_dirs() -> list[Path]:
    root = PROJECT_DIR / "outputs" / "full_word_reports"
    if not root.exists():
        return []
    dirs: list[Path] = []
    for p in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if p.is_dir() and (p / "qa" / "word_qa_report.json").exists():
            dirs.append(p)
    return dirs


def collect_stats() -> dict:
    stats: dict[str, object] = {}
    db = PROJECT_DIR / "processed" / "ranking.sqlite"
    if db.exists():
        conn = sqlite3.connect(db)
        table_counts = {}
        for table_name in [
            "dim_subject",
            "dim_subject_alias",
            "fact_ranking",
            "fact_ranking_subject_bridge",
            "fact_ranking_indicator",
            "fact_ranking_indicator_subject_bridge",
        ]:
            try:
                table_counts[table_name] = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            except sqlite3.Error:
                table_counts[table_name] = 0
        stats["table_counts"] = table_counts
        ranking_rows = conn.execute(
            """
            SELECT ranking_source, COUNT(*), COUNT(DISTINCT ranking_subject_norm), COUNT(DISTINCT ranking_year)
            FROM fact_ranking
            GROUP BY ranking_source
            ORDER BY ranking_source
            """
        ).fetchall()
        stats["ranking_by_source"] = ranking_rows
        usnews_rows = conn.execute(
            """
            SELECT source_file, release_year, ranking_year, COUNT(*)
            FROM fact_ranking
            WHERE ranking_source = 'US News'
            GROUP BY source_file, release_year, ranking_year
            ORDER BY release_year, ranking_year
            """
        ).fetchall()
        stats["usnews_sources"] = usnews_rows
        conn.close()
    audit = read_json(PROJECT_DIR / "outputs" / "word_openability_audit" / "latest" / "word_openability_audit.json")
    stats["word_openability"] = {
        "docx_count": audit.get("docx_count", ""),
        "ooxml_issue_count": audit.get("ooxml_issue_count", ""),
        "word_com_error_count": audit.get("word_com_error_count", ""),
    }
    report_rows = []
    status_labels = {
        "pass": "通过",
        "pass_with_warnings": "警告通过",
        "fail": "未通过",
    }
    for wdir in latest_valid_report_dirs()[:8]:
        qa = read_json(wdir / "qa" / "word_qa_report.json")
        render = qa.get("render", {})
        report_rows.append(
            [
                subject_label_from_dir(wdir),
                status_labels.get(qa.get("overall_status", ""), qa.get("overall_status", "")),
                str(len(render.get("page_checks", []))),
                str(len(render.get("blank_pages", []))),
                str(len(render.get("sparse_pages", []))),
            ]
        )
    stats["report_rows"] = report_rows
    return stats


def crop_white_margin(source: Path, target: Path, padding: int = 24) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGB")
    bg = Image.new("RGB", image.size, "white")
    diff = ImageChops.difference(image, bg).convert("L")
    bbox = diff.point(lambda px: 255 if px > 10 else 0).getbbox()
    if not bbox:
        image.save(target)
        return
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.size[0], bbox[2] + padding)
    bottom = min(image.size[1], bbox[3] + padding)
    image.crop((left, top, right, bottom)).save(target)


def font(size: int, bold: bool = False):
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fill, text_font) -> None:
    bbox = draw.textbbox((0, 0), text, font=text_font)
    x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) / 2
    y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) / 2
    draw.text((x, y), text, fill=fill, font=text_font)


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, text_font, fill, max_width: int, line_gap: int = 8) -> int:
    x, y = xy
    line = ""
    lines = []
    for char in text:
        trial = line + char
        if draw.textlength(trial, font=text_font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = char
    if line:
        lines.append(line)
    for item in lines:
        draw.text((x, y), item, fill=fill, font=text_font)
        bbox = draw.textbbox((x, y), item, font=text_font)
        y = bbox[3] + line_gap
    return y


def create_data_scale_figure(stats: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    counts = stats.get("table_counts", {})
    rows = [
        ("排名事实", counts.get("fact_ranking", 0), "四大排名总排名长表"),
        ("指标事实", counts.get("fact_ranking_indicator", 0), "四大排名分项指标长表"),
        ("排名桥接", counts.get("fact_ranking_subject_bridge", 0), "榜单口径到一级学科桥接"),
        ("指标桥接", counts.get("fact_ranking_indicator_subject_bridge", 0), "分项指标到一级学科桥接"),
        ("学科维表", counts.get("dim_subject", 0), "教育部一级学科与榜单口径"),
        ("别名映射", counts.get("dim_subject_alias", 0), "中英文、历史口径和展示口径别名"),
    ]
    width, height = 1600, 880
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_f = font(42, True)
    sub_f = font(22)
    label_f = font(25, True)
    small_f = font(20)
    num_f = font(26, True)
    draw.text((70, 56), "结构化数据底座规模", fill=(11, 37, 69), font=title_f)
    draw.text((72, 114), "原始 Excel 经清洗后沉淀为事实表、维表和桥接表，支撑跨学科报告复用。", fill=(91, 102, 120), font=sub_f)
    max_value = max(value for _, value, _ in rows) or 1
    top = 190
    bar_left = 330
    bar_right = 1320
    colors = [(42, 112, 176), (77, 160, 132), (235, 159, 52), (140, 109, 190), (89, 123, 158), (198, 87, 92)]
    for idx, (name, value, note) in enumerate(rows):
        y = top + idx * 98
        draw.text((78, y + 4), name, fill=(11, 37, 69), font=label_f)
        draw.text((78, y + 40), note, fill=(91, 102, 120), font=small_f)
        draw.rounded_rectangle((bar_left, y + 12, bar_right, y + 58), radius=18, fill=(239, 243, 248))
        scaled = int((bar_right - bar_left) * (value / max_value) ** 0.55)
        draw.rounded_rectangle((bar_left, y + 12, bar_left + scaled, y + 58), radius=18, fill=colors[idx])
        draw.text((bar_right + 36, y + 18), f"{value:,}", fill=colors[idx], font=num_f)
    draw.rounded_rectangle((70, 790, 1530, 825), radius=16, fill=(246, 250, 253), outline=(210, 222, 236))
    draw.text((95, 796), "说明：图中使用非线性缩放展示数量级差异，避免指标桥接表遮蔽较小维表。", fill=(91, 102, 120), font=small_f)
    image.save(target)


def create_indicator_matrix_figure(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_f = font(42, True)
    sub_f = font(22)
    head_f = font(24, True)
    cell_f = font(22)
    small_f = font(18)
    draw.text((70, 52), "四大排名指标口径共性矩阵", fill=(11, 37, 69), font=title_f)
    draw.text((72, 110), "以指标类别呈现软科、QS、U.S. News、THE 的覆盖关系，替代线条交叉图，便于汇报场景快速阅读。", fill=(91, 102, 120), font=sub_f)
    columns = ["软科", "QS", "U.S. News", "THE"]
    rows = [
        ("科研/论文", ["●", "", "●", "●"], "论文、引文、高被引等科研表现"),
        ("声誉", ["", "●", "●", "●"], "学术声誉、雇主声誉或同行评价"),
        ("国际化/合作", ["●", "●", "●", "●"], "国际合作、国际师资、国际学生等"),
        ("教学/环境", ["", "", "", "●"], "教学环境、师生比等领域评价"),
        ("产业/转化", ["●", "", "", "●"], "产业收入、产学合作或成果转化"),
        ("人才/奖项", ["●", "", "", ""], "高层次奖项或优秀人才指标"),
    ]
    x0, y0 = 70, 190
    w_label, w_col, w_note = 260, 170, 500
    row_h = 92
    draw.rounded_rectangle((x0, y0, x0 + w_label + w_col * 4 + w_note, y0 + row_h * (len(rows) + 1)), radius=22, fill=(250, 252, 255), outline=(198, 212, 228), width=2)
    draw.rectangle((x0, y0, x0 + w_label + w_col * 4 + w_note, y0 + row_h), fill=(232, 240, 247))
    draw_centered(draw, (x0, y0, x0 + w_label, y0 + row_h), "指标类别", (11, 37, 69), head_f)
    for idx, col in enumerate(columns):
        left = x0 + w_label + idx * w_col
        draw_centered(draw, (left, y0, left + w_col, y0 + row_h), col, (11, 37, 69), head_f)
    draw_centered(draw, (x0 + w_label + w_col * 4, y0, x0 + w_label + w_col * 4 + w_note, y0 + row_h), "解释", (11, 37, 69), head_f)
    palette = [(42, 112, 176), (73, 151, 122), (235, 159, 52), (140, 109, 190)]
    for r_idx, (label, marks, note) in enumerate(rows):
        y = y0 + row_h * (r_idx + 1)
        if r_idx % 2:
            draw.rectangle((x0, y, x0 + w_label + w_col * 4 + w_note, y + row_h), fill=(246, 249, 252))
        draw.line((x0, y, x0 + w_label + w_col * 4 + w_note, y), fill=(210, 222, 236), width=1)
        draw_centered(draw, (x0, y, x0 + w_label, y + row_h), label, (11, 37, 69), head_f)
        for c_idx, mark in enumerate(marks):
            cx = x0 + w_label + c_idx * w_col + w_col // 2
            cy = y + row_h // 2
            if mark:
                draw.ellipse((cx - 19, cy - 19, cx + 19, cy + 19), fill=palette[c_idx])
                draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill="white")
            else:
                draw.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline=(190, 200, 214), width=2)
        draw_wrapped(draw, (x0 + w_label + w_col * 4 + 24, y + 24), note, cell_f, (65, 74, 86), w_note - 48, 4)
    draw.text((82, 820), "注：本图表达“指标类别是否覆盖”，不直接替代各榜单官方权重。", fill=(91, 102, 120), font=small_f)
    image.save(target)


def prepare_assets(stats: dict) -> dict[str, Path]:
    POLISHED_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    crops = {
        "chemistry_page": POLISHED_ASSET_DIR / "chemistry_render_page_7_crop.png",
        "chemistry_paper_page": POLISHED_ASSET_DIR / "chemistry_render_page_13_crop.png",
        "clinical_page": POLISHED_ASSET_DIR / "clinical_render_page_13_crop.png",
        "economics_page": POLISHED_ASSET_DIR / "economics_render_page_13_crop.png",
        "data_scale": POLISHED_ASSET_DIR / "core_data_scale_polished.png",
        "commonality": POLISHED_ASSET_DIR / "indicator_commonality_polished.png",
    }
    crop_white_margin(ASSET_DIR / "chemistry_render_page_7.png", crops["chemistry_page"])
    crop_white_margin(ASSET_DIR / "chemistry_render_page_13.png", crops["chemistry_paper_page"])
    crop_white_margin(ASSET_DIR / "clinical_render_page_13.png", crops["clinical_page"])
    crop_white_margin(ASSET_DIR / "economics_render_page_13.png", crops["economics_page"])
    create_data_scale_figure(stats, crops["data_scale"])
    create_indicator_matrix_figure(crops["commonality"])
    return crops


def add_cover(doc: Document, crops: dict[str, Path]) -> None:
    add_para(doc, "阶段性工作报告", size=14, color=GRAY, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=8)
    add_para(
        doc,
        "同济大学学科国际排名报告生成项目",
        size=24,
        color=NAVY,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=5,
    )
    add_para(
        doc,
        "数据治理、学科映射、图表 Artifact 与 Word 自动化交付体系",
        size=12.5,
        color=DARK_BLUE,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=14,
    )
    add_picture_if_exists(doc, PROVIDED_IMAGE_DIR / "provided_background_architecture_2.png", "图 1 项目自动化生成体系概览", width=6.25)
    add_table(
        doc,
        ["项目项", "说明"],
        [
            ["项目目录", str(PROJECT_DIR)],
            ["报告日期", datetime.now().strftime("%Y 年 %m 月 %d 日")],
            ["当前阶段", "多学科报告生成流程、最新排名数据接入、映射治理、图表生成和 Word 质量门禁已形成可复用闭环。"],
            ["主要用途", "向项目相关方汇报阶段建设成果、系统架构、关键问题处理、报告效果和下一阶段计划。"],
        ],
        [1.35, 5.1],
    )
    doc.add_page_break()


def add_toc(doc: Document) -> None:
    add_heading(doc, "目录", 1)
    toc_items = [
        "一、项目背景与阶段目标",
        "二、总体架构与端到端数据流",
        "三、数据治理与学科映射体系",
        "四、Subject Agent 与图表 Artifact 体系",
        "五、Word 报告组装与质量门禁",
        "六、关键问题、治理原则与修复成果",
        "七、阶段产出与报告效果展示",
        "八、当前边界、风险与下一阶段建议",
        "附录 A：运行入口、配置接口与 API 约定",
        "附录 B：数据表、Artifact 与 QA 文件契约",
        "附录 C：阶段性验证清单",
    ]
    for item in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Inches(0.08)
        r = p.add_run(item)
        set_run_font(r, size=11.3)
    add_para(
        doc,
        "说明：本页为静态章节目录，正文保留 Word Heading 样式；如需正式页码目录，可在 Word 中基于标题样式安全生成。",
        size=9.2,
        color=GRAY,
        before=8,
    )
    doc.add_page_break()



def add_cover_v2(doc: Document, crops: dict[str, Path]) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(52)
    p.paragraph_format.space_after = Pt(0)

    add_para(doc, "内部阶段汇报材料", size=12.2, color=GRAY, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=8)
    add_para(
        doc,
        "同济大学学科国际排名报告生成项目",
        size=24,
        color=NAVY,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=7,
    )
    add_para(
        doc,
        "数据治理、学科映射、图表产物与 Word 自动化交付体系",
        size=12.5,
        color=DARK_BLUE,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        after=22,
    )
    add_callout(
        doc,
        "阶段定位",
        "本报告用于汇报当前自动化报告生成链路的建设进展、核心数据更新、口径映射规则、图表与 Word 质量门禁，以及下一阶段工程化收敛建议。",
    )
    add_table(
        doc,
        ["项目项", "说明"],
        [
            ["项目目录", str(PROJECT_DIR)],
            ["报告日期", datetime.now().strftime("%Y 年 %m 月 %d 日")],
            ["当前阶段", "多学科报告生成、最新排名数据接入、映射治理、图表生成和 Word 稳定性验证已形成闭环。"],
            ["汇报重点", "说明已完成的工程能力、仍需固化的质量门禁，以及后续批量交付的风险控制。"],
        ],
        [1.35, 5.1],
    )
    add_table(
        doc,
        ["数据底座", "图表产物", "Word 质量"],
        [["结构化入库与来源追踪", "每图每表保留数据、规格和预览", "QA、渲染、Word COM 三类检查"]],
        [2.15, 2.15, 2.15],
    )
    doc.add_page_break()


def build_doc() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stats = collect_stats()
    crops = prepare_assets(stats)

    doc = Document()
    apply_document_styles(doc)
    add_cover_v2(doc, crops)
    add_toc(doc)

    add_heading(doc, "一、项目背景与阶段目标", 1)
    add_para(
        doc,
        "本项目围绕“同济大学学科国际排名发展分析”报告的自动化生成展开。过去这类报告高度依赖人工查表、人工制图、人工排版和人工校对；当学科数量增加、排名口径变化、历史数据补齐、Word 样式反复调整时，人工流程很容易出现口径不一致、图表来源不清、版本难追溯和 Word 打开不稳定等问题。",
    )
    add_para(
        doc,
        "本阶段工作的重点，是把分散的 Excel 数据、学科映射表、四大排名数据和报告写作规则，转化为一条可追溯、可复用、可审计的生成链路。最终目标不是只生成几份样例 Word，而是建立“数据源可追溯、学科口径可解释、图表产物可复查、Word 文档可打开可渲染”的工程闭环。",
    )
    add_callout(
        doc,
        "阶段性结论",
        "目前系统已经可以针对多个一级学科生成完整 Word 报告，并在代表性学科上通过 Word 质量检查、页面渲染检查和本机 Word 打开验证。后续工作的重心应从单点修复转向全量批次质量门禁、映射 registry 固化和接口收敛。",
    )
    add_table(
        doc,
        ["建设目标", "当前完成情况", "汇报价值"],
        [
            ["数据层结构化", "形成 processed/ranking.sqlite 与 CSV 镜像，沉淀排名事实表、指标事实表、学科维表和桥接表。", "将分散 Excel 转为统一数据底座，支撑跨学科复用和追溯。"],
            ["映射治理", "以最新学科映射表为第一优先级，区分展示口径、匹配口径、数据补齐口径和保底口径。", "避免报告中出现没有映射表来源的私自口径。"],
            ["图表 Artifact 化", "每张图表保留数据、规格、预览图、来源追踪和正文解读草稿。", "图表可以复查、替换、复用，不再只是一张不可解释的图片。"],
            ["Word 质量门禁", "形成 Word 质量检查、页面渲染、本机 Word 打开和系统体检的检查组合。", "降低目录损坏、乱码、空白页、图题不一致等交付风险。"],
        ],
        [1.25, 2.85, 2.35],
        "表 1 阶段目标与完成情况",
    )

    add_heading(doc, "二、总体架构与端到端数据流", 1)
    add_para(
        doc,
        "系统架构采用分层设计：原始数据层保存四大排名、权重、学科映射和补充数据；结构化处理层把 Excel 清洗为事实表、维表和 SQLite；Subject Agent 层围绕目标学科选择排名口径并生成图表 Artifact；Word 组装层把图表、表格、正文、口径说明和建议章节整合为报告；QA 层负责结构检查、渲染页面检查和 Word 实际打开验证。",
    )
    add_picture_if_exists(doc, PROVIDED_IMAGE_DIR / "provided_background_architecture_1.png", "图 1 从人工撰写到 Agent 自动生成的流程转变", width=6.25)
    add_para(
        doc,
        "这套分层设计的关键，不是把所有逻辑堆在一个脚本里，而是明确每一层的输入、输出和审计边界。原始数据不被自动覆盖；processed 目录只承载派生结构化数据；subject_agent_runs 保留每次学科分析的中间产物；full_word_reports 保存最终 Word 与 QA；runtime 配置则定义当前学校、学科、年份和输出策略。",
    )
    add_picture_if_exists(doc, PROVIDED_IMAGE_DIR / "provided_background_architecture_3.png", "图 2 从需求输入到报告交付的运行闭环", width=6.25)
    add_picture_if_exists(doc, crops["data_scale"], "图 3 核心结构化数据表规模概览", width=6.1)
    table_counts = stats.get("table_counts", {})
    doc.add_page_break()
    add_table(
        doc,
        ["数据表", "记录数", "主要职责"],
        [
            ["学科维表", f"{table_counts.get('dim_subject', 0):,}", "统一管理教育部一级学科、榜单口径和报告展示学科。"],
            ["学科别名映射表", f"{table_counts.get('dim_subject_alias', 0):,}", "保存中英文、历史名称和展示名称之间的别名映射。"],
            ["总排名事实表", f"{table_counts.get('fact_ranking', 0):,}", "保存四大排名的总排名记录。"],
            ["排名学科桥接表", f"{table_counts.get('fact_ranking_subject_bridge', 0):,}", "把榜单排名记录桥接到一个或多个一级学科。"],
            ["分项指标事实表", f"{table_counts.get('fact_ranking_indicator', 0):,}", "保存各榜单分项指标的长表记录。"],
            ["指标学科桥接表", f"{table_counts.get('fact_ranking_indicator_subject_bridge', 0):,}", "把分项指标记录桥接到一级学科。"],
        ],
        [2.05, 1.05, 3.35],
        "表 2 核心数据层表规模与职责",
    )

    add_heading(doc, "三、数据治理与学科映射体系", 1)
    add_para(
        doc,
        "数据治理的核心难点在于：四大排名并不共享同一套学科命名，THE 常使用领域口径，US News 存在中英文口径和历史年份字段差异，QS 与软科也存在多口径、一对多或多年字段差异。如果只按字符串相等取数，报告会漏数；如果任意扩展映射，又会出现报告中没有来源依据的口径。",
    )
    add_para(
        doc,
        "因此，本阶段把“展示口径”和“内部匹配口径”分开处理：映射表中的候选学科是第一优先级；只要候选口径中存在可用数据，就不允许使用内部保底映射；只有候选口径全部无最新可用综合位次时，才允许启用经过定义的 fallback，并必须在正文中说明使用了什么保底口径、为什么使用、哪些候选口径没有数据。",
    )
    add_bullets(
        doc,
        [
            "展示口径：用于 Word 正文、图题和口径说明，是面向读者可见的榜单学科或领域名称。",
            "匹配别名：仅用于内部匹配原始榜单数据，不直接作为 Word 展示口径。",
            "数据口径交叉表：用于处理历史数据、THE 权重等源内命名差异，必须保留在来源追踪中。",
            "保底口径映射：只有在候选口径无数据时才可启用，并需要在报告中披露代理性。"
        ]
    )
    ranking_rows = stats.get("ranking_by_source", [])
    doc.add_page_break()
    add_table(
        doc,
        ["排名来源", "总记录数", "学科/领域数", "年份覆盖数"],
        [[str(a), f"{b:,}", str(c), str(d)] for a, b, c, d in ranking_rows],
        [1.35, 1.25, 1.35, 1.35],
        "表 3 四大排名总排名数据覆盖情况",
    )
    add_para(
        doc,
        "US News 是本阶段数据治理中改动最复杂的一条线。历史文件在年份、学科语言、学校名称列和总分列上存在差异：2021 年有 subjectscore，2024-2025 年有“总得分.1”，2026 年又引入最新发布文件。当前逻辑已经把这些差异前置到源文件解析层，不在 Word 组装阶段临时猜列名。",
    )
    add_table(
        doc,
        ["US News 来源文件", "发布年", "排名年", "入库行数"],
        [[str(a), str(b), str(c), f"{d:,}"] for a, b, c, d in stats.get("usnews_sources", [])],
        [3.55, 0.85, 0.85, 1.15],
        "表 4 US News 历史与最新数据接入情况",
    )

    add_heading(doc, "四、Subject Agent 与图表 Artifact 体系", 1)
    add_para(
        doc,
        "Subject Agent 是结构化数据和 Word 报告之间的执行层。它读取目标学校、目标学科、学科代码、报告年份、排名来源和口径策略，完成学科识别、候选口径判定、数据可用性检查、对标高校筛选、图表生成、source trace 留痕和 artifact 审计。",
    )
    add_table(
        doc,
        ["Artifact 文件", "作用"],
        [
            ["图表数据表", "保存作图或制表使用的最终结构化数据。"],
            ["图表规格说明", "记录图表类型、字段、筛选逻辑、排序方式和口径。"],
            ["图表预览图", "供 Word 直接插入或排版核查使用。"],
            ["来源追踪表", "记录源文件、工作表、行号、别名和学科桥接等追溯字段。"],
            ["正文解读稿", "为 Word 正文提供图表解读草稿。"],
            ["运行日志", "记录生成过程、行数、异常和降级原因。"],
        ],
        [2.3, 4.15],
        "表 5 单个 Artifact 的标准产物契约",
    )
    add_para(
        doc,
        "图表 Artifact 化以后，Word 组装层不再直接读取原始 Excel。这样做虽然增加了中间产物数量，但换来了可审计性：任何一个图表都可以反查数据、规格、来源和口径判断，后续如果要替换图形样式，也不需要重写数据治理逻辑。",
    )
    add_picture_if_exists(doc, crops["commonality"], "图 4 四大排名指标口径共性矩阵示例", width=6.1)

    add_heading(doc, "五、Word 报告组装与质量门禁", 1)
    add_para(
        doc,
        "Word 组装层承担的是最终交付责任：它不仅要插入图表，还要把学科候选口径、缺失数据、fallback 原因、对标高校范围、图题表题、建议章节和附录组织成一份读者能理解的报告。本阶段已经多次修复 Word 层问题，包括图题字体字号一致性、表格单元格垂直居中、图表前后留白、建议章节行距、目录 XML 损坏风险规避，以及 Word COM 打开稳定性验证。",
    )
    add_table(
        doc,
        ["质量门禁", "检查内容", "当前策略"],
        [
            ["Word 质量检查", "检查 DOCX zip 结构、XML、媒体引用、空白页、稀疏页和基础字段。", "每份报告生成后输出质量检查结果。"],
            ["页面渲染检查", "将 Word 转为 PDF/PNG 页面，检查缺字、重叠、空白页和排版异常。", "最终交付前必须实际渲染页面。"],
            ["本机 Word 打开检查", "用本机 Word 实际打开，识别修复弹窗、损坏字段和目录异常。", "关键报告必须通过打开稳定性检查。"],
            ["来源追踪检查", "抽查关键图表是否来自目标源文件、年份和口径。", "以来源追踪表和图表规格为准，不只看图片。"],
        ],
        [1.35, 2.85, 2.2],
        "表 6 Word 报告质量门禁",
    )
    openability = stats.get("word_openability", {})
    add_callout(
        doc,
        "最近一次打开稳定性结果",
        f"word_openability_audit 覆盖 {openability.get('docx_count', '')} 份报告，OOXML 问题数为 {openability.get('ooxml_issue_count', '')}，Word COM 打开错误数为 {openability.get('word_com_error_count', '')}。系统体检目前无 P0/P1 阻断，仍有若干 P2 维护性提示需要后续收敛。",
    )

    add_heading(doc, "六、关键问题、治理原则与修复成果", 1)
    add_para(
        doc,
        "本阶段的修复工作集中在“数据是否新、口径是否准、表述是否严谨、Word 是否稳定”四个方面。以下问题不是孤立 bug，而是推动系统规则成型的关键节点。",
    )
    add_table(
        doc,
        ["问题类型", "风险表现", "治理方式", "当前结果"],
        [
            ["US News 历史字段差异", "不同年份文件列名、语言和排名年口径不一致，导致 2024 等年份在 Word 中缺失。", "按源文件配置解析 release_year、ranking_year、总分列和中英文学科别名。", "历史和最新 US News 数据已接入总排名与分项指标链路。"],
            ["映射表一对多", "一级学科对应多个榜单口径时，报告可能私自扩展候选。", "以最新映射表候选口径为准；候选有数据时不使用保底映射。", "环境、化学、临床医学等一对多场景按候选集解释。"],
            ["保底口径披露", "候选口径均无数据时，直接使用内部近似口径会显得无来源。", "只在候选无数据时启用，并写明候选无数据、保底口径和数据可用性。", "读者可区分映射表候选与内部保底。"],
            ["对标表第 25 行歧义", "同济被追加到第 25 行时，容易误解为国内第 25 名。", "前 24 名正常列示；同济超出范围时以“同济参照”单独说明，不解释为名次。", "表格标题和正文表述更严谨。"],
            ["目录域代码损坏", "直接修改目录域代码曾导致 Word 修复弹窗。", "撤销直接目录 XML 后处理；目录样式变更采用安全路径。", "代表报告 Word 打开稳定。"],
            ["图题样式不一致", "后插入图题字体字号与模板不一致。", "统一后插入图题为仿宋_GB2312 12 号并设置 eastAsia 字体。", "图题显示稳定。"],
        ],
        [1.25, 1.85, 2.15, 1.2],
        "表 7 关键问题与修复成果",
    )

    add_heading(doc, "七、阶段产出与报告效果展示", 1)
    add_para(
        doc,
        "当前 outputs/full_word_reports 中保留了多份代表性学科报告，覆盖化学、临床医学、应用经济学、环境科学与工程、计算机科学与技术、土木工程、材料科学与工程、生物学、药学、管理科学与工程等学科。下面选取部分图表和渲染页展示报告效果。",
    )
    add_table(
        doc,
        ["学科报告", "Word质量", "渲染页数", "空白页", "稀疏页"],
        stats.get("report_rows", []),
        [2.6, 1.0, 0.9, 0.8, 0.8],
        "表 8 最近代表性 Word 报告 QA 摘要",
    )
    add_picture_if_exists(doc, ASSET_DIR / "chemistry_overview.png", "图 5 化学报告：同济四大排名最新概览", width=5.75)
    add_picture_if_exists(doc, ASSET_DIR / "chemistry_history.png", "图 6 化学报告：四大排名历史趋势", width=5.75)
    add_image_pair(
        doc,
        ASSET_DIR / "chemistry_usnews_peer_indicator.png",
        "图 7 化学 US News 对标高校分项指标",
        ASSET_DIR / "economics_usnews_indicator_trend.png",
        "图 8 应用经济学 US News 分项指标趋势",
    )
    add_para(
        doc,
        "除图表本身外，最终 Word 报告还需要在页面层面保持稳定。以下渲染页示例展示了正文段落、表格、图题和报告页眉页脚在实际 Word/PDF 输出中的组合效果。页面截图经过裁边处理，目的是突出正文内容而不是展示大片页边距。",
        after=4,
    )
    add_image_pair(
        doc,
        crops["chemistry_page"],
        "图 9 化学报告渲染页示例",
        crops["clinical_page"],
        "图 10 临床医学报告渲染页示例",
    )
    add_picture_if_exists(doc, crops["economics_page"], "图 11 应用经济学报告渲染页示例", width=4.45)
    add_picture_if_exists(doc, crops["chemistry_paper_page"], "图 12 化学报告论文与科研表现渲染页示例", width=4.45)

    add_heading(doc, "八、当前边界、风险与下一阶段建议", 1)
    add_para(
        doc,
        "项目已经形成可复用闭环，但仍处于阶段性建设状态。下一阶段不宜继续只围绕单份报告做局部修补，而应把已经验证过的规则固化为可持续运行的工程机制，重点推进入口统一、批量质量门禁、映射 registry 和交付说明模板。",
    )
    add_table(
        doc,
        ["方向", "当前边界", "建议动作"],
        [
            ["入口统一", "仍存在部分历史脚本和调试脚本。", "以 runtime profile + subject request 为唯一正式入口，继续收敛 legacy 脚本。"],
            ["模块拆分", "subject_artifact_builders.py 和 Word builder 体量较大。", "按 ranking、indicator、paper、Word assembly 拆分模块，保留统一接口。"],
            ["全量交付", "代表学科已多轮验证，但全量报告需要系统 gate。", "按学科批次运行 release quality gate，分批输出问题清单。"],
            ["映射治理", "新数据会持续带来新口径和例外。", "把映射表候选、内部 fallback、proxy 映射写入可审计 registry。"],
            ["交付说明", "报告使用者需要理解候选口径、缺失数据和保底映射。", "在 Word 首段和附录固定输出候选口径、选用口径、缺失数据和 fallback 原因。"],
        ],
        [1.15, 2.25, 3.05],
        "表 9 下一阶段建议",
    )

    add_heading(doc, "附录 A：运行入口、配置接口与 API 约定", 1)
    add_heading(doc, "A.1 正式入口", 2)
    add_table(
        doc,
        ["入口/配置", "用途"],
        [
            ["全局运行配置", "对应 configs/runtime/agent_runtime_profile.json，用于统一学校、报告年份、输出策略和 QA 开关。"],
            ["当前学科请求", "对应 configs/runtime/current_subject_request.json，用于记录目标学科、学科代码和排名来源。"],
            ["单学科报告入口", "负责写入当前学科请求并调用后续报告生成流程。"],
            ["学科 Agent 入口", "按学科生成图表、表格、来源追踪和审计结果。"],
            ["Word 组装入口", "将单学科产物组装为完整 Word 报告。"],
            ["系统体检入口", "跨学科、数据治理或可维护性修改后的系统检查入口。"],
            ["Word 打开审计入口", "执行本机 Word 打开和 OOXML 稳定性检查。"],
        ],
        [2.55, 3.85],
    )
    add_heading(doc, "A.2 请求对象字段", 2)
    add_table(
        doc,
        ["字段", "说明"],
        [
            ["目标学校", "当前默认同济大学。"],
            ["目标学科", "用于报告标题、学科解析和口径选择。"],
            ["学科代码", "教育部一级学科代码，是正式报告的核心学科标识来源。"],
            ["报告年份", "当前为 2026。"],
            ["排名来源", "通常为软科、QS、U.S. News、THE。"],
            ["保底策略", "决定是否允许并披露保底口径或代理数据。"],
            ["对标范围", "用于定义参与比较的内地高校样本范围。"],
        ],
        [1.75, 4.65],
    )
    add_heading(doc, "A.3 调用约定", 2)
    add_numbered(
        doc,
        [
            "正式运行优先改 runtime profile / subject request，不在多个脚本中散改硬编码。",
            "脚本入口保持显式变量风格，但显式变量默认从 runtime 配置读取。",
            "涉及中文路径、中文表头或映射常量时，避免通过 PowerShell 内联字符串传递，优先使用 UTF-8 文件和稳定 ASCII key。",
            "生成 Word 后至少检查 Word 质量检查、渲染检查、本机 Word 打开、关键图题和目录页。",
        ]
    )

    add_heading(doc, "附录 B：数据表、Artifact 与 QA 文件契约", 1)
    add_heading(doc, "B.1 数据查询契约", 2)
    add_para(
        doc,
        "查询学科排名时不能只依赖 fact_ranking.subject_id。THE、US News 等来源存在广域口径或一对多口径，应通过 dim_subject_alias 或 bridge 表连接，至少同时约束 ranking_source、ranking_subject_norm 和目标 subject_id。",
    )
    add_heading(doc, "B.2 Artifact 消费契约", 2)
    add_bullets(
        doc,
        [
            "Word writer 应消费目标 run_dir 下的 artifact，不重新读取原始 Excel。",
            "图表正文优先读取 narrative.md；涉及口径、年份和缺失数据时，以 source_trace.csv 和 spec 为准。",
            "正式图表使用 chart.png 或 Word-native table；附录可引用 table_data.csv、source_trace.csv 和 chart_spec.json。",
            "任何 candidate_indirect、external_proxy 或 fallback_mapping 都需要在正文或附录披露。"
        ]
    )
    add_heading(doc, "B.3 QA 文件契约", 2)
    add_compact_table(
        doc,
        ["文件", "关键字段/用途"],
        [
            ["Word 质量结果", "包括整体状态、空白页、稀疏页、压缩包结构和基础字段。"],
            ["产物审计报告", "汇总各图表和表格产物是否通过检查。"],
            ["Agent 决策摘要", "记录可用来源数、产物数和关键阻断数。"],
            ["来源决策矩阵", "记录四大排名是否可用，以及是否使用补充或保底来源。"],
            ["来源追踪表", "记录源文件、工作表、行号、别名和学科桥接等追溯字段。"],
        ],
        [2.1, 4.3],
    )

    doc.add_page_break()
    add_heading(doc, "附录 C：阶段性验证清单", 1)
    add_compact_table(
        doc,
        ["检查项", "证据", "结论"],
        [
            ["US News 最新数据接入", "2026 年 US News 世界学科排名文件已进入总排名、分项指标和同济历史指标链路。", "通过"],
            ["代表学科报告生成", "化学、临床医学、应用经济学等报告已完成 Word 质量检查和渲染检查。", "通过"],
            ["Word 打开稳定性", "word_openability_audit 最近结果为 OOXML issue=0、Word COM error=0。", "通过"],
            ["映射候选规则", "候选有数据时不使用保底映射；候选无数据时披露 fallback。", "通过"],
            ["对标表歧义修复", "同济超出前 24 名时以参照行说明，不解释为序号排名。", "通过"],
            ["系统体检", "audit_agent_system_readiness 无 P0/P1，仅保留 P2 维护性提示。", "通过"],
        ],
        [1.55, 3.8, 0.95],
    )
    add_para(
        doc,
        "本阶段报告本身也需经过 DOCX 渲染检查和 Word 实际打开检查后再对外呈现。",
        bold=True,
        color=DARK_BLUE,
        size=9.2,
    )

    normalize_fonts(doc)
    doc.save(DOCX_PATH)
    print(DOCX_PATH)


if __name__ == "__main__":
    build_doc()
