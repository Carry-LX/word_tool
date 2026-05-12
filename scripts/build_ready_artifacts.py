from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_ROOT = PROJECT_DIR / "outputs" / "artifacts"
CONFIG_DIR = PROJECT_DIR / "configs"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_RANKING_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
REGISTRY_PATH = CONFIG_DIR / "artifact_registry.yaml"
README_PATH = PROJECT_DIR / "README.md"

TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
TARGET_THE_AREA = "理学"
TARGET_THE_WEIGHT_AREA = "自然科学"
REPORT_YEAR = 2026

SOURCE_COLORS = {
    "软科": "#C64B46",
    "QS": "#315D9C",
    "US News": "#3C8D5A",
    "THE": "#7B5CA8",
}
GROUP_COLORS = {
    "声誉": "#5B8DEF",
    "科研/论文": "#47A878",
    "国际化/合作": "#D68A35",
    "教学/环境": "#7A60B0",
    "人才/奖项": "#C85D7B",
    "产业/转化": "#6B7280",
    "其他": "#9AA4B2",
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str = "#1F2933",
) -> None:
    left, top, right, bottom = box
    tw, th = text_size(draw, text, font)
    draw.text((left + (right - left - tw) / 2, top + (bottom - top - th) / 2 - 2), text, fill=fill, font=font)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    text = clean_text(text)
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if text_size(draw, candidate, font)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    fill: str = "#1F2933",
    line_gap: int = 6,
    max_lines: int | None = None,
) -> int:
    lines = wrap_text(draw, text, font, max_width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, len(lines[-1]) - 1)] + "…"
    x, y = xy
    line_h = text_size(draw, "高", font)[1] + line_gap
    for idx, line in enumerate(lines):
        draw.text((x, y + idx * line_h), line, font=font, fill=fill)
    return y + len(lines) * line_h


def image_canvas(width: int = 1600, height: int = 920) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), "#FFFFFF")
    return image, ImageDraw.Draw(image)


