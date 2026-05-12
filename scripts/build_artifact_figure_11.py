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
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "figure_11_usnews_peer_indicator_relative_rank"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
PEER_RECORDS_PATH = PROJECT_DIR / "outputs" / "artifacts" / "table_06_usnews_mainland_peer_ranking" / "latest_peer_records.csv"

ARTIFACT_ID = "figure_11_usnews_peer_indicator_relative_rank"
RANKING_SOURCE = "US News"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
RELEASE_YEAR = 2025
RANKING_YEAR = 2026
TOP_RANK_MIDPOINT = 200

EXCLUDED_INDICATORS = {"总得分"}
INDICATOR_ORDER = [
    "全球学术声誉排名",
    "地区学术声誉排名",
    "出版物排名",
    "标准化论文引用影响指数排名",
    "总被引频次排名",
    "被引用最多的10%的出版物数量排名",
    "总被引率占总被引文献的10%排名",
    "排名前1%的高被引论文数量排名",
    "前1%的高被引论文占论文总数的百分比排名",
    "具有国际合作出版物的比例排名",
    "国际合作排名",
]

INDICATOR_SHORT_NAMES = {
    "全球学术声誉排名": "全球声誉",
    "地区学术声誉排名": "地区声誉",
    "出版物排名": "出版物",
    "标准化论文引用影响指数排名": "标准化引用",
    "总被引频次排名": "总被引",
    "被引用最多的10%的出版物数量排名": "10%高引数量",
    "总被引率占总被引文献的10%排名": "10%高引比例",
    "排名前1%的高被引论文数量排名": "1%高引数量",
    "前1%的高被引论文占论文总数的百分比排名": "1%高引比例",
    "具有国际合作出版物的比例排名": "国际合作比例",
    "国际合作排名": "国际合作",
}

CHART_WIDTH = 1900
CHART_HEIGHT = 1540


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


