from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "table_04_mainland_rank_band_distribution"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"

ARTIFACT_ID = "table_04_mainland_rank_band_distribution"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026

SOURCE_ORDER = ["软科", "QS", "US News", "THE"]
RANK_BANDS = [
    {"rank_band": "前50", "rank_min": 1, "rank_max": 50},
    {"rank_band": "51-100", "rank_min": 51, "rank_max": 100},
    {"rank_band": "101-200", "rank_min": 101, "rank_max": 200},
]

TABLE_WIDTH = 1500
TABLE_HEIGHT = 860


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


def draw_centered(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str = "#1F2933",
) -> None:
    left, top, right, bottom = box
    tw, th = text_size(draw, text, font)
    draw.text((left + (right - left - tw) / 2, top + (bottom - top - th) / 2 - 2), text, fill=fill, font=font)


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


def rank_band(value: float) -> str:
    for band in RANK_BANDS:
        if band["rank_min"] <= value <= band["rank_max"]:
            return band["rank_band"]
    return "200以后"


def query_mainland_records() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    subject_id = resolve_subject_id()
    query = """
    SELECT
      f.fact_id,
      f.ranking_source,
      f.release_year,
      f.ranking_year,
      f.ranking_subject_raw,
      f.university_name_cn,
      f.university_name_en,
      f.country_or_region,
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
      AND f.is_mainland_china = 1
    ORDER BY f.ranking_source, f.release_year, f.ranking_year, f.rank_midpoint
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[subject_id])

    if df.empty:
        raise RuntimeError("未查询到内地高校排名数据。")

    df["release_year"] = pd.to_numeric(df["release_year"], errors="coerce").astype("Int64")
    df["ranking_year"] = pd.to_numeric(df["ranking_year"], errors="coerce").astype("Int64")
    df["rank_midpoint"] = pd.to_numeric(df["rank_midpoint"], errors="coerce")
    df = df.dropna(subset=["release_year", "ranking_year", "rank_midpoint"]).copy()

    trace_columns = [
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "university_name_cn",
        "university_name_en",
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
        "ranking_source",
        "release_year",
        "ranking_year",
        "ranking_subject_raw",
        "university_name_cn",
        "university_name_en",
        "country_or_region",
        "rank_raw",
        "rank_min",
        "rank_max",
        "rank_midpoint",
        "total_score",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    point_df = (
        df.groupby(point_columns, dropna=False)
        .agg(
            ranking_subject_alias=("ranking_subject_alias", join_unique),
            alias_type=("alias_type", join_unique),
            alias_match_rows=("alias_type", "size"),
        )
        .reset_index()
    )

    latest_rows = []
    for source, group in point_df.groupby("ranking_source"):
        latest_release_year = group["release_year"].max()
        latest_group = group[group["release_year"] == latest_release_year].copy()
        latest_ranking_year = latest_group["ranking_year"].max()
        latest_group = latest_group[latest_group["ranking_year"] == latest_ranking_year].copy()
        latest_rows.append(latest_group)

    latest_df = pd.concat(latest_rows, ignore_index=True)
    latest_df["rank_band"] = latest_df["rank_midpoint"].apply(rank_band)
    latest_df["source_order"] = latest_df["ranking_source"].map({source: idx for idx, source in enumerate(SOURCE_ORDER)})
    latest_df = latest_df.sort_values(["source_order", "rank_midpoint", "university_name_cn"]).drop(columns=["source_order"])
    return latest_df.reset_index(drop=True), trace_df, len(df)


def build_table_data(records_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    top200_df = records_df[records_df["rank_band"] != "200以后"].copy()
    summary_rows = []
    for source in SOURCE_ORDER:
        source_rows = records_df[records_df["ranking_source"] == source].copy()
        if source_rows.empty:
            continue
        release_year = int(source_rows["release_year"].max())
        ranking_year = int(source_rows["ranking_year"].max())
        subject_name = clean_text(source_rows["ranking_subject_raw"].iloc[0])
        for band in RANK_BANDS:
            count = int(((source_rows["rank_midpoint"] >= band["rank_min"]) & (source_rows["rank_midpoint"] <= band["rank_max"])).sum())
            summary_rows.append(
                {
                    "target_subject": TARGET_SUBJECT,
                    "ranking_source": source,
                    "release_year": release_year,
                    "ranking_year": ranking_year,
                    "ranking_subject_raw": subject_name,
                    "rank_band": band["rank_band"],
                    "rank_min": band["rank_min"],
                    "rank_max": band["rank_max"],
                    "mainland_university_count": count,
                }
            )
        summary_rows.append(
            {
                "target_subject": TARGET_SUBJECT,
                "ranking_source": source,
                "release_year": release_year,
                "ranking_year": ranking_year,
                "ranking_subject_raw": subject_name,
                "rank_band": "前200合计",
                "rank_min": 1,
                "rank_max": 200,
                "mainland_university_count": int(len(top200_df[top200_df["ranking_source"] == source])),
            }
        )
    table_df = pd.DataFrame(summary_rows)

    source_labels = {
        row["ranking_source"]: f"{row['ranking_source']}({int(row['release_year'])})"
        for _, row in table_df.drop_duplicates("ranking_source").iterrows()
    }
    matrix = table_df.pivot(index="rank_band", columns="ranking_source", values="mainland_university_count").fillna(0).astype(int)
    matrix = matrix.reindex([band["rank_band"] for band in RANK_BANDS] + ["前200合计"])
    matrix = matrix[[source for source in SOURCE_ORDER if source in matrix.columns]]
    matrix = matrix.rename(columns=source_labels).reset_index().rename(columns={"rank_band": "位次区间"})
    return table_df, matrix, top200_df


def render_table(matrix_df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (TABLE_WIDTH, TABLE_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    font_title = load_font(34, bold=True)
    font_subtitle = load_font(21)
    font_header = load_font(20, bold=True)
    font_cell = load_font(22)
    font_note = load_font(17)

    draw.text((80, 48), f"{TARGET_SUBJECT}学科四大国际排名中内地高校位次分布", fill="#1F2933", font=font_title)
    draw.text((80, 94), "按各榜单最新可用年度统计；排名区间以中位数归入分档", fill="#52606D", font=font_subtitle)

    left = 80
    top = 165
    row_h = 76
    col_widths = [230] + [260] * (len(matrix_df.columns) - 1)
    total_width = sum(col_widths)

    x = left
    for col_idx, col_name in enumerate(matrix_df.columns):
        w = col_widths[col_idx]
        draw.rectangle((x, top, x + w, top + row_h), fill="#EFF3F7", outline="#CBD2D9", width=1)
        draw_centered(draw, (x, top, x + w, top + row_h), str(col_name), font_header, "#1F2933")
        x += w

    for row_idx, row in matrix_df.iterrows():
        y = top + row_h * (row_idx + 1)
        fill = "#FFFFFF" if row_idx % 2 == 0 else "#F8FAFC"
        if clean_text(row["位次区间"]) == "前200合计":
            fill = "#F0F7F4"
        x = left
        for col_idx, col_name in enumerate(matrix_df.columns):
            w = col_widths[col_idx]
            draw.rectangle((x, y, x + w, y + row_h), fill=fill, outline="#CBD2D9", width=1)
            draw_centered(draw, (x, y, x + w, y + row_h), str(row[col_name]), font_cell, "#1F2933")
            x += w

    note = "注：THE 为领域排名口径，数学对应理学/Physical Sciences 领域；不同榜单覆盖高校规模不同，表内数量仅表示对应榜单口径下的内地高校数量。"
    draw.text((80, top + row_h * (len(matrix_df) + 1) + 42), note, fill="#52606D", font=font_note)
    draw.line((80, top + row_h * (len(matrix_df) + 1) + 28, 80 + total_width, top + row_h * (len(matrix_df) + 1) + 28), fill="#CBD2D9", width=1)
    image.save(output_path)


def build_table_markdown(matrix_df: pd.DataFrame) -> str:
    lines = [f"# 表4：{TARGET_SUBJECT}学科四大国际排名中内地高校位次分布", ""]
    header = "| " + " | ".join(matrix_df.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(matrix_df.columns)) + " |"
    lines.extend([header, separator])
    for _, row in matrix_df.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in matrix_df.columns) + " |")
    lines.extend(
        [
            "",
            "注：按各榜单最新可用年度统计，排名区间以 `rank_midpoint` 归入分档；THE 为领域排名口径。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_narrative(table_df: pd.DataFrame) -> str:
    total_rows = table_df[table_df["rank_band"] == "前200合计"].copy()
    lines = [
        "# 表4分析草稿：四大国际排名中内地高校位次分布",
        "",
        f"本表统计 `{TARGET_SUBJECT}` 学科在四大国际排名最新可用年度中，中国内地高校进入前200位的分布情况。",
        "",
        "## 前200概览",
        "",
    ]
    for _, row in total_rows.iterrows():
        lines.append(
            f"- {clean_text(row['ranking_source'])}：{int(row['release_year'])}发布，"
            f"{clean_text(row['ranking_subject_raw'])}，前200内地高校 `{int(row['mainland_university_count'])}` 所。"
        )
    lines.extend(
        [
            "",
            "## 口径说明",
            "",
            "- 分档使用 `rank_midpoint`，例如 `151-200` 归入 `101-200`。",
            "- `peer_records_top200.csv` 保留进入前200的内地高校明细，可继续用于对标高校列表和分项指标分析。",
            "- THE 为领域排名，数学对应 `理学/Physical Sciences`，正文中需要说明该口径。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    records_df, trace_df, raw_match_rows = query_mainland_records()
    table_df, matrix_df, top200_df = build_table_data(records_df)

    table_df.to_csv(OUTPUT_DIR / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix_df.to_csv(OUTPUT_DIR / "table_matrix.csv", index=False, encoding="utf-8-sig")
    top200_df.to_csv(OUTPUT_DIR / "peer_records_top200.csv", index=False, encoding="utf-8-sig")
    trace_df.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / "table.md").write_text(build_table_markdown(matrix_df), encoding="utf-8", newline="\n")
    (OUTPUT_DIR / "narrative.md").write_text(build_narrative(table_df), encoding="utf-8", newline="\n")
    render_table(matrix_df, OUTPUT_DIR / "table.png")

    validation = []
    for source in SOURCE_ORDER:
        source_table = table_df[table_df["ranking_source"] == source]
        if source_table.empty:
            continue
        band_sum = int(source_table[source_table["rank_band"].isin([band["rank_band"] for band in RANK_BANDS])]["mainland_university_count"].sum())
        total = int(source_table[source_table["rank_band"] == "前200合计"]["mainland_university_count"].iloc[0])
        validation.append({"ranking_source": source, "band_sum": band_sum, "top200_total": total, "match": band_sum == total})

    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": now_text(),
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "table_type": "rank band distribution",
        "data_source": "processed/ranking.sqlite: fact_ranking join dim_subject_alias",
        "selection_rule": "mainland China universities, latest release_year per ranking_source, latest ranking_year, rank_midpoint <= 200 for band totals",
        "rank_bands": RANK_BANDS,
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "dedup_latest_mainland_rows": len(records_df),
        "top200_peer_rows": len(top200_df),
        "validation": validation,
        "notes": [
            "Ranking ranges are assigned by rank_midpoint.",
            "Multiple subject-alias matches are deduplicated before counting.",
            "THE uses area-level ranking; Mathematics maps to Physical Sciences/理学.",
        ],
        "outputs": {
            "table_data": str(OUTPUT_DIR / "table_data.csv"),
            "table_matrix": str(OUTPUT_DIR / "table_matrix.csv"),
            "peer_records_top200": str(OUTPUT_DIR / "peer_records_top200.csv"),
            "table_markdown": str(OUTPUT_DIR / "table.md"),
            "table_png": str(OUTPUT_DIR / "table.png"),
            "narrative": str(OUTPUT_DIR / "narrative.md"),
            "source_trace": str(OUTPUT_DIR / "source_trace.csv"),
        },
    }
    (OUTPUT_DIR / "table_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    run_log = [
        "# table_04_mainland_rank_band_distribution run log",
        "",
        f"- generated_at: {spec['generated_at']}",
        f"- target_subject: {TARGET_SUBJECT}",
        f"- raw_match_rows_before_alias_dedup: {raw_match_rows}",
        f"- dedup_latest_mainland_rows: {len(records_df)}",
        f"- top200_peer_rows: {len(top200_df)}",
        f"- ranking_sources: {', '.join(SOURCE_ORDER)}",
        "",
        "## validation",
        "",
    ]
    for item in validation:
        run_log.append(f"- {item['ranking_source']}: band_sum={item['band_sum']}, top200_total={item['top200_total']}, match={item['match']}")
    (OUTPUT_DIR / "run_log.md").write_text("\n".join(run_log) + "\n", encoding="utf-8", newline="\n")

    global_log = LOG_DIR / "artifact_generation_run_log.md"
    if not global_log.exists():
        global_log.write_text("# Artifact 生成过程留档\n", encoding="utf-8", newline="\n")
    with global_log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"\n## {spec['generated_at']} {ARTIFACT_ID}\n\n"
            f"- 输出目录：`{OUTPUT_DIR}`\n"
            f"- alias 去重前匹配行数：{raw_match_rows}\n"
            f"- 最新年度内地高校记录：{len(records_df)}\n"
            f"- 前200内地高校明细：{len(top200_df)}\n"
            f"- 校验：{validation}\n"
        )

    return {
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "dedup_latest_mainland_rows": len(records_df),
        "top200_peer_rows": len(top200_df),
        "validation": validation,
        "output_dir": str(OUTPUT_DIR),
    }


def main() -> None:
    summary = build_outputs()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
