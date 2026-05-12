from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "figure_01_tongji_subject_ranking_overview"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"

ARTIFACT_ID = "figure_01_tongji_subject_ranking_overview"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026

CHART_WIDTH = 1600
CHART_HEIGHT = 900

SOURCE_ORDER = ["软科", "QS", "US News", "THE"]
SOURCE_COLORS = {
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
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


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


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def join_unique(values: pd.Series) -> str:
    cleaned = sorted({clean_text(value) for value in values if clean_text(value)})
    return "; ".join(cleaned)


def resolve_subject_id() -> str:
    dim_subject = pd.read_csv(DIM_SUBJECT_CSV, dtype=str).fillna("")
    target_rows = dim_subject[
        (dim_subject["ministry_subject_code"] == TARGET_SUBJECT_CODE)
        | (dim_subject["ministry_subject_name"] == TARGET_SUBJECT)
    ].copy()
    if target_rows.empty:
        raise RuntimeError(f"未找到目标学科：{TARGET_SUBJECT} / {TARGET_SUBJECT_CODE}")
    return clean_text(target_rows.iloc[0]["subject_id"])


def query_latest_data() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    subject_id = resolve_subject_id()
    query = """
    SELECT
      f.fact_id,
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
    df["target_university"] = TARGET_UNIVERSITY
    df["target_subject"] = TARGET_SUBJECT

    trace_columns = [
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
    trace_df = df[trace_columns].drop_duplicates().copy()

    point_columns = [
        "target_university",
        "target_subject",
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
    point_df = (
        df.groupby(point_columns, dropna=False)
        .agg(
            ranking_subject_alias=("ranking_subject_alias", join_unique),
            alias_type=("alias_type", join_unique),
            source_ref_count=("source_row", "nunique"),
        )
        .reset_index()
    )

    latest_rows = []
    conflicts = []
    for source, group in point_df.groupby("ranking_source"):
        latest_release_year = group["release_year"].max()
        latest_group = group[group["release_year"] == latest_release_year].copy()
        latest_ranking_year = latest_group["ranking_year"].max()
        latest_group = latest_group[latest_group["ranking_year"] == latest_ranking_year].copy()
        if len(latest_group) > 1:
            conflicts.append(
                {
                    "ranking_source": source,
                    "release_year": int(latest_release_year),
                    "ranking_year": int(latest_ranking_year),
                    "candidate_rows": latest_group[["ranking_subject_raw", "rank_raw", "rank_midpoint"]].to_dict(orient="records"),
                }
            )
            continue
        latest_rows.append(latest_group.iloc[0].to_dict())

    if conflicts:
        raise RuntimeError(f"最新排名存在多个候选点，需要人工核验：{conflicts}")

    latest_df = pd.DataFrame(latest_rows)
    latest_df["source_order"] = latest_df["ranking_source"].map({source: idx for idx, source in enumerate(SOURCE_ORDER)})
    latest_df = latest_df.sort_values(["source_order", "ranking_source"]).drop(columns=["source_order"]).reset_index(drop=True)
    return latest_df, trace_df, len(df)


def render_chart(df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    font_title = load_font(38, bold=True)
    font_subtitle = load_font(22)
    font_card_title = load_font(28, bold=True)
    font_rank = load_font(44, bold=True)
    font_label = load_font(18)
    font_body = load_font(19)
    font_note = load_font(17)

    title = f"{TARGET_UNIVERSITY}{TARGET_SUBJECT}学科国际排名概览"
    subtitle = "基于四大国际学科排名最新可用年度数据；卡片保留各榜单原始排名口径"
    draw.text((90, 48), title, fill="#1F2933", font=font_title)
    draw.text((90, 100), subtitle, fill="#52606D", font=font_subtitle)

    card_w = 680
    card_h = 250
    start_x = 90
    start_y = 170
    gap_x = 60
    gap_y = 46

    for idx, row in df.iterrows():
        col = idx % 2
        line = idx // 2
        x = start_x + col * (card_w + gap_x)
        y = start_y + line * (card_h + gap_y)
        source = clean_text(row["ranking_source"])
        color = SOURCE_COLORS.get(source, "#333333")

        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=6, fill="#FFFFFF", outline="#CBD2D9", width=2)
        draw.rectangle((x, y, x + 12, y + card_h), fill=color)
        draw.text((x + 34, y + 26), source, fill=color, font=font_card_title)

        year_text = f"{int(row['release_year'])}发布 / {int(row['ranking_year'])}排名"
        draw.text((x + 34, y + 66), year_text, fill="#52606D", font=font_label)

        rank_text = clean_text(row["rank_raw"])
        draw.text((x + 34, y + 100), rank_text, fill="#1F2933", font=font_rank)
        midpoint_text = f"排名中位数：{float(row['rank_midpoint']):.1f}"
        draw.text((x + 34, y + 160), midpoint_text, fill="#52606D", font=font_body)

        score_text = clean_text(row["total_score"])
        if score_text:
            draw.text((x + 300, y + 160), f"总分：{score_text}", fill="#52606D", font=font_body)

        subject_text = f"榜单学科口径：{clean_text(row['ranking_subject_raw'])}"
        for line_idx, line_text in enumerate(wrap_text(draw, subject_text, font_body, 560)[:2]):
            draw.text((x + 34, y + 196 + line_idx * 25), line_text, fill="#323F4B", font=font_body)

    note = "注：THE 为领域排名口径，数学对应理学/Physical Sciences 领域；不同榜单排名不宜直接等距比较。"
    draw.text((90, 800), note, fill="#52606D", font=font_note)
    image.save(output_path)


def build_narrative(df: pd.DataFrame) -> str:
    lines = [
        "# 图1分析草稿：同济大学数学学科国际排名概览",
        "",
        f"本图基于 `fact_ranking` 中 `{TARGET_UNIVERSITY}` `{TARGET_SUBJECT}` 学科的最新可用记录生成，覆盖软科、QS、US News 和 THE 四类榜单。",
        "",
        "## 最新排名",
        "",
    ]
    for _, row in df.iterrows():
        score_text = clean_text(row["total_score"])
        score_part = f"，总分 `{score_text}`" if score_text else ""
        lines.append(
            f"- {clean_text(row['ranking_source'])}：{int(row['release_year'])}发布，"
            f"{clean_text(row['ranking_subject_raw'])}，排名 `{clean_text(row['rank_raw'])}`"
            f"{score_part}。"
        )

    latest_years = ", ".join(
        f"{clean_text(row['ranking_source'])} {int(row['release_year'])}"
        for _, row in df.iterrows()
    )
    lines.extend(
        [
            "",
            "## 概览判断",
            "",
            "- 四类榜单均可检索到同济大学数学学科的最新记录，可支撑报告开头的国际排名概览。",
            f"- 各榜单最新年度分别为：{latest_years}。",
            "- THE 使用领域排名，不能和严格一级学科排名完全等同，需要在正文或图注中说明。",
            "",
            "## 口径说明",
            "",
            "- `chart_data.csv` 保留原始排名字符串和排名区间中位数。",
            "- `source_trace.csv` 保留来源文件、sheet、行号和 alias 命中痕迹。",
            "- 本图用于报告开头概览，不用于判断四个榜单之间的绝对优劣。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    df, trace_df, raw_match_rows = query_latest_data()

    chart_columns = [
        "target_university",
        "target_subject",
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "rank_raw",
        "rank_min",
        "rank_max",
        "rank_midpoint",
        "total_score",
        "ranking_subject_alias",
        "alias_type",
        "source_ref_count",
    ]
    chart_data = df[chart_columns].copy()
    chart_data.to_csv(OUTPUT_DIR / "chart_data.csv", index=False, encoding="utf-8-sig")
    trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")

    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": now_text(),
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "chart_type": "ranking overview cards",
        "data_source": "processed/ranking.sqlite: fact_ranking join dim_subject_alias",
        "selection_rule": "latest release_year per ranking_source, then latest ranking_year",
        "rank_direction": "smaller is better",
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "chart_rows_after_latest_selection": len(chart_data),
        "notes": [
            "Ranking ranges are preserved as raw strings and also represented by midpoint.",
            "Multiple subject-alias matches are deduplicated into one latest ranking point.",
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
        "# figure_01_tongji_subject_ranking_overview run log",
        "",
        f"- generated_at: {spec['generated_at']}",
        f"- target_university: {TARGET_UNIVERSITY}",
        f"- target_subject: {TARGET_SUBJECT}",
        f"- raw_match_rows_before_alias_dedup: {raw_match_rows}",
        f"- data_rows: {len(chart_data)}",
        f"- ranking_sources: {', '.join(chart_data['ranking_source'].tolist())}",
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
            f"- 榜单：{', '.join(chart_data['ranking_source'].tolist())}\n"
        )

    return {
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "rows": len(chart_data),
        "sources": chart_data["ranking_source"].tolist(),
        "output_dir": str(OUTPUT_DIR),
    }


def main() -> None:
    summary = build_outputs()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
