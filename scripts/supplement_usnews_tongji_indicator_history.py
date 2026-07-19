from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
EXTERNAL_PROCESSED_DIR = PROJECT_DIR / "external_data" / "processed"
EXTERNAL_REPORT_DIR = PROJECT_DIR / "external_data" / "reports"

OUTPUT_LONG_CSV = EXTERNAL_PROCESSED_DIR / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"
OUTPUT_WIDE_CSV = EXTERNAL_PROCESSED_DIR / "usnews_tongji_subject_indicator_history_2022_2026_wide.csv"
OUTPUT_SUMMARY_JSON = EXTERNAL_REPORT_DIR / "usnews_tongji_indicator_history_supplement_summary.json"
OUTPUT_SUMMARY_MD = EXTERNAL_REPORT_DIR / "usnews_tongji_indicator_history_supplement_summary.md"

SOURCE_CONFIGS = [
    {
        "file_keyword": "2021US News",
        "sheet": "Sheet1",
        "release_year_col": "pubyear",
        "ranking_year": 2021,
        "subject_en_col": "subject",
        "subject_cn_col": "",
        "university_en_col": "university",
        "university_cn_col": "university_zh",
        "rank_col": "subjectrank",
        "score_col": "subjectscore",
        "indicator_columns": {},
    },
    {
        "file_keyword": "2022US News",
        "sheet": "Sheet2",
        "release_year": 2021,
        "ranking_year": 2022,
        "subject_en_col": "subject",
        "subject_cn_col": "",
        "university_en_col": "university",
        "university_cn_col": "university_zh",
        "rank_col": "subjectrank",
        "score_col": "overallscore",
        "indicator_columns": {
            "globalresearchreputation": "全球学术声誉排名",
            "regionalresearchreputation": "地区学术声誉排名",
            "publications": "出版物排名",
            "books": "图书排名",
            "conferences": "会议排名",
            "normalizedcitationimpact": "标准化论文引用影响指数排名",
            "citations": "被引频次排名",
            "totalcitations": "总被引频次排名",
            "numberofpublicationsthatareamongthe10mostcited": "被引用最多的10%的出版物数量排名",
            "percentageoftotalpublicationsthatareamongthe10mostcited": "总被引率占总被引文献的10%排名",
            "internationalcollaborationrelativetocountry": "国际合作排名",
            "internationalcollaboration": "具有国际合作出版物的比例排名",
            "numberofhighlycitedpapersthatareamongthetop1mostcited": "排名前1%的高被引论文数量排名",
            "percentageofhighlycitedpapersthatareamongthetop1mostcited": "前1%的高被引论文占论文总数的百分比排名",
        },
    },
    {
        "file_keyword": "2023US News",
        "sheet": "sheet",
        "release_year_col": "发布时间",
        "ranking_year_col": "Time",
        "subject_en_col": "Subject",
        "subject_cn_col": "",
        "university_en_col": "Name",
        "university_cn_col": "",
        "rank_col": "Rank",
        "score_col": "OVERALL_SCORE",
        "indicator_columns": {
            "Global_Research_Reputatio": "全球学术声誉排名",
            "Regional_Research_Reputation": "地区学术声誉排名",
            "Publications": "出版物排名",
            "Books": "图书排名",
            "Conferences": "会议排名",
            "Normalized_Citation_Impact": "标准化论文引用影响指数排名",
            "Total_Citations": "总被引频次排名",
            "Publications_10_Percent": "被引用最多的10%的出版物数量排名",
            "Total_Publications_10_Percent": "总被引率占总被引文献的10%排名",
            "Relative_To_Country": "国际合作排名",
            "International_Collaboration": "具有国际合作出版物的比例排名",
            "Highly_Cited_Papers_Number_1_Percent": "排名前1%的高被引论文数量排名",
            "Highly_Cited_Papers_1_Percent": "前1%的高被引论文占论文总数的百分比排名",
        },
    },
    {
        "file_keyword": "2024-2025",
        "sheet": "全球排名",
        "release_year_col": "发布年份",
        "ranking_year_col": "排名年份",
        "subject_en_col": "学科",
        "subject_cn_col": "学科中文",
        "university_en_col": "名称",
        "university_cn_col": "中文名称",
        "rank_col": "世界排名",
        "score_col": "总得分.1",
        "indicator_columns": {
            "全球学术声誉排名": "全球学术声誉排名",
            "地区学术声誉排名": "地区学术声誉排名",
            "出版物排名": "出版物排名",
            "图书排名": "图书排名",
            "会议排名": "会议排名",
            "标准化论文引用影响指数排名": "标准化论文引用影响指数排名",
            "总被引频次排名": "总被引频次排名",
            "被引用最多的10%的出版物数量排名": "被引用最多的10%的出版物数量排名",
            "总被引率占总被引文献的10%排名": "总被引率占总被引文献的10%排名",
            "具有国际合作出版物的比例排名": "具有国际合作出版物的比例排名",
            "国际合作排名": "国际合作排名",
            "排名前1%的高被引论文数量排名": "排名前1%的高被引论文数量排名",
            "前1%的高被引论文占论文总数的百分比排名": "前1%的高被引论文占论文总数的百分比排名",
        },
    },
    {
        "file_keyword": "2025-2026",
        "sheet": "Sheet1",
        "release_year_col": "发布年度",
        "ranking_year_col": "排名年度",
        "subject_en_col": "学科英文",
        "subject_cn_col": "学科中文",
        "university_en_col": "外文名称",
        "university_cn_col": "中文名称",
        "rank_col": "国际排名",
        "score_col": "总得分",
        "indicator_columns": {
            "全球学术声誉排名": "全球学术声誉排名",
            "地区学术声誉排名": "地区学术声誉排名",
            "出版物排名": "出版物排名",
            "图书排名": "图书排名",
            "会议排名": "会议排名",
            "标准化论文引用影响指数排名": "标准化论文引用影响指数排名",
            "总被引频次排名": "总被引频次排名",
            "被引用最多的10%的出版物数量排名": "被引用最多的10%的出版物数量排名",
            "总被引率占总被引文献的10%排名": "总被引率占总被引文献的10%排名",
            "具有国际合作出版物的比例排名": "具有国际合作出版物的比例排名",
            "国际合作排名": "国际合作排名",
            "排名前1%的高被引论文数量排名": "排名前1%的高被引论文数量排名",
            "前1%的高被引论文占论文总数的百分比排名": "前1%的高被引论文占论文总数的百分比排名",
        },
    },
    {
        "file_keyword": "20260616",
        "sheet": "数据",
        "release_year_col": "发布年度",
        "ranking_year_col": "排名年度",
        "subject_en_col": "学科英文",
        "subject_cn_col": "学科中文",
        "university_en_col": "外文名称",
        "university_cn_col": "中文名称",
        "rank_col": "国际排名",
        "score_col": "总得分",
        "indicator_columns": {
            "全球学术声誉排名": "全球学术声誉排名",
            "地区学术声誉排名": "地区学术声誉排名",
            "出版物排名": "出版物排名",
            "图书排名": "图书排名",
            "会议排名": "会议排名",
            "标准化论文引用影响指数排名": "标准化论文引用影响指数排名",
            "总被引频次排名": "总被引频次排名",
            "被引用最多的10%的出版物数量排名": "被引用最多的10%的出版物数量排名",
            "总被引率占总被引文献的10%排名": "总被引率占总被引文献的10%排名",
            "具有国际合作出版物的比例排名": "具有国际合作出版物的比例排名",
            "国际合作排名": "国际合作排名",
            "排名前1%的高被引论文数量排名": "排名前1%的高被引论文数量排名",
            "前1%的高被引论文占论文总数的百分比排名": "前1%的高被引论文占论文总数的百分比排名",
        },
    },
]


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return "" if text.lower() == "nan" else text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def parse_year(value: Any, default: int | None = None) -> int | None:
    text = clean_text(value)
    match = re.search(r"20\d{2}", text)
    if match:
        return int(match.group(0))
    try:
        number = int(float(text))
        return number if 1900 <= number <= 2100 else default
    except Exception:
        return default


