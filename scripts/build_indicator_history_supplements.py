from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
PROCESSED_ROOT = PROJECT_ROOT / "external_data" / "processed"
REPORT_ROOT = PROJECT_ROOT / "external_data" / "reports"

TARGET_UNIVERSITY_CN = "同济大学"
TARGET_UNIVERSITY_EN_KEY = "tongji"
TARGET_SUBJECT_CN = "数学"
TARGET_SUBJECT_EN_KEY = "mathematics"

ARWU_SOURCES = [
    {
        "year": 2023,
        "path": DATA_ROOT / "2023年软科世界一流学科排名-20231030.xlsx",
        "sheet": "名单",
        "university_col": "中文名称",
        "subject_col": "学科领域",
        "rank_col": "国际排名",
        "score_col": "总得分",
        "indicator_cols": ["重要期刊论文数", "论文标准化影响力", "国际合作论文比例", "顶尖期刊论文数", "教师获权威奖项数"],
    },
    {
        "year": 2024,
        "path": DATA_ROOT / "2024年软科世界一流学科排名-20241111.xlsx",
        "sheet": "所有高校",
        "university_col": "中文校名",
        "subject_col": "学科领域",
        "rank_col": "排名",
        "score_col": "总分",
        "indicator_cols": ["世界一流教师", "世界一流成果", "高水平研究成果", "科研影响力", "国际合作"],
    },
    {
        "year": 2025,
        "path": DATA_ROOT / "2025年软科世界一流学科排名20251118.xlsx",
        "sheet": "数据",
        "university_col": "学校名称",
        "subject_col": "学科名称",
        "rank_col": "国际排名",
        "score_col": "总得分",
        "indicator_cols": ["高水平研究成果/重要期刊论文数", "科研影响力/论文标准化影响力", "国际合作/国际合作论文比例", "世界一流成果", "世界一流教师"],
    },
]

USNEWS_SOURCES = [
    {
        "year": 2022,
        "path": DATA_ROOT / "2022US News世界学科排名20211026.xlsx",
        "sheet": "Sheet2",
        "university_cols": ["university", "university_zh"],
        "subject_cols": ["subject"],
        "rank_col": "subjectrank",
        "score_col": "overallscore",
        "indicator_cols": [
            "globalresearchreputation",
            "regionalresearchreputation",
            "publications",
            "books",
            "conferences",
            "normalizedcitationimpact",
            "totalcitations",
            "numberofpublicationsthatareamongthe10mostcited",
            "percentageoftotalpublicationsthatareamongthe10mostcited",
            "internationalcollaborationrelativetocountry",
            "internationalcollaboration",
            "numberofhighlycitedpapersthatareamongthetop1mostcited",
            "percentageofhighlycitedpapersthatareamongthetop1mostcited",
        ],
    },
    {
        "year": 2023,
        "path": DATA_ROOT / "2023US News世界学科排名20221026.xlsx",
        "sheet": "sheet",
        "university_cols": ["Name"],
        "subject_cols": ["Subject"],
        "rank_col": "Rank",
        "score_col": "OVERALL_SCORE",
        "indicator_cols": [
            "Global_Research_Reputatio",
            "Regional_Research_Reputation",
            "Publications",
            "Books",
            "Conferences",
            "Normalized_Citation_Impact",
            "Total_Citations",
            "Publications_10_Percent",
            "Total_Publications_10_Percent",
            "Relative_To_Country",
            "International_Collaboration",
        ],
    },
    {
        "year": 2025,
        "path": DATA_ROOT / "2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx",
        "sheet": "全球排名",
        "university_cols": ["名称", "中文名称"],
        "subject_cols": ["学科", "学科中文"],
        "rank_col": "世界排名",
        "score_col": "总得分",
        "indicator_cols": [
            "出版物排名",
            "会议排名",
            "标准化论文引用影响指数排名",
            "总被引频次排名",
            "被引用最多的10%的出版物数量排名",
            "总被引率占总被引文献的10%排名",
            "具有国际合作出版物的比例排名",
            "国际合作排名",
            "排名前1%的高被引论文数量排名",
            "在被引用最多的前1%的论文占总论文的百分比排名",
            "全球学术声誉排名",
            "地区学术声誉排名",
        ],
    },
    {
        "year": 2026,
        "path": DATA_ROOT / "2025-2026年度US News世界学科排名20251124.xlsx",
        "sheet": "Sheet1",
        "university_cols": ["外文名称", "中文名称"],
        "subject_cols": ["学科英文", "学科中文"],
        "rank_col": "国际排名",
        "score_col": "总得分",
        "indicator_cols": [
            "全球学术声誉排名",
            "地区学术声誉排名",
            "出版物排名",
            "图书排名",
            "标准化论文引用影响指数排名",
            "总被引频次排名",
            "被引用最多的10%的出版物数量排名",
            "总被引率占总被引文献的10%排名",
            "具有国际合作出版物的比例排名",
            "国际合作排名",
            "排名前1%的高被引论文数量排名",
            "在被引用最多的前1%的论文占总论文的百分比排名",
        ],
    },
]


