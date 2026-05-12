from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CWTS_TRADITIONAL_XLSX = (
    PROJECT_ROOT
    / "external_data"
    / "raw"
    / "cwts_leiden_traditional_2025"
    / "CWTS Leiden Ranking Traditional Edition 2025.xlsx"
)
PROCESSED_ROOT = PROJECT_ROOT / "external_data" / "processed"
REPORT_ROOT = PROJECT_ROOT / "external_data" / "reports"
DIM_SUBJECT_CSV = PROJECT_ROOT / "processed" / "dim_subject.csv"
TARGET_COUNTRY = "China"
TARGET_UNIVERSITY_EN = "Tongji University"
FULL_COUNTING = 0

CWTS_FIELD_SLUGS = {
    "All sciences": "all_sciences",
    "Biomedical and health sciences": "biomedical_health",
    "Life and earth sciences": "life_earth",
    "Mathematics and computer science": "math_computer",
    "Physical sciences and engineering": "physical_engineering",
    "Social sciences and humanities": "social_humanities",
}

METRIC_COLUMNS = [
    "University",
    "ROR_ID",
    "Country",
    "Field",
    "Period",
    "Frac_counting",
    "P",
    "TCS",
    "TNCS",
    "MCS",
    "MNCS",
    "P_top_1",
    "P_top_5",
    "P_top_10",
    "PP_top_1",
    "PP_top_5",
    "PP_top_10",
    "P_int_collab",
    "PP_int_collab",
    "P_collab",
    "PP_collab",
]