def save_png_checked(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    with Image.open(path) as check:
        check.verify()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_artifact_log(artifact_id: str, lines: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "artifact_generation_run_log.md"
    if not log_path.exists():
        log_path.write_text("# Artifact 生成过程留档\n", encoding="utf-8", newline="\n")
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n## {now_text()} {artifact_id}\n\n")
        handle.write("\n".join(f"- {line}" for line in lines))
        handle.write("\n")


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    clean_df = df.fillna("").astype(str)
    columns = clean_df.columns.tolist()
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in clean_df.iterrows():
        values = [clean_text(row[col]).replace("|", "/") for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def output_dir(artifact_id: str) -> Path:
    return OUTPUT_ROOT / artifact_id


def read_weight_data() -> pd.DataFrame:
    df = pd.read_csv(FACT_WEIGHT_CSV, dtype=str).fillna("")
    df["weight_percent"] = pd.to_numeric(df["weight_percent"], errors="coerce").fillna(0.0)
    return df


def read_ranking_indicator_data() -> pd.DataFrame:
    df = pd.read_csv(FACT_RANKING_INDICATOR_CSV, dtype=str).fillna("")
    for column in ["release_year", "ranking_year", "metric_value", "metric_rank_midpoint", "world_rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def query_tongji_ranking_history() -> tuple[pd.DataFrame, pd.DataFrame]:
    query = """
    SELECT
      f.ranking_source,
      f.release_year,
      f.ranking_year,
      f.ranking_subject_raw,
      f.rank_raw,
      f.rank_min,
      f.rank_max,
      f.rank_midpoint,
      f.total_score,
      f.source_file,
      f.source_sheet,
      f.source_row,
      a.ranking_subject_alias,
      a.alias_type
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    JOIN dim_subject s
      ON a.subject_id = s.subject_id
    WHERE s.ministry_subject_code = ?
      AND f.is_tongji = 1
    ORDER BY f.ranking_source, f.release_year, f.ranking_year
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[TARGET_SUBJECT_CODE])
    if df.empty:
        raise RuntimeError("未查询到同济大学数学学科排名历史。")
    for column in ["release_year", "ranking_year", "rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    trace_df = df.drop_duplicates().copy()
    key_cols = [
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "rank_raw",
        "rank_min",
        "rank_max",
        "rank_midpoint",
        "total_score",
    ]
    chart_df = (
        df.groupby(key_cols, dropna=False)
        .agg(
            ranking_subject_alias=("ranking_subject_alias", lambda s: "; ".join(sorted({clean_text(x) for x in s if clean_text(x)}))),
            alias_type=("alias_type", lambda s: "; ".join(sorted({clean_text(x) for x in s if clean_text(x)}))),
            source_ref_count=("source_row", "nunique"),
        )
        .reset_index()
        .sort_values(["ranking_source", "release_year", "ranking_year"])
    )
    chart_df.insert(0, "target_subject", TARGET_SUBJECT)
    chart_df.insert(0, "target_university", TARGET_UNIVERSITY)
    return chart_df, trace_df


def render_ranking_cards(df: pd.DataFrame, path: Path) -> None:
    image, draw = image_canvas(1600, 900)
    font_title = load_font(38, True)
    font_subtitle = load_font(22)
    font_source = load_font(30, True)
    font_rank = load_font(58, True)
    font_meta = load_font(20)
    font_note = load_font(18)

    draw.text((85, 52), "同济大学数学学科国际排名概览", font=font_title, fill="#16202A")
    draw.text((85, 102), "四大国际排名最新发布年份口径，排名区间保留原始表达", font=font_subtitle, fill="#5A6573")

    latest = df.sort_values(["ranking_source", "release_year", "ranking_year"]).groupby("ranking_source", as_index=False).tail(1)
    order = ["软科", "QS", "US News", "THE"]
    card_w, card_h = 330, 420
    start_x, y = 85, 185
    gap = 42
    for idx, source in enumerate(order):
        row = latest[latest["ranking_source"] == source]
        if row.empty:
            continue
        item = row.iloc[0]
        x = start_x + idx * (card_w + gap)
        color = SOURCE_COLORS[source]
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill="#F8FAFC", outline="#D8DEE8", width=2)
        draw.rectangle((x, y, x + card_w, y + 12), fill=color)
        draw.text((x + 30, y + 42), source, font=font_source, fill=color)
        rank = clean_text(item["rank_raw"])
        draw.text((x + 30, y + 118), rank, font=font_rank, fill="#111827")
        draw.text((x + 30, y + 214), f"发布年份：{int(item['release_year'])}", font=font_meta, fill="#374151")
        draw.text((x + 30, y + 252), f"排名年份：{int(item['ranking_year'])}", font=font_meta, fill="#374151")
        subject = clean_text(item["ranking_subject_raw"])
        draw_wrapped(draw, (x + 30, y + 292), f"排名口径：{subject}", font_meta, card_w - 60, fill="#4B5563", max_lines=2)
        score = clean_text(item.get("total_score", ""))
        if score:
            draw.text((x + 30, y + 354), f"总分：{score}", font=font_meta, fill="#4B5563")
    draw.text((85, 670), "说明：THE 为领域排名，数学映射至理学 / Physical Sciences；区间排名用于图中展示时另保留中位位次字段。", font=font_note, fill="#5A6573")
    save_png_checked(image, path)


def render_history_line(df: pd.DataFrame, path: Path) -> None:
    image, draw = image_canvas(1600, 920)
    font_title = load_font(36, True)
    font_subtitle = load_font(21)
    font_axis = load_font(18)
    font_label = load_font(15)
    font_legend = load_font(18)

    left, top, right, bottom = 140, 150, 1320, 740
    draw.text((90, 48), "同济大学数学学科四大国际排名历史趋势", font=font_title, fill="#16202A")
    draw.text((90, 94), "排名区间按中间位次绘图，数值越小表示排名越靠前", font=font_subtitle, fill="#5A6573")

    years = sorted(int(x) for x in df["release_year"].dropna().unique())
    values = [to_float(x) for x in df["rank_midpoint"].dropna()]
    y_min = 0
    y_max = max(500, int(math.ceil(max(values) / 100.0) * 100))

    def xp(year: int) -> float:
        return left + (year - min(years)) / max(1, max(years) - min(years)) * (right - left)

    def yp(value: float) -> float:
        return top + (value - y_min) / max(1, y_max - y_min) * (bottom - top)

    for tick in range(0, y_max + 1, 100):
        y = yp(tick)
        draw.line((left, y, right, y), fill="#E5E7EB", width=1)
        draw.text((left - 62, y - 10), str(tick), font=font_axis, fill="#697586")
    draw.line((left, top, left, bottom), fill="#9AA5B1", width=2)
    draw.line((left, bottom, right, bottom), fill="#9AA5B1", width=2)
    for year in years:
        x = xp(year)
        draw.line((x, bottom, x, bottom + 8), fill="#9AA5B1", width=2)
        draw_center(draw, (x - 34, bottom + 16, x + 34, bottom + 44), str(year), font_axis, "#52606D")

    for source, group in df.groupby("ranking_source"):
        group = group.sort_values(["release_year", "ranking_year"])
        color = SOURCE_COLORS.get(source, "#333333")
        points = [(xp(int(row["release_year"])), yp(float(row["rank_midpoint"]))) for _, row in group.iterrows()]
        if len(points) > 1:
            draw.line(points, fill=color, width=4)
        for (_, row), (x, y) in zip(group.iterrows(), points):
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color, outline="#FFFFFF", width=2)
            label = clean_text(row["rank_raw"])
            draw.text((x + 9, y - 20), label, font=font_label, fill=color)

    lx, ly = 1360, 176
    draw.text((lx, ly - 42), "榜单", font=font_legend, fill="#16202A")
    for idx, source in enumerate(["软科", "QS", "US News", "THE"]):
        y = ly + idx * 48
        color = SOURCE_COLORS[source]
        draw.line((lx, y + 12, lx + 40, y + 12), fill=color, width=5)
        draw.ellipse((lx + 16, y + 4, lx + 30, y + 18), fill=color, outline="#FFFFFF", width=2)
        draw.text((lx + 54, y), source, font=font_legend, fill="#374151")
    save_png_checked(image, path)


def render_weight_donut(df: pd.DataFrame, path: Path, title: str, subtitle: str) -> None:
    image, draw = image_canvas(1500, 900)
    font_title = load_font(36, True)
    font_subtitle = load_font(21)
    font_label = load_font(18)
    font_big = load_font(30, True)

    draw.text((72, 42), title, font=font_title, fill="#16202A")
    draw.text((72, 88), subtitle, font=font_subtitle, fill="#5A6573")
    rows = df.sort_values("weight_percent", ascending=False).to_dict("records")
    total = sum(to_float(row["weight_percent"]) for row in rows) or 100.0
    palette = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD", "#E17C05", "#937860", "#8C8C8C"]
    box = (92, 170, 732, 810)
    start = -90.0
    for idx, row in enumerate(rows):
        pct = to_float(row["weight_percent"])
        extent = 360.0 * pct / total
        draw.pieslice(box, start, start + extent, fill=palette[idx % len(palette)], outline="#FFFFFF", width=2)
        start += extent
    draw.ellipse((255, 333, 569, 647), fill="#FFFFFF", outline="#FFFFFF")
    draw_center(draw, (270, 405, 554, 455), f"{total:.0f}%", font_big, "#16202A")
    draw_center(draw, (270, 460, 554, 500), "权重合计", font_label, "#5A6573")

    x0, y0 = 820, 175
    for idx, row in enumerate(rows):
        y = y0 + idx * 66
        color = palette[idx % len(palette)]
        draw.rounded_rectangle((x0, y, x0 + 28, y + 28), radius=6, fill=color)
        label = clean_text(row["indicator_name"])
        draw.text((x0 + 46, y - 2), label, font=font_label, fill="#1F2933")
        draw.text((x0 + 510, y - 2), f"{to_float(row['weight_percent']):.1f}%", font=font_label, fill="#374151")
        group = clean_text(row.get("indicator_group", ""))
        if group:
            draw.text((x0 + 46, y + 28), group, font=load_font(15), fill="#697586")
    save_png_checked(image, path)


def render_commonality_flow(df: pd.DataFrame, path: Path) -> None:
    image, draw = image_canvas(1600, 940)
    font_title = load_font(36, True)
    font_subtitle = load_font(21)
    font_node = load_font(21, True)
    font_small = load_font(16)
    draw.text((70, 42), "四大国际学科排名指标共性", font=font_title, fill="#16202A")
    draw.text((70, 88), "按指标组归并：权重数据优先，US News 数学权重缺失时使用实际分项指标覆盖关系", font=font_subtitle, fill="#5A6573")

    sources = ["软科", "QS", "US News", "THE"]
    groups = sorted(df["indicator_group"].dropna().unique().tolist(), key=lambda x: (-df[df["indicator_group"] == x]["link_value"].sum(), x))
    source_y = {source: 190 + idx * 150 for idx, source in enumerate(sources)}
    group_y = {group: 155 + idx * min(92, 590 // max(1, len(groups))) for idx, group in enumerate(groups)}
    sx, gx = 160, 1120
    for source in sources:
        color = SOURCE_COLORS[source]
        y = source_y[source]
        draw.rounded_rectangle((sx, y, sx + 210, y + 70), radius=12, fill="#F8FAFC", outline=color, width=3)
        draw_center(draw, (sx, y, sx + 210, y + 70), source, font_node, color)
    for group in groups:
        color = GROUP_COLORS.get(group, "#9AA4B2")
        y = group_y[group]
        total = df[df["indicator_group"] == group]["link_value"].sum()
        draw.rounded_rectangle((gx, y, gx + 275, y + 62), radius=12, fill="#FFFFFF", outline=color, width=3)
        draw.text((gx + 20, y + 10), group, font=font_node, fill=color)
        draw.text((gx + 180, y + 16), f"{total:.1f}", font=font_small, fill="#697586")
    for _, row in df.iterrows():
        source = row["ranking_source"]
        group = row["indicator_group"]
        color = GROUP_COLORS.get(group, "#9AA4B2")
        y1 = source_y[source] + 35
        y2 = group_y[group] + 31
        width = max(2, min(16, int(to_float(row["link_value"]) / 4) + 2))
        draw.line((sx + 210, y1, gx, y2), fill=color, width=width)
    draw.text((70, 850), "注：link_value 对有权重榜单为权重百分比；US News 因数学权重缺失，使用数学分项指标数量并在数据缺口报告中单列权重缺口。", font=font_small, fill="#697586")
    save_png_checked(image, path)


def render_the_weight_tree(df: pd.DataFrame, path: Path) -> None:
    image, draw = image_canvas(1650, 980)
    font_title = load_font(36, True)
    font_subtitle = load_font(21)
    font_group = load_font(21, True)
    font_label = load_font(16)
    draw.text((70, 42), "THE 世界学科排名自然科学领域指标权重", font=font_title, fill="#16202A")
    draw.text((70, 88), "数学学科按 THE 理学 / Physical Sciences 领域口径，对应自然科学权重体系", font=font_subtitle, fill="#5A6573")

    group_df = df.groupby("indicator_group", as_index=False)["weight_percent"].sum().sort_values("weight_percent", ascending=False)
    left_x, right_x = 85, 620
    top = 170
    row_gap = 142
    for idx, group_row in group_df.iterrows():
        group = clean_text(group_row["indicator_group"])
        color = GROUP_COLORS.get(group, "#7A869A")
        y = top + list(group_df.index).index(idx) * row_gap
        draw.rounded_rectangle((left_x, y, left_x + 360, y + 86), radius=12, fill="#F8FAFC", outline=color, width=3)
        draw.text((left_x + 22, y + 17), group, font=font_group, fill=color)
        draw.text((left_x + 250, y + 20), f"{to_float(group_row['weight_percent']):.1f}%", font=font_group, fill="#374151")
        children = df[df["indicator_group"] == group].sort_values("weight_percent", ascending=False).head(5)
        child_y = y - 10
        for child_idx, (_, child) in enumerate(children.iterrows()):
            cy = child_y + child_idx * 42
            draw.line((left_x + 360, y + 43, right_x, cy + 18), fill=color, width=2)
            draw.rounded_rectangle((right_x, cy, right_x + 780, cy + 34), radius=8, fill="#FFFFFF", outline="#D6DCE5", width=1)
            draw.text((right_x + 16, cy + 6), clean_text(child["indicator_name"])[:44], font=font_label, fill="#1F2933")
            draw.text((right_x + 690, cy + 6), f"{to_float(child['weight_percent']):.1f}%", font=font_label, fill="#374151")
    save_png_checked(image, path)


def render_table_image(matrix_df: pd.DataFrame, path: Path, title: str, subtitle: str, max_rows: int = 24) -> None:
    cols = matrix_df.columns.tolist()
    rows = matrix_df.head(max_rows).fillna("").to_dict("records")
    width = max(1500, 160 + len(cols) * 150)
    height = 220 + (len(rows) + 1) * 46 + 80
    image, draw = image_canvas(width, height)
    font_title = load_font(32, True)
    font_subtitle = load_font(19)
    font_header = load_font(15, True)
    font_cell = load_font(14)
    draw.text((55, 36), title, font=font_title, fill="#16202A")
    draw.text((55, 80), subtitle, font=font_subtitle, fill="#5A6573")
    left, top, row_h = 55, 140, 46
    col_widths = [76 if i == 0 else 170 for i in range(len(cols))]
    if len(cols) > 2:
        col_widths[1] = 260
    x = left
    for idx, col in enumerate(cols):
        w = col_widths[idx]
        draw.rectangle((x, top, x + w, top + row_h), fill="#E9EEF5", outline="#CBD2D9")
        draw_center(draw, (x, top, x + w, top + row_h), str(col), font_header, "#1F2933")
        x += w
    for ridx, row in enumerate(rows):
        y = top + (ridx + 1) * row_h
        fill = "#FFFFFF" if ridx % 2 == 0 else "#F8FAFC"
        x = left
        for cidx, col in enumerate(cols):
            w = col_widths[cidx]
            draw.rectangle((x, y, x + w, y + row_h), fill=fill, outline="#CBD2D9")
            text = clean_text(row[col])
            if cidx == 1:
                draw.text((x + 8, y + 13), text[:18], font=font_cell, fill="#1F2933")
            else:
                draw_center(draw, (x, y, x + w, y + row_h), text[:16], font_cell, "#374151")
            x += w
    if len(matrix_df) > max_rows:
        draw.text((55, height - 52), f"注：图片预览展示前 {max_rows} 行，完整数据见 table_matrix.csv / table_data.csv。", font=load_font(15), fill="#697586")
    save_png_checked(image, path)


def render_peer_small_multiples(chart_df: pd.DataFrame, path: Path, title: str, rank_mode: bool) -> None:
    image, draw = image_canvas(1650, 980)
    font_title = load_font(34, True)
    font_subtitle = load_font(20)
    font_panel = load_font(17, True)
    font_small = load_font(14)
    draw.text((70, 38), title, font=font_title, fill="#16202A")
    draw.text((70, 82), "灰线为对标高校范围，蓝点为中位数，红点为同济大学；排名类指标数值越小越靠前", font=font_subtitle, fill="#5A6573")

    rows = chart_df.to_dict("records")
    cols = 2 if len(rows) <= 6 else 3
    panel_w = 730 if cols == 2 else 500
    panel_h = 122
    start_x, start_y = 70, 150
    x_gap, y_gap = 50, 28
    for idx, row in enumerate(rows):
        col = idx % cols
        rr = idx // cols
        x = start_x + col * (panel_w + x_gap)
        y = start_y + rr * (panel_h + y_gap)
        draw.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=10, fill="#FFFFFF", outline="#D8DEE8", width=1)
        name = clean_text(row.get("indicator_short_name", "")) or clean_text(row.get("indicator_name", ""))
        draw.text((x + 16, y + 14), name[:24], font=font_panel, fill="#16202A")

        if rank_mode:
            best = to_float(row.get("peer_best_indicator_rank"))
            median = to_float(row.get("peer_median_indicator_rank"))
            worst = to_float(row.get("peer_worst_indicator_rank"))
            tongji = to_float(row.get("tongji_indicator_rank"))
        else:
            best = to_float(row.get("peer_worst_score"))
            median = to_float(row.get("peer_median_score"))
            worst = to_float(row.get("peer_best_score"))
            tongji = to_float(row.get("tongji_score"))
        min_v, max_v = min(best, median, worst, tongji), max(best, median, worst, tongji)
        if min_v == max_v:
            max_v = min_v + 1

        line_x1, line_x2 = x + 44, x + panel_w - 44
        line_y = y + 73

        def xpos(value: float) -> float:
            return line_x1 + (value - min_v) / (max_v - min_v) * (line_x2 - line_x1)

        xb, xw, xm, xt = xpos(best), xpos(worst), xpos(median), xpos(tongji)
        draw.line((min(xb, xw), line_y, max(xb, xw), line_y), fill="#B8C2D0", width=8)
        draw.ellipse((xm - 7, line_y - 7, xm + 7, line_y + 7), fill="#315D9C", outline="#FFFFFF", width=2)
        draw.ellipse((xt - 9, line_y - 9, xt + 9, line_y + 9), fill="#C64B46", outline="#FFFFFF", width=2)
        draw.text((x + 16, y + 94), f"同济：{tongji:g}", font=font_small, fill="#C64B46")
        rel = clean_text(row.get("tongji_relative_rank_with_peer_reference", row.get("tongji_relative_rank_in_peer_scope", "")))
        if rel:
            draw.text((x + panel_w - 180, y + 94), f"相对位次：{rel}", font=font_small, fill="#374151")
    save_png_checked(image, path)


def build_weight_artifact(artifact_id: str, ranking_source: str, subject_area: str, title: str, subtitle: str) -> dict[str, Any]:
    out = output_dir(artifact_id)
    out.mkdir(parents=True, exist_ok=True)
    weights = read_weight_data()
    df = weights[(weights["ranking_source"] == ranking_source) & (weights["ranking_subject_or_area"] == subject_area)].copy()
    if df.empty:
        raise RuntimeError(f"{artifact_id} 未找到权重数据：{ranking_source} / {subject_area}")
    df = df.sort_values("weight_percent", ascending=False).reset_index(drop=True)
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df[["source_file", "source_sheet", "source_row", "ranking_source", "ranking_subject_or_area", "indicator_name", "weight_percent"]].to_csv(
        out / "source_trace.csv", index=False, encoding="utf-8-sig"
    )
    if artifact_id == "figure_06_the_indicator_weight":
        render_the_weight_tree(df, out / "chart.png")
        chart_type = "tree weight diagram"
    else:
        render_weight_donut(df, out / "chart.png", title, subtitle)
        chart_type = "donut weight chart"
    spec = {
        "artifact_id": artifact_id,
        "generated_at": now_text(),
        "target_subject": TARGET_SUBJECT,
        "target_university": TARGET_UNIVERSITY,
        "ranking_source": ranking_source,
        "ranking_subject_or_area": subject_area,
        "chart_type": chart_type,
        "data_source": "processed/fact_indicator_weight.csv",
        "row_count": len(df),
        "weight_total": float(df["weight_percent"].sum()),
        "outputs": {
            "chart_data": str(out / "chart_data.csv"),
            "chart_png": str(out / "chart.png"),
            "source_trace": str(out / "source_trace.csv"),
        },
    }
    (out / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    narrative = [
        f"# {title}",
        "",
        f"本图基于 `{ranking_source}` 的 `{subject_area}` 指标权重绘制，共 `{len(df)}` 个指标，权重合计 `{df['weight_percent'].sum():.1f}%`。",
        "",
        "## 重绘所需文件",
        "",
        "- chart_data.csv",
        "- chart_spec.json",
        "- source_trace.csv",
    ]
    (out / "narrative.md").write_text("\n".join(narrative) + "\n", encoding="utf-8", newline="\n")
    (out / "run_log.md").write_text(
        f"# {artifact_id} run log\n\n- generated_at: {spec['generated_at']}\n- rows: {len(df)}\n- weight_total: {df['weight_percent'].sum():.1f}\n",
        encoding="utf-8",
        newline="\n",
    )
    write_artifact_log(artifact_id, [f"输出目录：`{out}`", f"权重行数：{len(df)}", f"权重合计：{df['weight_percent'].sum():.1f}%"])
    return spec


def build_commonality_artifact() -> dict[str, Any]:
    artifact_id = "figure_02_ranking_indicator_commonality"
    out = output_dir(artifact_id)
    out.mkdir(parents=True, exist_ok=True)
    weights = read_weight_data()
    parts: list[pd.DataFrame] = []
    for source, subject_area in [("软科", "数学"), ("QS", "数学"), ("THE", "自然科学")]:
        subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == subject_area)].copy()
        subset["basis"] = "weight_percent"
        subset["link_value"] = subset["weight_percent"]
        parts.append(subset[["ranking_source", "ranking_subject_or_area", "indicator_name", "indicator_group", "basis", "link_value", "source_file", "source_sheet", "source_row"]])

    indicators = read_ranking_indicator_data()
    usn = indicators[
        (indicators["ranking_source"] == "US News")
        & (indicators["ranking_subject_norm"] == "数学")
        & (indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"]))
        & (indicators["metric_type"] == "rank")
    ].copy()
    if not usn.empty:
        latest_release = usn["release_year"].max()
        latest_ranking = usn[usn["release_year"] == latest_release]["ranking_year"].max()
        usn = usn[(usn["release_year"] == latest_release) & (usn["ranking_year"] == latest_ranking)].copy()
        usn["ranking_subject_or_area"] = "数学"
        usn["basis"] = "indicator_count_usnews_math_weight_missing"
        usn["link_value"] = 1.0
        parts.append(usn[["ranking_source", "ranking_subject_or_area", "indicator_name", "indicator_group", "basis", "link_value", "source_file", "source_sheet", "source_row"]])

    long_df = pd.concat(parts, ignore_index=True).fillna("")
    link_df = (
        long_df.groupby(["ranking_source", "ranking_subject_or_area", "indicator_group", "basis"], as_index=False)
        .agg(link_value=("link_value", "sum"), indicator_count=("indicator_name", "nunique"))
        .sort_values(["ranking_source", "indicator_group"])
    )
    link_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_commonality_flow(link_df, out / "chart.png")
    spec = {
        "artifact_id": artifact_id,
        "generated_at": now_text(),
        "target_subject": TARGET_SUBJECT,
        "chart_type": "indicator commonality flow",
        "data_source": "processed/fact_indicator_weight.csv + processed/fact_ranking_indicator.csv",
        "row_count": len(link_df),
        "notes": [
            "软科、QS、THE 使用权重百分比汇总到指标组。",
            "US News 数学权重缺失，因此本图的 US News 侧只展示数学分项指标覆盖关系；权重缺口已进入 data_gap_report。",
        ],
    }
    (out / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out / "narrative.md").write_text(
        "# 图2 分析草稿：四大国际学科排名指标共性\n\n本图把四大榜单指标归并到声誉、科研/论文、国际化/合作、教学/环境等指标组。US News 数学权重缺失，当前仅用已入库数学分项指标表示覆盖关系，不能解释为权重。\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / "run_log.md").write_text(f"# {artifact_id} run log\n\n- generated_at: {spec['generated_at']}\n- rows: {len(link_df)}\n", encoding="utf-8", newline="\n")
    write_artifact_log(artifact_id, [f"输出目录：`{out}`", f"link rows：{len(link_df)}", "US News 权重缺失已在缺口报告中单列"])
    return spec


def build_the_indicator_history_table() -> dict[str, Any]:
    artifact_id = "table_03_the_tongji_indicator_history"
    out = output_dir(artifact_id)
    out.mkdir(parents=True, exist_ok=True)
    indicators = read_ranking_indicator_data()
    df = indicators[
        (indicators["ranking_source"] == "THE")
        & (indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"]))
        & (indicators["ranking_subject_raw"].isin(["理学", "Physical Sciences"]))
    ].copy()
    if df.empty:
        raise RuntimeError("未找到 THE 理学/Physical Sciences 同济分项指标历史。")
    df = df.sort_values(["ranking_year", "metric_type", "indicator_name"]).reset_index(drop=True)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    df[["source_file", "source_sheet", "source_row", "release_year", "ranking_year", "ranking_subject_raw", "indicator_name", "metric_type", "metric_raw"]].to_csv(
        out / "source_trace.csv", index=False, encoding="utf-8-sig"
    )
    years = sorted(int(x) for x in df["ranking_year"].dropna().unique())
    rank_df = df[df["metric_type"].isin(["score", "rank"])].copy()
    row_order = ["总得分", "教学", "教学排名", "科研环境", "科研环境排名", "科研质量", "科研质量排名", "商业收入", "商业收入排名", "国际化视野", "国际化视野排名"]
    rows = []
    for indicator in row_order:
        subset = rank_df[rank_df["indicator_name"] == indicator]
        if subset.empty:
            continue
        row = {"指标": indicator}
        for year in years:
            value = subset[subset["ranking_year"] == year]["metric_raw"]
            row[str(year)] = clean_text(value.iloc[0]) if not value.empty else ""
        rows.append(row)
    matrix_df = pd.DataFrame(rows)
    matrix_df.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    render_table_image(matrix_df, out / "table.png", "THE 理学领域同济大学分项指标历史", "覆盖 2023-2026 排名年份；排名类指标数值越小越靠前", max_rows=24)
    (out / "table.md").write_text(dataframe_to_markdown(matrix_df), encoding="utf-8", newline="\n")
    spec = {
        "artifact_id": artifact_id,
        "generated_at": now_text(),
        "target_subject": TARGET_SUBJECT,
        "target_university": TARGET_UNIVERSITY,
        "table_type": "THE indicator history wide table",
        "data_source": "processed/fact_ranking_indicator.csv",
        "long_rows": len(df),
        "matrix_rows": len(matrix_df),
        "years": years,
    }
    (out / "table_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out / "narrative.md").write_text(
        "# 表4 分析草稿：THE 分项指标历史\n\n同济大学数学按 THE 理学 / Physical Sciences 领域口径处理。当前数据覆盖 2023-2026 排名年份，包含总得分、五类一级指标得分及对应排名。\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / "run_log.md").write_text(f"# {artifact_id} run log\n\n- generated_at: {spec['generated_at']}\n- long_rows: {len(df)}\n- years: {years}\n", encoding="utf-8", newline="\n")
    write_artifact_log(artifact_id, [f"输出目录：`{out}`", f"长表行数：{len(df)}", f"年份：{years}"])
    return spec


def build_appendix_history_table() -> dict[str, Any]:
    artifact_id = "table_09_peer_full_ranking_history_appendix"
    out = output_dir(artifact_id)
    out.mkdir(parents=True, exist_ok=True)
    source_artifacts = [
        ("软科", "table_05_arwu_mainland_peer_ranking"),
        ("US News", "table_06_usnews_mainland_peer_ranking"),
        ("QS", "table_07_qs_mainland_peer_ranking"),
        ("THE", "table_08_the_mainland_peer_ranking"),
    ]
    matrix_parts: list[pd.DataFrame] = []
    data_rows: list[dict[str, Any]] = []
    trace_parts: list[pd.DataFrame] = []
    for source, source_artifact in source_artifacts:
        matrix_path = output_dir(source_artifact) / "table_matrix.csv"
        latest_path = output_dir(source_artifact) / "latest_peer_records.csv"
        if not matrix_path.exists():
            continue
        matrix = pd.read_csv(matrix_path, dtype=str).fillna("")
        matrix.insert(0, "榜单", source)
        matrix_parts.append(matrix)
        for _, row in matrix.iterrows():
            university = clean_text(row.get("学校", row.get("瀛︽牎", "")))
            for col in matrix.columns:
                if col[:4].isdigit() and ("排名" in col or "鎺掑悕" in col):
                    data_rows.append(
                        {
                            "ranking_source": source,
                            "university": university,
                            "ranking_year": col[:4],
                            "rank_raw": clean_text(row[col]),
                            "source_artifact": source_artifact,
                        }
                    )
        if latest_path.exists():
            trace = pd.read_csv(latest_path, dtype=str).fillna("")
            trace.insert(0, "source_artifact", source_artifact)
            trace.insert(0, "ranking_source_for_appendix", source)
            trace_parts.append(trace)
    if not matrix_parts:
        raise RuntimeError("未找到 peer ranking 表格输出，无法生成附表。")
    full_matrix = pd.concat(matrix_parts, ignore_index=True, sort=False).fillna("")
    table_data = pd.DataFrame(data_rows)
    full_matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    table_data.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    source_trace = pd.concat(trace_parts, ignore_index=True, sort=False).fillna("") if trace_parts else table_data.copy()
    source_trace.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    preview_cols = [col for col in full_matrix.columns if col in ["榜单", "序号", "学校"] or col[:4].isdigit()]
    if not preview_cols:
        preview_cols = full_matrix.columns[:8].tolist()
    render_table_image(full_matrix[preview_cols], out / "table.png", "附表：数学学科对标高校排名历史", "由软科、QS、US News、THE 四个 peer ranking 表汇总", max_rows=28)
    (out / "table.md").write_text(dataframe_to_markdown(full_matrix), encoding="utf-8", newline="\n")
    spec = {
        "artifact_id": artifact_id,
        "generated_at": now_text(),
        "target_subject": TARGET_SUBJECT,
        "table_type": "appendix full peer ranking history",
        "data_source": "outputs/artifacts/table_05/06/07/08 table_matrix.csv + latest_peer_records.csv",
        "matrix_rows": len(full_matrix),
        "long_rows": len(table_data),
        "sources": [source for source, _ in source_artifacts],
    }
    (out / "table_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out / "narrative.md").write_text(
        "# 附表说明：对标高校排名历史\n\n本附表汇总四个榜单已生成的对标高校表格，用于 Word 附录或后续横向版面排版。图片仅作预览，完整宽表以 table_matrix.csv 为准。\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / "run_log.md").write_text(f"# {artifact_id} run log\n\n- generated_at: {spec['generated_at']}\n- matrix_rows: {len(full_matrix)}\n- long_rows: {len(table_data)}\n", encoding="utf-8", newline="\n")
    write_artifact_log(artifact_id, [f"输出目录：`{out}`", f"宽表行数：{len(full_matrix)}", f"长表行数：{len(table_data)}"])
    return spec


def restyle_existing_figures() -> list[str]:
    updated: list[str] = []
    fig01 = output_dir("figure_01_tongji_subject_ranking_overview")
    if (fig01 / "chart_data.csv").exists():
        df = pd.read_csv(fig01 / "chart_data.csv")
        render_ranking_cards(df, fig01 / "chart.png")
        updated.append("figure_01_tongji_subject_ranking_overview")

    fig07 = output_dir("figure_07_all_rankings_history")
    if (fig07 / "chart_data.csv").exists():
        df = pd.read_csv(fig07 / "chart_data.csv")
        render_history_line(df, fig07 / "chart.png")
        updated.append("figure_07_all_rankings_history")

    peer_specs = [
        ("figure_09_arwu_peer_indicator_relative_rank", "软科排名前200位内地高校分项指标相对表现", False),
        ("figure_11_usnews_peer_indicator_relative_rank", "US News 排名前200位内地高校分项指标相对排名", True),
        ("figure_12_the_peer_indicator_relative_rank", "THE 排名前200位内地高校分项指标相对排名", True),
    ]
    for artifact_id, title, rank_mode in peer_specs:
        out = output_dir(artifact_id)
        if (out / "chart_data.csv").exists():
            df = pd.read_csv(out / "chart_data.csv")
            render_peer_small_multiples(df, out / "chart.png", title, rank_mode)
            updated.append(artifact_id)
    write_artifact_log("restyle_existing_figures", [f"重绘正式图：{', '.join(updated)}"])
    return updated


def build_data_gap_report() -> dict[str, Any]:
    report_dir = CONFIG_DIR / "data_gap_report"
    report_dir.mkdir(parents=True, exist_ok=True)
    gaps = [
        {
            "logical_slot_id": "L005",
            "artifact_id": "figure_05_usnews_indicator_weight",
            "object": "US News 数学学科指标权重图",
            "gap_type": "missing_usnews_math_weight",
            "why_blocking": "fact_indicator_weight 当前没有 US News-数学 权重行，不能用计算机科学、商业与经济等其他学科权重替代。",
            "required_input": "US News 数学学科指标体系及权重表，至少包含指标名、权重、适用学科/年份、来源文件。",
        },
        {
            "logical_slot_id": "L019",
            "artifact_id": "figure_13_paper_output_citation_relative_rank",
            "object": "论文及被引总量相对排名图",
            "gap_type": "missing_paper_metric_source",
            "why_blocking": "data/ 与 processed/ 中未发现 WOS、InCites、ESI 或论文指标独立来源，不能从排名表臆造论文量和被引量。",
            "required_input": "37 所对标高校论文总量、被引总量及统计口径字段。",
        },
        {
            "logical_slot_id": "L020",
            "artifact_id": "figure_14_paper_cnci_cpp_relative_rank",
            "object": "CNCI 及篇均被引相对排名图",
            "gap_type": "missing_paper_quality_source",
            "why_blocking": "当前数据没有 CNCI 与篇均被引字段。",
            "required_input": "37 所对标高校 CNCI、篇均被引数、统计年份/窗口。",
        },
        {
            "logical_slot_id": "L021",
            "artifact_id": "figure_15_paper_highly_cited_relative_rank",
            "object": "高被引 TOP 论文量相对排名图",
            "gap_type": "missing_highly_cited_source",
            "why_blocking": "当前数据没有 TOP1% / TOP10% 高被引论文量字段。",
            "required_input": "37 所对标高校高被引论文数量及 TOP 口径。",
        },
        {
            "logical_slot_id": "L022",
            "artifact_id": "figure_16_paper_international_collab_relative_rank",
            "object": "国际合著论文占比相对排名图",
            "gap_type": "missing_international_collab_source",
            "why_blocking": "当前数据没有国际合著论文数量或占比字段。",
            "required_input": "37 所对标高校国际合著论文数、论文总数或国际合著占比。",
        },
    ]
    partial_constraints = [
        {
            "logical_slot_id": "L008",
            "artifact_id": "table_01_arwu_tongji_indicator_history",
            "status": "partial_only_latest_year",
            "note": "软科数学同济分项指标当前主要只有 2025；若模板坚持多年历史，需要补历史分项指标。",
        },
        {
            "logical_slot_id": "L009",
            "artifact_id": "table_02_usnews_tongji_indicator_history",
            "status": "partial_only_latest_year",
            "note": "US News 数学同济分项指标当前主要只有 2026；若模板坚持多年历史，需要补历史分项指标。",
        },
        {
            "logical_slot_id": "L010",
            "artifact_id": "figure_10_usnews_indicator_history_trend",
            "status": "partial_only_latest_year",
            "note": "US News 分项指标趋势图需要多年分项指标，当前不可生成可靠趋势。",
        },
    ]
    write_csv(report_dir / "data_gap_report.csv", gaps, list(gaps[0].keys()))
    (report_dir / "data_gap_report.json").write_text(
        json.dumps({"generated_at": now_text(), "hard_data_gaps": gaps, "partial_data_constraints": partial_constraints}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# Data Gap Report",
        "",
        f"- generated_at: {now_text()}",
        "- hard_data_gap_count: 5",
        "- 口径：这里的 5 个缺口是会阻断图表可靠绘制的硬缺口；软科/US News 分项历史的单年问题另列为 partial constraints。",
        "",
        "## 5 个硬性数据缺口",
        "",
        "| slot | artifact | 对象 | 缺口 | 需要补什么 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for gap in gaps:
        lines.append(f"| {gap['logical_slot_id']} | {gap['artifact_id']} | {gap['object']} | {gap['gap_type']} | {gap['required_input']} |")
    lines.extend(["", "## 非硬缺口但影响趋势完整性的约束", "", "| slot | artifact | 状态 | 说明 |", "| --- | --- | --- | --- |"])
    for item in partial_constraints:
        lines.append(f"| {item['logical_slot_id']} | {item['artifact_id']} | {item['status']} | {item['note']} |")
    lines.append("")
    (report_dir / "data_gap_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    write_artifact_log("data_gap_report", [f"输出目录：`{report_dir}`", "硬性缺口：5", "部分历史约束：3"])
    return {"hard_data_gap_count": len(gaps), "partial_constraint_count": len(partial_constraints), "report_dir": str(report_dir)}


def registry_entry(
    artifact_id: str,
    artifact_type: str,
    script_path: str,
    output_subdir: str,
    spec_file: str,
    required_outputs: list[str],
    optional_outputs: list[str],
    data_dependencies: list[str],
    reference_caption: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "priority": "P1" if artifact_type == "chart" else "P2",
        "status": "verified",
        "section": "按 Word 槽位映射",
        "reference_caption": reference_caption,
        "purpose": "根据已治理排名数据生成可插入 Word 的正式图表产物。",
        "script_path": script_path,
        "output_dir": output_subdir,
        "spec_file": spec_file,
        "required_outputs": required_outputs,
        "optional_outputs": optional_outputs,
        "data_dependencies": data_dependencies,
        "current_subject": TARGET_SUBJECT,
    }


def update_registry() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {item["artifact_id"]: item for item in registry.get("artifacts", [])}
    new_entries = [
        registry_entry(
            "figure_02_ranking_indicator_commonality",
            "chart",
            "scripts/build_artifact_figure_02.py",
            "outputs/artifacts/figure_02_ranking_indicator_commonality",
            "chart_spec.json",
            ["chart_data.csv", "chart_spec.json", "chart.png", "source_trace.csv", "narrative.md", "run_log.md"],
            [],
            ["processed/fact_indicator_weight.csv", "processed/fact_ranking_indicator.csv"],
            "图2、XX学科在世界学科排名中指标共性",
        ),
        registry_entry(
            "figure_03_arwu_indicator_weight",
            "chart",
            "scripts/build_artifact_figure_03.py",
            "outputs/artifacts/figure_03_arwu_indicator_weight",
            "chart_spec.json",
            ["chart_data.csv", "chart_spec.json", "chart.png", "source_trace.csv", "narrative.md", "run_log.md"],
            [],
            ["processed/fact_indicator_weight.csv"],
            "图3、软科世界一流学科数学指标权重",
        ),
        registry_entry(
            "figure_04_qs_indicator_weight",
            "chart",
            "scripts/build_artifact_figure_04.py",
            "outputs/artifacts/figure_04_qs_indicator_weight",
            "chart_spec.json",
            ["chart_data.csv", "chart_spec.json", "chart.png", "source_trace.csv", "narrative.md", "run_log.md"],
            [],
            ["processed/fact_indicator_weight.csv"],
            "图4、QS学科排名数学指标权重",
        ),
        registry_entry(
            "figure_06_the_indicator_weight",
            "chart",
            "scripts/build_artifact_figure_06.py",
            "outputs/artifacts/figure_06_the_indicator_weight",
            "chart_spec.json",
            ["chart_data.csv", "chart_spec.json", "chart.png", "source_trace.csv", "narrative.md", "run_log.md"],
            [],
            ["processed/fact_indicator_weight.csv"],
            "图4、THE世界学科排名自然科学领域指标权重",
        ),
        registry_entry(
            "table_03_the_tongji_indicator_history",
            "table",
            "scripts/build_artifact_table_03.py",
            "outputs/artifacts/table_03_the_tongji_indicator_history",
            "table_spec.json",
            ["table_data.csv", "table_spec.json", "table.png", "source_trace.csv", "narrative.md", "run_log.md"],
            ["table_matrix.csv", "table.md"],
            ["processed/fact_ranking_indicator.csv"],
            "表4、xx学科在THE排名中的细分指标排名历史",
        ),
        registry_entry(
            "table_09_peer_full_ranking_history_appendix",
            "table",
            "scripts/build_artifact_table_09.py",
            "outputs/artifacts/table_09_peer_full_ranking_history_appendix",
            "table_spec.json",
            ["table_data.csv", "table_spec.json", "table.png", "source_trace.csv", "narrative.md", "run_log.md"],
            ["table_matrix.csv", "table.md"],
            [
                "outputs/artifacts/table_05_arwu_mainland_peer_ranking/table_matrix.csv",
                "outputs/artifacts/table_06_usnews_mainland_peer_ranking/table_matrix.csv",
                "outputs/artifacts/table_07_qs_mainland_peer_ranking/table_matrix.csv",
                "outputs/artifacts/table_08_the_mainland_peer_ranking/table_matrix.csv",
            ],
            "附表：XX学科对标高校学科排名历史",
        ),
    ]
    for entry in new_entries:
        by_id[entry["artifact_id"]] = entry
    original_order = [item["artifact_id"] for item in registry.get("artifacts", [])]
    add_order = [entry["artifact_id"] for entry in new_entries if entry["artifact_id"] not in original_order]
    registry["artifacts"] = [by_id[artifact_id] for artifact_id in original_order if artifact_id in by_id] + [by_id[artifact_id] for artifact_id in add_order]
    registry["version"] = 2
    registry["last_updated"] = now_text()
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return {"artifact_count": len(registry["artifacts"]), "new_or_updated": len(new_entries)}


def update_readme(summary: dict[str, Any]) -> None:
    section_title = "## 本轮正式图表与数据缺口产物"
    block = [
        section_title,
        "",
        f"- generated_at: {now_text()}",
        f"- 新增可审计 artifact：`figure_02`、`figure_03`、`figure_04`、`figure_06`、`table_03`、`table_09`。",
        f"- 已重绘正式样式图：`{', '.join(summary.get('restyled_figures', []))}`。",
        "- 已输出 5 个硬性缺口：见 `configs/data_gap_report/data_gap_report.md`。",
        "- 软科/US News 分项指标多年历史仍是 partial constraint，未计入 5 个硬性缺口，但后续生成趋势图前需要补数据或降级口径。",
        "",
    ]
    text = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else "# word_tool\n"
    if section_title in text:
        text = text.split(section_title)[0].rstrip() + "\n\n" + "\n".join(block)
    else:
        text = text.rstrip() + "\n\n" + "\n".join(block)
    README_PATH.write_text(text, encoding="utf-8", newline="\n")


BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "figure_02_ranking_indicator_commonality": build_commonality_artifact,
    "figure_03_arwu_indicator_weight": lambda: build_weight_artifact(
        "figure_03_arwu_indicator_weight",
        "软科",
        "数学",
        "软科世界一流学科数学指标权重",
        "按 2025 指标权重表归一化百分比绘制",
    ),
    "figure_04_qs_indicator_weight": lambda: build_weight_artifact(
        "figure_04_qs_indicator_weight",
        "QS",
        "数学",
        "QS 学科排名数学指标权重",
        "按 QS 数学学科指标权重绘制",
    ),
    "figure_06_the_indicator_weight": lambda: build_weight_artifact(
        "figure_06_the_indicator_weight",
        "THE",
        "自然科学",
        "THE 世界学科排名自然科学领域指标权重",
        "数学按 THE 理学 / Physical Sciences 领域口径处理",
    ),
    "table_03_the_tongji_indicator_history": build_the_indicator_history_table,
    "table_09_peer_full_ranking_history_appendix": build_appendix_history_table,
}


def build_single(artifact_id: str) -> dict[str, Any]:
    if artifact_id not in BUILDERS:
        raise KeyError(f"未知 artifact_id: {artifact_id}")
    spec = BUILDERS[artifact_id]()
    update_registry()
    return spec


def build_all_ready_artifacts() -> dict[str, Any]:
    built = []
    errors: list[dict[str, str]] = []
    for artifact_id, builder in BUILDERS.items():
        try:
            builder()
            built.append(artifact_id)
        except Exception as exc:
            errors.append({"artifact_id": artifact_id, "error": str(exc)})
    restyled = restyle_existing_figures()
    gap_summary = build_data_gap_report()
    registry_summary = update_registry()
    summary = {
        "generated_at": now_text(),
        "built_artifacts": built,
        "restyled_figures": restyled,
        "errors": errors,
        "data_gap_report": gap_summary,
        "registry": registry_summary,
    }
    (CONFIG_DIR / "ready_artifacts_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    update_readme(summary)
    if errors:
        raise RuntimeError(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    build_all_ready_artifacts()


if __name__ == "__main__":
    main()