USNEWS_SOFT_SCIENCE_MATH_WEIGHT_CANDIDATE = [
    ("全球研究声誉", 12.5),
    ("区域研究声誉", 12.5),
    ("出版物", 17.5),
    ("图书", None),
    ("会议", None),
    ("标准化引用影响", 7.5),
    ("总引用次数", 12.5),
    ("被引用次数最多的 10% 的出版物数量", 12.5),
    ("被引用次数最多的 10% 的出版物占总出版物的百分比", 5.0),
    ("在各自领域中被引用次数最多的前 1% 的高被引论文数量", 5.0),
    ("被引用次数最多的前 1% 的论文占总出版物的百分比", 5.0),
    ("国际合作——相对于国家", 5.0),
    ("国际合作", 5.0),
]


def text_contains_any(value: object, keys: list[str]) -> bool:
    text = str(value).lower()
    return any(key.lower() in text for key in keys)


def extract_arwu() -> pd.DataFrame:
    rows = []
    for source in ARWU_SOURCES:
        if not source["path"].exists():
            continue
        df = pd.read_excel(source["path"], sheet_name=source["sheet"])
        mask = (
            df[source["university_col"]].astype(str).str.contains(TARGET_UNIVERSITY_CN, regex=False, na=False)
            & df[source["subject_col"]].astype(str).str.contains(TARGET_SUBJECT_CN, regex=False, na=False)
        )
        for _, row in df[mask].iterrows():
            base = {
                "ranking_source": "软科",
                "ranking_year": source["year"],
                "university_name_cn": TARGET_UNIVERSITY_CN,
                "subject_name": TARGET_SUBJECT_CN,
                "rank_raw": row.get(source["rank_col"]),
                "total_score": row.get(source["score_col"]),
                "source_file": source["path"].name,
                "source_sheet": source["sheet"],
            }
            for indicator in source["indicator_cols"]:
                rows.append({**base, "indicator_name": indicator, "indicator_value": row.get(indicator)})
    return pd.DataFrame(rows)


def extract_usnews() -> pd.DataFrame:
    rows = []
    for source in USNEWS_SOURCES:
        if not source["path"].exists():
            continue
        df = pd.read_excel(source["path"], sheet_name=source["sheet"])
        university_mask = pd.Series(False, index=df.index)
        for col in source["university_cols"]:
            if col in df.columns:
                university_mask |= df[col].apply(lambda value: text_contains_any(value, [TARGET_UNIVERSITY_CN, TARGET_UNIVERSITY_EN_KEY]))
        subject_mask = pd.Series(False, index=df.index)
        for col in source["subject_cols"]:
            if col in df.columns:
                subject_mask |= df[col].apply(lambda value: text_contains_any(value, [TARGET_SUBJECT_CN, TARGET_SUBJECT_EN_KEY]))
        for _, row in df[university_mask & subject_mask].iterrows():
            base = {
                "ranking_source": "US News",
                "ranking_year": source["year"],
                "university_name_cn": TARGET_UNIVERSITY_CN,
                "university_name_en": "Tongji University",
                "subject_name": TARGET_SUBJECT_CN,
                "rank_raw": row.get(source["rank_col"]),
                "total_score": row.get(source["score_col"]),
                "source_file": source["path"].name,
                "source_sheet": source["sheet"],
            }
            for indicator in source["indicator_cols"]:
                if indicator in df.columns:
                    rows.append({**base, "indicator_name": indicator, "indicator_value": row.get(indicator)})
    return pd.DataFrame(rows)


