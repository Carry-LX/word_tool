from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "figure_12_the_peer_indicator_relative_rank"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
PEER_RECORDS_PATH = PROJECT_DIR / "outputs" / "artifacts" / "table_08_the_mainland_peer_ranking" / "latest_peer_records.csv"

ARTIFACT_ID = "figure_12_the_peer_indicator_relative_rank"
RANKING_SOURCE = "THE"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
THE_AREA = "理学"
THE_WEIGHT_AREA = "自然科学"
RELEASE_YEAR = 2026
RANKING_YEAR = 2026

RANK_INDICATORS = [
    "教学排名",
    "科研环境排名",
    "科研质量排名",
    "商业收入排名",
    "国际化视野排名",
]

SCORE_INDICATORS = {
    "教学排名": "教学",
    "科研环境排名": "科研环境",
    "科研质量排名": "科研质量",
    "商业收入排名": "商业收入",
    "国际化视野排名": "国际化视野",
}

WEIGHT_INDICATOR_MAP = {
    "教学排名": "教学",
    "科研环境排名": "研究环境",
    "科研质量排名": "研究质量",
    "商业收入排名": "产业",
    "国际化视野排名": "国际展望",
}

INDICATOR_SHORT_NAMES = {
    "教学排名": "教学",
    "科研环境排名": "科研环境",
    "科研质量排名": "科研质量",
    "商业收入排名": "商业收入",
    "国际化视野排名": "国际化视野",
}

CHART_WIDTH = 1800
CHART_HEIGHT = 1080


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def normalize_text_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
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


def draw_text_right(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str = "#1F2933",
) -> None:
    tw, _ = text_size(draw, text, font)
    draw.text((x - tw, y), text, font=font, fill=fill)


def query_source_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(SQLITE_PATH)
    indicator_sql = """
    SELECT
      ranking_indicator_id,
      ranking_source,
      release_year,
      ranking_year,
      ranking_subject_raw,
      ranking_subject_norm,
      university_name_cn,
      university_name_en,
      country_or_region,
      is_mainland_china,
      is_tongji,
      world_rank_raw,
      world_rank_midpoint,
      indicator_name,
      indicator_norm,
      indicator_group,
      metric_type,
      metric_raw,
      metric_value,
      source_file,
      source_sheet,
      source_row
    FROM fact_ranking_indicator
    WHERE ranking_source = ?
      AND release_year = ?
      AND ranking_year = ?
      AND ranking_subject_raw = ?
      AND metric_value IS NOT NULL
    """
    indicator_df = pd.read_sql_query(
        indicator_sql,
        con,
        params=[RANKING_SOURCE, RELEASE_YEAR, RANKING_YEAR, THE_AREA],
    )

    weight_sql = """
    SELECT
      weight_id,
      ranking_source,
      ranking_subject_or_area,
      ranking_subject_norm,
      indicator_name,
      indicator_norm,
      indicator_group,
      indicator_level,
      raw_group,
      raw_indicator_name,
      weight_raw,
      weight_percent,
      source_file,
      source_sheet,
      source_row,
      notes
    FROM fact_indicator_weight
    WHERE ranking_source = ?
      AND ranking_subject_or_area = ?
    """
    weight_df = pd.read_sql_query(weight_sql, con, params=[RANKING_SOURCE, THE_WEIGHT_AREA])
    con.close()

    if not PEER_RECORDS_PATH.exists():
        raise RuntimeError(f"缺少已验证的 THE peer 样本文件：{PEER_RECORDS_PATH}")
    peer_df = pd.read_csv(PEER_RECORDS_PATH)
    if indicator_df.empty:
        raise RuntimeError("未查询到 THE 目标领域分项指标事实。")
    if weight_df.empty:
        raise RuntimeError("未查询到 THE 自然科学权重事实。")
    if peer_df.empty:
        raise RuntimeError("THE 已验证 peer 样本为空。")
    return indicator_df, weight_df, peer_df


