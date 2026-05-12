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
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "figure_09_arwu_peer_indicator_relative_rank"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"

ARTIFACT_ID = "figure_09_arwu_peer_indicator_relative_rank"
RANKING_SOURCE = "软科"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
RELEASE_YEAR = 2025
RANKING_YEAR = 2025
TOP_RANK_MIDPOINT = 200

COMPONENT_INDICATORS = [
    "高水平研究成果/重要期刊论文数",
    "科研影响力/论文标准化影响力",
    "国际合作/国际合作论文比例",
    "世界一流成果",
    "世界一流教师",
]

AGGREGATE_WEIGHT_RULES = {
    "高水平研究成果/重要期刊论文数": ["重要期刊论文", "顶尖期刊论文"],
    "科研影响力/论文标准化影响力": ["论文标准化影响力"],
    "国际合作/国际合作论文比例": ["国际合作论文比例"],
    "世界一流成果": ["国际学术组织负责人", "国际期刊主编", "国际权威奖项"],
    "世界一流教师": ["获权威奖项教师"],
}

CHART_WIDTH = 1800
CHART_HEIGHT = 1180


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
    text = re.sub(r"[\s\-\_·•.,，。()（）\[\]【】/\\&]+", "", text)
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


def query_indicator_rows() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
      AND metric_type = 'score'
      AND metric_value IS NOT NULL
    """
    indicator_df = pd.read_sql_query(
        indicator_sql,
        con,
        params=[RANKING_SOURCE, RELEASE_YEAR, RANKING_YEAR, TARGET_SUBJECT],
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
    weight_df = pd.read_sql_query(weight_sql, con, params=[RANKING_SOURCE, TARGET_SUBJECT])

    ranking_sql = """
    SELECT
      ranking_source,
      release_year,
      ranking_year,
      ranking_subject_raw,
      university_name_cn,
      university_name_en,
      country_or_region,
      is_mainland_china,
      is_tongji,
      rank_raw,
      rank_midpoint,
      total_score,
      source_file,
      source_sheet,
      source_row
    FROM fact_ranking
    WHERE ranking_source = ?
      AND release_year = ?
      AND ranking_year = ?
      AND ranking_subject_raw = ?
    """
    ranking_df = pd.read_sql_query(ranking_sql, con, params=[RANKING_SOURCE, RELEASE_YEAR, RANKING_YEAR, TARGET_SUBJECT])
    con.close()

    if indicator_df.empty:
        raise RuntimeError("未查询到软科目标学科分项指标事实，请先检查 fact_ranking_indicator。")
    if weight_df.empty:
        raise RuntimeError("未查询到软科目标学科指标权重，请先检查 fact_indicator_weight。")
    if ranking_df.empty:
        raise RuntimeError("未查询到软科目标学科总排名事实，请先检查 fact_ranking。")
    return indicator_df, weight_df, ranking_df


def build_weight_summary(weight_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for aggregate_name, detail_names in AGGREGATE_WEIGHT_RULES.items():
        detail_df = weight_df[weight_df["indicator_name"].isin(detail_names)].copy()
        rows.append(
            {
                "aggregate_indicator_name": aggregate_name,
                "detail_indicator_names": "；".join(detail_names),
                "matched_detail_count": int(len(detail_df)),
                "weight_percent_sum": float(detail_df["weight_percent"].fillna(0).sum()),
                "source_rows": "；".join(str(int(v)) for v in detail_df["source_row"].dropna().unique()),
            }
        )
    return pd.DataFrame(rows)


def build_chart_data(indicator_df: pd.DataFrame, ranking_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    component_df = indicator_df[indicator_df["indicator_name"].isin(COMPONENT_INDICATORS)].copy()
    component_df["university_key"] = component_df["university_name_cn"].apply(normalize_text_key)

    peer_keys = ranking_df[
        (ranking_df["is_mainland_china"] == 1)
        & (ranking_df["rank_midpoint"] <= TOP_RANK_MIDPOINT)
    ].copy()
    peer_keys["university_key"] = peer_keys["university_name_cn"].apply(normalize_text_key)
    peer_keys = peer_keys.sort_values(["rank_midpoint", "university_name_cn"]).drop_duplicates("university_key")
    peer_key_set = set(peer_keys["university_key"].tolist())

    target_key = normalize_text_key(TARGET_UNIVERSITY)
    peer_indicator_df = component_df[component_df["university_key"].isin(peer_key_set)].copy()
    target_indicator_df = component_df[component_df["university_key"] == target_key].copy()

    peer_indicator_df["scope_role"] = "peer_top200"
    target_indicator_df["scope_role"] = "target_reference_outside_peer_scope"
    combined_df = pd.concat([peer_indicator_df, target_indicator_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(["university_key", "indicator_name"], keep="first").reset_index(drop=True)

    if len(peer_keys) == 0:
        raise RuntimeError("软科前200内地高校样本为空，无法计算相对排名。")
    if target_indicator_df.empty:
        raise RuntimeError("同济大学分项指标记录为空，无法生成外部参照。")

    rank_frames = []
    chart_rows = []
    for indicator_name in COMPONENT_INDICATORS:
        peer_one = peer_indicator_df[peer_indicator_df["indicator_name"] == indicator_name].copy()
        target_one = target_indicator_df[target_indicator_df["indicator_name"] == indicator_name].copy()
        comparison_one = pd.concat([peer_one, target_one], ignore_index=True)
        comparison_one = comparison_one.drop_duplicates(["university_key", "indicator_name"], keep="first")
        comparison_one["relative_rank_peer_only"] = comparison_one["metric_value"].rank(
            method="min",
            ascending=False,
        )
        peer_rank_map = peer_one[["university_key", "metric_value"]].drop_duplicates("university_key")
        peer_rank_map["peer_only_rank"] = peer_rank_map["metric_value"].rank(method="min", ascending=False)
        comparison_one = comparison_one.merge(peer_rank_map[["university_key", "peer_only_rank"]], on="university_key", how="left")
        comparison_one["relative_rank_with_tongji"] = comparison_one["metric_value"].rank(method="min", ascending=False)
        comparison_one["comparison_scope_size"] = len(comparison_one)
        comparison_one["peer_scope_size"] = len(peer_one)
        rank_frames.append(comparison_one)

        target_row = target_one.iloc[0]
        target_rank = float(comparison_one[comparison_one["university_key"] == target_key]["relative_rank_with_tongji"].iloc[0])
        target_score = float(target_row["metric_value"])
        peer_scores = peer_one["metric_value"].dropna()
        chart_rows.append(
            {
                "indicator_name": indicator_name,
                "peer_scope_size": int(len(peer_one)),
                "comparison_scope_size": int(len(comparison_one)),
                "peer_best_score": float(peer_scores.max()),
                "peer_median_score": float(peer_scores.median()),
                "peer_worst_score": float(peer_scores.min()),
                "tongji_score": target_score,
                "tongji_relative_rank_with_peer_reference": int(target_rank),
                "tongji_percentile_from_top": round((1 - (target_rank - 1) / max(len(comparison_one) - 1, 1)) * 100, 1),
                "tongji_in_peer_scope": bool(target_key in peer_key_set),
            }
        )

    long_df = pd.concat(rank_frames, ignore_index=True)
    peer_order = peer_keys[["university_key", "rank_raw", "rank_midpoint", "total_score"]].rename(
        columns={
            "rank_raw": "world_rank_raw_from_fact_ranking",
            "rank_midpoint": "world_rank_midpoint_from_fact_ranking",
            "total_score": "total_score_from_fact_ranking",
        }
    )
    long_df = long_df.merge(peer_order, on="university_key", how="left")
    chart_df = pd.DataFrame(chart_rows)
    tongji_df = long_df[long_df["university_key"] == target_key].copy()
    return long_df, chart_df, tongji_df


def render_chart(chart_df: pd.DataFrame, weight_summary_df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    title_font = load_font(42, bold=True)
    subtitle_font = load_font(25)
    label_font = load_font(24)
    small_font = load_font(21)
    axis_font = load_font(19)
    bold_small_font = load_font(22, bold=True)

    margin_left = 480
    margin_right = 180
    axis_left = margin_left
    axis_right = CHART_WIDTH - margin_right
    title_y = 55
    plot_top = 285
    row_gap = 145
    max_rank = int(chart_df["comparison_scope_size"].max())

    draw.text((70, title_y), "软科数学前200内地高校分项指标相对位置", font=title_font, fill="#1F2933")
    draw.text(
        (70, title_y + 58),
        "前200内地高校作为 peer 样本；同济大学因软科数学排名 401-500，作为外部参照点加入比较",
        font=subtitle_font,
        fill="#52616F",
    )

    def x_for_rank(rank: float) -> int:
        if max_rank <= 1:
            return axis_left
        return int(axis_left + (rank - 1) / (max_rank - 1) * (axis_right - axis_left))

    for tick in [1, 5, 10, 15, 20, max_rank]:
        if tick > max_rank:
            continue
        x = x_for_rank(tick)
        draw.line((x, plot_top - 42, x, plot_top + row_gap * (len(chart_df) - 1) + 72), fill="#E4E9F0", width=2)
        draw_text_right(draw, x + 12, plot_top - 72, str(tick), axis_font, "#52616F")
    draw.text((axis_left, plot_top - 112), "相对排名（越靠左越好）", font=axis_font, fill="#52616F")

    weight_map = {
        row["aggregate_indicator_name"]: row["weight_percent_sum"]
        for _, row in weight_summary_df.iterrows()
    }

    for idx, row in chart_df.iterrows():
        y = plot_top + idx * row_gap
        indicator_name = str(row["indicator_name"])
        short_name = indicator_name.replace("/重要期刊论文数", "").replace("/论文标准化影响力", "").replace("/国际合作论文比例", "")
        weight = weight_map.get(indicator_name, 0.0)
        draw_text_right(draw, margin_left - 35, y - 20, short_name, label_font, "#1F2933")
        draw_text_right(draw, margin_left - 35, y + 18, f"权重约 {weight:.1f}%", small_font, "#7B8794")

        draw.line((axis_left, y, axis_right, y), fill="#D7DEE8", width=6)
        for rank in range(1, max_rank + 1):
            x = x_for_rank(rank)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#C9D3DF")

        tongji_rank = float(row["tongji_relative_rank_with_peer_reference"])
        tongji_x = x_for_rank(tongji_rank)
        draw.ellipse((tongji_x - 15, y - 15, tongji_x + 15, y + 15), fill="#C0392B")
        draw.ellipse((tongji_x - 7, y - 7, tongji_x + 7, y + 7), fill="#FFFFFF")
        if tongji_x > axis_right - 210:
            draw_text_right(draw, tongji_x - 22, y - 28, f"同济 {int(tongji_rank)}/{max_rank}", bold_small_font, "#C0392B")
            draw_text_right(draw, tongji_x - 22, y + 4, f"得分 {row['tongji_score']}", axis_font, "#7B2D26")
        else:
            draw.text((tongji_x + 22, y - 28), f"同济 {int(tongji_rank)}/{max_rank}", font=bold_small_font, fill="#C0392B")
            draw.text((tongji_x + 22, y + 4), f"得分 {row['tongji_score']}", font=axis_font, fill="#7B2D26")

        draw.text(
            (axis_right + 28, y - 26),
            f"peer中位 {row['peer_median_score']:.1f}",
            font=axis_font,
            fill="#52616F",
        )

    legend_y = CHART_HEIGHT - 155
    draw.ellipse((70, legend_y - 12, 94, legend_y + 12), fill="#C0392B")
    draw.text((110, legend_y - 18), "同济大学外部参照点", font=small_font, fill="#1F2933")
    draw.ellipse((380, legend_y - 7, 394, legend_y + 7), fill="#C9D3DF")
    draw.text((410, legend_y - 18), "peer 样本相对排名刻度", font=small_font, fill="#1F2933")
    draw.text(
        (70, legend_y + 38),
        "注：软科数学前200内地高校为21所；同济不在该样本内，因此相对名次按“21所peer+同济参照”计算。",
        font=small_font,
        fill="#52616F",
    )

    image.save(output_path)


def build_source_trace(long_df: pd.DataFrame, weight_df: pd.DataFrame) -> pd.DataFrame:
    indicator_cols = [
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "university_name_cn",
        "world_rank_raw",
        "world_rank_midpoint",
        "indicator_name",
        "metric_raw",
        "metric_value",
        "scope_role",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    trace_indicator = long_df[indicator_cols].copy()
    trace_indicator.insert(0, "trace_type", "ranking_indicator")

    weight_cols = [
        "ranking_source",
        "ranking_subject_or_area",
        "indicator_name",
        "indicator_group",
        "weight_percent",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    trace_weight = weight_df[weight_cols].copy()
    trace_weight.insert(0, "trace_type", "indicator_weight")
    return pd.concat([trace_indicator, trace_weight], ignore_index=True, sort=False)


def write_markdown_table(chart_df: pd.DataFrame, path: Path) -> None:
    rows = [
        "| 指标 | peer样本数 | 同济得分 | 同济相对名次 | peer最高 | peer中位 | peer最低 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in chart_df.iterrows():
        rows.append(
            "| {indicator_name} | {peer_scope_size} | {tongji_score:.1f} | {rank}/{scope} | {best:.1f} | {median:.1f} | {worst:.1f} |".format(
                indicator_name=row["indicator_name"],
                peer_scope_size=int(row["peer_scope_size"]),
                tongji_score=float(row["tongji_score"]),
                rank=int(row["tongji_relative_rank_with_peer_reference"]),
                scope=int(row["comparison_scope_size"]),
                best=float(row["peer_best_score"]),
                median=float(row["peer_median_score"]),
                worst=float(row["peer_worst_score"]),
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_narrative(chart_df: pd.DataFrame, path: Path) -> None:
    best = chart_df.sort_values("tongji_relative_rank_with_peer_reference").iloc[0]
    weakest = chart_df.sort_values("tongji_relative_rank_with_peer_reference", ascending=False).iloc[0]
    text = f"""# 图8分析草稿：软科排名前200位内地高校分项指标相对排名

