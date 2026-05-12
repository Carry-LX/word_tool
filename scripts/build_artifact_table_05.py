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
OUTPUT_DIR = PROJECT_DIR / "outputs" / "artifacts" / "table_05_arwu_mainland_peer_ranking"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"

ARTIFACT_ID = "table_05_arwu_mainland_peer_ranking"
RANKING_SOURCE = "软科"
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
TOP_RANK_MIDPOINT = 200

TABLE_WIDTH = 1700
TABLE_HEIGHT = 1650


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


def query_arwu_records() -> tuple[pd.DataFrame, pd.DataFrame, int]:
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
      f.is_tongji,
      a.subject_id,
      a.ranking_subject_alias,
      a.alias_type
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
      AND f.ranking_source = ?
      AND f.is_mainland_china = 1
    ORDER BY f.release_year, f.rank_midpoint, f.university_name_cn
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[subject_id, RANKING_SOURCE])

    if df.empty:
        raise RuntimeError("未查询到软科内地高校排名数据。")

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
        "is_tongji",
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
    duplicate_check = point_df.groupby(["release_year", "university_name_cn"], dropna=False).size().reset_index(name="row_count")
    conflicts = duplicate_check[duplicate_check["row_count"] > 1]
    if not conflicts.empty:
        detail = conflicts.head(20).to_dict(orient="records")
        raise RuntimeError(f"软科同一高校同一年出现多个候选排名，需要人工核验：{detail}")

    return point_df, trace_df, len(df)