def parse_numeric(value: Any) -> float | None:
    text = clean_text(value).replace("#", "").replace("=", "").replace(",", "")
    if not text or text in {"-", "NA", "N/A"}:
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    if "-" in text and len(numbers) >= 2:
        return (float(numbers[0]) + float(numbers[1])) / 2
    return float(numbers[0])


def source_file_for(keyword: str) -> Path:
    matches = [path for path in DATA_DIR.glob("*.xlsx") if keyword in path.name]
    if not matches:
        raise FileNotFoundError(f"未找到 US News 源文件: {keyword}")
    return sorted(matches, key=lambda path: path.name)[0]


def is_tongji_row(row: pd.Series, cn_col: str, en_col: str) -> bool:
    cn = clean_text(row.get(cn_col)) if cn_col else ""
    en = clean_text(row.get(en_col)) if en_col else ""
    return "同济" in cn or normalize_key(en) == "tongjiuniversity"


def build_long_rows() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for config in SOURCE_CONFIGS:
        source_file = source_file_for(config["file_keyword"])
        df = pd.read_excel(source_file, sheet_name=config["sheet"], dtype=object).fillna("")
        df.columns = [clean_text(column) for column in df.columns]
        for idx, row in df.iterrows():
            if not is_tongji_row(row, config.get("university_cn_col", ""), config.get("university_en_col", "")):
                continue
            subject_cn = clean_text(row.get(config.get("subject_cn_col", ""))) if config.get("subject_cn_col") else ""
            subject_en = clean_text(row.get(config.get("subject_en_col", ""))) if config.get("subject_en_col") else ""
            subject_raw = subject_cn or subject_en
            release_year = parse_year(row.get(config.get("release_year_col", "")), config.get("release_year"))
            ranking_year = parse_year(row.get(config.get("ranking_year_col", "")), config.get("ranking_year"))
            base = {
                "ranking_source": "US News",
                "release_year": release_year,
                "ranking_year": ranking_year,
                "ranking_subject_raw": subject_raw,
                "ranking_subject_norm": normalize_key(subject_raw),
                "ranking_subject_en": subject_en,
                "ranking_subject_en_norm": normalize_key(subject_en),
                "university_name_cn": clean_text(row.get(config.get("university_cn_col", ""))),
                "university_name_en": clean_text(row.get(config.get("university_en_col", ""))),
                "world_rank_raw": clean_text(row.get(config["rank_col"])),
                "world_rank_midpoint": parse_numeric(row.get(config["rank_col"])),
                "source_file": source_file.name,
                "source_sheet": config["sheet"],
                "source_row": int(idx) + 2,
            }
            score_value = clean_text(row.get(config["score_col"]))
            if score_value:
                rows.append(
                    {
                        **base,
                        "indicator_name": "总得分",
                        "indicator_norm": normalize_key("总得分"),
                        "metric_type": "score",
                        "indicator_value": score_value,
                        "indicator_value_num": parse_numeric(score_value),
                    }
                )
            for source_column, indicator_name in config["indicator_columns"].items():
                if source_column not in df.columns:
                    continue
                value = clean_text(row.get(source_column))
                if not value:
                    continue
                rows.append(
                    {
                        **base,
                        "indicator_name": indicator_name,
                        "indicator_norm": normalize_key(indicator_name),
                        "metric_type": "rank",
                        "indicator_value": value,
                        "indicator_value_num": parse_numeric(value),
                    }
                )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["ranking_subject_norm", "ranking_year", "indicator_name"]).reset_index(drop=True)