def build_weight_summary(weight_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rank_indicator, weight_indicator in WEIGHT_INDICATOR_MAP.items():
        matched = weight_df[
            (weight_df["indicator_name"] == weight_indicator)
            & (weight_df["indicator_level"] == "一级指标")
        ].copy()
        if matched.empty:
            matched = weight_df[weight_df["indicator_name"] == weight_indicator].copy()
        rows.append(
            {
                "rank_indicator_name": rank_indicator,
                "score_indicator_name": SCORE_INDICATORS[rank_indicator],
                "weight_indicator_name": weight_indicator,
                "matched_weight_count": int(len(matched)),
                "weight_percent": float(matched["weight_percent"].iloc[0]) if not matched.empty else None,
                "source_rows": "；".join(str(int(v)) for v in matched["source_row"].dropna().unique()),
                "coverage_note": "THE自然科学一级指标权重匹配" if not matched.empty else "未匹配到权重",
            }
        )
    return pd.DataFrame(rows)


def build_chart_data(
    indicator_df: pd.DataFrame,
    weight_summary_df: pd.DataFrame,
    peer_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rank_df = indicator_df[indicator_df["indicator_name"].isin(RANK_INDICATORS)].copy()
    score_df = indicator_df[indicator_df["indicator_name"].isin(set(SCORE_INDICATORS.values()))].copy()
    rank_df["university_key"] = rank_df["university_name_en"].apply(normalize_text_key)
    rank_df.loc[rank_df["university_key"] == "", "university_key"] = rank_df.loc[rank_df["university_key"] == "", "university_name_cn"].apply(normalize_text_key)
    score_df["university_key"] = score_df["university_name_en"].apply(normalize_text_key)
    score_df.loc[score_df["university_key"] == "", "university_key"] = score_df.loc[score_df["university_key"] == "", "university_name_cn"].apply(normalize_text_key)

    peer_df = peer_df.copy()
    peer_keys = set(peer_df["university_key"].tolist())
    target_key = clean_text(peer_df.loc[peer_df["is_tongji"] == 1, "university_key"].iloc[0])
    peer_rank_df = rank_df[rank_df["university_key"].isin(peer_keys)].copy()
    peer_rank_df["scope_role"] = "peer_top200"

    if len(peer_df) == 0:
        raise RuntimeError("THE 前200内地高校样本为空。")
    if target_key not in set(peer_rank_df["university_key"].tolist()):
        raise RuntimeError("同济大学未在 THE peer 指标样本中匹配到。")

    score_lookup = score_df[["university_key", "indicator_name", "metric_value", "metric_raw"]].copy()
    score_lookup = score_lookup.rename(
        columns={
            "indicator_name": "score_indicator_name",
            "metric_value": "indicator_score",
            "metric_raw": "indicator_score_raw",
        }
    )
    peer_rank_df["score_indicator_name"] = peer_rank_df["indicator_name"].map(SCORE_INDICATORS)
    peer_rank_df = peer_rank_df.merge(score_lookup, on=["university_key", "score_indicator_name"], how="left")
    peer_meta = peer_df[["university_key", "rank_raw", "rank_midpoint", "total_score", "latest_order"]].rename(
        columns={
            "rank_raw": "world_rank_raw_from_peer_scope",
            "rank_midpoint": "world_rank_midpoint_from_peer_scope",
            "total_score": "total_score_from_peer_scope",
        }
    )
    peer_rank_df = peer_rank_df.merge(peer_meta, on="university_key", how="left")

    weight_map = {
        row["rank_indicator_name"]: row["weight_percent"]
        for _, row in weight_summary_df.iterrows()
    }

    chart_rows = []
    long_frames = []
    for indicator_name in RANK_INDICATORS:
        one = peer_rank_df[peer_rank_df["indicator_name"] == indicator_name].copy()
        if one.empty:
            continue
        one["relative_rank_in_peer_scope"] = one["metric_value"].rank(method="min", ascending=True)
        one["peer_scope_size"] = len(one)
        long_frames.append(one)

        target_row = one[one["university_key"] == target_key].iloc[0]
        peer_values = one["metric_value"].dropna()
        chart_rows.append(
            {
                "indicator_name": indicator_name,
                "indicator_short_name": INDICATOR_SHORT_NAMES[indicator_name],
                "indicator_group": clean_text(target_row["indicator_group"]),
                "weight_percent": weight_map.get(indicator_name),
                "peer_scope_size": int(len(one)),
                "peer_best_indicator_rank": float(peer_values.min()),
                "peer_median_indicator_rank": float(peer_values.median()),
                "peer_worst_indicator_rank": float(peer_values.max()),
                "tongji_indicator_rank": float(target_row["metric_value"]),
                "tongji_indicator_score": float(target_row["indicator_score"]) if pd.notna(target_row["indicator_score"]) else None,
                "tongji_relative_rank_in_peer_scope": int(target_row["relative_rank_in_peer_scope"]),
                "tongji_percentile_from_top": round((1 - (float(target_row["relative_rank_in_peer_scope"]) - 1) / max(len(one) - 1, 1)) * 100, 1),
                "tongji_in_peer_scope": True,
            }
        )

    long_df = pd.concat(long_frames, ignore_index=True)
    chart_df = pd.DataFrame(chart_rows)
    tongji_df = long_df[long_df["university_key"] == target_key].copy()
    return long_df, chart_df, tongji_df


def render_chart(chart_df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    title_font = load_font(40, bold=True)
    subtitle_font = load_font(24)
    label_font = load_font(24)
    small_font = load_font(20)
    axis_font = load_font(18)
    bold_small_font = load_font(22, bold=True)

    margin_left = 420
    margin_right = 220
    axis_left = margin_left
    axis_right = CHART_WIDTH - margin_right
    title_y = 52
    plot_top = 250
    row_gap = 130
    max_rank = int(chart_df["peer_scope_size"].max())

    draw.text((70, title_y), "THE理学前200内地高校分项指标相对位置", font=title_font, fill="#1F2933")
    draw.text(
        (70, title_y + 56),
        "数学按 THE 理学/Physical Sciences 领域处理；同济已在前200 peer 样本内",
        font=subtitle_font,
        fill="#52616F",
    )
    draw.text((axis_left, plot_top - 82), "peer内相对排名（越靠左越好）", font=axis_font, fill="#52616F")

    def x_for_rank(rank: float) -> int:
        return int(axis_left + (rank - 1) / (max_rank - 1) * (axis_right - axis_left))

    for tick in [1, 5, 10, 15, max_rank]:
        x = x_for_rank(tick)
        draw.line((x, plot_top - 35, x, plot_top + row_gap * (len(chart_df) - 1) + 58), fill="#E4E9F0", width=2)
        draw_text_right(draw, x + 10, plot_top - 60, str(tick), axis_font, "#52616F")

    group_colors = {
        "教学/环境": "#5B8DEF",
        "科研/论文": "#5AA469",
        "产业/转化": "#C17C2E",
        "国际化/合作": "#B26EEC",
    }
    for idx, row in chart_df.iterrows():
        y = plot_top + idx * row_gap
        group = clean_text(row["indicator_group"])
        color = group_colors.get(group, "#7B8794")
        weight_text = f"权重约 {float(row['weight_percent']):.1f}%" if pd.notna(row["weight_percent"]) else "权重缺失"
        draw_text_right(draw, margin_left - 36, y - 24, str(row["indicator_short_name"]), label_font, "#1F2933")
        draw_text_right(draw, margin_left - 36, y + 8, weight_text, small_font, color)

        draw.line((axis_left, y, axis_right, y), fill="#D7DEE8", width=6)
        for rank in range(1, max_rank + 1):
            x = x_for_rank(rank)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#C9D3DF")

        tongji_rank = float(row["tongji_relative_rank_in_peer_scope"])
        tongji_x = x_for_rank(tongji_rank)
        draw.ellipse((tongji_x - 15, y - 15, tongji_x + 15, y + 15), fill="#C0392B")
        draw.ellipse((tongji_x - 7, y - 7, tongji_x + 7, y + 7), fill="#FFFFFF")
        if tongji_x > axis_right - 230:
            draw_text_right(draw, tongji_x - 22, y - 28, f"同济 {int(tongji_rank)}/{max_rank}", bold_small_font, "#C0392B")
            draw_text_right(draw, tongji_x - 22, y + 4, f"指标排名 {int(row['tongji_indicator_rank'])}", axis_font, "#7B2D26")
        else:
            draw.text((tongji_x + 22, y - 28), f"同济 {int(tongji_rank)}/{max_rank}", font=bold_small_font, fill="#C0392B")
            draw.text((tongji_x + 22, y + 4), f"指标排名 {int(row['tongji_indicator_rank'])}", font=axis_font, fill="#7B2D26")
        draw.text((axis_right + 28, y - 20), f"peer中位 {row['peer_median_indicator_rank']:.0f}", font=axis_font, fill="#52616F")

    legend_y = CHART_HEIGHT - 145
    draw.ellipse((70, legend_y - 12, 94, legend_y + 12), fill="#C0392B")
    draw.text((112, legend_y - 18), "同济大学", font=small_font, fill="#1F2933")
    draw.ellipse((300, legend_y - 7, 314, legend_y + 7), fill="#C9D3DF")
    draw.text((332, legend_y - 18), "peer 样本相对排名刻度", font=small_font, fill="#1F2933")
    draw.text(
        (70, legend_y + 38),
        "注：THE理学前200内地高校为18所；分项指标使用THE排名字段，数值越小越好；权重使用THE自然科学一级指标。",
        font=small_font,
        fill="#52616F",
    )
    image.save(output_path)


def build_source_trace(long_df: pd.DataFrame, weight_summary_df: pd.DataFrame, weight_df: pd.DataFrame) -> pd.DataFrame:
    indicator_cols = [
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "university_name_cn",
        "university_name_en",
        "world_rank_raw",
        "world_rank_midpoint",
        "indicator_name",
        "metric_raw",
        "metric_value",
        "indicator_score_raw",
        "indicator_score",
        "scope_role",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    trace_indicator = long_df[indicator_cols].copy()
    trace_indicator.insert(0, "trace_type", "ranking_indicator")

    used_weight_names = set(weight_summary_df["weight_indicator_name"].tolist())
    trace_weight = weight_df[weight_df["indicator_name"].isin(used_weight_names)].copy()
    trace_weight.insert(0, "trace_type", "indicator_weight")
    return pd.concat([trace_indicator, trace_weight], ignore_index=True, sort=False)


def write_markdown_table(chart_df: pd.DataFrame, path: Path) -> None:
    rows = [
        "| 指标 | 权重 | peer样本数 | 同济指标排名 | 同济peer内相对名次 | 同济得分 | peer最佳 | peer中位 | peer最弱 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in chart_df.iterrows():
        rows.append(
            "| {indicator} | {weight:.1f}% | {peer} | {tongji_metric:.0f} | {relative}/{scope} | {score:.1f} | {best:.0f} | {median:.0f} | {worst:.0f} |".format(
                indicator=row["indicator_short_name"],
                weight=float(row["weight_percent"]),
                peer=int(row["peer_scope_size"]),
                tongji_metric=float(row["tongji_indicator_rank"]),
                relative=int(row["tongji_relative_rank_in_peer_scope"]),
                scope=int(row["peer_scope_size"]),
                score=float(row["tongji_indicator_score"]),
                best=float(row["peer_best_indicator_rank"]),
                median=float(row["peer_median_indicator_rank"]),
                worst=float(row["peer_worst_indicator_rank"]),
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_narrative(chart_df: pd.DataFrame, path: Path) -> None:
    best = chart_df.sort_values("tongji_relative_rank_in_peer_scope").iloc[0]
    weakest = chart_df.sort_values("tongji_relative_rank_in_peer_scope", ascending=False).iloc[0]
    text = f"""# 图9分析草稿：THE排名前200位内地高校分项指标相对排名

本图以 THE {RANKING_YEAR} 排名年度 `{THE_AREA}` 领域进入世界前200的中国内地高校为 peer 样本，共 `{int(chart_df['peer_scope_size'].max())}` 所。`{TARGET_SUBJECT}` 在 THE 中按 `理学/Physical Sciences` 领域口径处理。

THE 分项指标同时提供得分和排名。本图使用分项排名字段计算 peer 内相对位置，排名数值越小代表表现越靠前；权重采用 THE 权重表中的 `自然科学` 一级指标。由于同济大学已进入 THE 理学前200样本，本图直接展示其在 18 所 peer 高校中的相对位置。

同济大学在 peer 内相对位置最好的是 `{best['indicator_short_name']}`，在 18 所高校中位列第 `{int(best['tongji_relative_rank_in_peer_scope'])}`；相对靠后的指标是 `{weakest['indicator_short_name']}`，位列第 `{int(weakest['tongji_relative_rank_in_peer_scope'])}`。

## 口径说明

- `chart_data.csv` 是绘图摘要，一行一个 THE 分项指标。
- `peer_indicator_long.csv` 保留 18 所 peer 高校的逐校逐指标排名和得分。
- `indicator_weight_summary.csv` 保留 THE 自然科学一级指标权重映射。
- `tongji_indicator_check.csv` 单独保留同济大学分项指标记录。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = now_text()

    indicator_df, weight_df, peer_df = query_source_data()
    weight_summary_df = build_weight_summary(weight_df)
    long_df, chart_df, tongji_df = build_chart_data(indicator_df, weight_summary_df, peer_df)
    source_trace_df = build_source_trace(long_df, weight_summary_df, weight_df)

    chart_df.to_csv(OUTPUT_DIR / "chart_data.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(OUTPUT_DIR / "peer_indicator_long.csv", index=False, encoding="utf-8-sig")
    tongji_df.to_csv(OUTPUT_DIR / "tongji_indicator_check.csv", index=False, encoding="utf-8-sig")
    weight_summary_df.to_csv(OUTPUT_DIR / "indicator_weight_summary.csv", index=False, encoding="utf-8-sig")
    source_trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_chart(chart_df, OUTPUT_DIR / "chart.png")
    write_markdown_table(chart_df, OUTPUT_DIR / "chart_table.md")
    write_narrative(chart_df, OUTPUT_DIR / "narrative.md")

    validation = {
        "release_year": RELEASE_YEAR,
        "ranking_year": RANKING_YEAR,
        "peer_scope_size": int(chart_df["peer_scope_size"].max()),
        "indicator_count": int(len(chart_df)),
        "peer_indicator_rows": int(len(long_df)),
        "tongji_indicator_rows": int(len(tongji_df)),
        "tongji_in_peer_scope": bool(chart_df["tongji_in_peer_scope"].all()),
        "weight_area": THE_WEIGHT_AREA,
        "weight_all_matched": bool((weight_summary_df["matched_weight_count"] > 0).all()),
        "metric_rule": "THE rank metrics: lower is better; score retained for interpretation.",
    }
    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": generated_at,
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "ranking_source": RANKING_SOURCE,
        "the_area": THE_AREA,
        "weight_area": THE_WEIGHT_AREA,
        "chart_type": "indicator relative rank dot plot",
        "data_source": "processed/ranking.sqlite: fact_ranking_indicator + fact_indicator_weight; peer scope from table_08 latest_peer_records.csv",
        "selection_rule": "THE mainland universities in 理学/Physical Sciences with rank_midpoint <= 200 from verified table_08 peer records.",
        "relative_rank_rule": "THE indicator rank fields are used; lower metric_value is better; rank(method='min', ascending=True) within peer_top200.",
        "validation": validation,
        "outputs": {
            "chart_data": str(OUTPUT_DIR / "chart_data.csv"),
            "peer_indicator_long": str(OUTPUT_DIR / "peer_indicator_long.csv"),
            "tongji_indicator_check": str(OUTPUT_DIR / "tongji_indicator_check.csv"),
            "indicator_weight_summary": str(OUTPUT_DIR / "indicator_weight_summary.csv"),
            "chart_table": str(OUTPUT_DIR / "chart_table.md"),
            "chart_png": str(OUTPUT_DIR / "chart.png"),
            "narrative": str(OUTPUT_DIR / "narrative.md"),
            "source_trace": str(OUTPUT_DIR / "source_trace.csv"),
        },
        "notes": [
            "THE is area-level ranking; Mathematics maps to Physical Sciences/理学.",
            "Tongji is inside THE 2026 Physical Sciences top-200 mainland peer scope.",
            "THE natural sciences first-level weights are mapped to the five available component rank fields.",
        ],
    }
    (OUTPUT_DIR / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    run_log = f"""# {ARTIFACT_ID} run log

- generated_at: {generated_at}
- script: `scripts/build_artifact_figure_12.py`
- input_sqlite: `{SQLITE_PATH}`
- peer_records: `{PEER_RECORDS_PATH}`
- target_subject: `{TARGET_SUBJECT}`
- the_area: `{THE_AREA}`
- weight_area: `{THE_WEIGHT_AREA}`
- peer_scope_size: {validation['peer_scope_size']}
- indicator_count: {validation['indicator_count']}
- peer_indicator_rows: {validation['peer_indicator_rows']}
- tongji_indicator_rows: {validation['tongji_indicator_rows']}
- tongji_in_peer_scope: {validation['tongji_in_peer_scope']}
- weight_all_matched: {validation['weight_all_matched']}
- output_dir: `{OUTPUT_DIR}`
"""
    (OUTPUT_DIR / "run_log.md").write_text(run_log, encoding="utf-8")
    with (LOG_DIR / "artifact_generation_run_log.md").open("a", encoding="utf-8") as f:
        f.write("\n\n" + run_log)

    print(json.dumps(validation | {"output_dir": str(OUTPUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