def build_table_data(records_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    latest_year = int(records_df["release_year"].max())
    latest_df = records_df[records_df["release_year"] == latest_year].copy()
    latest_top_df = latest_df[latest_df["rank_midpoint"] <= TOP_RANK_MIDPOINT].copy()
    latest_top_df = latest_top_df.sort_values(["rank_midpoint", "university_name_cn"]).reset_index(drop=True)
    latest_top_df["latest_order"] = range(1, len(latest_top_df) + 1)

    peer_names = latest_top_df["university_name_cn"].tolist()
    table_data = records_df[records_df["university_name_cn"].isin(peer_names)].copy()
    table_data = table_data.sort_values(["university_name_cn", "release_year"]).reset_index(drop=True)

    years = sorted(int(year) for year in records_df["release_year"].dropna().unique())
    matrix_rows = []
    for _, latest in latest_top_df.iterrows():
        name = clean_text(latest["university_name_cn"])
        history = table_data[table_data["university_name_cn"] == name].copy()
        row = {
            "序号": int(latest["latest_order"]),
            "学校": name,
            f"{latest_year}排名": clean_text(latest["rank_raw"]),
            f"{latest_year}排名中位数": float(latest["rank_midpoint"]),
            f"{latest_year}总分": clean_text(latest["total_score"]),
        }
        for year in years:
            year_rows = history[history["release_year"] == year]
            row[f"{year}排名"] = clean_text(year_rows.iloc[0]["rank_raw"]) if not year_rows.empty else ""
        matrix_rows.append(row)
    matrix_df = pd.DataFrame(matrix_rows)
    ordered_columns = ["序号", "学校"] + [f"{year}排名" for year in years] + [f"{latest_year}排名中位数", f"{latest_year}总分"]
    matrix_df = matrix_df[ordered_columns]
    matrix_df = matrix_df.fillna("")

    tongji_df = records_df[records_df["university_name_cn"] == TARGET_UNIVERSITY].copy()
    tongji_df = tongji_df.sort_values("release_year").reset_index(drop=True)
    return table_data, matrix_df, latest_top_df, tongji_df


def render_table(matrix_df: pd.DataFrame, tongji_df: pd.DataFrame, output_path: Path) -> None:
    image = Image.new("RGB", (TABLE_WIDTH, TABLE_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    font_title = load_font(34, bold=True)
    font_subtitle = load_font(20)
    font_header = load_font(18, bold=True)
    font_cell = load_font(17)
    font_note = load_font(16)

    latest_rank = ""
    if not tongji_df.empty:
        latest = tongji_df.sort_values(["release_year", "ranking_year"]).tail(1).iloc[0]
        latest_rank = clean_text(latest["rank_raw"])

    draw.text((70, 42), f"软科{TARGET_SUBJECT}学科内地高校前200排名变化", fill="#1F2933", font=font_title)
    subtitle = f"以最新年份进入前{TOP_RANK_MIDPOINT}的内地高校为样本；{TARGET_UNIVERSITY}最新软科排名：{latest_rank or '未检索到'}"
    draw.text((70, 88), subtitle, fill="#52606D", font=font_subtitle)

    left = 70
    top = 145
    row_h = 56
    col_widths = [70, 260, 170, 170, 170, 190, 150]
    headers = matrix_df.columns.tolist()

    x = left
    for col_idx, header in enumerate(headers):
        w = col_widths[col_idx]
        draw.rectangle((x, top, x + w, top + row_h), fill="#EFF3F7", outline="#CBD2D9", width=1)
        draw_centered(draw, (x, top, x + w, top + row_h), str(header), font_header)
        x += w

    for row_idx, row in matrix_df.iterrows():
        y = top + row_h * (row_idx + 1)
        fill = "#FFFFFF" if row_idx % 2 == 0 else "#F8FAFC"
        x = left
        for col_idx, header in enumerate(headers):
            w = col_widths[col_idx]
            text = clean_text(row[header])
            draw.rectangle((x, y, x + w, y + row_h), fill=fill, outline="#CBD2D9", width=1)
            if header == "学校":
                draw.text((x + 12, y + 16), text, fill="#1F2933", font=font_cell)
            else:
                draw_centered(draw, (x, y, x + w, y + row_h), text, font_cell)
            x += w

    note_y = top + row_h * (len(matrix_df) + 1) + 34
    note = "注：排名区间保留原文；最新年份按 rank_midpoint <= 200 筛选。总分为空表示原榜单该排名段未提供精确总分。"
    draw.text((70, note_y), note, fill="#52606D", font=font_note)
    image.save(output_path)


def build_table_markdown(matrix_df: pd.DataFrame) -> str:
    lines = [f"# 表5：软科{TARGET_SUBJECT}学科内地高校前200排名变化", ""]
    lines.append("| " + " | ".join(matrix_df.columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(matrix_df.columns)) + " |")
    for _, row in matrix_df.iterrows():
        lines.append("| " + " | ".join(clean_text(row[col]) for col in matrix_df.columns) + " |")
    lines.append("")
    lines.append("注：以软科最新年份进入前200的内地高校为样本，排名区间保留原文。")
    return "\n".join(lines) + "\n"


def build_narrative(matrix_df: pd.DataFrame, tongji_df: pd.DataFrame) -> str:
    latest_year_columns = [col for col in matrix_df.columns if col.endswith("排名") and col[:4].isdigit()]
    latest_year = max(int(col[:4]) for col in latest_year_columns)
    top10_names = "、".join(matrix_df.head(10)["学校"].tolist())
    tongji_sentence = f"{TARGET_UNIVERSITY}未检索到软科{TARGET_SUBJECT}学科排名记录。"
    if not tongji_df.empty:
        latest = tongji_df.sort_values(["release_year", "ranking_year"]).tail(1).iloc[0]
        tongji_sentence = (
            f"{TARGET_UNIVERSITY}在软科{TARGET_SUBJECT}学科最新记录为 "
            f"{int(latest['release_year'])} 年 `{clean_text(latest['rank_raw'])}`，"
            f"未进入本表前{TOP_RANK_MIDPOINT}对标样本。"
        )

    lines = [
        "# 表5分析草稿：软科排名中内地高校位于前列的比较",
        "",
        f"本表以软科 {latest_year} 年 `{TARGET_SUBJECT}` 学科进入前{TOP_RANK_MIDPOINT}的中国内地高校为样本，并回看这些高校在已有年份中的排名变化。",
        "",
        "## 样本概览",
        "",
        f"- 最新年份进入前{TOP_RANK_MIDPOINT}的内地高校共 `{len(matrix_df)}` 所。",
        f"- 最新年份排名靠前的高校包括：{top10_names}。",
        f"- {tongji_sentence}",
        "",
        "## 口径说明",
        "",
        "- `table_matrix.csv` 是报告展示用宽表。",
        "- `table_data.csv` 保留样本高校逐年排名长表。",
        "- `latest_peer_records.csv` 保留最新年份前200样本。",
        "- 排名区间保留原文，排序和筛选使用 `rank_midpoint`。",
    ]
    return "\n".join(lines) + "\n"


def build_outputs() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    records_df, trace_df, raw_match_rows = query_arwu_records()
    table_data, matrix_df, latest_top_df, tongji_df = build_table_data(records_df)

    table_data.to_csv(OUTPUT_DIR / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix_df.to_csv(OUTPUT_DIR / "table_matrix.csv", index=False, encoding="utf-8-sig")
    latest_top_df.to_csv(OUTPUT_DIR / "latest_peer_records.csv", index=False, encoding="utf-8-sig")
    tongji_df.to_csv(OUTPUT_DIR / "tongji_scope_check.csv", index=False, encoding="utf-8-sig")

    used_names = set(latest_top_df["university_name_cn"].tolist()) | {TARGET_UNIVERSITY}
    used_trace = trace_df[trace_df["university_name_cn"].isin(used_names)].copy()
    used_trace.to_csv(OUTPUT_DIR / "source_trace.csv", index=False, encoding="utf-8-sig")

    (OUTPUT_DIR / "table.md").write_text(build_table_markdown(matrix_df), encoding="utf-8", newline="\n")
    (OUTPUT_DIR / "narrative.md").write_text(build_narrative(matrix_df, tongji_df), encoding="utf-8", newline="\n")
    render_table(matrix_df, tongji_df, OUTPUT_DIR / "table.png")

    latest_year = int(latest_top_df["release_year"].max())
    validation = {
        "latest_year": latest_year,
        "latest_top_peer_rows": len(latest_top_df),
        "matrix_rows": len(matrix_df),
        "unique_latest_peer_universities": int(latest_top_df["university_name_cn"].nunique()),
        "latest_peer_rows_match_matrix": len(latest_top_df) == len(matrix_df),
        "tongji_in_latest_top_scope": TARGET_UNIVERSITY in set(latest_top_df["university_name_cn"].tolist()),
        "tongji_records": len(tongji_df),
    }

    spec = {
        "artifact_id": ARTIFACT_ID,
        "generated_at": now_text(),
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "ranking_source": RANKING_SOURCE,
        "table_type": "mainland peer ranking history",
        "data_source": "processed/ranking.sqlite: fact_ranking join dim_subject_alias",
        "selection_rule": f"{RANKING_SOURCE} mainland universities with latest_year rank_midpoint <= {TOP_RANK_MIDPOINT}, then attach all available years",
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "dedup_mainland_rows": len(records_df),
        "validation": validation,
        "notes": [
            "Ranking ranges are preserved as raw strings.",
            "Latest peer scope is selected by rank_midpoint.",
            "Tongji is reported separately if it is outside the latest top peer scope.",
        ],
        "outputs": {
            "table_data": str(OUTPUT_DIR / "table_data.csv"),
            "table_matrix": str(OUTPUT_DIR / "table_matrix.csv"),
            "latest_peer_records": str(OUTPUT_DIR / "latest_peer_records.csv"),
            "tongji_scope_check": str(OUTPUT_DIR / "tongji_scope_check.csv"),
            "table_markdown": str(OUTPUT_DIR / "table.md"),
            "table_png": str(OUTPUT_DIR / "table.png"),
            "narrative": str(OUTPUT_DIR / "narrative.md"),
            "source_trace": str(OUTPUT_DIR / "source_trace.csv"),
        },
    }
    (OUTPUT_DIR / "table_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    run_log = [
        "# table_05_arwu_mainland_peer_ranking run log",
        "",
        f"- generated_at: {spec['generated_at']}",
        f"- target_subject: {TARGET_SUBJECT}",
        f"- ranking_source: {RANKING_SOURCE}",
        f"- raw_match_rows_before_alias_dedup: {raw_match_rows}",
        f"- dedup_mainland_rows: {len(records_df)}",
        f"- latest_top_peer_rows: {len(latest_top_df)}",
        f"- matrix_rows: {len(matrix_df)}",
        f"- tongji_in_latest_top_scope: {validation['tongji_in_latest_top_scope']}",
        "",
        "## validation",
        "",
        json.dumps(validation, ensure_ascii=False, indent=2),
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
            f"- 最新年前{TOP_RANK_MIDPOINT}内地高校：{len(latest_top_df)}\n"
            f"- 同济是否进入样本：{validation['tongji_in_latest_top_scope']}\n"
        )

    return {
        "raw_match_rows_before_alias_dedup": raw_match_rows,
        "dedup_mainland_rows": len(records_df),
        "latest_top_peer_rows": len(latest_top_df),
        "matrix_rows": len(matrix_df),
        "tongji_in_latest_top_scope": validation["tongji_in_latest_top_scope"],
        "output_dir": str(OUTPUT_DIR),
    }


def main() -> None:
    summary = build_outputs()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