def build_usnews_weight_candidate() -> pd.DataFrame:
    rows = []
    for indicator, weight in USNEWS_SOFT_SCIENCE_MATH_WEIGHT_CANDIDATE:
        rows.append(
            {
                "ranking_source": "US News",
                "ranking_subject_or_area": "数学",
                "ranking_subject_norm": "数学",
                "indicator_name": indicator,
                "weight_percent": weight,
                "evidence_status": "candidate_indirect",
                "source_basis": "本地权重表将数学列在 US News 软科学分组下但权重行为空；公开历史方法表显示 Mathematics 属 soft sciences。该候选权重沿用本地软科学中 Business & Economics 行的 2025 权重结构。",
                "do_not_auto_merge": True,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    arwu = extract_arwu()
    usnews = extract_usnews()
    weights = build_usnews_weight_candidate()

    arwu_path = PROCESSED_ROOT / "local_arwu_tongji_math_indicator_history.csv"
    usnews_path = PROCESSED_ROOT / "local_usnews_tongji_math_indicator_history.csv"
    weight_path = PROCESSED_ROOT / "usnews_math_weight_candidate_indirect.csv"
    arwu.to_csv(arwu_path, index=False, encoding="utf-8-sig")
    usnews.to_csv(usnews_path, index=False, encoding="utf-8-sig")
    weights.to_csv(weight_path, index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "arwu_indicator_rows": int(len(arwu)),
        "arwu_years": sorted(arwu["ranking_year"].dropna().unique().tolist()) if not arwu.empty else [],
        "usnews_indicator_rows": int(len(usnews)),
        "usnews_years": sorted(usnews["ranking_year"].dropna().unique().tolist()) if not usnews.empty else [],
        "usnews_weight_candidate_rows": int(len(weights)),
        "judgment": {
            "arwu_history": "can_recover_from_local_raw_files" if len(arwu["ranking_year"].dropna().unique()) >= 2 else "still_partial",
            "usnews_history": "can_recover_from_local_raw_files" if len(usnews["ranking_year"].dropna().unique()) >= 2 else "still_partial",
            "usnews_weight": "candidate_only_requires_human_acceptance_or_official_source",
        },
    }
    (REPORT_ROOT / "indicator_history_supplement_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    lines = [
        "# Indicator History Supplement Summary",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- arwu_indicator_rows: {summary['arwu_indicator_rows']}",
        f"- arwu_years: {summary['arwu_years']}",
        f"- usnews_indicator_rows: {summary['usnews_indicator_rows']}",
        f"- usnews_years: {summary['usnews_years']}",
        f"- usnews_weight_candidate_rows: {summary['usnews_weight_candidate_rows']}",
        "",
        "## Judgment",
        "",
        "- 软科同济数学分项历史可从本地 2023/2025 原始表恢复；2024 原表未找到同济数学记录，应按未上榜/未入表记录为缺测。",
        "- US News 同济数学分项历史可从本地 2022/2023/2025/2026 原始表恢复，2021 原表只有总分/排名，不含完整分项。",
        "- US News 数学权重目前只能生成候选间接表，不能自动并入正式权重事实表。",
        "",
        "## Files",
        "",
        f"- `{arwu_path}`",
        f"- `{usnews_path}`",
        f"- `{weight_path}`",
    ]
    (REPORT_ROOT / "indicator_history_supplement_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