本图以软科 {RELEASE_YEAR} 年 `{TARGET_SUBJECT}` 学科进入世界前200的中国内地高校为 peer 样本，共 `{int(chart_df['peer_scope_size'].max())}` 所。由于同济大学软科数学最新排名为 `401-500`，不属于前200 peer 样本，因此本图将同济作为外部参照点加入比较，计算其在 `peer样本+同济` 范围内的相对位置。

从分项指标看，同济大学相对位置最好的是 `{best['indicator_name']}`，在 `{int(best['comparison_scope_size'])}` 个比较对象中位列第 `{int(best['tongji_relative_rank_with_peer_reference'])}`；相对靠后的指标是 `{weakest['indicator_name']}`，位列第 `{int(weakest['tongji_relative_rank_with_peer_reference'])}`。该结果说明，同济当前在软科数学榜单中的主要短板并不只体现在总排名，还可以进一步拆解到分项指标得分差距。

## 口径说明

- `chart_data.csv` 是绘图摘要，一行一个分项指标。
- `peer_indicator_long.csv` 保留 21 所 peer 高校和同济参照点的逐校逐指标数据。
- `indicator_weight_summary.csv` 将权重表中的软科细项权重汇总到当前事实表可用的五个指标口径。
- `tongji_indicator_check.csv` 单独保留同济大学分项指标记录，便于报告中解释同济不在前200样本内的情况。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = now_text()

    indicator_df, weight_df, ranking_df = query_indicator_rows()
    weight_summary_df = build_weight_summary(weight_df)
    long_df, chart_df, tongji_df = build_chart_data(indicator_df, ranking_df)
    source_trace_df = build_source_trace(long_df, weight_df)

    chart_df.to_csv(OUTPUT_DIR / "chart_data.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(OUTPUT_DIR / "peer_indicator_long.csv", index=False, encoding="utf-8-sig")
    tongji_df.to_csv(OUTPUT_DIR / "tongji_indicator_check.csv", index=False, encoding="utf-8-sig")
    weight_summary_df.to_csv(OUTPUT_DIR / "indicator_weight_summary.csv", index=False, encoding="utf-8-sig")
    source_trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")

    render_chart(chart_df, weight_summary_df, OUTPUT_DIR / "chart.png")
    write_markdown_table(chart_df, OUTPUT_DIR / "chart_table.md")
    write_narrative(chart_df, OUTPUT_DIR / "narrative.md")

    validation = {
        "release_year": RELEASE_YEAR,
        "ranking_year": RANKING_YEAR,
        "peer_scope_size": int(chart_df["peer_scope_size"].max()),
        "comparison_scope_size": int(chart_df["comparison_scope_size"].max()),
        "indicator_count": int(len(chart_df)),
        "peer_indicator_rows": int((long_df["scope_role"] == "peer_top200").sum()),
        "tongji_indicator_rows": int((long_df["scope_role"] == "target_reference_outside_peer_scope").sum()),
        "tongji_in_peer_scope": bool(chart_df["tongji_in_peer_scope"].any()),
        "component_indicators": COMPONENT_INDICATORS,
        "weight_summary_all_matched": bool((weight_summary_df["matched_detail_count"] > 0).all()),
    }
    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": generated_at,
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "ranking_source": RANKING_SOURCE,
        "chart_type": "indicator relative rank dot plot",
        "data_source": "processed/ranking.sqlite: fact_ranking_indicator + fact_indicator_weight + fact_ranking",
        "selection_rule": "ARWU mainland universities in target subject with latest rank_midpoint <= 200; Tongji is added as outside-peer reference because it ranks 401-500.",
        "relative_rank_rule": "Higher metric_value is better; rank(method='min', ascending=False) within peer_top200 + Tongji reference.",
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
            "Tongji is not in ARWU 2025 Mathematics top-200 mainland peer scope.",
            "ARWU fact table exposes five component score columns; detailed weight rows are aggregated to those five components where possible.",
            "辅助总得分 and 总得分 are excluded from the component-indicator chart.",
        ],
    }
    (OUTPUT_DIR / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    run_log = f"""# {ARTIFACT_ID} run log

- generated_at: {generated_at}
- script: `scripts/build_artifact_figure_09.py`
- input_sqlite: `{SQLITE_PATH}`
- target_subject: `{TARGET_SUBJECT}`
- ranking_source: `{RANKING_SOURCE}`
- peer_scope_size: {validation['peer_scope_size']}
- comparison_scope_size: {validation['comparison_scope_size']}
- indicator_count: {validation['indicator_count']}
- peer_indicator_rows: {validation['peer_indicator_rows']}
- tongji_indicator_rows: {validation['tongji_indicator_rows']}
- tongji_in_peer_scope: {validation['tongji_in_peer_scope']}
- output_dir: `{OUTPUT_DIR}`
"""
    (OUTPUT_DIR / "run_log.md").write_text(run_log, encoding="utf-8")
    with (LOG_DIR / "artifact_generation_run_log.md").open("a", encoding="utf-8") as f:
        f.write("\n\n" + run_log)

    print(json.dumps(validation | {"output_dir": str(OUTPUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