def normalize_university_key(cn_name: Any, en_name: Any) -> str:
    en = clean_text(en_name)
    cn = clean_text(cn_name)
    base = en or cn
    base = base.lower()
    base = base.replace("&", " and ")
    base = re.sub(r"\bcas\b", " ", base)
    base = re.sub(r"\bchina\b$", " ", base)
    base = re.sub(r"\s*-\s*china\b", " ", base)
    base = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", base)
    return base


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
      AND metric_type = 'rank'
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
    """
    weight_df = pd.read_sql_query(weight_sql, con, params=[RANKING_SOURCE])
    con.close()

    indicator_df = indicator_df[~indicator_df["indicator_name"].isin(EXCLUDED_INDICATORS)].copy()
    if not PEER_RECORDS_PATH.exists():
        raise RuntimeError(f"缺少已验证的 US News peer 样本文件：{PEER_RECORDS_PATH}")
    peer_df = pd.read_csv(PEER_RECORDS_PATH)
    if indicator_df.empty:
        raise RuntimeError("未查询到 US News 目标学科排名型分项指标。")
    if peer_df.empty:
        raise RuntimeError("US News 已验证 peer 样本为空。")
    return indicator_df, peer_df, weight_df


def build_weight_coverage(weight_df: pd.DataFrame) -> pd.DataFrame:
    exact_df = weight_df[weight_df["ranking_subject_or_area"] == TARGET_SUBJECT].copy()
    available_subjects = sorted(weight_df["ranking_subject_or_area"].dropna().unique().tolist())
    rows = []
    for indicator_name in INDICATOR_ORDER:
        rows.append(
            {
                "target_subject": TARGET_SUBJECT,
                "indicator_name": indicator_name,
                "exact_subject_weight_found": bool(not exact_df.empty),
                "matched_weight_percent": "",
                "coverage_note": "当前 fact_indicator_weight 中没有 US News 数学权重行，未使用替代学科权重。",
                "available_usnews_weight_subjects": "；".join(available_subjects),
            }
        )
    return pd.DataFrame(rows)


def assign_university_keys(df: pd.DataFrame) -> pd.DataFrame:
    keyed_df = df.copy()
    keyed_df["university_key_base"] = keyed_df.apply(
        lambda row: normalize_university_key(row["university_name_cn"], row["university_name_en"]),
        axis=1,
    )

    distinct_universities = keyed_df[["university_key_base", "university_name_cn"]].drop_duplicates()
    conflict_bases = set(
        distinct_universities.groupby("university_key_base")["university_name_cn"].nunique().loc[lambda s: s > 1].index.tolist()
    )
    keyed_df["university_key_cn"] = keyed_df["university_name_cn"].apply(normalize_text_key)
    keyed_df["university_key"] = keyed_df.apply(
        lambda row: f"{row['university_key_base']}_{row['university_key_cn']}"
        if row["university_key_base"] in conflict_bases
        else row["university_key_base"],
        axis=1,
    )
    return keyed_df


def build_chart_data(indicator_df: pd.DataFrame, peer_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    indicator_df = indicator_df[indicator_df["indicator_name"].isin(INDICATOR_ORDER)].copy()
    indicator_df = assign_university_keys(indicator_df)
    peer_df = peer_df.copy()
    peer_df = peer_df.sort_values(["rank_midpoint", "university_name_cn"]).drop_duplicates("university_key")
    peer_keys = set(peer_df["university_key"].tolist())

    target_key_candidates = set()
    target_indicator = indicator_df[(indicator_df["university_name_cn"] == TARGET_UNIVERSITY) | (indicator_df["is_tongji"] == 1)].copy()
    target_key_candidates.update(target_indicator["university_key"].dropna().tolist())
    target_keys = {key for key in target_key_candidates if clean_text(key)}
    if not target_keys:
        raise RuntimeError("未找到同济大学 US News 指标记录。")

    peer_indicator_df = indicator_df[indicator_df["university_key"].isin(peer_keys)].copy()
    target_indicator_df = indicator_df[indicator_df["university_key"].isin(target_keys)].copy()
    peer_indicator_df["scope_role"] = "peer_top200"
    target_indicator_df["scope_role"] = "target_reference_outside_peer_scope"
    combined_df = pd.concat([peer_indicator_df, target_indicator_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(["university_key", "indicator_name"], keep="first").reset_index(drop=True)

    if len(peer_df) == 0:
        raise RuntimeError("US News 前200内地高校样本为空，无法计算相对排名。")
    if target_indicator_df.empty:
        raise RuntimeError("同济大学分项指标记录为空。")

    long_frames = []
    chart_rows = []
    for indicator_name in INDICATOR_ORDER:
        peer_one = peer_indicator_df[peer_indicator_df["indicator_name"] == indicator_name].copy()
        target_one = target_indicator_df[target_indicator_df["indicator_name"] == indicator_name].copy()
        if peer_one.empty or target_one.empty:
            continue
        comparison_one = pd.concat([peer_one, target_one], ignore_index=True)
        comparison_one = comparison_one.drop_duplicates(["university_key", "indicator_name"], keep="first")
        comparison_one["relative_rank_with_tongji"] = comparison_one["metric_value"].rank(method="min", ascending=True)
        comparison_one["comparison_scope_size"] = len(comparison_one)
        comparison_one["peer_scope_size"] = len(peer_one)
        long_frames.append(comparison_one)

        target_row = target_one.iloc[0]
        target_metric_rank = float(target_row["metric_value"])
        target_relative_rank = float(comparison_one[comparison_one["university_key"] == target_row["university_key"]]["relative_rank_with_tongji"].iloc[0])
        peer_values = peer_one["metric_value"].dropna()
        chart_rows.append(
            {
                "indicator_name": indicator_name,
                "indicator_short_name": INDICATOR_SHORT_NAMES.get(indicator_name, indicator_name),
                "indicator_group": clean_text(target_row["indicator_group"]),
                "peer_scope_size": int(len(peer_one)),
                "comparison_scope_size": int(len(comparison_one)),
                "peer_best_indicator_rank": float(peer_values.min()),
                "peer_median_indicator_rank": float(peer_values.median()),
                "peer_worst_indicator_rank": float(peer_values.max()),
                "tongji_indicator_rank": target_metric_rank,
                "tongji_relative_rank_with_peer_reference": int(target_relative_rank),
                "tongji_percentile_from_top": round((1 - (target_relative_rank - 1) / max(len(comparison_one) - 1, 1)) * 100, 1),
                "tongji_in_peer_scope": bool(target_row["university_key"] in peer_keys),
            }
        )

    long_df = pd.concat(long_frames, ignore_index=True)
    ranking_cols = peer_df[["university_key", "rank_raw", "rank_midpoint", "total_score"]].rename(
        columns={
            "rank_raw": "world_rank_raw_from_fact_ranking",
            "rank_midpoint": "world_rank_midpoint_from_fact_ranking",
            "total_score": "total_score_from_fact_ranking",
        }
    )
    long_df = long_df.merge(ranking_cols, on="university_key", how="left")
    chart_df = pd.DataFrame(chart_rows)
    tongji_df = long_df[long_df["scope_role"] == "target_reference_outside_peer_scope"].copy()
    return long_df, chart_df, tongji_df


def render_chart(chart_df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    title_font = load_font(42, bold=True)
    subtitle_font = load_font(25)
    label_font = load_font(22)
    small_font = load_font(19)
    axis_font = load_font(18)
    bold_small_font = load_font(21, bold=True)

    margin_left = 420
    margin_right = 240
    axis_left = margin_left
    axis_right = CHART_WIDTH - margin_right
    title_y = 55
    plot_top = 255
    row_gap = 98
    max_rank = int(chart_df["comparison_scope_size"].max())

    draw.text((70, title_y), "US News数学前200内地高校分项指标相对位置", font=title_font, fill="#1F2933")
    draw.text(
        (70, title_y + 58),
        "US News分项为排名字段，越小越好；同济数学排名261，作为外部参照点加入比较",
        font=subtitle_font,
        fill="#52616F",
    )
    draw.text((axis_left, plot_top - 85), "相对排名（越靠左越好）", font=axis_font, fill="#52616F")

    def x_for_rank(rank: float) -> int:
        return int(axis_left + (rank - 1) / (max_rank - 1) * (axis_right - axis_left))

    for tick in [1, 10, 20, 30, 40, max_rank]:
        if tick > max_rank:
            continue
        x = x_for_rank(tick)
        draw.line((x, plot_top - 35, x, plot_top + row_gap * (len(chart_df) - 1) + 56), fill="#E4E9F0", width=2)
        draw_text_right(draw, x + 14, plot_top - 60, str(tick), axis_font, "#52616F")

    group_colors = {
        "声誉": "#5B8DEF",
        "科研/论文": "#5AA469",
        "国际化/合作": "#B26EEC",
    }
    for idx, row in chart_df.iterrows():
        y = plot_top + idx * row_gap
        group = clean_text(row["indicator_group"])
        color = group_colors.get(group, "#7B8794")
        draw_text_right(draw, margin_left - 34, y - 22, str(row["indicator_short_name"]), label_font, "#1F2933")
        draw_text_right(draw, margin_left - 34, y + 8, group, small_font, color)

        draw.line((axis_left, y, axis_right, y), fill="#D7DEE8", width=5)
        for rank in range(1, max_rank + 1):
            x = x_for_rank(rank)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#C9D3DF")

        tongji_rank = float(row["tongji_relative_rank_with_peer_reference"])
        tongji_x = x_for_rank(tongji_rank)
        draw.ellipse((tongji_x - 13, y - 13, tongji_x + 13, y + 13), fill="#C0392B")
        draw.ellipse((tongji_x - 6, y - 6, tongji_x + 6, y + 6), fill="#FFFFFF")
        if tongji_x > axis_right - 230:
            draw_text_right(draw, tongji_x - 20, y - 25, f"同济 {int(tongji_rank)}/{max_rank}", bold_small_font, "#C0392B")
            draw_text_right(draw, tongji_x - 20, y + 2, f"指标排名 {int(row['tongji_indicator_rank'])}", axis_font, "#7B2D26")
        else:
            draw.text((tongji_x + 20, y - 25), f"同济 {int(tongji_rank)}/{max_rank}", font=bold_small_font, fill="#C0392B")
            draw.text((tongji_x + 20, y + 2), f"指标排名 {int(row['tongji_indicator_rank'])}", font=axis_font, fill="#7B2D26")
        draw.text(
            (axis_right + 30, y - 20),
            f"peer中位 {row['peer_median_indicator_rank']:.0f}",
            font=axis_font,
            fill="#52616F",
        )

    legend_y = CHART_HEIGHT - 155
    draw.ellipse((70, legend_y - 12, 94, legend_y + 12), fill="#C0392B")
    draw.text((112, legend_y - 18), "同济大学外部参照点", font=small_font, fill="#1F2933")
    draw.ellipse((395, legend_y - 7, 409, legend_y + 7), fill="#C9D3DF")
    draw.text((426, legend_y - 18), "peer 样本相对排名刻度", font=small_font, fill="#1F2933")
    draw.text(
        (70, legend_y + 38),
        "注：US News数学前200内地高校为43所；同济不在该样本内，因此相对名次按“43所peer+同济参照”计算。当前权重事实表无US News数学权重行。",
        font=small_font,
        fill="#52616F",
    )
    image.save(output_path)


def build_source_trace(long_df: pd.DataFrame, weight_coverage_df: pd.DataFrame) -> pd.DataFrame:
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
        "scope_role",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    trace_indicator = long_df[indicator_cols].copy()
    trace_indicator.insert(0, "trace_type", "ranking_indicator")

    trace_weight = weight_coverage_df.copy()
    trace_weight.insert(0, "trace_type", "indicator_weight_coverage")
    return pd.concat([trace_indicator, trace_weight], ignore_index=True, sort=False)


def write_markdown_table(chart_df: pd.DataFrame, path: Path) -> None:
    rows = [
        "| 指标 | 指标组 | peer样本数 | 同济指标排名 | 同济相对名次 | peer最佳 | peer中位 | peer最弱 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in chart_df.iterrows():
        rows.append(
            "| {indicator} | {group} | {peer} | {tongji_metric:.0f} | {relative}/{scope} | {best:.0f} | {median:.0f} | {worst:.0f} |".format(
                indicator=row["indicator_short_name"],
                group=row["indicator_group"],
                peer=int(row["peer_scope_size"]),
                tongji_metric=float(row["tongji_indicator_rank"]),
                relative=int(row["tongji_relative_rank_with_peer_reference"]),
                scope=int(row["comparison_scope_size"]),
                best=float(row["peer_best_indicator_rank"]),
                median=float(row["peer_median_indicator_rank"]),
                worst=float(row["peer_worst_indicator_rank"]),
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_narrative(chart_df: pd.DataFrame, path: Path) -> None:
    best = chart_df.sort_values("tongji_relative_rank_with_peer_reference").iloc[0]
    weakest = chart_df.sort_values("tongji_relative_rank_with_peer_reference", ascending=False).iloc[0]
    text = f"""# 图7分析草稿：US News排名前200位内地高校分项指标相对排名