def write_outputs(long_df: pd.DataFrame) -> dict[str, Any]:
    EXTERNAL_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    EXTERNAL_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(OUTPUT_LONG_CSV, index=False, encoding="utf-8-sig")
    wide = (
        long_df.pivot_table(
            index=["ranking_subject_raw", "ranking_subject_en", "indicator_name", "metric_type"],
            columns="ranking_year",
            values="indicator_value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    wide.to_csv(OUTPUT_WIDE_CSV, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": now_text(),
        "long_rows": int(len(long_df)),
        "wide_rows": int(len(wide)),
        "subject_count": int(long_df["ranking_subject_norm"].nunique()) if not long_df.empty else 0,
        "years": sorted(int(year) for year in pd.to_numeric(long_df["ranking_year"], errors="coerce").dropna().unique()),
        "subjects": sorted(long_df["ranking_subject_raw"].dropna().unique().tolist()),
        "outputs": {
            "long": str(OUTPUT_LONG_CSV),
            "wide": str(OUTPUT_WIDE_CSV),
        },
    }
    OUTPUT_SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    lines = [
        "# US News 同济分项指标历史共性补充",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- long_rows: {summary['long_rows']}",
        f"- wide_rows: {summary['wide_rows']}",
        f"- subject_count: {summary['subject_count']}",
        f"- years: {', '.join(str(year) for year in summary['years'])}",
        "",
        "## 输出",
        "",
        f"- `{OUTPUT_LONG_CSV}`",
        f"- `{OUTPUT_WIDE_CSV}`",
        "",
        "## 说明",
        "",
        "- 数据来自本地已有 US News 学科排名明细 Excel，不是单独为某一学科手工录入。",
        "- 2021 文件只有总分/总排名，缺少分项指标列，因此仅纳入总得分，不生成分项指标排名。",
        "- 该补充文件按 US News 原始学科口径保存，后续 subject agent 通过学科 alias 自动筛选目标学科。",
    ]
    OUTPUT_SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    long_df = build_long_rows()
    summary = write_outputs(long_df)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
