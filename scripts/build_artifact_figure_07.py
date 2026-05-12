from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "figure_07_all_rankings_history"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_SUBJECT_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"

ARTIFACT_ID = "figure_07_all_rankings_history"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026

CHART_WIDTH = 1600
CHART_HEIGHT = 920
PLOT_LEFT = 150
PLOT_RIGHT = 1320
PLOT_TOP = 120
PLOT_BOTTOM = 760

SERIES_COLORS = {
    "软科": "#C44E52",
    "QS": "#4C72B0",
    "US News": "#55A868",
    "THE": "#8172B2",
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def query_chart_data() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    dim_subject = pd.read_csv(DIM_SUBJECT_CSV, dtype=str).fillna("")
    target_rows = dim_subject[
        (dim_subject["ministry_subject_code"] == TARGET_SUBJECT_CODE)
        | (dim_subject["ministry_subject_name"] == TARGET_SUBJECT)
    ].copy()
    if target_rows.empty:
        raise RuntimeError(f"未找到目标学科：{TARGET_SUBJECT} / {TARGET_SUBJECT_CODE}")
    subject_id = target_rows.iloc[0]["subject_id"]

    query = """
    SELECT
      f.ranking_source,
      f.release_year,
      f.ranking_year,
      f.ranking_subject_raw,
      f.rank_raw,
      f.rank_midpoint,
      f.total_score,
      f.source_file,
      f.source_sheet,
      f.source_row,
      f.ranking_subject_norm,
      a.subject_id,
      a.ranking_subject_alias,
      a.alias_type
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
      AND f.is_tongji = 1
    ORDER BY f.ranking_source, f.release_year, f.ranking_year
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[subject_id])

    if df.empty:
        raise RuntimeError("未查询到图表数据。")

    df["release_year"] = pd.to_numeric(df["release_year"], errors="coerce").astype("Int64")
    df["ranking_year"] = pd.to_numeric(df["ranking_year"], errors="coerce").astype("Int64")
    df["rank_midpoint"] = pd.to_numeric(df["rank_midpoint"], errors="coerce")
    df = df.dropna(subset=["release_year", "rank_midpoint"]).copy()
    df["chart_year"] = df["release_year"].astype(int)
    df["target_university"] = TARGET_UNIVERSITY
    df["target_subject"] = TARGET_SUBJECT

    source_columns = [
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "rank_raw",
        "rank_midpoint",
        "source_file",
        "source_sheet",
        "source_row",
        "ranking_subject_alias",
        "alias_type",
    ]
    trace_df = df[source_columns].drop_duplicates().copy()

    point_columns = [
        "target_university",
        "target_subject",
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "rank_raw",
        "rank_midpoint",
        "total_score",
        "chart_year",
    ]

    def join_unique(values: pd.Series) -> str:
        cleaned = sorted({clean_text(value) for value in values if clean_text(value)})
        return "; ".join(cleaned)

    chart_df = (
        df.groupby(point_columns, dropna=False)
        .agg(
            ranking_subject_alias=("ranking_subject_alias", join_unique),
            alias_type=("alias_type", join_unique),
            source_ref_count=("source_row", "nunique"),
        )
        .reset_index()
        .sort_values(["ranking_source", "release_year", "ranking_year", "rank_midpoint"])
    )

    conflict_counts = chart_df.groupby(["ranking_source", "release_year"], dropna=False).size().reset_index(name="point_count")
    conflicts = conflict_counts[conflict_counts["point_count"] > 1]
    if not conflicts.empty:
        detail = conflicts.to_dict(orient="records")
        raise RuntimeError(f"同一榜单同一发布年度出现多个候选排名点，需要人工核验：{detail}")

    return chart_df, trace_df, len(df)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def render_chart(df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    font_title = load_font(34, bold=True)
    font_subtitle = load_font(21)
    font_axis = load_font(18)
    font_label = load_font(16)
    font_legend = load_font(18)
    font_note = load_font(16)

    title = "同济大学数学学科四大国际排名历史趋势"
    subtitle = "排名区间按中间位次绘制；数值越小表示排名越靠前"
    draw.text((PLOT_LEFT, 38), title, fill="#1F2933", font=font_title)
    draw.text((PLOT_LEFT, 82), subtitle, fill="#52606D", font=font_subtitle)

    years = sorted(int(year) for year in df["chart_year"].dropna().unique())
    min_year, max_year = min(years), max(years)
    y_values = df["rank_midpoint"].dropna().tolist()
    y_min = max(0, math.floor(min(y_values) / 50) * 50 - 50)
    y_max = math.ceil(max(y_values) / 50) * 50 + 50

    def x_pos(year: int) -> float:
        if max_year == min_year:
            return (PLOT_LEFT + PLOT_RIGHT) / 2
        return PLOT_LEFT + (year - min_year) / (max_year - min_year) * (PLOT_RIGHT - PLOT_LEFT)

    def y_pos(value: float) -> float:
        return PLOT_TOP + (value - y_min) / (y_max - y_min) * (PLOT_BOTTOM - PLOT_TOP)

    def overlaps(box: tuple[float, float, float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
        left, top, right, bottom = box
        for other_left, other_top, other_right, other_bottom in boxes:
            if left < other_right and right > other_left and top < other_bottom and bottom > other_top:
                return True
        return False

    # Grid and axes
    for tick in range(int(y_min), int(y_max) + 1, 50):
        y = y_pos(tick)
        draw.line((PLOT_LEFT, y, PLOT_RIGHT, y), fill="#E4E7EB", width=1)
        draw.text((PLOT_LEFT - 72, y - 10), str(tick), fill="#52606D", font=font_axis)
    draw.line((PLOT_LEFT, PLOT_TOP, PLOT_LEFT, PLOT_BOTTOM), fill="#9AA5B1", width=2)
    draw.line((PLOT_LEFT, PLOT_BOTTOM, PLOT_RIGHT, PLOT_BOTTOM), fill="#9AA5B1", width=2)

    for year in years:
        x = x_pos(year)
        draw.line((x, PLOT_BOTTOM, x, PLOT_BOTTOM + 8), fill="#9AA5B1", width=2)
        label = str(year)
        tw, _ = text_size(draw, label, font_axis)
        draw.text((x - tw / 2, PLOT_BOTTOM + 16), label, fill="#52606D", font=font_axis)

    # Axis labels
    draw.text((40, PLOT_TOP + 220), "排名中位数", fill="#52606D", font=font_axis)
    draw.text((PLOT_LEFT + 500, PLOT_BOTTOM + 54), "发布年度", fill="#52606D", font=font_axis)

    # Lines
    placed_label_boxes: list[tuple[float, float, float, float]] = []
    for source, group in df.groupby("ranking_source"):
        group = group.sort_values("chart_year")
        color = SERIES_COLORS.get(source, "#333333")
        points = [(x_pos(int(row["chart_year"])), y_pos(float(row["rank_midpoint"]))) for _, row in group.iterrows()]
        if len(points) >= 2:
            draw.line(points, fill=color, width=4)
        for (_, row), (x, y) in zip(group.iterrows(), points):
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color, outline="white", width=2)
            rank_label = clean_text(row["rank_raw"])
            tw, th = text_size(draw, rank_label, font_label)
            label_x = min(max(x + 9, PLOT_LEFT + 4), PLOT_RIGHT - tw - 4)
            label_y = min(max(y - 20, PLOT_TOP + 4), PLOT_BOTTOM - th - 4)
            for offset in [0, 20, -24, 42, -46, 64, -68]:
                candidate_y = min(max(label_y + offset, PLOT_TOP + 4), PLOT_BOTTOM - th - 4)
                candidate = (label_x - 3, candidate_y - 3, label_x + tw + 3, candidate_y + th + 3)
                if not overlaps(candidate, placed_label_boxes):
                    label_y = candidate_y
                    placed_label_boxes.append(candidate)
                    break
            draw.text((label_x, label_y), rank_label, fill=color, font=font_label)

    # Legend
    legend_x = PLOT_RIGHT + 45
    legend_y = PLOT_TOP + 10
    draw.text((legend_x, legend_y - 35), "榜单", fill="#1F2933", font=font_legend)
    for idx, source in enumerate(["软科", "QS", "US News", "THE"]):
        y = legend_y + idx * 42
        color = SERIES_COLORS[source]
        draw.line((legend_x, y + 10, legend_x + 34, y + 10), fill=color, width=5)
        draw.ellipse((legend_x + 13, y + 3, legend_x + 27, y + 17), fill=color, outline="white", width=2)
        draw.text((legend_x + 48, y), source, fill="#323F4B", font=font_legend)

    note = "注：THE为领域排名口径，数学对应理学/Physical Sciences领域；排名区间用于绘图时取中间位次。"
    draw.text((PLOT_LEFT, 830), note, fill="#52606D", font=font_note)
    image.save(output_path)


def build_narrative(df: pd.DataFrame) -> str:
    latest_rows = []
    for source, group in df.groupby("ranking_source"):
        latest = group.sort_values(["release_year", "ranking_year"]).tail(1).iloc[0]
        earliest = group.sort_values(["release_year", "ranking_year"]).head(1).iloc[0]
        delta = float(latest["rank_midpoint"]) - float(earliest["rank_midpoint"])
        direction = "提升" if delta < 0 else "下降" if delta > 0 else "保持稳定"
        latest_rows.append(
            {
                "source": source,
                "latest": latest,
                "earliest": earliest,
                "direction": direction,
                "delta": abs(delta),
            }
        )

    lines = [
        "# 图7分析草稿：同济大学数学学科四大国际排名历史趋势",
        "",
        f"本图基于 `fact_ranking` 中同济大学 `{TARGET_SUBJECT}` 学科相关记录生成，覆盖软科、QS、US News 和 THE 四类榜单。排名区间在绘图时取中间位次，正文和表格仍保留原始排名字符串。",
        "",
        "## 最新排名概览",
        "",
    ]
    for item in sorted(latest_rows, key=lambda x: x["source"]):
        latest = item["latest"]
        lines.append(
            f"- {item['source']}：{int(latest['release_year'])}发布，"
            f"{clean_text(latest['ranking_subject_raw'])}，排名 `{clean_text(latest['rank_raw'])}`。"
        )

    lines.extend(["", "## 趋势观察", ""])
    for item in sorted(latest_rows, key=lambda x: x["source"]):
        latest = item["latest"]
        earliest = item["earliest"]
        lines.append(
            f"- {item['source']}：从 {int(earliest['release_year'])} 年 `{clean_text(earliest['rank_raw'])}` "
            f"到 {int(latest['release_year'])} 年 `{clean_text(latest['rank_raw'])}`，按中间位次看整体{item['direction']}。"
        )

    lines.extend(
        [
            "",
            "## 口径说明",
            "",
            "- THE 为领域排名，数学对应 `理学/Physical Sciences` 领域，不是严格的一级学科排名。",
            "- 趋势图使用 `rank_midpoint`，用于处理 `201-250` 这类区间排名。",
            "- 原始排名、来源文件、sheet 和行号见 `source_trace.csv`。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    df, trace_df, raw_match_rows = query_chart_data()

    chart_columns = [
        "target_university",
        "target_subject",
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "rank_raw",
        "rank_midpoint",
        "total_score",
        "ranking_subject_alias",
        "alias_type",
        "source_ref_count",
    ]
    chart_data = df[chart_columns].sort_values(["ranking_source", "release_year", "ranking_year"])
    chart_data.to_csv(OUTPUT_DIR / "chart_data.csv", index=False, encoding="utf-8-sig")

    trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")

    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": now_text(),
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "chart_type": "multi-series line chart",
        "data_source": "processed/ranking.sqlite: fact_ranking join dim_subject_alias",
        "x": "release_year",
        "y": "rank_midpoint",
        "series": "ranking_source",
        "rank_direction": "smaller is better",
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "chart_rows_after_alias_dedup": len(chart_data),
        "notes": [
            "Ranking ranges are plotted by midpoint.",
            "Raw rank strings are preserved in chart_data.csv.",
            "Multiple subject-alias matches are deduplicated into one chart point and retained in source_trace.csv.",
            "THE uses area-level ranking; Mathematics maps to Physical Sciences/理学.",
        ],
        "outputs": {
            "chart_data": str(OUTPUT_DIR / "chart_data.csv"),
            "chart_png": str(OUTPUT_DIR / "chart.png"),
            "narrative": str(OUTPUT_DIR / "narrative.md"),
            "source_trace": str(OUTPUT_DIR / "source_trace.csv"),
        },
    }
    (OUTPUT_DIR / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (OUTPUT_DIR / "narrative.md").write_text(build_narrative(df), encoding="utf-8", newline="\n")
    render_chart(df, OUTPUT_DIR / "chart.png")

    run_log = [
        "# figure_07_all_rankings_history run log",
        "",
        f"- generated_at: {spec['generated_at']}",
        f"- target_university: {TARGET_UNIVERSITY}",
        f"- target_subject: {TARGET_SUBJECT}",
        f"- raw_match_rows_before_alias_dedup: {raw_match_rows}",
        f"- data_rows: {len(chart_data)}",
        f"- ranking_sources: {', '.join(sorted(chart_data['ranking_source'].unique()))}",
        "",
        "## outputs",
        "",
        "- chart_data.csv",
        "- chart_spec.json",
        "- chart.png",
        "- narrative.md",
        "- source_trace.csv",
    ]
    (OUTPUT_DIR / "run_log.md").write_text("\n".join(run_log) + "\n", encoding="utf-8", newline="\n")

    global_log = LOG_DIR / "artifact_generation_run_log.md"
    if not global_log.exists():
        global_log.write_text("# Artifact 生成过程留档\n", encoding="utf-8", newline="\n")
    with global_log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"\n## {spec['generated_at']} {ARTIFACT_ID}\n\n"
            f"- 输出目录：`{OUTPUT_DIR}`\n"
            f"- alias 去重前匹配行数：{raw_match_rows}\n"
            f"- 数据行数：{len(chart_data)}\n"
            f"- 榜单：{', '.join(sorted(chart_data['ranking_source'].unique()))}\n"
        )

    return {
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "rows": len(chart_data),
        "sources": sorted(chart_data["ranking_source"].unique()),
        "output_dir": str(OUTPUT_DIR),
    }


def main() -> None:
    summary = build_outputs()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