本图以 US News {RANKING_YEAR} 排名年度 `{TARGET_SUBJECT}` 学科进入世界前200的中国内地高校为 peer 样本，共 `{int(chart_df['peer_scope_size'].max())}` 所。由于同济大学 US News 数学最新排名为 `261`，不属于前200 peer 样本，因此本图将同济作为外部参照点加入比较，计算其在 `peer样本+同济` 范围内的相对位置。

US News 分项指标为排名字段，数值越小代表表现越靠前。同济大学在相对位置最好的是 `{best['indicator_short_name']}`，在 `{int(best['comparison_scope_size'])}` 个比较对象中位列第 `{int(best['tongji_relative_rank_with_peer_reference'])}`；相对靠后的指标是 `{weakest['indicator_short_name']}`，位列第 `{int(weakest['tongji_relative_rank_with_peer_reference'])}`。

## 口径说明

- `chart_data.csv` 是绘图摘要，一行一个分项指标。
- `peer_indicator_long.csv` 保留 43 所 peer 高校和同济参照点的逐校逐指标数据。
- `indicator_weight_coverage.csv` 记录权重覆盖情况；当前 `fact_indicator_weight` 中没有 US News 数学权重行，因此本图不展示权重。
- `tongji_indicator_check.csv` 单独保留同济大学分项指标记录，便于解释同济不在前200样本内。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = now_text()

    indicator_df, ranking_df, weight_df = query_source_data()
    weight_coverage_df = build_weight_coverage(weight_df)
    long_df, chart_df, tongji_df = build_chart_data(indicator_df, ranking_df)
    source_trace_df = build_source_trace(long_df, weight_coverage_df)

    chart_df.to_csv(OUTPUT_DIR / "chart_data.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(OUTPUT_DIR / "peer_indicator_long.csv", index=False, encoding="utf-8-sig")
    tongji_df.to_csv(OUTPUT_DIR / "tongji_indicator_check.csv", index=False, encoding="utf-8-sig")
    weight_coverage_df.to_csv(OUTPUT_DIR / "indicator_weight_coverage.csv", index=False, encoding="utf-8-sig")
    source_trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_chart(chart_df, OUTPUT_DIR / "chart.png")
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
        "weight_exact_subject_found": bool(weight_coverage_df["exact_subject_weight_found"].any()),
        "metric_rule": "US News rank metrics: lower is better.",
    }
    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": generated_at,
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "ranking_source": RANKING_SOURCE,
        "chart_type": "indicator relative rank dot plot",
        "data_source": "processed/ranking.sqlite: fact_ranking_indicator + fact_ranking; fact_indicator_weight checked for coverage",
        "selection_rule": "US News mainland universities in target subject with latest rank_midpoint <= 200; Tongji is added as outside-peer reference because it ranks 261.",
        "relative_rank_rule": "US News indicator metrics are rank fields; lower metric_value is better; rank(method='min', ascending=True) within peer_top200 + Tongji reference.",
        "validation": validation,
        "outputs": {
            "chart_data": str(OUTPUT_DIR / "chart_data.csv"),
            "peer_indicator_long": str(OUTPUT_DIR / "peer_indicator_long.csv"),
            "tongji_indicator_check": str(OUTPUT_DIR / "tongji_indicator_check.csv"),
            "indicator_weight_coverage": str(OUTPUT_DIR / "indicator_weight_coverage.csv"),
            "chart_table": str(OUTPUT_DIR / "chart_table.md"),
            "chart_png": str(OUTPUT_DIR / "chart.png"),
            "narrative": str(OUTPUT_DIR / "narrative.md"),
            "source_trace": str(OUTPUT_DIR / "source_trace.csv"),
        },
        "notes": [
            "Tongji is not in US News 2026 Mathematics top-200 mainland peer scope.",
            "US News Mathematics has ranking-type component indicators, not score-type component indicators.",
            "Current fact_indicator_weight has no US News Mathematics weight rows; no substitute weights are applied.",
        ],
    }
    (OUTPUT_DIR / "chart_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    run_log = f"""# {ARTIFACT_ID} run log

- generated_at: {generated_at}
- script: `scripts/build_artifact_figure_11.py`
- input_sqlite: `{SQLITE_PATH}`
- target_subject: `{TARGET_SUBJECT}`
- ranking_source: `{RANKING_SOURCE}`
- peer_scope_size: {validation['peer_scope_size']}
- comparison_scope_size: {validation['comparison_scope_size']}
- indicator_count: {validation['indicator_count']}
- peer_indicator_rows: {validation['peer_indicator_rows']}
- tongji_indicator_rows: {validation['tongji_indicator_rows']}
- tongji_in_peer_scope: {validation['tongji_in_peer_scope']}
- weight_exact_subject_found: {validation['weight_exact_subject_found']}
- output_dir: `{OUTPUT_DIR}`
"""
    (OUTPUT_DIR / "run_log.md").write_text(run_log, encoding="utf-8")
    with (LOG_DIR / "artifact_generation_run_log.md").open("a", encoding="utf-8") as f:
        f.write("\n\n" + run_log)

    print(json.dumps(validation | {"output_dir": str(OUTPUT_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