RANK_METRICS = [
    "P",
    "TCS",
    "TNCS",
    "MCS",
    "MNCS",
    "P_top_1",
    "P_top_5",
    "P_top_10",
    "PP_top_1",
    "PP_top_5",
    "PP_top_10",
    "P_int_collab",
    "PP_int_collab",
    "P_collab",
    "PP_collab",
]


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def normalize_subject_code(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\.0$", "", text)
    return text.zfill(4)


def period_sort_key(value: Any) -> tuple[int, int]:
    numbers = [int(item) for item in re.findall(r"\d{4}", clean_text(value))]
    if not numbers:
        return (0, 0)
    return (max(numbers), min(numbers))


def read_cwts_results() -> pd.DataFrame:
    return pd.read_excel(CWTS_TRADITIONAL_XLSX, sheet_name="Results", usecols=METRIC_COLUMNS)


def read_university_name_crosswalk() -> pd.DataFrame:
    rows = []
    for file_name in ["fact_ranking.csv", "fact_ranking_indicator.csv"]:
        path = PROJECT_ROOT / "processed" / file_name
        if not path.exists():
            continue
        header = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns.tolist()
        if "university_name_cn" in header and "university_name_en" in header:
            usecols = ["university_name_cn", "university_name_en"]
        elif "university_name" in header and "university_name_en" in header:
            usecols = ["university_name", "university_name_en"]
        else:
            continue
        frame = pd.read_csv(path, usecols=usecols, encoding="utf-8-sig", engine="python", on_bad_lines="skip")
        frame.columns = ["university_name_cn", "university_name_en"]
        rows.append(frame)
    if not rows:
        return pd.DataFrame(columns=["university_name_en_key", "university_name_cn"])
    crosswalk = pd.concat(rows, ignore_index=True)
    crosswalk = crosswalk.dropna(subset=["university_name_en"]).drop_duplicates()
    crosswalk["university_name_en_key"] = crosswalk["university_name_en"].astype(str).str.lower().str.strip()
    crosswalk = crosswalk.drop_duplicates(subset=["university_name_en_key"], keep="first")
    return crosswalk[["university_name_en_key", "university_name_cn"]]


def add_cn_name(frame: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["university_name_en_key"] = result["University"].astype(str).str.lower().str.strip()
    if not crosswalk.empty:
        result = result.merge(crosswalk, how="left", on="university_name_en_key")
    else:
        result["university_name_cn"] = ""
    return result.drop(columns=["university_name_en_key"])


def add_metric_ranks(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for metric in RANK_METRICS:
        if metric in result.columns:
            result[f"{metric}_china_field_rank"] = (
                pd.to_numeric(result[metric], errors="coerce")
                .rank(ascending=False, method="min", na_option="bottom")
                .astype("Int64")
            )
    return result


def choose_cwts_field(subject: pd.Series) -> dict[str, str]:
    code = normalize_subject_code(subject.get("ministry_subject_code"))
    name = clean_text(subject.get("ministry_subject_name"))
    short_name = clean_text(subject.get("subject_short_name"))
    category = clean_text(subject.get("ministry_category_name"))
    text = f"{name} {short_name} {category}"

    keyword_rules = [
        (
            "Biomedical and health sciences",
            ["医学", "临床", "口腔", "公共卫生", "护理", "药", "中医", "基础医学", "生物医学"],
            "医学/健康关键词",
            "high",
        ),
        (
            "Mathematics and computer science",
            ["数学", "统计", "计算机", "软件", "网络空间", "人工智能", "智能科学", "数据科学"],
            "数学/计算机关键词",
            "high",
        ),
        (
            "Life and earth sciences",
            ["生物", "生态", "农", "林", "水产", "食品", "环境", "地理", "地质", "海洋", "大气"],
            "生命/地球/环境关键词",
            "medium",
        ),
        (
            "Physical sciences and engineering",
            [
                "物理",
                "化学",
                "力学",
                "机械",
                "材料",
                "土木",
                "建筑",
                "交通",
                "电气",
                "电子",
                "信息",
                "控制",
                "仪器",
                "能源",
                "航空",
                "船舶",
                "矿",
                "冶金",
                "纺织",
                "测绘",
                "水利",
                "工程",
            ],
            "理工/工程关键词",
            "medium",
        ),
        (
            "Social sciences and humanities",
            ["哲学", "经济", "法", "政治", "社会", "教育", "文学", "外国语", "新闻", "历史", "管理", "艺术", "设计"],
            "社科/人文关键词",
            "medium",
        ),
    ]
    for field, keywords, rationale, confidence in keyword_rules:
        if any(keyword in text for keyword in keywords):
            return {
                "cwts_field": field,
                "cwts_field_slug": CWTS_FIELD_SLUGS[field],
                "mapping_confidence": confidence,
                "mapping_rationale": rationale,
            }

    category_code = code[:2]
    category_defaults = {
        "01": "Social sciences and humanities",
        "02": "Social sciences and humanities",
        "03": "Social sciences and humanities",
        "04": "Social sciences and humanities",
        "05": "Social sciences and humanities",
        "06": "Social sciences and humanities",
        "07": "Physical sciences and engineering",
        "08": "Physical sciences and engineering",
        "09": "Life and earth sciences",
        "10": "Biomedical and health sciences",
        "12": "Social sciences and humanities",
        "13": "Social sciences and humanities",
        "14": "Physical sciences and engineering",
    }
    field = category_defaults.get(category_code, "All sciences")
    return {
        "cwts_field": field,
        "cwts_field_slug": CWTS_FIELD_SLUGS[field],
        "mapping_confidence": "low" if field == "All sciences" else "category_default",
        "mapping_rationale": "按教育部学科门类默认映射",
    }


def build_subject_field_crosswalk(latest_full: pd.DataFrame) -> pd.DataFrame:
    dim = pd.read_csv(DIM_SUBJECT_CSV, encoding="utf-8-sig")
    rows = []
    field_counts = latest_full.groupby("Field").size().to_dict()
    tongji_fields = set(latest_full[latest_full["University"] == TARGET_UNIVERSITY_EN]["Field"].astype(str))
    for _, subject in dim.iterrows():
        mapping = choose_cwts_field(subject)
        field = mapping["cwts_field"]
        rows.append(
            {
                "subject_id": subject.get("subject_id"),
                "ministry_subject_code": normalize_subject_code(subject.get("ministry_subject_code")),
                "ministry_subject_name": subject.get("ministry_subject_name"),
                "ministry_category_name": subject.get("ministry_category_name"),
                **mapping,
                "china_latest_rows_in_field": int(field_counts.get(field, 0)),
                "tongji_has_field_record": field in tongji_fields,
                "proxy_scope_note": "CWTS 为五大宽领域代理，不是严格一级学科口径。",
            }
        )
    return pd.DataFrame(rows)


def write_subject_specific_legacy_outputs(latest_full: pd.DataFrame, crosswalk: pd.DataFrame) -> None:
    math_computer = latest_full[latest_full["Field"] == "Mathematics and computer science"].copy()
    math_computer = add_metric_ranks(math_computer)
    math_computer.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_china_math_computer_latest.csv",
        index=False,
        encoding="utf-8-sig",
    )

    all_sciences = latest_full[latest_full["Field"] == "All sciences"].copy()
    all_sciences = add_metric_ranks(all_sciences)
    all_sciences.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_china_all_sciences_latest.csv",
        index=False,
        encoding="utf-8-sig",
    )

    field = "Mathematics and computer science"
    math_subjects = set(crosswalk[crosswalk["cwts_field"] == field]["ministry_subject_code"].astype(str))
    legacy = math_computer.copy()
    legacy["matched_current_math_peer"] = legacy["University"].eq(TARGET_UNIVERSITY_EN)
    legacy["proxy_subject_codes"] = ";".join(sorted(math_subjects))
    legacy.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_math_peer_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )


def main() -> None:
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    cwts = read_cwts_results()
    crosswalk_names = read_university_name_crosswalk()
    periods = sorted(cwts["Period"].dropna().unique(), key=period_sort_key)
    latest_period = periods[-1]

    latest_full = cwts[
        (cwts["Country"] == TARGET_COUNTRY)
        & (cwts["Period"] == latest_period)
        & (cwts["Frac_counting"] == FULL_COUNTING)
    ].copy()
    latest_full = add_cn_name(latest_full, crosswalk_names)
    latest_full.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_china_latest_full_count.csv",
        index=False,
        encoding="utf-8-sig",
    )
    latest_full.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_china_latest_all_fields.csv",
        index=False,
        encoding="utf-8-sig",
    )

    field_outputs = {}
    for field, slug in CWTS_FIELD_SLUGS.items():
        field_df = latest_full[latest_full["Field"] == field].copy()
        field_df = add_metric_ranks(field_df)
        output_path = PROCESSED_ROOT / f"cwts_traditional_2025_china_field_{slug}_latest.csv"
        field_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        field_outputs[field] = {
            "slug": slug,
            "rows": int(len(field_df)),
            "path": str(output_path.relative_to(PROJECT_ROOT)),
        }

    tongji_history = cwts[cwts["University"] == TARGET_UNIVERSITY_EN].copy()
    tongji_history.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_tongji_all_fields_history.csv",
        index=False,
        encoding="utf-8-sig",
    )
    tongji_history.to_csv(
        PROCESSED_ROOT / "cwts_traditional_2025_tongji_history.csv",
        index=False,
        encoding="utf-8-sig",
    )

    subject_crosswalk = build_subject_field_crosswalk(latest_full)
    subject_crosswalk.to_csv(
        PROCESSED_ROOT / "cwts_subject_field_crosswalk.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_subject_specific_legacy_outputs(latest_full, subject_crosswalk)

    summary = {
        "generated_at": now_text(),
        "source_file": str(CWTS_TRADITIONAL_XLSX),
        "latest_period": clean_text(latest_period),
        "china_latest_full_count_rows": int(len(latest_full)),
        "tongji_history_rows": int(len(tongji_history)),
        "field_outputs": field_outputs,
        "subject_crosswalk_rows": int(len(subject_crosswalk)),
        "subject_crosswalk_confidence": subject_crosswalk["mapping_confidence"].value_counts().to_dict(),
        "sources": [
            "https://zenodo.org/records/17473109",
            "https://traditional.leidenranking.com/information/fields",
        ],
        "notes": [
            "CWTS Traditional 2025 is a public Web of Science based bibliometric proxy.",
            "The five CWTS fields are broad fields. They can close paper-metric gaps only as documented proxies.",
            "Do not label MNCS/MCS as InCites CNCI. Keep source_trace wording explicit.",
        ],
    }
    (REPORT_ROOT / "cwts_processing_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    report_lines = [
        "# CWTS Common Paper-Metric Supplement",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- latest_period: {summary['latest_period']}",
        f"- china_latest_full_count_rows: {summary['china_latest_full_count_rows']}",
        f"- subject_crosswalk_rows: {summary['subject_crosswalk_rows']}",
        "",
        "## Outputs",
        "",
        "- `external_data/processed/cwts_subject_field_crosswalk.csv`",
        "- `external_data/processed/cwts_traditional_2025_china_latest_all_fields.csv`",
        "- `external_data/processed/cwts_traditional_2025_china_field_<field>_latest.csv`",
        "- `external_data/processed/cwts_traditional_2025_tongji_all_fields_history.csv`",
        "",
        "## Judgment",
        "",
        "This supplement converts the earlier math-only CWTS bridge into a reusable broad-field proxy. It is suitable for paper output, citation, highly cited paper, and collaboration charts when the report accepts a documented CWTS wide-field proxy.",
    ]
    (REPORT_ROOT / "cwts_processing_summary.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
