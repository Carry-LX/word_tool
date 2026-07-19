from __future__ import annotations

import csv
import html
import json
import math
import re
import time
import traceback
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from PIL import Image, ImageChops, ImageDraw, ImageFont

import agent_runtime
import ranking_public_supplements as public_supplements


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = agent_runtime.load_runtime_profile()
SUBJECT_REQUEST = agent_runtime.load_subject_request(RUNTIME_PROFILE)
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
EXTERNAL_DATA_DIR = PROJECT_DIR / "external_data"
EXTERNAL_PROCESSED_DIR = EXTERNAL_DATA_DIR / "processed"
EXTERNAL_REPORT_DIR = EXTERNAL_DATA_DIR / "reports"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"
THE_RANKING_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_ranking_area_crosswalk.json"
INDICATOR_GROUP_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "indicator_group_crosswalk.json"
CWTS_MATH_PEER_CSV = EXTERNAL_PROCESSED_DIR / "cwts_traditional_2025_math_peer_coverage.csv"
CWTS_SUBJECT_FIELD_CROSSWALK_CSV = EXTERNAL_PROCESSED_DIR / "cwts_subject_field_crosswalk.csv"
CWTS_CHINA_ALL_FIELDS_CSV = EXTERNAL_PROCESSED_DIR / "cwts_traditional_2025_china_latest_all_fields.csv"
WOS_SUBJECT_PAPER_CSV = EXTERNAL_PROCESSED_DIR / "wos_37_university_subject_paper_metrics_20260511.csv"
USNEWS_HISTORY_CSV = EXTERNAL_PROCESSED_DIR / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"
ARWU_HISTORY_CSV = EXTERNAL_PROCESSED_DIR / "local_arwu_tongji_math_indicator_history.csv"
ARWU_PUBLIC_TONGJI_LONG_CSV = EXTERNAL_PROCESSED_DIR / "arwu_gras_public_tongji_history_2023_2025_long.csv"
USNEWS_WEIGHT_CANDIDATE_CSV = EXTERNAL_PROCESSED_DIR / "usnews_math_weight_candidate_indirect.csv"
UNIVERSITY_PROVINCE_CSV = PROCESSED_DIR / "dim_university_province.csv"
QS_USNEWS_RANKING_FILE = "2021-2026年中国内地QS&US世界学科排名数据（20260603更新）.xlsx"

RANKING_SOURCES = agent_runtime.normalize_ranking_sources(
    SUBJECT_REQUEST.get("ranking_sources"),
    agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", agent_runtime.SUPPORTED_RANKING_SOURCES),
)
TOP_RANK_MIDPOINT = 200
MAIN_WORD_PEER_TABLE_MAX_ROWS = 24
APPENDIX_WORD_MAX_ROWS = 36
WEIGHT_TREE_MAX_PARENTS = 5
WEIGHT_TREE_MAX_LEAVES_PER_PARENT = 5
SOURCE_COLORS = {
    "软科": "#C64B46",
    "QS": "#315D9C",
    "US News": "#3C8D5A",
    "THE": "#7B5CA8",
}
GROUP_COLORS = {
    "声誉": "#5B8DEF",
    "科研/论文": "#47A878",
    "国际化/合作": "#D68A35",
    "教学/环境": "#7A60B0",
    "人才/奖项": "#C85D7B",
    "产业/转化": "#6B7280",
    "其他": "#9AA4B2",
}


def subject_code(subject: dict[str, Any]) -> str:
    return clean_text(subject.get("target_subject_code") or subject.get("ministry_subject_code"))


def is_math_subject(subject: dict[str, Any]) -> bool:
    return subject_code(subject) == "0701" or clean_text(subject.get("subject_id")) == "subject_0701"


def supports_cwts_math_computer_proxy(subject: dict[str, Any]) -> bool:
    return subject_code(subject) in {"0701", "0811", "0812", "0835", "1405"}


def cwts_field_for_subject(subject: dict[str, Any]) -> dict[str, Any]:
    code = subject_code(subject)
    crosswalk = read_external_csv(CWTS_SUBJECT_FIELD_CROSSWALK_CSV)
    if not crosswalk.empty and "ministry_subject_code" in crosswalk.columns:
        matches = crosswalk[crosswalk["ministry_subject_code"].astype(str).str.zfill(4) == code]
        if not matches.empty:
            return matches.iloc[0].to_dict()
    if supports_cwts_math_computer_proxy(subject):
        return {
            "cwts_field": "Mathematics and computer science",
            "cwts_field_slug": "math_computer",
            "mapping_confidence": "legacy",
            "mapping_rationale": "legacy math/computer subject code rule",
        }
    return {
        "cwts_field": "",
        "cwts_field_slug": "",
        "mapping_confidence": "missing",
        "mapping_rationale": "missing CWTS subject-field crosswalk",
    }


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def clean_rank_display(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"^[#=＝]+\s*(?=\d)", "", text).strip()
    return re.sub(r"\s+", " ", text)


def display_ranking_source(source: Any) -> str:
    text = clean_text(source)
    return "U.S. News" if text in {"US News", "U.S. News", "U.S.News"} else text


def ordered_unique(values: list[Any]) -> list[str]:
    seen = set()
    rows: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def valid_mapping_value(value: Any) -> str:
    return public_supplements.valid_mapping_value(value)


def single_mapping_value(value: Any) -> str:
    text = valid_mapping_value(value)
    if not text or re.search(r"[\n\r,;，、；/]+", text):
        return ""
    return text


def canonical_the_area(value: Any) -> str:
    area = valid_mapping_value(value)
    if area and THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        return valid_mapping_value(crosswalk.get(area, area))
    return area


def the_ranking_area_candidates(value: Any) -> list[str]:
    area = valid_mapping_value(value)
    if not area:
        return []
    values: list[Any] = [area, canonical_the_area(area)]
    if THE_RANKING_AREA_CROSSWALK_JSON.exists():
        crosswalk = json.loads(THE_RANKING_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        for item in list(values):
            mapped = crosswalk.get(clean_text(item))
            if isinstance(mapped, list):
                values.extend(mapped)
            elif mapped:
                values.append(mapped)
    return ordered_unique([valid_mapping_value(item) for item in values])


def display_missing_label(value: str = "missing") -> str:
    labels = {
        "not_published": "\u672a\u53d1\u5e03",
        "not_listed": "\u672a\u4e0a\u699c",
        "not_measured": "\u7f3a\u6d4b",
    }
    return labels.get(value, "\u7f3a\u6d4b")


def canonical_indicator_name(source: str, indicator_name: Any) -> str:
    name = clean_text(indicator_name)
    key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", name.lower())
    arwu_map = {
        "q1": "\u9ad8\u8d28\u91cf\u7814\u7a76",
        "\u9ad8\u6c34\u5e73\u7814\u7a76\u6210\u679c\u91cd\u8981\u671f\u520a\u8bba\u6587\u6570": "\u9ad8\u8d28\u91cf\u7814\u7a76",
        "\u91cd\u8981\u671f\u520a\u8bba\u6587\u6570": "\u9ad8\u8d28\u91cf\u7814\u7a76",
        "highqualityresearch": "\u9ad8\u8d28\u91cf\u7814\u7a76",
        "cnci": "\u7814\u7a76\u5f71\u54cd",
        "\u79d1\u7814\u5f71\u54cd\u529b\u8bba\u6587\u6807\u51c6\u5316\u5f71\u54cd\u529b": "\u7814\u7a76\u5f71\u54cd",
        "\u8bba\u6587\u6807\u51c6\u5316\u5f71\u54cd\u529b": "\u7814\u7a76\u5f71\u54cd",
        "researchimpact": "\u7814\u7a76\u5f71\u54cd",
        "ic": "\u56fd\u9645\u5408\u4f5c",
        "\u56fd\u9645\u5408\u4f5c\u56fd\u9645\u5408\u4f5c\u8bba\u6587\u6bd4\u4f8b": "\u56fd\u9645\u5408\u4f5c",
        "\u56fd\u9645\u5408\u4f5c\u8bba\u6587\u6bd4\u4f8b": "\u56fd\u9645\u5408\u4f5c",
        "internationalcollaboration": "\u56fd\u9645\u5408\u4f5c",
        "top": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "\u4e16\u754c\u4e00\u6d41\u6210\u679c": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "\u9876\u5c16\u671f\u520a\u8bba\u6587\u6570": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "worldclassoutput": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "award": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
        "\u4e16\u754c\u4e00\u6d41\u6559\u5e08": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
        "\u6559\u5e08\u83b7\u6743\u5a01\u5956\u9879\u6570": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
        "worldclassfaculty": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
    }
    the_map = {
        "\u7bc7\u5747\u88ab\u5f15": "\u79d1\u7814\u8d28\u91cf",
        "\u7bc7\u5747\u88ab\u5f15\u6392\u540d": "\u79d1\u7814\u8d28\u91cf\u6392\u540d",
        "\u7814\u7a76": "\u79d1\u7814\u73af\u5883",
        "\u7814\u7a76\u6392\u540d": "\u79d1\u7814\u73af\u5883\u6392\u540d",
    }
    if source in {"ARWU", "\u8f6f\u79d1", "ARWU GRAS public web"}:
        return arwu_map.get(key, name)
    if source == "THE":
        return the_map.get(key, the_map.get(name, name))
    return name


def normalize_text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", clean_text(value).lower())


def peer_indicator_display_name(source: str, indicator_name: Any, rank_mode: bool) -> str:
    name = canonical_indicator_name(source, indicator_name)
    key = normalize_text_key(name)
    short_name_map = {
        "软科": {
            "世界一流成果": "一流成果",
            "世界一流教师": "一流师资",
            "国际合作国际合作论文比例": "国际合作",
            "科研影响力论文标准化影响力": "论文影响力",
            "高水平研究成果重要期刊论文数": "高水平成果",
        },
        "US News": {
            "会议排名": "会议",
            "具有国际合作出版物的比例排名": "国际合作比例",
            "出版物排名": "论文数量",
            "前1的高被引论文占论文总数的百分比排名": "高被引占比",
            "国际合作排名": "国际合作",
            "总被引率占总被引文献的10排名": "前10%高被引占比",
            "总被引频次排名": "总被引频次",
            "排名前1的高被引论文数量排名": "高被引论文数量",
            "标准化论文引用影响指数排名": "标准化引文影响",
            "被引用最多的10的出版物数量排名": "前10%高被引论文数",
        },
        "THE": {
            "商业收入排名": "产业收入",
            "国际化视野排名": "国际化",
            "教学排名": "教学",
            "科研环境排名": "科研环境",
            "科研质量排名": "科研质量",
        },
    }
    mapped = short_name_map.get(source, {}).get(key, "")
    if mapped:
        return mapped
    value = name
    replacements = [
        ("具有国际合作出版物的比例", "国际合作比例"),
        ("排名前1%的高被引论文数量", "高被引论文数量"),
        ("前1%的高被引论文占论文总数的百分比", "高被引占比"),
        ("标准化论文引用影响指数", "标准化引文影响"),
        ("被引用最多的10%的出版物数量", "前10%高被引论文数"),
        ("总被引率占总被引文献的10%", "前10%高被引占比"),
        ("国际合作/国际合作论文比例", "国际合作"),
        ("科研影响力/论文标准化影响力", "论文影响力"),
        ("高水平研究成果/重要期刊论文数", "高水平成果"),
        ("世界一流成果", "一流成果"),
        ("世界一流教师", "一流师资"),
        ("出版物", "论文"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    if rank_mode:
        value = value.replace("排名", "")
    return value[:12]


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
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


def ellipsize_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: float) -> str:
    if text_size(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    keep = text
    while keep and text_size(draw, keep + suffix, font)[0] > max_width:
        keep = keep[:-1]
    return (keep + suffix) if keep else suffix


def draw_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str = "#1F2933",
) -> None:
    left, top, right, bottom = box
    tw, th = text_size(draw, text, font)
    draw.text((left + (right - left - tw) / 2, top + (bottom - top - th) / 2 - 1), text, fill=fill, font=font)


def draw_text_right(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.ImageFont,
    fill: str = "#1F2933",
) -> None:
    tw, _ = text_size(draw, text, font)
    draw.text((x - tw, y), text, font=font, fill=fill)


def draw_text_label(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    background: str = "#FFFFFF",
) -> None:
    bbox = draw.textbbox((x, y), text, font=font)
    pad_x, pad_y = 4, 2
    draw.rounded_rectangle(
        (bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y),
        radius=4,
        fill=background,
    )
    draw.text((x, y), text, font=font, fill=fill)


def elide_text(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont, max_width: int) -> str:
    value = re.sub(r"\s+", " ", clean_text(text)).strip()
    if text_size(draw, value, font)[0] <= max_width:
        return value
    ellipsis = "…"
    while value and text_size(draw, value + ellipsis, font)[0] > max_width:
        value = value[:-1]
    return value + ellipsis if value else ellipsis


def wrap_text(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont, max_width: int, max_lines: int = 2) -> list[str]:
    value = re.sub(r"\s+", " ", clean_text(text)).strip()
    if not value:
        return [""]
    lines: list[str] = []
    current = ""
    for char in value:
        candidate = current + char
        if text_size(draw, candidate, font)[0] <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = char
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and text_size(draw, lines[-1], font)[0] > max_width:
        lines[-1] = elide_text(draw, lines[-1], font, max_width)
    if len(value) > sum(len(line.replace("…", "")) for line in lines):
        lines[-1] = elide_text(draw, lines[-1] + "…", font, max_width)
    return lines or [""]


def draw_text_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: Any,
    font: ImageFont.ImageFont,
    fill: str = "#374151",
    align: str = "center",
    max_lines: int = 2,
) -> None:
    left, top, right, bottom = box
    pad_x = 8
    lines = wrap_text(draw, text, font, int(right - left - pad_x * 2), max_lines=max_lines)
    line_heights = [text_size(draw, line, font)[1] for line in lines]
    line_gap = 4
    total_h = sum(line_heights) + line_gap * max(0, len(lines) - 1)
    y = top + (bottom - top - total_h) / 2 - 1
    for idx, line in enumerate(lines):
        tw, th = text_size(draw, line, font)
        if align == "left":
            x = left + pad_x
        elif align == "right":
            x = right - pad_x - tw
        else:
            x = left + (right - left - tw) / 2
        draw.text((x, y), line, font=font, fill=fill)
        y += th + line_gap


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    clean_df = df.fillna("").astype(str)
    cols = [str(col) for col in clean_df.columns.tolist()]
    clean_df.columns = cols
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in clean_df.iterrows():
        lines.append("| " + " | ".join(clean_text(row[col]).replace("|", "/") for col in cols) + " |")
    return "\n".join(lines) + "\n"


def is_mainland(row: pd.Series) -> bool:
    flag = clean_text(row.get("is_mainland_china", "")).lower()
    country = clean_text(row.get("country_or_region", "")).lower()
    return flag in {"1", "true"} or country in {"china", "中国", "中国内地", "中国大陆", "china (mainland)"}


def dedupe_records(records: pd.DataFrame) -> pd.DataFrame:
    df = records.copy()
    if "fact_id" in df.columns:
        df = df.drop_duplicates(subset=["fact_id"])
    else:
        df = df.drop_duplicates()
    return df


def latest_source_rows(records: pd.DataFrame, source: str) -> pd.DataFrame:
    df = dedupe_records(records)
    source_df = df[df["ranking_source"] == source].copy()
    if source_df.empty:
        return source_df
    latest_release = source_df["release_year"].max()
    source_df = source_df[source_df["release_year"] == latest_release].copy()
    latest_ranking = source_df["ranking_year"].max()
    return source_df[source_df["ranking_year"] == latest_ranking].copy()


def university_identity(row: pd.Series) -> str:
    en = clean_text(row.get("university_name_en", "")).lower()
    cn = clean_text(row.get("university_name_cn", ""))
    return en or cn


def alias_specificity_score(row: pd.Series, subject: dict[str, Any], source: str) -> int:
    alias_type = clean_text(row.get("alias_type", ""))
    raw = clean_text(row.get("ranking_subject_raw", "")).lower()
    alias = clean_text(row.get("ranking_subject_alias", "")).lower()
    expected = clean_text(expected_weight_area(subject, source)).lower()
    target = clean_text(subject.get("target_subject", "")).lower()
    subject_alias = clean_text(subject.get(f"{source.lower()}_subject_name", "")).lower()
    score = 50
    if expected and (raw == expected or alias == expected):
        score -= 25
    if subject_alias and (raw == subject_alias or alias == subject_alias):
        score -= 20
    if target and (raw == target or alias == target):
        score -= 18
    type_scores = {
        "dim_subject_column": 0,
        "mapping_sheet1": 4,
        "source_subject_cn": 6,
        "source_subject_en": 6,
        "manual_config_subject_alias": 14,
        "manual_the_area_alias": 16,
        "manual_config_area_alias": 18,
    }
    score += type_scores.get(alias_type, 12)
    broad_aliases = {"engineering", "工程学", "工程", "physical sciences", "natural sciences"}
    if raw in broad_aliases or alias in broad_aliases:
        score += 20
    subject_code = clean_text(subject.get("target_subject_code")) or clean_text(subject.get("ministry_subject_code"))
    if source == "US News" and (subject_code == "0812" or clean_text(subject.get("subject_id")) == "subject_0812"):
        subject_keys = {normalize_text_key(raw), normalize_text_key(alias)}
        if subject_keys & {"computerscience", "计算机科学"}:
            score -= 80
        elif subject_keys & {"artificialintelligence", "人工智能"}:
            score += 35
        elif subject_keys & {"engineering", "工程学", "工程"}:
            score += 60
    return score


def dedupe_university_rows(df: pd.DataFrame, subject: dict[str, Any], source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df, df
    work = df.copy()
    work["_university_key"] = work.apply(university_identity, axis=1)
    work["_alias_specificity_score"] = work.apply(lambda row: alias_specificity_score(row, subject, source), axis=1)
    work["_rank_sort"] = pd.to_numeric(work.get("rank_midpoint", pd.Series(dtype=str)), errors="coerce")
    work["_score_sort"] = pd.to_numeric(work.get("total_score", pd.Series(dtype=str)), errors="coerce")
    work = work.sort_values(
        ["_university_key", "_alias_specificity_score", "_rank_sort", "_score_sort"],
        ascending=[True, True, True, False],
        na_position="last",
    )
    kept = work.drop_duplicates(subset=["_university_key"], keep="first").copy()
    dropped = work[~work.index.isin(kept.index)].copy()
    cleanup = ["_university_key", "_alias_specificity_score", "_rank_sort", "_score_sort"]
    kept = kept.drop(columns=cleanup, errors="ignore")
    dropped = dropped.drop(columns=cleanup, errors="ignore")
    return kept.reset_index(drop=True), dropped.reset_index(drop=True)


def dedupe_subject_rows_by_period(df: pd.DataFrame, subject: dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    work["_alias_specificity_score"] = work.apply(
        lambda row: alias_specificity_score(row, subject, clean_text(row.get("ranking_source", ""))),
        axis=1,
    )
    work["_rank_sort"] = pd.to_numeric(work.get("rank_midpoint", pd.Series(dtype=str)), errors="coerce")
    work["_score_sort"] = pd.to_numeric(work.get("total_score", pd.Series(dtype=str)), errors="coerce")
    group_cols = [col for col in ["ranking_source", "release_year", "ranking_year", "university_name_cn", "university_name_en"] if col in work.columns]
    work = work.sort_values(
        group_cols + ["_alias_specificity_score", "_rank_sort", "_score_sort"],
        ascending=[True] * len(group_cols) + [True, True, False],
        na_position="last",
    )
    result = work.drop_duplicates(subset=group_cols, keep="first").copy()
    return result.drop(columns=["_alias_specificity_score", "_rank_sort", "_score_sort"], errors="ignore").reset_index(drop=True)


def artifact_dir(run_dir: Path, artifact_id: str) -> Path:
    out = run_dir / "artifacts" / artifact_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def chart_content_bbox(image: Image.Image, threshold: int = 10) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    return diff.point(lambda value: 255 if value > threshold else 0).getbbox()


def crop_chart_whitespace(image: Image.Image, padding: int = 28) -> Image.Image:
    bbox = chart_content_bbox(image)
    if not bbox:
        return image
    left, top, right, bottom = bbox
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    if crop_box == (0, 0, image.width, image.height):
        return image
    return image.crop(crop_box)


def audit_chart_png(path: Path) -> dict[str, Any]:
    with Image.open(path) as check:
        image = check.convert("RGB")
        bbox = chart_content_bbox(image)
        if bbox:
            left, top, right, bottom = bbox
            margins = {
                "left": left,
                "top": top,
                "right": image.width - right,
                "bottom": image.height - bottom,
            }
            content_ratio = round(((right - left) * (bottom - top)) / max(1, image.width * image.height), 4)
        else:
            margins = {"left": image.width, "top": image.height, "right": image.width, "bottom": image.height}
            content_ratio = 0.0
        max_margin_ratio = max(margins.values()) / max(1, max(image.size))
        warnings = []
        if max_margin_ratio > 0.08:
            warnings.append("large_outer_margin")
        if content_ratio < 0.58:
            warnings.append("low_content_coverage")
        payload = {
            "image": str(path),
            "width": image.width,
            "height": image.height,
            "content_bbox": list(bbox) if bbox else [],
            "margins_px": margins,
            "content_ratio": content_ratio,
            "max_margin_ratio": round(max_margin_ratio, 4),
            "warnings": warnings,
        }
    qa_path = path.with_name("chart_image_qa.json")
    qa_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return payload


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = crop_chart_whitespace(image)
    image.save(path)
    with Image.open(path) as check:
        check.verify()
    audit_chart_png(path)


def read_weights() -> pd.DataFrame:
    df = pd.read_csv(FACT_WEIGHT_CSV, dtype=str).fillna("")
    df["weight_percent"] = pd.to_numeric(df["weight_percent"], errors="coerce").fillna(0.0)
    return df


def read_indicators() -> pd.DataFrame:
    df = pd.read_csv(FACT_INDICATOR_CSV, dtype=str).fillna("")
    for column in ["release_year", "ranking_year", "metric_value", "metric_rank_midpoint", "world_rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def read_external_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def ensure_wos_subject_paper_csv() -> dict[str, Any]:
    candidates = [
        path
        for path in DATA_DIR.glob("*web of science*20260511.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    ]
    newest_source = max(candidates, key=lambda path: path.stat().st_mtime, default=None)
    if newest_source is None:
        return {"status": "missing_source_xlsx"}
    if WOS_SUBJECT_PAPER_CSV.exists() and WOS_SUBJECT_PAPER_CSV.stat().st_mtime >= newest_source.stat().st_mtime:
        return {"status": "fresh", "source_file": newest_source.name}
    try:
        import build_data_layer_v2

        frame = build_data_layer_v2.build_wos_subject_paper_wide()
        return {
            "status": "rebuilt",
            "source_file": newest_source.name,
            "rows": int(len(frame)),
        }
    except Exception as exc:
        return {
            "status": "rebuild_failed",
            "source_file": newest_source.name,
            "error": str(exc),
        }


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def short_university_name(row: pd.Series) -> str:
    cn = clean_text(row.get("university_name_cn", ""))
    en = clean_text(row.get("University", "")) or clean_text(row.get("university_name_en", ""))
    return cn or en


def is_tongji_name(value: Any) -> bool:
    text = clean_text(value).lower()
    return "同济" in text or "tongji" in text


def expected_weight_area(subject: dict[str, Any], source: str) -> str:
    override = subject.get("source_runtime_overrides", {}).get(source, {})
    override_area = valid_mapping_value(override.get("weight_subject_or_area")) or valid_mapping_value(override.get("ranking_subject_or_area"))
    if override_area:
        return override_area
    if source == "软科":
        return valid_mapping_value(subject.get("arwu_subject_name")) or clean_text(subject.get("target_subject"))
    if source == "QS":
        return (
            valid_mapping_value(subject.get("qs_subject_name"))
            or source_alias_display(subject, source)
        )
    if source == "US News":
        return valid_mapping_value(subject.get("usnews_subject_name")) or source_alias_display(subject, source)
    area = valid_mapping_value(subject.get("the_subject_area"))
    if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        if area in crosswalk:
            return crosswalk[area]
    return area or source_alias_display(subject, source)


@lru_cache(maxsize=1)
def load_usnews_bilingual_subject_aliases() -> dict[str, tuple[str, ...]]:
    pairs: dict[str, set[str]] = {}

    def add_pair(left: Any, right: Any) -> None:
        left_text = clean_text(left)
        right_text = clean_text(right)
        if not left_text or not right_text or normalize_text_key(left_text) == normalize_text_key(right_text):
            return
        pairs.setdefault(normalize_text_key(left_text), set()).add(right_text)
        pairs.setdefault(normalize_text_key(right_text), set()).add(left_text)

    configs = [
        (QS_USNEWS_RANKING_FILE, "USnews（2021-2025）", "学科中文", "学科英文"),
    ]
    for filename, sheet, cn_col, en_col in configs:
        path = DATA_DIR / filename
        if not path.exists():
            continue
        try:
            df = pd.read_excel(path, sheet_name=sheet, dtype=str).fillna("")
        except Exception:
            continue
        if cn_col not in df.columns or en_col not in df.columns:
            continue
        for _, row in df[[cn_col, en_col]].drop_duplicates().iterrows():
            add_pair(row.get(cn_col), row.get(en_col))
    return {key: tuple(sorted(values)) for key, values in pairs.items() if values}


def expand_usnews_bilingual_values(values: list[Any]) -> list[str]:
    aliases = load_usnews_bilingual_subject_aliases()
    expanded: list[str] = []
    for value in values:
        for item in candidate_subject_areas(value):
            if not clean_text(item):
                continue
            expanded.append(item)
            expanded.extend(aliases.get(normalize_text_key(item), ()))
    return ordered_unique(expanded)


def source_primary_alias_values(subject: dict[str, Any], source: str) -> list[str]:
    values: list[str] = []
    for row in subject.get("alias_details", []):
        if clean_text(row.get("ranking_source")) != source:
            continue
        source_note = clean_text(row.get("source_note"))
        if source == "US News" and "USNEWS_ENGINEERING_BROAD" in source_note:
            continue
        alias = clean_text(row.get("ranking_subject_alias"))
        if alias:
            values.append(alias)
    if values:
        return ordered_unique(values)
    return ordered_unique(subject.get("alias_summary", {}).get(source, []))


def primary_source_area_values(subject: dict[str, Any], source: str) -> list[str]:
    values: list[Any] = [
        subject.get("target_subject"),
        subject.get("subject_short_name"),
        subject.get("ministry_subject_name"),
    ]
    override = subject.get("source_runtime_overrides", {}).get(source, {})
    if source == "US News":
        values.extend(candidate_subject_areas(subject.get("usnews_subject_name")))
        values.extend([override.get("ranking_subject_or_area"), override.get("weight_subject_or_area")])
        values.extend(source_primary_alias_values(subject, source))
        return expand_usnews_bilingual_values(values)
    values.extend([override.get("ranking_subject_or_area"), override.get("weight_subject_or_area")])
    values.extend(subject.get("alias_summary", {}).get(source, []))
    candidates: list[str] = []
    for value in values:
        candidates.extend(candidate_subject_areas(value))
    return ordered_unique(candidates)


def primary_source_area_keys_for_frame(df: pd.DataFrame, subject: dict[str, Any], source: str) -> set[str]:
    if source != "US News" or df.empty:
        return set()
    available_keys: set[str] = set()
    for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
        if column in df.columns:
            available_keys.update(normalize_text_key(value) for value in df[column].tolist() if normalize_text_key(value))
    if not available_keys:
        return set()
    scored_matches: list[tuple[int, int, int, set[str]]] = []
    for preferred in primary_source_area_values(subject, source):
        equivalent_values = expand_usnews_bilingual_values([preferred])
        equivalent_keys = {normalize_text_key(value) for value in equivalent_values if normalize_text_key(value)}
        equivalent_keys.update(key.replace("/", "") for key in list(equivalent_keys) if "/" in key)
        matched_keys = equivalent_keys & available_keys
        if matched_keys:
            masks = []
            for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
                if column in df.columns:
                    masks.append(df[column].map(normalize_text_key).isin(matched_keys))
            if masks:
                mask = masks[0]
                for item in masks[1:]:
                    mask = mask | item
                matched = df[mask].copy()
                years = matched.get("ranking_year", pd.Series(dtype=str)).map(clean_text).nunique()
                if "is_tongji" in matched.columns:
                    tongji_matched = matched[matched["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
                    tongji_years = tongji_matched.get("ranking_year", pd.Series(dtype=str)).map(clean_text).nunique()
                else:
                    tongji_years = 0
            else:
                years = 0
                tongji_years = 0
            scored_matches.append((int(tongji_years), int(years), -len(scored_matches), matched_keys))
    if scored_matches:
        scored_matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return scored_matches[0][3]
    return set()


def expected_ranking_area(subject: dict[str, Any], source: str) -> str:
    override = subject.get("source_runtime_overrides", {}).get(source, {})
    if source == "QS":
        mapped = single_mapping_value(subject.get("qs_subject_name"))
        if mapped:
            return mapped
    if source == "THE":
        mapped = valid_mapping_value(subject.get("the_subject_area"))
        if mapped:
            return mapped
    override_area = valid_mapping_value(override.get("ranking_subject_or_area"))
    if override_area:
        return override_area
    if source == "软科":
        aliases = public_supplements.arwu_public_aliases(subject)
        return (
            valid_mapping_value(subject.get("arwu_subject_name"))
            or (aliases[0] if aliases else "")
            or clean_text(subject.get("target_subject"))
        )
    if source == "QS":
        return source_alias_display(subject, source)
    if source == "US News":
        return (
            valid_mapping_value(subject.get("usnews_subject_name"))
            or valid_mapping_value(override.get("weight_subject_or_area"))
            or source_alias_display(subject, source)
        )
    if source == "THE":
        return source_alias_display(subject, source)
    return clean_text(subject.get("target_subject"))


def source_area_candidates(subject: dict[str, Any], source: str) -> list[str]:
    override = subject.get("source_runtime_overrides", {}).get(source, {})
    override_values = [
        valid_mapping_value(override.get("ranking_subject_or_area")),
        valid_mapping_value(override.get("weight_subject_or_area")),
    ]
    override_values = [value for value in ordered_unique(override_values) if value]
    if override_values:
        candidates: list[str] = []
        for value in override_values:
            candidates.extend(candidate_subject_areas(value))
        candidates = ordered_unique(candidates)
        if source == "THE":
            expanded: list[str] = []
            for candidate in candidates:
                expanded.extend(the_ranking_area_candidates(candidate))
            return ordered_unique(expanded)
        return candidates

    values: list[Any] = [expected_ranking_area(subject, source), expected_weight_area(subject, source)]
    values.extend(subject_alias_values(subject, source))
    candidates: list[str] = []
    for value in ordered_unique([valid_mapping_value(item) for item in values]):
        candidates.extend(candidate_subject_areas(value))
    candidates = ordered_unique(candidates)
    if source == "THE":
        expanded: list[str] = []
        for candidate in candidates:
            expanded.extend(the_ranking_area_candidates(candidate))
        return ordered_unique(expanded)
    return candidates


def filter_to_selected_source_area(df: pd.DataFrame, subject: dict[str, Any], source: str) -> pd.DataFrame:
    if df.empty:
        return df
    mapping_candidates = mapping_table_aliases(subject, source)
    if mapping_candidates:
        selection = stored_source_selection(subject, source) or select_source_area(df, subject, source)
        selected = clean_text(selection.get("selected_ranking_subject_or_area"))
        if not selected:
            return df.iloc[0:0].copy()
        return df[exact_subject_mask(df, [selected])].copy()
    primary_keys = primary_source_area_keys_for_frame(df, subject, source)
    if primary_keys:
        masks = []
        for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
            if column in df.columns:
                masks.append(df[column].map(normalize_text_key).isin(primary_keys))
        if masks:
            mask = masks[0]
            for item in masks[1:]:
                mask = mask | item
            matched = df[mask].copy()
            if not matched.empty:
                return matched
    candidate_keys = {normalize_text_key(value) for value in source_area_candidates(subject, source) if normalize_text_key(value)}
    if not candidate_keys:
        return df.iloc[0:0].copy()
    masks = []
    for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
        if column in df.columns:
            masks.append(df[column].map(normalize_text_key).isin(candidate_keys))
    if not masks:
        return df
    mask = masks[0]
    for item in masks[1:]:
        mask = mask | item
    matched = df[mask].copy()
    return matched


def latest_selected_source_rows(records: pd.DataFrame, subject: dict[str, Any], source: str) -> pd.DataFrame:
    latest = latest_source_rows(records, source)
    return filter_to_selected_source_area(latest, subject, source)


def source_title_subject_label(subject: dict[str, Any], source: str) -> str:
    target = clean_text(subject.get("target_subject"))
    area = expected_ranking_area(subject, source)
    area_parts = candidate_subject_areas(area)
    if target and len(area_parts) > 1:
        return f"{target}相关口径"
    if area and target and area != target:
        return f"{area}口径"
    return target or area


def candidate_subject_areas(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"[\n\r、，,;；]+", text) if part.strip()]
    return parts or [text]


def split_scope_values(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[\n\r,;\uFF0C\u3001\uFF1B/|]+", text) if part.strip()]


def mapping_table_aliases(subject: dict[str, Any], source: str) -> list[str]:
    aliases: list[str] = []
    for row in subject.get("alias_details", []):
        if clean_text(row.get("ranking_source")) != source:
            continue
        source_note = clean_text(row.get("source_note"))
        alias_type = clean_text(row.get("alias_type"))
        is_mapping_table_source = (
            "mapping_sheet1" in alias_type
            or "dim_subject_column" in alias_type
            or "教育部学科映射Sheet1" in source_note
            or source_note in {"arwu_subject_name", "qs_subject_name", "usnews_subject_name", "the_subject_area"}
        )
        if not is_mapping_table_source:
            continue
        alias = valid_mapping_value(row.get("ranking_subject_alias"))
        if alias:
            aliases.append(alias)
    aliases = ordered_unique(aliases)
    configured_value = {
        "软科": subject.get("arwu_subject_name"),
        "QS": subject.get("qs_subject_name"),
        "US News": subject.get("usnews_subject_name"),
        "THE": subject.get("the_subject_area"),
    }.get(source, "")
    alias_by_key = {normalize_text_key(alias): alias for alias in aliases}
    ordered: list[str] = []
    for item in split_scope_values(configured_value):
        matched = alias_by_key.get(normalize_text_key(item))
        if matched and matched not in ordered:
            ordered.append(matched)
    return ordered + [alias for alias in aliases if alias not in ordered]


def mapping_table_display_label(subject: dict[str, Any], source: str, default: str = "") -> str:
    aliases = mapping_table_aliases(subject, source)
    if not aliases:
        return default
    alias_by_key = {normalize_text_key(alias): alias for alias in aliases}
    configured_value = {
        "软科": subject.get("arwu_subject_name"),
        "QS": subject.get("qs_subject_name"),
        "US News": subject.get("usnews_subject_name"),
        "THE": subject.get("the_subject_area"),
    }.get(source, "")
    ordered: list[str] = []
    for item in split_scope_values(configured_value):
        key = normalize_text_key(item)
        if key in alias_by_key and alias_by_key[key] not in ordered:
            ordered.append(alias_by_key[key])
    for alias in aliases:
        if alias not in ordered:
            ordered.append(alias)
    return "；".join(ordered)


def selected_mapping_table_label(
    subject: dict[str, Any],
    source: str,
    observed: str,
    default: str = "",
) -> str:
    aliases = mapping_table_aliases(subject, source)
    if not aliases:
        return default
    observed_key = normalize_text_key(observed)
    if observed_key:
        for alias in aliases:
            if normalize_text_key(alias) == observed_key:
                return alias
    configured_value = {
        "软科": subject.get("arwu_subject_name"),
        "QS": subject.get("qs_subject_name"),
        "US News": subject.get("usnews_subject_name"),
        "THE": subject.get("the_subject_area"),
    }.get(source, "")
    alias_by_key = {normalize_text_key(alias): alias for alias in aliases}
    for item in split_scope_values(configured_value):
        matched = alias_by_key.get(normalize_text_key(item))
        if matched:
            return matched
    return aliases[0]


def exact_subject_mask(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    alias_keys = {normalize_text_key(alias) for alias in aliases if normalize_text_key(alias)}
    for column in ["ranking_subject_raw", "ranking_subject_norm"]:
        if column in df.columns:
            mask = mask | df[column].map(normalize_text_key).isin(alias_keys)
    return mask


def score_exact_subject_aliases(df: pd.DataFrame, aliases: list[str]) -> list[tuple[int, int, int, int, str]]:
    scored: list[tuple[int, int, int, int, str]] = []
    for index, alias in enumerate(aliases):
        matched = df[exact_subject_mask(df, [alias])].copy()
        if matched.empty:
            continue
        years = matched.get("ranking_year", pd.Series(dtype=str)).map(clean_text).nunique()
        tongji = matched[
            matched.get("is_tongji", pd.Series([""] * len(matched), index=matched.index))
            .astype(str)
            .str.lower()
            .isin(["true", "1"])
        ]
        tongji_years = tongji.get("ranking_year", pd.Series(dtype=str)).map(clean_text).nunique()
        latest_year_value = pd.to_numeric(matched.get("ranking_year"), errors="coerce").max()
        latest_year = int(latest_year_value) if pd.notna(latest_year_value) else 0
        scored.append((int(tongji_years), int(years), latest_year, -index, alias))
    return sorted(scored, reverse=True)


def selected_exact_mapping_candidate(df: pd.DataFrame, subject: dict[str, Any], source: str) -> str:
    scored = score_exact_subject_aliases(df, mapping_table_aliases(subject, source))
    return scored[0][4] if scored else ""


def reasonable_fallback_rules(subject: dict[str, Any], source: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in subject.get("alias_details", []):
        if clean_text(row.get("ranking_source")) != source:
            continue
        alias_type = clean_text(row.get("alias_type"))
        source_note = clean_text(row.get("source_note"))
        if alias_type.startswith("manual_subject_alias_rule:"):
            mapping_class = alias_type.split(":", 1)[1]
            rule_id = source_note.rsplit(":", 1)[-1]
            if mapping_class not in {"deterministic", "broad_multi_subject"}:
                continue
        elif source == "THE" and (
            "the_ranking_area_crosswalk" in alias_type
            or "manual_area_alias_rule" in alias_type
        ):
            mapping_class = "deterministic_area_crosswalk"
            rule_id = "THE_AREA_NAME_CROSSWALK"
        else:
            continue
        if rule_id == "USNEWS_ENGINEERING_BROAD":
            continue
        alias = valid_mapping_value(row.get("ranking_subject_alias"))
        if not alias:
            continue
        item = grouped.setdefault(
            rule_id,
            {"rule_id": rule_id, "mapping_class": mapping_class, "aliases": []},
        )
        item["aliases"].append(alias)
    return [
        {**item, "aliases": ordered_unique(item["aliases"])}
        for item in grouped.values()
    ]


def select_source_area(df: pd.DataFrame, subject: dict[str, Any], source: str) -> dict[str, Any]:
    primary = selected_exact_mapping_candidate(df, subject, source)
    if primary:
        return {
            "selection_mode": "mapping_table_candidate",
            "selected_ranking_subject_or_area": primary,
        }
    fallback_scores: list[tuple[int, int, int, int, int, str]] = []
    for rule_index, rule in enumerate(reasonable_fallback_rules(subject, source)):
        for score in score_exact_subject_aliases(df, rule["aliases"]):
            class_priority = 1 if rule["mapping_class"] in {"deterministic", "deterministic_area_crosswalk"} else 0
            fallback_scores.append((*score[:3], class_priority, -rule_index, score[4]))
    if fallback_scores:
        fallback_scores.sort(reverse=True)
        return {
            "selection_mode": "fallback_mapping",
            "selected_ranking_subject_or_area": fallback_scores[0][5],
        }
    return {"selection_mode": "missing", "selected_ranking_subject_or_area": ""}


def stored_source_selection(subject: dict[str, Any], source: str) -> dict[str, Any]:
    selections = subject.get("ranking_selection_by_source", {})
    return selections.get(source, {}) if isinstance(selections, dict) else {}


def chart_subject_display_label(subject: dict[str, Any], source: str, row: pd.Series | dict[str, Any]) -> str:
    observed = clean_text(row.get("source_ranking_subject_raw", "")) or clean_text(row.get("ranking_subject_raw", ""))
    selection = stored_source_selection(subject, source)
    if clean_text(selection.get("selection_mode")) == "fallback_mapping":
        return clean_text(selection.get("selected_ranking_subject_or_area")) or observed
    mapping_label = selected_mapping_table_label(subject, source, observed)
    if mapping_label:
        return mapping_label
    if isinstance(row, pd.Series):
        return clean_text(row.get("ranking_subject_alias", "")) or clean_text(row.get("ranking_subject_raw", ""))
    return clean_text(row.get("ranking_subject_alias", "")) or clean_text(row.get("ranking_subject_raw", ""))


def subject_alias_values(subject: dict[str, Any], source: str) -> set[str]:
    values = {valid_mapping_value(value) for value in subject.get("alias_summary", {}).get(source, []) if valid_mapping_value(value)}
    override = subject.get("source_runtime_overrides", {}).get(source, {})
    for field in ["weight_subject_or_area", "ranking_subject_or_area", "proxy_subject_en"]:
        value = valid_mapping_value(override.get(field))
        if value:
            values.add(value)
    if source == "软科":
        values.update(public_supplements.arwu_public_aliases(subject))
    for row in subject.get("public_supplements", []):
        if clean_text(row.get("ranking_source")) != source:
            continue
        if bool(row.get("requires_disclosure")):
            continue
        for field in ["subject_or_area", "subject_or_area_en"]:
            value = valid_mapping_value(row.get(field))
            if value:
                values.add(value)
    return values


def source_alias_display(subject: dict[str, Any], source: str) -> str:
    aliases = [valid_mapping_value(value) for value in subject.get("alias_summary", {}).get(source, [])]
    aliases = [value for value in ordered_unique(aliases) if value]
    return "、".join(aliases)


def candidate_weight_areas(subject: dict[str, Any], source: str) -> list[str]:
    values: list[Any] = [expected_weight_area(subject, source)]
    values.extend(subject_alias_values(subject, source))
    candidates: list[str] = []
    for value in ordered_unique([valid_mapping_value(value) for value in values]):
        candidates.extend(candidate_subject_areas(value))
    return expand_weight_area_candidates(source, candidates)


def expand_weight_area_candidates(source: str, candidates: list[str]) -> list[str]:
    expanded: list[str] = []
    qs_aliases = {
        "\u7ecf\u6d4e\u4e0e\u8ba1\u91cf\u7ecf\u6d4e\u5b66": [
            "\u7ecf\u6d4e\u5b66",
            "Economics and Econometrics",
        ],
        "Economics and Econometrics": [
            "\u7ecf\u6d4e\u5b66",
            "\u7ecf\u6d4e\u4e0e\u8ba1\u91cf\u7ecf\u6d4e\u5b66",
        ],
        "\u7ecf\u6d4e\u5b66": [
            "Economics and Econometrics",
            "\u7ecf\u6d4e\u4e0e\u8ba1\u91cf\u7ecf\u6d4e\u5b66",
        ],
    }
    for candidate in candidates:
        if not clean_text(candidate):
            continue
        expanded.append(candidate)
        if source == "QS":
            candidate_key = normalize_text_key(candidate)
            for alias_key, alias_values in qs_aliases.items():
                if normalize_text_key(alias_key) == candidate_key:
                    expanded.extend(alias_values)
    return ordered_unique(expanded)


def find_weight_subset(weights: pd.DataFrame, source: str, candidates: list[str]) -> tuple[pd.DataFrame, str]:
    weight_keys = {
        normalize_text_key(area): area
        for area in weights[weights["ranking_source"] == source]["ranking_subject_or_area"].drop_duplicates().tolist()
        if clean_text(area)
    }
    for candidate in candidates:
        subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)].copy()
        if not subset.empty:
            return subset, candidate
        mapped_area = weight_keys.get(normalize_text_key(candidate), "")
        if mapped_area:
            subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == mapped_area)].copy()
            if not subset.empty:
                return subset, mapped_area
    return pd.DataFrame(), candidates[0] if candidates else ""


def latest_overview_subject_areas(run_dir: Path, source: str) -> list[str]:
    path = run_dir / "artifacts" / "figure_01_tongji_subject_ranking_overview" / "chart_data.csv"
    if not path.exists():
        return []
    df = read_external_csv(path)
    if df.empty or "ranking_source" not in df.columns:
        return []
    source_df = df[df["ranking_source"].map(clean_text) == source].copy()
    if source_df.empty:
        return []
    if "ranking_year" in source_df.columns:
        source_df["_year_sort"] = pd.to_numeric(source_df["ranking_year"], errors="coerce")
        source_df = source_df.sort_values("_year_sort", na_position="first")
    values: list[str] = []
    for row in reversed(source_df.to_dict("records")):
        for column in ["ranking_subject_raw", "ranking_subject_alias", "source_ranking_subject_raw"]:
            value = clean_text(row.get(column))
            if value:
                values.extend(candidate_subject_areas(value))
    return ordered_unique(values)


def normalize_commonality_group(value: Any) -> str:
    text = clean_text(value)
    mapping = json.loads(INDICATOR_GROUP_CROSSWALK_JSON.read_text(encoding="utf-8")) if INDICATOR_GROUP_CROSSWALK_JSON.exists() else {}
    return mapping.get(text, text or "其他")


def filter_indicators_for_subject(indicators: pd.DataFrame, subject: dict[str, Any], source: str) -> pd.DataFrame:
    aliases = subject_alias_values(subject, source)
    df = indicators[indicators["ranking_source"] == source].copy()
    selected = filter_to_selected_source_area(df, subject, source)
    if not selected.empty and len(selected) < len(df):
        return selected
    if aliases:
        df = df[df["ranking_subject_raw"].isin(aliases) | df["ranking_subject_norm"].isin(aliases)].copy()
    return df


def university_keys_from_peer_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    keys = set()
    for column in ["university_name_cn", "university_name_en", "学校"]:
        if column in df.columns:
            keys.update(clean_text(value) for value in df[column].tolist() if clean_text(value))
    return keys


def peer_scope_from_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str).fillna("")
    if df.empty:
        return df
    df["_university_key"] = df.apply(university_identity, axis=1)
    df["_peer_subject_raw"] = df.get("ranking_subject_raw", pd.Series([""] * len(df))).map(clean_text)
    df["_peer_subject_norm"] = df.get("ranking_subject_norm", pd.Series([""] * len(df))).map(clean_text)
    df["_peer_subject_alias"] = df.get("ranking_subject_alias", pd.Series([""] * len(df))).map(clean_text)
    return df


def write_common_outputs(out: Path, artifact_id: str, artifact_type: str, data_rows: int, trace_rows: int, extra: dict[str, Any] | None = None) -> None:
    spec = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "generated_at": now_text(),
        "data_rows": data_rows,
        "source_trace_rows": trace_rows,
    }
    if extra:
        spec.update(extra)
    spec_name = "chart_spec.json" if artifact_type == "chart" else "table_spec.json"
    (out / spec_name).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out / "run_log.md").write_text(
        f"# {artifact_id} run log\n\n- generated_at: {spec['generated_at']}\n- data_rows: {data_rows}\n- source_trace_rows: {trace_rows}\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / "narrative.md").write_text(
        f"# {artifact_id}\n\n本产物由 `scripts/run_subject_agent.py` 在学科专属 run 目录中自动生成。重绘时优先使用本目录下的数据文件、spec 文件和 source trace。\n",
        encoding="utf-8",
        newline="\n",
    )


def append_builder_result(results: list[dict[str, Any]], artifact_id: str, builder: Callable[[], dict[str, Any]]) -> None:
    started = time.perf_counter()
    try:
        result = builder()
        if not isinstance(result, dict):
            result = {"artifact_id": artifact_id, "status": "error", "reason": f"builder returned {type(result).__name__}"}
        result.setdefault("artifact_id", artifact_id)
        result.setdefault("status", "generated")
    except Exception as exc:
        result = {
            "artifact_id": artifact_id,
            "status": "error",
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "traceback": traceback.format_exc(),
        }
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    results.append(result)


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    max_lines: int = 2,
    line_gap: int = 4,
) -> None:
    x, y = xy
    lines: list[str] = []
    current = ""
    for char in clean_text(text):
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and (bbox[2] - bbox[0]) > max_width:
            lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    for index, line in enumerate(lines[:max_lines]):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_height = bbox[3] - bbox[1]
        draw.text((x, y + index * (line_height + line_gap)), line, font=font, fill=fill)


def render_cards(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 900), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(38, True)
    font_sub = load_font(22)
    font_source = load_font(30, True)
    font_rank = load_font(56, True)
    font_meta = load_font(19)
    draw.text((85, 52), f"同济大学{subject_name}学科国际排名概览", font=font_title, fill="#16202A")
    available_sources = [source for source in RANKING_SOURCES if not df[df["ranking_source"] == source].empty]
    subtitle = "四大国际排名最新发布年份口径；每张卡片列出该榜单实际学科/领域口径" if len(available_sources) >= 4 else "按当前可核验来源展示；每张卡片列出实际学科/领域口径，缺失榜单不强行补齐"
    draw.text((85, 102), subtitle, font=font_sub, fill="#5A6573")
    card_w, card_h, gap = 330, 420, 42
    total_w = len(available_sources) * card_w + max(0, len(available_sources) - 1) * gap
    start_x = max(85, int((1600 - total_w) / 2))
    for idx, source in enumerate(available_sources):
        row = df[df["ranking_source"] == source]
        if row.empty:
            continue
        item = row.iloc[0]
        x, y = start_x + idx * (card_w + gap), 185
        color = SOURCE_COLORS[source]
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill="#F8FAFC", outline="#D8DEE8", width=2)
        draw.rectangle((x, y, x + card_w, y + 12), fill=color)
        source_label = display_ranking_source(source)
        draw.text((x + 30, y + 42), source_label, font=font_source, fill=color)
        draw.text((x + 30, y + 118), clean_rank_display(item["rank_raw"]), font=font_rank, fill="#111827")
        draw.text((x + 30, y + 214), f"发布年份：{int(item['release_year'])}", font=font_meta, fill="#374151")
        draw.text((x + 30, y + 252), f"排名年份：{int(item['ranking_year'])}", font=font_meta, fill="#374151")
        subject_label = clean_text(item.get("ranking_subject_display")) or clean_text(item["ranking_subject_raw"])
        draw_wrapped_text(draw, (x + 30, y + 292), f"排名口径：{subject_label}", font_meta, "#4B5563", card_w - 60)
        score = clean_text(item.get("total_score", ""))
        if score:
            draw.text((x + 30, y + 354), f"总分：{score}", font=font_meta, fill="#4B5563")
    save_png(image, out_path)


def build_figure_01(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "figure_01_tongji_subject_ranking_overview"
    out = artifact_dir(run_dir, artifact_id)
    rows = []
    traces = []
    df = dedupe_records(records)
    tongji_all = df[df["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    tongji_all = supplement_the_tongji_history(tongji_all, subject)
    for source in RANKING_SOURCES:
        source_rows = tongji_all[tongji_all["ranking_source"] == source].copy()
        source_rows = filter_to_selected_source_area(source_rows, subject, source)
        source_rows = dedupe_subject_rows_by_period(source_rows, subject)
        if source_rows.empty:
            continue
        if source == "THE" or (source == "QS" and single_mapping_value(subject.get("qs_subject_name"))):
            source_rows = normalize_external_history_subject_display(source_rows, subject, source)
        source_rows["_sort_ranking_year"] = pd.to_numeric(source_rows.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
        source_rows["_sort_release_year"] = pd.to_numeric(source_rows.get("release_year", pd.Series(dtype=str)), errors="coerce")
        source_rows = source_rows.sort_values(["_sort_ranking_year", "_sort_release_year"], ascending=[False, False])
        item = source_rows.iloc[0].drop(labels=["_sort_ranking_year", "_sort_release_year"], errors="ignore").to_dict()
        item["ranking_subject_display"] = chart_subject_display_label(subject, source, item)
        rows.append(item)
        traces.extend(source_rows.drop(columns=["_sort_ranking_year", "_sort_release_year"], errors="ignore").to_dict("records"))
    chart_df = pd.DataFrame(rows)
    trace_df = pd.DataFrame(traces)
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    trace_df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_cards(chart_df, clean_text(subject["target_subject"]), out / "chart.png")
    write_common_outputs(out, artifact_id, "chart", len(chart_df), len(trace_df), {"chart_type": "ranking cards"})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(chart_df), "output_dir": str(out)}


def render_history(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1700, 940), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(42, True)
    font_sub = load_font(24)
    font_axis = load_font(24, True)
    font_label = load_font(22, True)
    left, top, right, bottom = 138, 148, 1248, 748
    draw.text((72, 92), "排名区间按中间位次绘图，数值越小表示排名越靠前", font=font_sub, fill="#5A6573")
    df = df.copy()
    axis_years = pd.to_numeric(df.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
    if "release_year" in df.columns:
        axis_years = axis_years.fillna(pd.to_numeric(df["release_year"], errors="coerce"))
    df["_history_axis_year"] = axis_years
    df = df.dropna(subset=["_history_axis_year", "rank_midpoint"]).copy()
    years = sorted(int(x) for x in df["_history_axis_year"].dropna().unique())
    values = [to_float(x) for x in df["rank_midpoint"].dropna()]
    available_sources = [source for source in RANKING_SOURCES if not df[df["ranking_source"] == source].empty]
    title_scope = "四大国际排名" if len(available_sources) >= 4 else "可用国际排名"
    draw.text((72, 38), f"同济大学{subject_name}学科{title_scope}历史趋势", font=font_title, fill="#16202A")
    if not years or not values:
        save_png(image, out_path)
        return
    y_min = 0
    y_max = max(500, int(math.ceil(max(values) / 100.0) * 100))

    def xp(year: int) -> float:
        return left + (year - min(years)) / max(1, max(years) - min(years)) * (right - left)

    def yp(value: float) -> float:
        return top + (value - y_min) / max(1, y_max - y_min) * (bottom - top)

    for tick in range(0, y_max + 1, 100):
        y = yp(tick)
        draw.line((left, y, right, y), fill="#E5E7EB", width=2)
        draw_text_right(draw, left - 18, y - 14, str(tick), font_axis, "#52606D")
    draw.line((left, top, left, bottom), fill="#8792A0", width=3)
    draw.line((left, bottom, right, bottom), fill="#8792A0", width=3)
    for year in years:
        x = xp(year)
        draw_center(draw, (x - 48, bottom + 18, x + 48, bottom + 54), str(year), font_axis, "#52606D")
    label_items: list[dict[str, Any]] = []
    for source in available_sources:
        group = df[df["ranking_source"] == source].copy()
        if group.empty:
            continue
        group = group.sort_values(["_history_axis_year", "release_year"])
        color = SOURCE_COLORS.get(source, "#333333")
        points = [(xp(int(row["_history_axis_year"])), yp(float(row["rank_midpoint"]))) for _, row in group.iterrows()]
        if len(points) > 1:
            draw.line(points, fill=color, width=6)
        point_count = len(points)
        for point_index, ((_, row), (x, y)) in enumerate(zip(group.iterrows(), points)):
            draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=color, outline="#FFFFFF", width=3)
            label = clean_rank_display(row.get("rank_raw")) or f"{float(row['rank_midpoint']):g}"
            label_items.append(
                {
                    "source": source,
                    "year": int(row["_history_axis_year"]),
                    "x": x,
                    "y": y,
                    "label": label,
                    "color": color,
                    "point_index": point_index,
                    "point_count": point_count,
                }
            )

    placed_label_boxes: list[tuple[float, float, float, float]] = []

    def box_overlaps(candidate: tuple[float, float, float, float]) -> bool:
        c_left, c_top, c_right, c_bottom = candidate
        for p_left, p_top, p_right, p_bottom in placed_label_boxes:
            if c_right < p_left or c_left > p_right or c_bottom < p_top or c_top > p_bottom:
                continue
            return True
        return False

    def candidate_label_box(item: dict[str, Any], x: float, y: float) -> tuple[float, float, float, float]:
        tw, th = text_size(draw, item["label"], font_label)
        return x - 6, y - 4, x + tw + 6, y + th + 4

    preferred_offsets = {
        "软科": [-44, -72, 18, 46],
        "QS": [20, -44, 48, -72],
        "US News": [-44, 20, -72, 48],
        "THE": [20, 48, -44, -72],
    }
    for item in sorted(label_items, key=lambda value: (value["year"], value["y"])):
        dx = 16 if item["x"] < right - 190 else -126
        offsets = preferred_offsets.get(item["source"], [-44, 20, 48, -72])
        chosen_x = item["x"] + dx
        chosen_y = min(max(top + 4, item["y"] + offsets[0]), bottom - 30)
        chosen_box = candidate_label_box(item, chosen_x, chosen_y)
        for dy in offsets:
            target_y = min(max(top + 4, item["y"] + dy), bottom - 30)
            candidate = candidate_label_box(item, chosen_x, target_y)
            if not box_overlaps(candidate):
                chosen_y = target_y
                chosen_box = candidate
                break
        placed_label_boxes.append(chosen_box)
        draw_text_label(draw, chosen_x, chosen_y, item["label"], font_label, item["color"])

    lx, ly = 1292, 168
    for idx, source in enumerate(available_sources):
        y = ly + idx * 58
        color = SOURCE_COLORS[source]
        draw.line((lx, y + 16, lx + 48, y + 16), fill=color, width=7)
        source_label = display_ranking_source(source)
        draw.text((lx + 62, y), source_label, font=font_axis, fill="#374151")
    save_png(image, out_path)


def rank_midpoint_from_raw(value: Any) -> float | None:
    text = clean_text(value).replace("–", "-").replace("—", "-").replace("~", "-")
    if not text or text in {"未进入", "滑落"}:
        return None
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if not numbers:
        return None
    if len(numbers) >= 2 and "-" in text:
        return (min(numbers[0], numbers[1]) + max(numbers[0], numbers[1])) / 2
    return float(numbers[0])


def supplement_the_tongji_history(tongji: pd.DataFrame, subject: dict[str, Any]) -> pd.DataFrame:
    paths = sorted(DATA_DIR.glob("*THE*2023-2026*.xlsx"))
    if not paths:
        return tongji
    try:
        history = pd.read_excel(paths[0], sheet_name="同济历史", dtype=str).fillna("")
    except Exception:
        return tongji
    if history.empty:
        return tongji

    candidates = {
        valid_mapping_value(subject.get("the_subject_area")),
        valid_mapping_value(expected_weight_area(subject, "THE")),
        clean_text(subject.get("subject_short_name")),
        clean_text(subject.get("target_subject")),
    }
    candidates.update(valid_mapping_value(value) for value in subject.get("alias_summary", {}).get("THE", []))
    candidate_keys = {normalize_text_key(value) for value in candidates if value}

    area_col = "THE学科领域" if "THE学科领域" in history.columns else history.columns[0]
    matched = history[history[area_col].map(normalize_text_key).isin(candidate_keys)].copy()
    if matched.empty:
        return tongji

    existing_years = set(
        pd.to_numeric(tongji[tongji["ranking_source"] == "THE"].get("ranking_year", pd.Series(dtype=str)), errors="coerce")
        .dropna()
        .astype(int)
        .tolist()
    )
    additions: list[dict[str, Any]] = []
    row = matched.iloc[0]
    source_file = paths[0].name
    source_area = clean_text(row.get(area_col))
    display_area = expected_ranking_area(subject, "THE") or source_area
    for column in history.columns:
        match = re.search(r"(20\d{2})国际排名", clean_text(column))
        if not match:
            continue
        year = int(match.group(1))
        if year < 2023 or year > 2026:
            continue
        if year in existing_years:
            continue
        rank_raw = clean_text(row.get(column))
        midpoint = rank_midpoint_from_raw(rank_raw)
        if midpoint is None:
            continue
        additions.append(
            {
                "fact_id": f"the_tongji_history_{subject_code(subject) or 'subject'}_{year}",
                "ranking_source": "THE",
                "release_year": year,
                "ranking_year": year,
                "ranking_subject_raw": display_area,
                "university_name_cn": clean_text(subject.get("target_university")) or "同济大学",
                "university_name_en": "Tongji University",
                "country_or_region": "中国内地",
                "is_mainland_china": "1",
                "is_tongji": "1",
                "rank_raw": rank_raw,
                "rank_midpoint": midpoint,
                "total_score": "",
                "source_file": source_file,
                "source_sheet": "同济历史",
                "source_row": int(row.name) + 2,
                "ranking_subject_alias": display_area,
                "source_ranking_subject_raw": source_area,
                "alias_type": "the_tongji_history_sheet",
            }
        )
    if not additions:
        return tongji
    return pd.concat([tongji, pd.DataFrame(additions)], ignore_index=True, sort=False).fillna("")


def build_figure_07(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "figure_07_all_rankings_history"
    out = artifact_dir(run_dir, artifact_id)
    df = dedupe_records(records)
    tongji = df[df["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    tongji = supplement_the_tongji_history(tongji, subject)
    parts = []
    trace_parts = []
    usnews_supplemental = pd.DataFrame()
    for source in RANKING_SOURCES:
        all_source_rows = tongji[tongji["ranking_source"] == source].copy()
        source_rows = filter_to_selected_source_area(all_source_rows, subject, source)
        source_rows = dedupe_subject_rows_by_period(source_rows, subject)
        if source == "US News" and not all_source_rows.empty:
            selected_ids = set(source_rows.get("fact_id", pd.Series(dtype=str)).astype(str).tolist())
            supplemental = all_source_rows[~all_source_rows.get("fact_id", pd.Series(dtype=str)).astype(str).isin(selected_ids)].copy()
            mapping_candidates = mapping_table_aliases(subject, source)
            if mapping_candidates:
                supplemental = supplemental[exact_subject_mask(supplemental, mapping_candidates)].copy()
            else:
                supplemental = supplemental.iloc[0:0].copy()
            if not supplemental.empty:
                supplemental["_sort_ranking_year"] = pd.to_numeric(supplemental.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
                supplemental["_sort_release_year"] = pd.to_numeric(supplemental.get("release_year", pd.Series(dtype=str)), errors="coerce")
                supplemental["_sort_rank"] = pd.to_numeric(supplemental.get("rank_midpoint", pd.Series(dtype=str)), errors="coerce")
                supplemental = supplemental.sort_values(
                    ["ranking_subject_raw", "_sort_ranking_year", "_sort_release_year", "_sort_rank"],
                    ascending=[True, False, False, True],
                    na_position="last",
                )
                usnews_supplemental = supplemental.drop_duplicates(subset=["ranking_subject_raw"], keep="first").drop(
                    columns=["_sort_ranking_year", "_sort_release_year", "_sort_rank"],
                    errors="ignore",
                )
        if not source_rows.empty:
            trace_parts.append(source_rows)
            if source == "THE" or (source == "QS" and single_mapping_value(subject.get("qs_subject_name"))):
                source_rows = normalize_external_history_subject_display(source_rows, subject, source)
            parts.append(source_rows)
    if parts:
        tongji = pd.concat(parts, ignore_index=True, sort=False)
        tongji = tongji.astype("object").where(tongji.notna(), "")
    else:
        tongji = tongji.iloc[0:0].copy()
    if trace_parts:
        trace_tongji = pd.concat(trace_parts, ignore_index=True, sort=False)
        trace_tongji = trace_tongji.astype("object").where(trace_tongji.notna(), "")
    else:
        trace_tongji = tongji.iloc[0:0].copy()
    tongji = tongji.sort_values(["ranking_source", "ranking_year", "release_year"])
    trace_tongji = trace_tongji.sort_values(["ranking_source", "ranking_year", "release_year"])
    if usnews_supplemental.empty:
        usnews_supplemental = pd.DataFrame(columns=trace_tongji.columns if not trace_tongji.empty else tongji.columns)
    tongji.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    trace_tongji.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    usnews_supplemental.to_csv(out / "usnews_supplemental_subject_ranks.csv", index=False, encoding="utf-8-sig")
    render_history(tongji, clean_text(subject["target_subject"]), out / "chart.png")
    write_common_outputs(out, artifact_id, "chart", len(tongji), len(trace_tongji), {"chart_type": "multi-source history line", "x_axis": "ranking_year"})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(tongji), "output_dir": str(out)}


def write_weight_donut_svg(df: pd.DataFrame, title: str, svg_path: Path) -> None:
    work = df.copy()
    work["weight_percent"] = pd.to_numeric(work["weight_percent"], errors="coerce").fillna(0.0)
    rows_all = work.sort_values("weight_percent", ascending=False).to_dict("records")
    rows = [row for row in rows_all if to_float(row["weight_percent"]) > 0]
    total = sum(to_float(row["weight_percent"]) for row in rows) or 100.0
    max_pct = max([to_float(row["weight_percent"]) for row in rows] or [1.0])
    zero_rows = [row for row in rows_all if to_float(row["weight_percent"]) <= 0]
    width, height = 1700, 980
    palette = [
        "#214E6F",
        "#D9824B",
        "#4F8A6D",
        "#B55C5D",
        "#8773A8",
        "#D2B45F",
        "#58A6B8",
        "#A08168",
        "#6B7280",
        "#9A6B86",
    ]

    def rect(x: float, y: float, w: float, h: float, rx: float, fill: str, stroke: str = "none", sw: float = 1) -> str:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"/>'

    def text(x: float, y: float, value: Any, size: int, fill: str, weight: int = 400, anchor: str = "start") -> str:
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" dominant-baseline="middle">{svg_escape(value)}</text>'
        )

    def polar(cx: float, cy: float, radius: float, angle_deg: float) -> tuple[float, float]:
        angle = math.radians(angle_deg)
        return cx + radius * math.sin(angle), cy - radius * math.cos(angle)

    def donut_slice(cx: float, cy: float, outer_r: float, inner_r: float, start_angle: float, end_angle: float) -> str:
        end_angle = min(end_angle, start_angle + 359.99)
        large_arc = 1 if end_angle - start_angle > 180 else 0
        ox1, oy1 = polar(cx, cy, outer_r, start_angle)
        ox2, oy2 = polar(cx, cy, outer_r, end_angle)
        ix1, iy1 = polar(cx, cy, inner_r, start_angle)
        ix2, iy2 = polar(cx, cy, inner_r, end_angle)
        return (
            f"M {ox1:.2f} {oy1:.2f} "
            f"A {outer_r:.2f} {outer_r:.2f} 0 {large_arc} 1 {ox2:.2f} {oy2:.2f} "
            f"L {ix2:.2f} {iy2:.2f} "
            f"A {inner_r:.2f} {inner_r:.2f} 0 {large_arc} 0 {ix1:.2f} {iy1:.2f} Z"
        )

    def truncate(value: Any, limit: int = 24) -> str:
        text_value = clean_text(value)
        return text_value if len(text_value) <= limit else text_value[: limit - 1] + "…"

    elements: list[str] = [
        rect(0, 0, width, height, 0, "#F7F3EC"),
        rect(38, 28, width - 76, height - 66, 34, "#FFFCF6", "#E6DED2", 2),
        text(70, 68, title, 42, "#15212E", 700),
        text(78, 116, "按权重降序展示：左侧为构成圆环，右侧为可复核的比例条", 22, "#667085"),
        '<ellipse cx="450" cy="556" rx="320" ry="320" fill="#E7DED0"/>',
    ]

    angle = 0.0
    for idx, row in enumerate(rows):
        pct = to_float(row["weight_percent"])
        extent = 360.0 * pct / total
        color = palette[idx % len(palette)]
        elements.append(f'<path d="{donut_slice(438, 538, 320, 146, angle, angle + extent)}" fill="{color}" stroke="#FFFCF6" stroke-width="5"/>')
        angle += extent
    elements.extend(
        [
            '<circle cx="438" cy="538" r="146" fill="#FFFCF6" stroke="#EFE7DB" stroke-width="2"/>',
            text(438, 486, f"{total:.0f}%", 50, "#15212E", 700, "middle"),
            text(438, 532, "权重合计", 18, "#667085", 400, "middle"),
            text(438, 570, f"{len(rows)} 个有效指标", 16, "#8A7665", 400, "middle"),
        ]
    )

    legend_x, legend_y = 840, 188
    legend_w, legend_h = 760, 676
    elements.extend(
        [
            rect(legend_x, legend_y, legend_w, legend_h, 28, "#FFFFFF", "#E8DFD3", 2),
            text(legend_x + 34, legend_y + 44, "权重构成", 30, "#15212E", 700),
            text(legend_x + 34, legend_y + 84, "比例条长度与当前图内最大权重对齐", 18, "#667085"),
        ]
    )
    row_top = legend_y + 120
    row_h = 58 if len(rows) > 8 else 68
    bar_x = legend_x + 462
    bar_w = 180
    for idx, row in enumerate(rows[:10]):
        y = row_top + idx * row_h
        color = palette[idx % len(palette)]
        pct = to_float(row["weight_percent"])
        if idx % 2 == 0:
            elements.append(rect(legend_x + 20, y - 10, legend_w - 40, row_h - 4, 14, "#FAF7F1"))
        elements.append(rect(legend_x + 36, y + 7, 24, 24, 7, color))
        elements.append(text(legend_x + 76, y + 20, truncate(row["indicator_name"]), 23, "#1F2933"))
        elements.append(rect(bar_x, y + 14, bar_w, 12, 6, "#ECE6DD"))
        elements.append(rect(bar_x, y + 14, max(4, bar_w * pct / max_pct), 12, 6, color))
        elements.append(text(legend_x + legend_w - 38, y + 20, f"{pct:.1f}%", 24, "#263241", 700, "end"))

    note_y = legend_y + legend_h - 30
    if len(rows) > 10:
        note = "注：右侧仅展示前 10 项，完整数据见 chart_plot_data.csv。"
    elif zero_rows:
        zero_names = "、".join(clean_text(row.get("indicator_name")) for row in zero_rows[:3] if clean_text(row.get("indicator_name")))
        suffix = "等" if len(zero_rows) > 3 else ""
        note = f"注：{zero_names}{suffix} 0% 指标不进入圆环面积。"
    else:
        note = "注：圆环面积与右侧比例均来自同一份 chart_plot_data.csv。"
    elements.append(text(legend_x + 34, note_y, note, 16, "#8A7665"))

    svg = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<style>text{font-family:"Microsoft YaHei","SimHei","Arial",sans-serif;}</style>',
            *elements,
            "</svg>",
        ]
    )
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


def render_weight(df: pd.DataFrame, title: str, out_path: Path) -> None:
    image = Image.new("RGB", (1700, 980), "#F7F3EC")
    draw = ImageDraw.Draw(image)
    font_title = load_font(42, True)
    font_sub = load_font(22)
    font_label = load_font(23)
    font_label_bold = load_font(24, True)
    font_small = load_font(18)
    font_tiny = load_font(16)

    work = df.copy()
    work["weight_percent"] = pd.to_numeric(work["weight_percent"], errors="coerce").fillna(0.0)
    rows_all = work.sort_values("weight_percent", ascending=False).to_dict("records")
    rows = [row for row in rows_all if to_float(row["weight_percent"]) > 0]
    total = sum(to_float(row["weight_percent"]) for row in rows) or 100.0
    max_pct = max([to_float(row["weight_percent"]) for row in rows] or [1.0])
    zero_rows = [row for row in rows_all if to_float(row["weight_percent"]) <= 0]

    palette = [
        "#214E6F",
        "#D9824B",
        "#4F8A6D",
        "#B55C5D",
        "#8773A8",
        "#D2B45F",
        "#58A6B8",
        "#A08168",
        "#6B7280",
        "#9A6B86",
    ]

    draw.rounded_rectangle((38, 28, 1662, 942), radius=34, fill="#FFFCF6", outline="#E6DED2", width=2)
    draw_text_box(draw, (70, 40, 1180, 92), title, font_title, "#15212E", "left", max_lines=1)
    subtitle = "按权重降序展示：左侧为构成圆环，右侧为可复核的比例条"
    draw.text((78, 105), subtitle, font=font_sub, fill="#667085")

    box = (118, 218, 758, 858)
    draw.ellipse((box[0] + 12, box[1] + 18, box[2] + 12, box[3] + 18), fill="#E7DED0")
    start = -90.0
    for idx, row in enumerate(rows):
        pct = to_float(row["weight_percent"])
        extent = 360.0 * pct / total
        draw.pieslice(box, start, start + extent, fill=palette[idx % len(palette)], outline="#FFFCF6", width=5)
        start += extent
    draw.ellipse((292, 392, 584, 684), fill="#FFFCF6", outline="#EFE7DB", width=2)
    draw_center(draw, (310, 452, 566, 510), f"{total:.0f}%", load_font(50, True), "#15212E")
    draw_center(draw, (310, 516, 566, 548), "权重合计", font_small, "#667085")
    draw_center(draw, (310, 552, 566, 584), f"{len(rows)} 个有效指标", font_tiny, "#8A7665")

    legend_x, legend_y = 840, 188
    legend_w, legend_h = 760, 676
    draw.rounded_rectangle((legend_x, legend_y, legend_x + legend_w, legend_y + legend_h), radius=28, fill="#FFFFFF", outline="#E8DFD3", width=2)
    draw.text((legend_x + 34, legend_y + 28), "权重构成", font=load_font(30, True), fill="#15212E")
    draw.text((legend_x + 34, legend_y + 70), "比例条长度与当前图内最大权重对齐", font=font_small, fill="#667085")

    row_top = legend_y + 120
    row_h = 58 if len(rows) > 8 else 68
    bar_x = legend_x + 462
    bar_w = 180
    for idx, row in enumerate(rows[:10]):
        y = row_top + idx * row_h
        color = palette[idx % len(palette)]
        pct = to_float(row["weight_percent"])
        if idx % 2 == 0:
            draw.rounded_rectangle((legend_x + 20, y - 10, legend_x + legend_w - 20, y + row_h - 14), radius=14, fill="#FAF7F1")
        draw.rounded_rectangle((legend_x + 36, y + 7, legend_x + 60, y + 31), radius=7, fill=color)
        draw_text_box(draw, (legend_x + 76, y - 8, legend_x + 440, y + 44), row["indicator_name"], font_label, "#1F2933", "left", max_lines=2)
        draw.rounded_rectangle((bar_x, y + 14, bar_x + bar_w, y + 26), radius=6, fill="#ECE6DD")
        fill_w = max(4, int(bar_w * pct / max_pct))
        draw.rounded_rectangle((bar_x, y + 14, bar_x + fill_w, y + 26), radius=6, fill=color)
        draw_text_right(draw, legend_x + legend_w - 38, y + 2, f"{pct:.1f}%", font_label_bold, "#263241")

    note_y = legend_y + legend_h - 46
    if len(rows) > 10:
        draw.text((legend_x + 34, note_y), "注：右侧仅展示前 10 项，完整数据见 chart_plot_data.csv。", font=font_tiny, fill="#8A7665")
    elif zero_rows:
        zero_names = "、".join(clean_text(row.get("indicator_name")) for row in zero_rows[:3] if clean_text(row.get("indicator_name")))
        suffix = "等" if len(zero_rows) > 3 else ""
        draw.text((legend_x + 34, note_y), f"注：{zero_names}{suffix} 0% 指标不进入圆环面积。", font=font_tiny, fill="#8A7665")
    else:
        draw.text((legend_x + 34, note_y), "注：圆环面积与右侧比例均来自同一份 chart_plot_data.csv。", font=font_tiny, fill="#8A7665")
    save_png(image, out_path)
    write_weight_donut_svg(work, title, out_path.with_suffix(".svg"))


def build_weight_tree_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["weight_percent"] = pd.to_numeric(work["weight_percent"], errors="coerce").fillna(0.0)
    work = work[work["weight_percent"] > 0].copy()
    work = work[~work["indicator_name"].astype(str).isin(["合计", "总计"])].copy()
    work = work[~work["indicator_group"].astype(str).isin(["合计", "总计"])].copy()
    if work.empty:
        return pd.DataFrame(columns=["parent_indicator", "parent_weight_percent", "indicator_name", "weight_percent", "weight_percent_original", "weight_adjustment_note"])

    if "indicator_level" in work.columns and (work["indicator_level"] == "一级指标").any():
        rows = []
        primary_weights: dict[str, float] = {}
        current_parent = ""
        for _, item in work.iterrows():
            level = clean_text(item.get("indicator_level"))
            name = clean_text(item.get("indicator_name"))
            if not name:
                continue
            if level == "一级指标":
                current_parent = name
                primary_weights[current_parent] = to_float(item.get("weight_percent"))
                continue
            parent = current_parent or clean_text(item.get("indicator_group")) or "其他"
            rows.append(
                {
                    "parent_indicator": parent,
                    "parent_weight_percent": primary_weights.get(parent, 0.0),
                    "indicator_name": name,
                    "weight_percent": to_float(item.get("weight_percent")),
                    "weight_percent_original": to_float(item.get("weight_percent")),
                    "weight_adjustment_note": "",
                }
            )
        tree_df = pd.DataFrame(rows)
        if tree_df.empty:
            tree_df = work.rename(columns={"indicator_name": "parent_indicator"})[["parent_indicator", "weight_percent"]].copy()
            tree_df["parent_weight_percent"] = tree_df["weight_percent"]
            tree_df["indicator_name"] = tree_df["parent_indicator"]
            tree_df["weight_percent_original"] = tree_df["weight_percent"]
            tree_df["weight_adjustment_note"] = ""
            return tree_df[["parent_indicator", "parent_weight_percent", "indicator_name", "weight_percent", "weight_percent_original", "weight_adjustment_note"]]
        for parent, value in primary_weights.items():
            tree_df.loc[tree_df["parent_indicator"] == parent, "parent_weight_percent"] = value
        for parent, group in tree_df.groupby("parent_indicator"):
            parent_weight = float(group["parent_weight_percent"].max())
            child_sum = float(group["weight_percent"].sum())
            if parent_weight <= 0 or child_sum <= parent_weight * 1.2:
                continue
            for row_index, row in group.iterrows():
                child_weight = float(row["weight_percent"])
                if child_weight <= parent_weight:
                    continue
                other_sum = float(group.drop(index=row_index)["weight_percent"].sum())
                repaired = max(0.0, round(parent_weight - other_sum, 4))
                if 0 < repaired < child_weight:
                    tree_df.at[row_index, "weight_percent"] = repaired
                    tree_df.at[row_index, "weight_adjustment_note"] = "二级指标权重超过一级权重，绘图值按一级剩余权重修正；原始值保留在weight_percent_original"
        return tree_df

    grouped = (
        work.groupby("indicator_group", dropna=False)["weight_percent"]
        .sum()
        .reset_index()
        .rename(columns={"indicator_group": "parent_indicator", "weight_percent": "parent_weight_percent"})
    )
    tree_df = work.merge(grouped, left_on="indicator_group", right_on="parent_indicator", how="left")
    tree_df["parent_indicator"] = tree_df["parent_indicator"].map(lambda value: clean_text(value) or "其他")
    tree_df["weight_percent_original"] = tree_df["weight_percent"]
    tree_df["weight_adjustment_note"] = ""
    return tree_df[["parent_indicator", "parent_weight_percent", "indicator_name", "weight_percent", "weight_percent_original", "weight_adjustment_note"]]


def svg_escape(value: Any) -> str:
    return html.escape(clean_text(value), quote=True)


def write_weight_tree_svg(tree_df: pd.DataFrame, title: str, svg_path: Path) -> None:
    work = tree_df.copy()
    work["parent_weight_percent"] = pd.to_numeric(work["parent_weight_percent"], errors="coerce").fillna(0.0)
    work["weight_percent"] = pd.to_numeric(work["weight_percent"], errors="coerce").fillna(0.0)
    parent_order = (
        work.groupby("parent_indicator", dropna=False)["parent_weight_percent"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )[:WEIGHT_TREE_MAX_PARENTS]
    work = work[work["parent_indicator"].isin(parent_order)].copy()
    leaf_rows_by_parent = {
        parent: work[work["parent_indicator"] == parent]
        .sort_values("weight_percent", ascending=False)
        .head(WEIGHT_TREE_MAX_LEAVES_PER_PARENT)
        for parent in parent_order
    }
    leaf_count = sum(len(rows) for rows in leaf_rows_by_parent.values())
    row_h = 58
    group_gap = 28
    top = 180
    bottom = 78
    width = 2200
    height = max(760, top + leaf_count * row_h + len(parent_order) * 22 + max(0, len(parent_order) - 1) * group_gap + bottom)
    root_total = work.groupby("parent_indicator")["parent_weight_percent"].max().sum()
    if root_total <= 0:
        root_total = work["weight_percent"].sum()
    max_leaf_weight = max(float(work["weight_percent"].max()), 1.0)

    def rect(x: float, y: float, w: float, h: float, rx: float, fill: str, stroke: str = "none", sw: float = 1) -> str:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"/>'

    def line(x1: float, y1: float, x2: float, y2: float, stroke: str, sw: float = 1) -> str:
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw:.1f}" stroke-linecap="round"/>'

    def circle(cx: float, cy: float, r: float, fill: str) -> str:
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"/>'

    def text(x: float, y: float, value: Any, size: int, fill: str, weight: int = 400, anchor: str = "start") -> str:
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" dominant-baseline="middle">{svg_escape(value)}</text>'
        )

    elements: list[str] = [
        rect(0, 0, width, height, 0, "#F7F3EC"),
        rect(42, 30, width - 84, height - 64, 34, "#FFFCF6", "#E5DCCE", 2),
        text(72, 76, title, 44, "#15212E", 700),
        text(76, 123, "左侧展示评价体系总量，中间展示一级维度，右侧用比例条展示二级指标权重", 21, "#667085"),
    ]

    parent_x0, parent_x1 = 382, 752
    leaf_x0, leaf_x1 = 880, 2058
    leaf_name_x = leaf_x0 + 54
    leaf_bar_x = leaf_x1 - 382
    leaf_bar_w = 250
    leaf_pct_x = leaf_x1 - 26
    palette = ["#214E6F", "#B55C5D", "#4F8A6D", "#8773A8", "#D9824B", "#6B7280"]
    spine_x = 338
    block_specs: list[dict[str, Any]] = []
    current_y = top
    for idx, parent in enumerate(parent_order):
        parent_rows = leaf_rows_by_parent[parent]
        weight_value = float(work[work["parent_indicator"] == parent]["parent_weight_percent"].max())
        block_h = max(92, len(parent_rows) * row_h + 22)
        parent_box = (parent_x0, current_y + max(0, (block_h - 80) / 2), parent_x1, current_y + max(0, (block_h - 80) / 2) + 80)
        block_specs.append({"parent": parent, "rows": parent_rows, "weight": weight_value, "box": parent_box, "top": current_y, "height": block_h, "color": palette[idx % len(palette)]})
        current_y += block_h + group_gap

    if block_specs:
        content_top = block_specs[0]["top"]
        content_bottom = block_specs[-1]["top"] + block_specs[-1]["height"]
        root_mid = (content_top + content_bottom) / 2
        spine_top = content_top + 24
        spine_bottom = content_bottom - 24
    else:
        root_mid = top + 90
        spine_top = top + 24
        spine_bottom = top + 156
    root_box = (80, root_mid - 65, 292, root_mid + 65)
    elements.extend(
        [
            rect(root_box[0], root_box[1], root_box[2] - root_box[0], root_box[3] - root_box[1], 20, "#FFFFFF", "#263241", 3),
            text((root_box[0] + root_box[2]) / 2, root_box[1] + 45, "指标体系", 28, "#15212E", 700, "middle"),
            text((root_box[0] + root_box[2]) / 2, root_box[1] + 95, f"{root_total:.1f}%", 30, "#52606D", 700, "middle"),
        ]
    )

    if block_specs:
        elements.append(line(root_box[2], root_mid, spine_x, root_mid, "#A9B1BC", 2))
        elements.append(line(spine_x, spine_top, spine_x, spine_bottom, "#D2D8E0", 3))

    for item in block_specs:
        parent_rows = item["rows"]
        weight_value = float(item["weight"])
        parent_box = item["box"]
        block_top = item["top"]
        block_h = item["height"]
        color = item["color"]
        parent_mid = (parent_box[1] + parent_box[3]) / 2
        elements.append(line(spine_x, parent_mid, parent_box[0], parent_mid, color, max(2, min(8, int(weight_value / max(root_total, 1.0) * 16)))))
        elements.append(rect(parent_box[0], parent_box[1], parent_box[2] - parent_box[0], parent_box[3] - parent_box[1], 18, "#FFFFFF", color, 3))
        elements.append(rect(parent_box[0] + 18, parent_box[1] + 52, parent_box[2] - parent_box[0] - 36, 10, 5, "#EEE6DC"))
        elements.append(rect(parent_box[0] + 18, parent_box[1] + 52, (parent_box[2] - parent_box[0] - 36) * weight_value / max(root_total, 1.0), 10, 5, color))
        elements.append(text(parent_box[0] + 18, parent_box[1] + 30, item["parent"], 24, color, 700))
        elements.append(text(parent_box[2] - 18, parent_box[1] + 31, f"{weight_value:.1f}%", 26, color, 700, "end"))

        elements.append(rect(leaf_x0 - 20, block_top - 4, leaf_x1 - leaf_x0 + 38, block_h - 10, 18, "#FFFFFF", "#E9DED0", 1))
        elements.append(line(parent_box[2], parent_mid, leaf_x0 - 20, parent_mid, color, 2))
        branch_x = leaf_x0 + 16
        if len(parent_rows) > 1:
            elements.append(line(branch_x, block_top + 29, branch_x, block_top + (len(parent_rows) - 1) * row_h + 29, color, 2))
        for leaf_idx, (_, leaf) in enumerate(parent_rows.iterrows()):
            y = block_top + 8 + leaf_idx * row_h
            leaf_weight = float(leaf["weight_percent"])
            if leaf_idx % 2 == 0:
                elements.append(rect(leaf_x0 + 32, y, leaf_x1 - leaf_x0 - 44, 44, 12, "#FBF8F2"))
            elements.append(line(branch_x, y + 22, leaf_x0 + 32, y + 22, color, 2))
            elements.append(circle(leaf_x0 + 12, y + 20, 7, color))
            elements.append(text(leaf_name_x, y + 23, leaf["indicator_name"], 21, "#1F2933"))
            elements.append(rect(leaf_bar_x, y + 17, leaf_bar_w, 12, 6, "#ECE6DD"))
            elements.append(rect(leaf_bar_x, y + 17, max(6, leaf_bar_w * leaf_weight / max_leaf_weight), 12, 6, color))
            elements.append(text(leaf_pct_x, y + 23, f"{leaf_weight:.1f}%", 22, "#263241", 700, "end"))

    note = (
        "图中展示主要一级维度下权重较高的二级指标，完整权重明细保留在 chart_tree_data.csv 中。"
        if len(work) > leaf_count
        else "一级维度权重与二级指标权重均来自 chart_tree_data.csv，图中比例条按最大二级指标权重归一化。"
    )
    elements.append(text(76, height - 58, f"注：{note}", 16, "#8A7665"))
    svg = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<style>text{font-family:"Microsoft YaHei","SimHei","Arial",sans-serif;}</style>',
            *elements,
            "</svg>",
        ]
    )
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


def render_weight_tree(tree_df: pd.DataFrame, title: str, out_path: Path) -> None:
    work = tree_df.copy()
    work["parent_weight_percent"] = pd.to_numeric(work["parent_weight_percent"], errors="coerce").fillna(0.0)
    work["weight_percent"] = pd.to_numeric(work["weight_percent"], errors="coerce").fillna(0.0)
    parent_order = (
        work.groupby("parent_indicator", dropna=False)["parent_weight_percent"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    parent_order = parent_order[:WEIGHT_TREE_MAX_PARENTS]
    work = work[work["parent_indicator"].isin(parent_order)].copy()

    leaf_rows_by_parent = {
        parent: work[work["parent_indicator"] == parent]
        .sort_values("weight_percent", ascending=False)
        .head(WEIGHT_TREE_MAX_LEAVES_PER_PARENT)
        for parent in parent_order
    }
    leaf_count = sum(len(rows) for rows in leaf_rows_by_parent.values())
    row_h = 58
    group_gap = 28
    top = 180
    bottom = 78
    width = 2200
    height = max(760, top + leaf_count * row_h + len(parent_order) * 22 + max(0, len(parent_order) - 1) * group_gap + bottom)

    scale = 2
    image = Image.new("RGB", (width * scale, height * scale), "#F7F3EC")
    draw = ImageDraw.Draw(image)

    def p(value: float) -> int:
        return int(round(value * scale))

    def box(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(p(value) for value in values)

    def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
        return load_font(size * scale, bold)

    def line(points: tuple[float, float, float, float], fill: str, width_px: int = 1) -> None:
        draw.line(tuple(p(value) for value in points), fill=fill, width=max(1, p(width_px)))

    def rounded(values: tuple[float, float, float, float], radius: int, fill: str, outline: str | None = None, width_px: int = 1) -> None:
        draw.rounded_rectangle(box(values), radius=p(radius), fill=fill, outline=outline, width=max(1, p(width_px)))

    def text(x: float, y: float, value: str, font_obj: ImageFont.ImageFont, fill: str) -> None:
        draw.text((p(x), p(y)), value, font=font_obj, fill=fill)

    def text_box(values: tuple[float, float, float, float], value: Any, font_obj: ImageFont.ImageFont, fill: str, align: str = "left", max_lines: int = 2) -> None:
        draw_text_box(draw, box(values), value, font_obj, fill, align, max_lines=max_lines)

    def text_right(x: float, y: float, value: str, font_obj: ImageFont.ImageFont, fill: str) -> None:
        draw_text_right(draw, p(x), p(y), value, font_obj, fill)

    font_title = font(44, True)
    font_sub = font(21)
    font_root = font(28, True)
    font_root_pct = font(30, True)
    font_parent = font(24, True)
    font_parent_pct = font(26, True)
    font_leaf = font(21)
    font_leaf_pct = font(22, True)
    font_note = font(16)

    rounded((42, 30, width - 42, height - 34), 34, "#FFFCF6", "#E5DCCE", 2)
    text_box((72, 48, 1220, 104), title, font_title, "#15212E", "left", max_lines=1)
    text(76, 112, "左侧展示评价体系总量，中间展示一级维度，右侧用比例条展示二级指标权重", font_sub, "#667085")

    root_total = work.groupby("parent_indicator")["parent_weight_percent"].max().sum()
    if root_total <= 0:
        root_total = work["weight_percent"].sum()
    max_leaf_weight = max(float(work["weight_percent"].max()), 1.0)

    parent_x0, parent_x1 = 382, 752
    leaf_x0, leaf_x1 = 880, 2058
    leaf_name_x = leaf_x0 + 54
    leaf_bar_x = leaf_x1 - 382
    leaf_bar_w = 250
    leaf_pct_x = leaf_x1 - 26
    palette = ["#214E6F", "#B55C5D", "#4F8A6D", "#8773A8", "#D9824B", "#6B7280"]
    spine_x = 338
    block_specs: list[dict[str, Any]] = []
    current_y = top
    for idx, parent in enumerate(parent_order):
        parent_rows = leaf_rows_by_parent[parent]
        weight = float(work[work["parent_indicator"] == parent]["parent_weight_percent"].max())
        block_h = max(92, len(parent_rows) * row_h + 22)
        parent_box = (parent_x0, current_y + max(0, (block_h - 80) / 2), parent_x1, current_y + max(0, (block_h - 80) / 2) + 80)
        block_specs.append({"parent": parent, "rows": parent_rows, "weight": weight, "box": parent_box, "top": current_y, "height": block_h, "color": palette[idx % len(palette)]})
        current_y += block_h + group_gap

    if block_specs:
        content_top = block_specs[0]["top"]
        content_bottom = block_specs[-1]["top"] + block_specs[-1]["height"]
        root_mid = (content_top + content_bottom) / 2
        spine_top = content_top + 24
        spine_bottom = content_bottom - 24
    else:
        root_mid = top + 90
        spine_top = top + 24
        spine_bottom = top + 156
    root_box = (80, root_mid - 65, 292, root_mid + 65)
    rounded(root_box, 20, "#FFFFFF", "#263241", 3)
    text_box((root_box[0] + 18, root_box[1] + 20, root_box[2] - 18, root_box[1] + 68), "指标体系", font_root, "#15212E", "center", max_lines=1)
    draw_center(draw, box((root_box[0], root_box[1] + 72, root_box[2], root_box[3] - 18)), f"{root_total:.1f}%", font_root_pct, "#52606D")

    if block_specs:
        line((root_box[2], root_mid, spine_x, root_mid), "#A9B1BC", 2)
        line((spine_x, spine_top, spine_x, spine_bottom), "#D2D8E0", 3)

    for item in block_specs:
        parent = item["parent"]
        parent_rows = item["rows"]
        weight = item["weight"]
        parent_box = item["box"]
        block_top = item["top"]
        block_h = item["height"]
        color = item["color"]
        parent_mid = (parent_box[1] + parent_box[3]) / 2
        line((spine_x, parent_mid, parent_box[0], parent_mid), color, max(2, min(8, int(weight / max(root_total, 1.0) * 16))))
        rounded(parent_box, 18, "#FFFFFF", color, 3)
        rounded((parent_box[0] + 18, parent_box[1] + 52, parent_box[2] - 18, parent_box[1] + 62), 5, "#EEE6DC")
        rounded((parent_box[0] + 18, parent_box[1] + 52, parent_box[0] + 18 + (parent_box[2] - parent_box[0] - 36) * weight / max(root_total, 1.0), parent_box[1] + 62), 5, color)
        text_box((parent_box[0] + 18, parent_box[1] + 8, parent_box[2] - 118, parent_box[1] + 48), parent, font_parent, color, "left", max_lines=1)
        text_right(parent_box[2] - 18, parent_box[1] + 10, f"{weight:.1f}%", font_parent_pct, color)

        group_card = (leaf_x0 - 20, block_top - 4, leaf_x1 + 18, block_top + block_h - 14)
        rounded(group_card, 18, "#FFFFFF", "#E9DED0", 1)
        line((parent_box[2], parent_mid, leaf_x0 - 20, parent_mid), color, 2)
        branch_x = leaf_x0 + 16
        if len(parent_rows) > 1:
            line((branch_x, block_top + 29, branch_x, block_top + (len(parent_rows) - 1) * row_h + 29), color, 2)
        for leaf_idx, (_, leaf) in enumerate(parent_rows.iterrows()):
            y = block_top + 8 + leaf_idx * row_h
            weight = float(leaf["weight_percent"])
            row_box = (leaf_x0 + 32, y, leaf_x1 - 12, y + 44)
            if leaf_idx % 2 == 0:
                rounded(row_box, 12, "#FBF8F2")
            line((branch_x, y + 22, leaf_x0 + 32, y + 22), color, 2)
            draw.ellipse(box((leaf_x0 + 5, y + 13, leaf_x0 + 19, y + 27)), fill=color)
            label = clean_text(leaf["indicator_name"])
            text_box((leaf_name_x, y + 3, leaf_bar_x - 28, y + 41), label, font_leaf, "#1F2933", "left", max_lines=1)
            rounded((leaf_bar_x, y + 17, leaf_bar_x + leaf_bar_w, y + 29), 6, "#ECE6DD")
            fill_w = max(6, leaf_bar_w * weight / max_leaf_weight)
            rounded((leaf_bar_x, y + 17, leaf_bar_x + fill_w, y + 29), 6, color)
            text_right(leaf_pct_x, y + 6, f"{weight:.1f}%", font_leaf_pct, "#263241")

    if len(work) > leaf_count:
        text(76, height - 58, "注：图中展示主要一级维度下权重较高的二级指标，完整权重明细保留在 chart_tree_data.csv 中。", font_note, "#8A7665")
    else:
        text(76, height - 58, "注：一级维度权重与二级指标权重均来自 chart_tree_data.csv，图中比例条按最大二级指标权重归一化。", font_note, "#8A7665")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_png(image, out_path)
    with Image.open(out_path) as check:
        check.verify()
    write_weight_tree_svg(tree_df, title, out_path.with_suffix(".svg"))


def build_weight_artifact(run_dir: Path, subject: dict[str, Any], source: str, artifact_id: str, title_source: str) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    weights = read_weights()
    overview_candidates = latest_overview_subject_areas(run_dir, source)
    if source == "THE" and overview_candidates:
        candidates = ordered_unique([item for value in overview_candidates for item in [value, canonical_the_area(value)] if item])
    else:
        candidates = overview_candidates or candidate_weight_areas(subject, source)
    candidates = expand_weight_area_candidates(source, candidates)
    df, area = find_weight_subset(weights, source, candidates)
    if df.empty and overview_candidates:
        return {
            "artifact_id": artifact_id,
            "status": "skipped",
            "reason": f"missing selected-source weight: {source}/{';'.join(overview_candidates)}",
        }
    if df.empty and source == "THE":
        df, area = find_weight_subset(weights, source, ["自然科学"])
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing weight: {source}/{area}"}
    expected_area = expected_ranking_area(subject, source)
    if source == "THE" and valid_mapping_value(subject.get("the_subject_area")):
        display_area = valid_mapping_value(subject.get("the_subject_area"))
    elif source == "QS" and valid_mapping_value(expected_area):
        display_area = valid_mapping_value(expected_area)
    elif overview_candidates and len(overview_candidates) == 1:
        overview_area = valid_mapping_value(overview_candidates[0])
        display_area = overview_area if normalize_text_key(overview_area) == normalize_text_key(area) else area
    else:
        display_area = expected_area or area
    if source in {"QS", "US News", "软科", "THE"} and display_area and area and normalize_text_key(display_area) != normalize_text_key(area):
        df = df.copy()
        df["source_ranking_subject_or_area"] = df["ranking_subject_or_area"]
        df["ranking_subject_or_area"] = display_area
    plot_df = df
    if "indicator_level" in df.columns:
        first_level = df[df["indicator_level"] == "一级指标"].copy()
        if not first_level.empty:
            plot_df = first_level
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    plot_df.to_csv(out / "chart_plot_data.csv", index=False, encoding="utf-8-sig")
    source_trace_columns = ["source_file", "source_sheet", "source_row", "ranking_source", "ranking_subject_or_area", "indicator_name", "weight_percent"]
    if "source_ranking_subject_or_area" in df.columns:
        source_trace_columns.append("source_ranking_subject_or_area")
    df[source_trace_columns].to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    if source in {"US News", "THE"}:
        tree_df = build_weight_tree_data(df)
        tree_df.to_csv(out / "chart_tree_data.csv", index=False, encoding="utf-8-sig")
        render_weight_tree(tree_df, f"{title_source}{display_area or area}口径指标权重", out / "chart.png")
        chart_type = "hierarchical weight tree"
    else:
        render_weight(plot_df, f"{title_source}{display_area or area}口径指标权重", out / "chart.png")
        chart_type = "donut weight chart"
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(df),
        len(df),
        {
            "ranking_source": source,
            "ranking_subject_or_area": display_area or area,
            "source_ranking_subject_or_area": area,
            "candidate_subject_or_areas": candidates[:12],
            "plot_rows": len(plot_df),
            "plot_weight_total": float(plot_df["weight_percent"].sum()),
            "chart_type": chart_type,
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def ranked_sources_with_tongji_latest(run_dir: Path) -> set[str]:
    path = run_dir / "ranking_availability.csv"
    if not path.exists():
        return set(RANKING_SOURCES)
    df = read_external_csv(path)
    if df.empty or "ranking_source" not in df.columns:
        return set(RANKING_SOURCES)
    if "tongji_latest_rows" not in df.columns:
        return set(RANKING_SOURCES)
    rows = df[pd.to_numeric(df["tongji_latest_rows"], errors="coerce").fillna(0) > 0]
    return {clean_text(value) for value in rows["ranking_source"].tolist() if clean_text(value)}


def ranked_sources_with_peer_latest(run_dir: Path) -> set[str]:
    path = run_dir / "ranking_availability.csv"
    if not path.exists():
        return set(RANKING_SOURCES)
    df = read_external_csv(path)
    if df.empty or "ranking_source" not in df.columns or "mainland_top200_rows" not in df.columns:
        return set(RANKING_SOURCES)
    rows = df[pd.to_numeric(df["mainland_top200_rows"], errors="coerce").fillna(0) > 0]
    return {clean_text(value) for value in rows["ranking_source"].tolist() if clean_text(value)}


def render_commonality_flow(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 940), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(36, True)
    font_sub = load_font(20)
    font_node = load_font(20, True)
    font_small = load_font(15)
    present_sources = [source for source in RANKING_SOURCES if source in set(df["ranking_source"].map(clean_text))]
    source_count_text = "四大国际排名" if len(present_sources) >= 4 else f"{len(present_sources)}类可用国际排名"
    draw.text((70, 42), f"{subject_name}学科{source_count_text}指标共性", font=font_title, fill="#16202A")
    draw.text((70, 88), "仅纳入已有同济最新综合排名的榜单；按指标组归并展示权重或分项覆盖", font=font_sub, fill="#5A6573")

    groups = sorted(df["indicator_group"].dropna().unique().tolist(), key=lambda g: (-df[df["indicator_group"] == g]["link_value"].sum(), g))
    source_y = {source: 220 + idx * 170 for idx, source in enumerate(present_sources)}
    group_step = min(92, 590 // max(1, len(groups)))
    group_y = {group: 155 + idx * group_step for idx, group in enumerate(groups)}
    sx, gx = 155, 1120
    for source in present_sources:
        color = SOURCE_COLORS[source]
        y = source_y[source]
        draw.rounded_rectangle((sx, y, sx + 210, y + 70), radius=12, fill="#F8FAFC", outline=color, width=3)
        draw_center(draw, (sx, y, sx + 210, y + 70), display_ranking_source(source), font_node, color)
    for group in groups:
        color = GROUP_COLORS.get(group, "#9AA4B2")
        y = group_y[group]
        total = df[df["indicator_group"] == group]["link_value"].sum()
        draw.rounded_rectangle((gx, y, gx + 300, y + 62), radius=12, fill="#FFFFFF", outline=color, width=3)
        draw.text((gx + 18, y + 10), group, font=font_node, fill=color)
        draw.text((gx + 218, y + 16), f"{total:.1f}", font=font_small, fill="#697586")
    for _, row in df.iterrows():
        source = row["ranking_source"]
        group = row["indicator_group"]
        color = GROUP_COLORS.get(group, "#9AA4B2")
        y1 = source_y.get(source, 190) + 35
        y2 = group_y.get(group, 155) + 31
        width = max(2, min(16, int(to_float(row["link_value"]) / 4) + 2))
        draw.line((sx + 210, y1, gx, y2), fill=color, width=width)
    draw.text((70, 850), "注：未形成同济最新综合排名的榜单不纳入本图，避免方法权重与实际排名口径混用。", font=font_small, fill="#697586")
    save_png(image, out_path)


def build_figure_02(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_02_ranking_indicator_commonality"
    out = artifact_dir(run_dir, artifact_id)
    weights = read_weights()
    indicators = read_indicators()
    parts = []
    ranked_sources = ranked_sources_with_tongji_latest(run_dir)
    for source in RANKING_SOURCES:
        if source not in ranked_sources:
            continue
        overview_candidates = latest_overview_subject_areas(run_dir, source)
        if source == "THE" and overview_candidates:
            weight_candidates = ordered_unique([item for value in overview_candidates for item in [value, canonical_the_area(value)] if item])
        else:
            weight_candidates = overview_candidates or candidate_weight_areas(subject, source)
        subset, area = find_weight_subset(weights, source, weight_candidates)
        if subset.empty and source == "THE" and not overview_candidates:
            subset, area = find_weight_subset(weights, source, ["自然科学"])
        if not subset.empty:
            plot_subset = subset
            first_level = subset[subset.get("indicator_level", "") == "一级指标"].copy() if "indicator_level" in subset.columns else pd.DataFrame()
            if source == "THE" and not first_level.empty:
                plot_subset = first_level
            plot_subset = plot_subset.copy()
            display_area = (
                valid_mapping_value(subject.get("the_subject_area"))
                if source == "THE" and valid_mapping_value(subject.get("the_subject_area"))
                else overview_candidates[0] if overview_candidates else (expected_ranking_area(subject, source) or area)
            )
            if display_area and area and normalize_text_key(display_area) != normalize_text_key(area):
                plot_subset["source_ranking_subject_or_area"] = plot_subset["ranking_subject_or_area"]
                plot_subset["ranking_subject_or_area"] = display_area
            plot_subset["basis"] = "weight_percent"
            plot_subset["link_value"] = plot_subset["weight_percent"]
            part_columns = ["ranking_source", "ranking_subject_or_area", "indicator_name", "indicator_group", "basis", "link_value", "source_file", "source_sheet", "source_row"]
            if "source_ranking_subject_or_area" in plot_subset.columns:
                part_columns.append("source_ranking_subject_or_area")
            parts.append(plot_subset[part_columns])
        else:
            ind = filter_indicators_for_subject(indicators, subject, source)
            tongji = ind[ind["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
            if not tongji.empty:
                latest_release = tongji["release_year"].max()
                latest_ranking = tongji[tongji["release_year"] == latest_release]["ranking_year"].max()
                tongji = tongji[(tongji["release_year"] == latest_release) & (tongji["ranking_year"] == latest_ranking)].copy()
                tongji = tongji[tongji["metric_type"].isin(["score", "rank"])].copy()
                tongji["ranking_subject_or_area"] = expected_ranking_area(subject, source) or clean_text(subject.get("target_subject"))
                tongji["basis"] = "indicator_count_weight_missing"
                tongji["link_value"] = 1.0
                parts.append(tongji[["ranking_source", "ranking_subject_or_area", "indicator_name", "indicator_group", "basis", "link_value", "source_file", "source_sheet", "source_row"]])
    if not parts:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "no weight or indicator coverage data"}
    long_df = pd.concat(parts, ignore_index=True).fillna("")
    long_df["indicator_group_raw"] = long_df["indicator_group"]
    long_df["indicator_group"] = long_df["indicator_group"].apply(normalize_commonality_group)
    link_df = (
        long_df.groupby(["ranking_source", "ranking_subject_or_area", "indicator_group", "basis"], as_index=False)
        .agg(link_value=("link_value", "sum"), indicator_count=("indicator_name", "nunique"))
        .sort_values(["ranking_source", "indicator_group"])
    )
    link_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_commonality_flow(link_df, clean_text(subject["target_subject"]), out / "chart.png")
    write_common_outputs(out, artifact_id, "chart", len(link_df), len(long_df), {"chart_type": "indicator commonality flow"})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(link_df), "output_dir": str(out)}


def render_peer_indicator_chart(df: pd.DataFrame, title: str, out_path: Path, rank_mode: bool) -> None:
    image = Image.new("RGB", (1780, 980), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(34, True)
    font_sub = load_font(20)
    font_panel = load_font(17, True)
    font_small = load_font(14)
    draw.text((70, 38), title, font=font_title, fill="#16202A")
    draw.text((70, 82), "灰线为对标高校范围，蓝点为中位数，红点为同济大学；排名类指标数值越小越靠前", font=font_sub, fill="#5A6573")
    rows = df.to_dict("records")
    cols = 2 if len(rows) <= 6 else 3
    panel_w = 730 if cols == 2 else 500
    panel_h = 122
    start_x, start_y = 70, 150
    x_gap, y_gap = 50, 28
    for idx, row in enumerate(rows):
        col = idx % cols
        rr = idx // cols
        x = start_x + col * (panel_w + x_gap)
        y = start_y + rr * (panel_h + y_gap)
        draw.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=8, fill="#FFFFFF", outline="#D8DEE8", width=1)
        name = clean_text(row.get("indicator_short_name", "")) or clean_text(row.get("indicator_name", ""))
        draw.text((x + 16, y + 14), name[:24], font=font_panel, fill="#16202A")
        if rank_mode:
            best = to_float(row.get("peer_best_indicator_rank"))
            median = to_float(row.get("peer_median_indicator_rank"))
            worst = to_float(row.get("peer_worst_indicator_rank"))
            tongji = to_float(row.get("tongji_indicator_rank"))
        else:
            best = to_float(row.get("peer_worst_score"))
            median = to_float(row.get("peer_median_score"))
            worst = to_float(row.get("peer_best_score"))
            tongji = to_float(row.get("tongji_score"))
        min_v, max_v = min(best, median, worst, tongji), max(best, median, worst, tongji)
        if min_v == max_v:
            max_v = min_v + 1
        line_x1, line_x2 = x + 44, x + panel_w - 44
        line_y = y + 73

        def xpos(value: float) -> float:
            return line_x1 + (value - min_v) / (max_v - min_v) * (line_x2 - line_x1)

        xb, xw, xm, xt = xpos(best), xpos(worst), xpos(median), xpos(tongji)
        draw.line((min(xb, xw), line_y, max(xb, xw), line_y), fill="#B8C2D0", width=8)
        draw.ellipse((xm - 7, line_y - 7, xm + 7, line_y + 7), fill="#315D9C", outline="#FFFFFF", width=2)
        draw.ellipse((xt - 9, line_y - 9, xt + 9, line_y + 9), fill="#C64B46", outline="#FFFFFF", width=2)
        draw.text((x + 16, y + 94), f"同济：{tongji:g}", font=font_small, fill="#C64B46")
        rel = clean_text(row.get("tongji_relative_rank_with_peer_reference", ""))
        if rel:
            draw.text((x + panel_w - 180, y + 94), f"相对位次：{rel}", font=font_small, fill="#374151")
    save_png(image, out_path)


def render_peer_indicator_template_chart(plot_df: pd.DataFrame, title: str, out_path: Path) -> None:
    indicator_col = "display_indicator_name" if "display_indicator_name" in plot_df.columns else "indicator_name"
    indicators = plot_df[indicator_col].drop_duplicates().tolist()
    if not indicators:
        return
    university_order = (
        plot_df[["display_university", "_university_key", "peer_order", "is_tongji"]]
        .drop_duplicates("_university_key")
        .sort_values(["peer_order", "display_university"])
        .reset_index(drop=True)
    )
    if university_order.empty:
        return
    name_count = len(university_order)
    left = 150
    right = 56
    title_y = 32
    subtitle_top = 82
    subtitle_box_h = 56
    header_top = 152
    top = 226
    bottom = 72
    column_gap = 18
    column_w = 228 if len(indicators) <= 5 else 208 if len(indicators) <= 7 else 184
    width = max(1350, left + right + len(indicators) * column_w + (len(indicators) - 1) * column_gap)
    row_step = 20 if name_count <= 45 else 15 if name_count <= 75 else 11
    plot_h = max(520, min(940, row_step * max(1, name_count - 1)))
    height = top + plot_h + bottom

    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    title_font_size = 34
    font_title = load_font(title_font_size, True)
    font_sub = load_font(20)
    font_indicator = load_font(16 if len(indicators) >= 8 else 18, True)
    font_axis = load_font(16, True)
    font_name = load_font(15 if name_count <= 70 else 13)
    font_value = load_font(15, True)
    while title_font_size > 22 and text_size(draw, title, font_title)[0] > width - 104:
        title_font_size -= 2
        font_title = load_font(title_font_size, True)
    draw.text((52, title_y), title, font=font_title, fill="#16202A")
    draw_text_box(
        draw,
        (52, subtitle_top, width - 52, subtitle_top + subtitle_box_h),
        "模板样式：纵轴为对标高校，横向分列为分项指标；蓝线为高校序列，红点为同济大学。",
        font_sub,
        "#5A6573",
        "left",
        max_lines=2,
    )

    key_to_y = {
        clean_text(row["_university_key"]): top + idx / max(1, name_count - 1) * plot_h
        for idx, row in university_order.iterrows()
    }
    label_stride = 1 if name_count <= 42 else 2 if name_count <= 70 else 4
    for idx, row in university_order.iterrows():
        key = clean_text(row["_university_key"])
        y = key_to_y[key]
        is_tongji = str(row.get("is_tongji", "")).lower() in {"true", "1"}
        if idx % label_stride == 0 or is_tongji or idx in {0, name_count - 1}:
            name = clean_text(row.get("display_university"))[:10]
            fill = "#C64B46" if is_tongji else "#52606D"
            draw_text_right(draw, left - 12, int(y - 7), name, font_name, fill)

    plot_bottom = top + plot_h
    for idx, indicator in enumerate(indicators):
        group = plot_df[plot_df[indicator_col] == indicator].copy().sort_values("peer_order")
        if group.empty:
            continue
        x0 = left + idx * (column_w + column_gap)
        x1 = x0 + column_w
        draw.line((x0 - 9, top - 8, x0 - 9, plot_bottom + 26), fill="#D7DEE8", width=3)
        draw_text_box(draw, (x0, header_top, x1, top - 20), clean_text(indicator), font_indicator, "#16202A", "center", max_lines=3)
        values = pd.to_numeric(group["display_rank"], errors="coerce").dropna()
        if values.empty:
            continue
        min_v = max(0.0, math.floor(float(values.min()) / 50) * 50)
        max_v = max(float(values.max()), min_v + 1)
        if max_v <= 10:
            min_v = 0.0
            max_v = max(10.0, max_v)
        for frac in [0, 0.5, 1]:
            x = x0 + frac * (x1 - x0)
            draw.line((x, top, x, plot_bottom), fill="#EEF2F7", width=2)
        draw.line((x0, top, x0, plot_bottom), fill="#C7D0DD", width=2)
        draw.line((x0, plot_bottom, x1, plot_bottom), fill="#C7D0DD", width=2)

        points = []
        for _, item in group.iterrows():
            value = to_float(item.get("display_rank"), default=math.nan)
            key = clean_text(item.get("_university_key"))
            if math.isnan(value) or key not in key_to_y:
                continue
            x = x0 + (value - min_v) / (max_v - min_v) * (x1 - x0)
            y = key_to_y[key]
            points.append((x, y, item))
        if len(points) >= 2:
            draw.line([(x, y) for x, y, _ in points], fill="#6EA0E6", width=5)
        for x, y, item in points:
            is_tongji = str(item.get("is_tongji", "")).lower() in {"true", "1"}
            color = "#C64B46" if is_tongji else "#4F83CC"
            radius = 8 if is_tongji else 4
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#FFFFFF", width=2)
            if is_tongji:
                draw.text((x + 7, y - 8), clean_text(item.get("display_rank")), font=font_value, fill=color)
        draw.text((x0 - 2, plot_bottom + 12), f"{min_v:g}", font=font_axis, fill="#697586")
        draw_text_right(draw, x1 + 2, plot_bottom + 12, f"{max_v:g}", font_axis, "#697586")
    save_png(image, out_path)


def render_peer_indicator_line_chart(plot_df: pd.DataFrame, title: str, out_path: Path) -> None:
    indicators = plot_df["indicator_name"].drop_duplicates().tolist()
    if not indicators:
        return
    cols = 2 if len(indicators) <= 8 else 3
    panel_w = 780 if cols == 2 else 520
    panel_h = 250
    left, top = 70, 126
    x_gap, y_gap = 52, 52
    rows = math.ceil(len(indicators) / cols)
    width = left * 2 + cols * panel_w + (cols - 1) * x_gap
    height = top + rows * panel_h + (rows - 1) * y_gap + 70
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(34, True)
    font_sub = load_font(18)
    font_panel = load_font(17, True)
    font_small = load_font(12)
    draw.text((left, 38), title, font=font_title, fill="#16202A")
    draw.text((left, 82), "横轴为对标高校，纵轴为相对排名或指标排名；数值越小表示相对表现越靠前，红点为同济大学。", font=font_sub, fill="#5A6573")
    for idx, indicator in enumerate(indicators):
        group = plot_df[plot_df["indicator_name"] == indicator].copy()
        group = group.sort_values("peer_order")
        if group.empty:
            continue
        col = idx % cols
        row = idx // cols
        x0 = left + col * (panel_w + x_gap)
        y0 = top + row * (panel_h + y_gap)
        draw.rectangle((x0, y0, x0 + panel_w, y0 + panel_h), fill="#FFFFFF", outline="#D8DEE8")
        draw.text((x0 + 14, y0 + 10), clean_text(indicator)[:28], font=font_panel, fill="#16202A")
        chart_left, chart_top = x0 + 54, y0 + 48
        chart_right, chart_bottom = x0 + panel_w - 24, y0 + panel_h - 42
        values = pd.to_numeric(group["display_rank"], errors="coerce").dropna()
        if values.empty:
            continue
        min_v = max(1, math.floor(float(values.min()) / 50) * 50)
        max_v = max(float(values.max()), min_v + 1)
        for frac in [0, 0.5, 1]:
            y = chart_top + frac * (chart_bottom - chart_top)
            draw.line((chart_left, y, chart_right, y), fill="#EEF2F7")
        draw.line((chart_left, chart_top, chart_left, chart_bottom), fill="#C7D0DD")
        draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill="#C7D0DD")
        points = []
        n = max(1, len(group) - 1)
        for pos, (_, item) in enumerate(group.iterrows()):
            value = to_float(item.get("display_rank"), default=math.nan)
            if math.isnan(value):
                continue
            x = chart_left + pos / n * (chart_right - chart_left)
            y = chart_top + (value - min_v) / (max_v - min_v) * (chart_bottom - chart_top)
            points.append((x, y, item))
        if len(points) >= 2:
            draw.line([(x, y) for x, y, _ in points], fill="#6EA0E6", width=3)
        for x, y, item in points:
            is_tongji = str(item.get("is_tongji", "")).lower() in {"true", "1"}
            color = "#C64B46" if is_tongji else "#4F83CC"
            radius = 6 if is_tongji else 3
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#FFFFFF", width=1)
            if is_tongji:
                draw.text((x + 8, y - 9), clean_text(item.get("display_rank")), font=font_small, fill=color)
        first_name = clean_text(group.iloc[0].get("display_university"))
        last_name = clean_text(group.iloc[-1].get("display_university"))
        draw.text((chart_left, chart_bottom + 12), first_name[:7], font=font_small, fill="#697586")
        draw.text((chart_right - 72, chart_bottom + 12), last_name[:7], font=font_small, fill="#697586")
    save_png(image, out_path)


def render_peer_indicator_summary_chart(chart_df: pd.DataFrame, title: str, out_path: Path) -> None:
    work = chart_df.copy()
    rank_col = "tongji_relative_rank_with_peer_reference"
    if rank_col not in work.columns:
        rank_col = "tongji_relative_rank_in_peer_scope"
    size_col = "peer_scope_size" if "peer_scope_size" in work.columns else "comparison_scope_size"
    work[rank_col] = pd.to_numeric(work[rank_col], errors="coerce")
    work[size_col] = pd.to_numeric(work[size_col], errors="coerce")
    work = work.dropna(subset=[rank_col, size_col]).copy()
    if work.empty:
        return
    work = work.sort_values([rank_col, "display_indicator_name" if "display_indicator_name" in work.columns else "indicator_name"])

    width = 1760
    row_h = 76
    top = 220
    bottom = 62
    height = max(780, top + len(work) * row_h + bottom)
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(42, True)
    font_sub = load_font(24)
    font_label = load_font(25, True)
    font_small = load_font(22)
    font_value = load_font(24, True)
    draw_text_box(draw, (50, 24, width - 64, 122), title, font_title, "#16202A", "left", max_lines=2)
    draw.text((50, 138), "每条标尺表示一个分项指标的对标范围；红点越靠左，说明同济大学相对位次越靠前。", font=font_sub, fill="#5A6573")

    label_left = 70
    label_right = 520
    track_left = 560
    track_right = 1468
    value_left = 1502
    for idx, (_, row) in enumerate(work.iterrows()):
        y = top + idx * row_h
        indicator = clean_text(row.get("display_indicator_name", "")) or clean_text(row.get("indicator_short_name", "")) or clean_text(row.get("indicator_name", ""))
        rank = max(1.0, float(row[rank_col]))
        size = max(rank, float(row[size_col]))
        percentile = max(0.0, min(1.0, (size - rank) / max(size - 1, 1)))
        marker_x = track_left + (rank - 1) / max(size - 1, 1) * (track_right - track_left)
        color = "#C64B46" if percentile < 0.5 else "#D68A35" if percentile < 0.75 else "#315D9C"

        if idx % 2 == 0:
            draw.rounded_rectangle((48, y - 12, width - 60, y + 48), radius=8, fill="#F7F9FC")
        draw_text_box(draw, (label_left, y - 10, label_right, y + 50), indicator, font_label, "#1F2933", "left", max_lines=2)
        draw.line((track_left, y + 20, track_right, y + 20), fill="#D7DEE8", width=13)
        draw.line((track_left, y + 20, marker_x, y + 20), fill=color, width=13)
        for frac, text in [(0, "靠前"), (0.5, "中位"), (1, "靠后")]:
            x = track_left + frac * (track_right - track_left)
            draw.line((x, y + 3, x, y + 37), fill="#AAB4C3", width=3)
            if idx == 0:
                draw_center(draw, (x - 38, y - 48, x + 38, y - 18), text, font_small, "#697586")
        draw.ellipse((marker_x - 16, y + 4, marker_x + 16, y + 36), fill="#C64B46", outline="#FFFFFF", width=4)
        draw.text((value_left, y - 1), f"第{int(rank)} / {int(size)}位", font=font_value, fill="#C64B46")
        draw.text((value_left, y + 34), f"前{percentile * 100:.1f}%", font=font_small, fill="#52606D")

    draw.text((58, height - 44), "注：相对位次按同一排名口径下的内地对标高校范围计算；不同榜单分项指标含义不同，不宜跨榜单直接等同。", font=font_small, fill="#697586")
    save_png(image, out_path)


def relative_rank(values: pd.Series, tongji_value: float, higher_better: bool) -> int:
    numeric = pd.to_numeric(values, errors="coerce").dropna().tolist()
    numeric.append(tongji_value)
    ordered = sorted(numeric, reverse=higher_better)
    for idx, value in enumerate(ordered, start=1):
        if value == tongji_value:
            return idx
    return len(ordered)


def display_university(row: pd.Series) -> str:
    cn = clean_text(row.get("university_name_cn"))
    return cn or clean_text(row.get("university_name_en"))


def university_province_key(value: Any) -> str:
    name = clean_text(value)
    return re.sub(r"[（(].*?[）)]", "", name).strip()


def load_university_province_map() -> dict[str, str]:
    if not UNIVERSITY_PROVINCE_CSV.exists():
        return {}
    df = read_external_csv(UNIVERSITY_PROVINCE_CSV)
    if df.empty or "university_name_cn" not in df.columns or "province" not in df.columns:
        return {}
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        name = clean_text(row.get("university_name_cn"))
        province = clean_text(row.get("province"))
        if name and province and name not in mapping:
            mapping[name] = province
        key = university_province_key(name)
        if key and province and key not in mapping:
            mapping[key] = province
    return mapping


def lookup_province(province_map: dict[str, str], university_name: Any) -> str:
    name = clean_text(university_name)
    return province_map.get(name) or province_map.get(university_province_key(name), "")


def build_peer_history_matrix(
    source_records: pd.DataFrame,
    latest_peers: pd.DataFrame,
    source: str,
    include_source_prefix: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if latest_peers.empty:
        return pd.DataFrame(), pd.DataFrame()
    province_map = load_university_province_map()
    top = latest_peers.copy()
    top["_display_university"] = top.apply(display_university, axis=1)
    top["_latest_midpoint"] = pd.to_numeric(top["rank_midpoint"], errors="coerce")
    top = top.sort_values(["_latest_midpoint", "_display_university"]).reset_index(drop=True)
    latest_names = {
        clean_text(value)
        for value in top.get("university_name_cn", pd.Series(dtype=str)).tolist()
        + top.get("university_name_en", pd.Series(dtype=str)).tolist()
        if clean_text(value)
    }
    history = source_records[
        source_records["university_name_cn"].isin(latest_names) | source_records["university_name_en"].isin(latest_names)
    ].copy()
    if history.empty:
        return pd.DataFrame(), history
    history["_display_university"] = history.apply(display_university, axis=1)
    history["_year"] = pd.to_numeric(history["ranking_year"], errors="coerce")
    history = history.dropna(subset=["_year"]).copy()
    history["_year"] = history["_year"].astype(int).astype(str)
    year_cols = sorted(history["_year"].dropna().unique().tolist(), key=lambda value: int(value))
    published_years = set(year_cols)
    rows = []
    for idx, peer in top.iterrows():
        name = clean_text(peer.get("_display_university"))
        peer_history = history[history["_display_university"] == name].copy()
        row_kind = clean_text(peer.get("_word_row_kind", ""))
        row_label = "同济参照" if row_kind == "tongji_reference" else str(idx + 1)
        row = {"序号/说明": row_label, "学校名称": name, "省份": lookup_province(province_map, name)}
        for year in year_cols:
            values = peer_history[peer_history["_year"] == year]["rank_raw"]
            col_name = f"{source} {year}" if include_source_prefix else year
            if not values.empty:
                row[col_name] = clean_text(values.iloc[0])
            else:
                row[col_name] = display_missing_label("not_listed") if year in published_years else display_missing_label("not_published")
        rows.append(row)
    return pd.DataFrame(rows), history


def compact_peer_scope_for_word(latest_peers: pd.DataFrame, max_rows: int = MAIN_WORD_PEER_TABLE_MAX_ROWS) -> pd.DataFrame:
    if latest_peers.empty or len(latest_peers) <= max_rows:
        compact = latest_peers.copy()
        compact["_word_row_kind"] = "top_sample"
        return compact
    compact = latest_peers.head(max_rows).copy()
    compact["_word_row_kind"] = "top_sample"
    is_tongji = latest_peers.get("is_tongji", pd.Series([""] * len(latest_peers), index=latest_peers.index)).astype(str).str.lower().isin(["true", "1"])
    tongji_rows = latest_peers[
        is_tongji
        | latest_peers.get("university_name_cn", pd.Series(dtype=str)).astype(str).str.contains("同济", na=False)
        | latest_peers.get("university_name_en", pd.Series(dtype=str)).astype(str).str.lower().str.contains("tongji", na=False)
    ].copy()
    if not tongji_rows.empty:
        compact_has_tongji = (
            compact.get("is_tongji", pd.Series([""] * len(compact), index=compact.index)).astype(str).str.lower().isin(["true", "1"]).any()
            or compact.get("university_name_cn", pd.Series(dtype=str)).astype(str).str.contains("同济", na=False).any()
            or compact.get("university_name_en", pd.Series(dtype=str)).astype(str).str.lower().str.contains("tongji", na=False).any()
        )
        if not compact_has_tongji:
            reference = tongji_rows.head(1).copy()
            reference["_word_row_kind"] = "tongji_reference"
            compact = pd.concat([compact, reference], ignore_index=True)
    return compact.reset_index(drop=True)


def build_peer_indicator_figure(
    run_dir: Path,
    subject: dict[str, Any],
    source: str,
    peer_artifact_id: str,
    artifact_id: str,
    title: str,
    rank_mode: bool,
) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    peer_scope = peer_scope_from_file(artifact_dir(run_dir, peer_artifact_id) / "latest_peer_records.csv")
    if peer_scope.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing peer scope: {peer_artifact_id}"}
    peer_scope = peer_scope[peer_scope["_university_key"].astype(str).str.len() > 0].copy()
    peer_scope["_rank_sort"] = pd.to_numeric(peer_scope.get("rank_midpoint", pd.Series(dtype=str)), errors="coerce")
    peer_scope = peer_scope.sort_values(["_rank_sort", "university_name_cn", "university_name_en"], na_position="last").copy()
    peer_order_lookup = {key: idx for idx, key in enumerate(peer_scope["_university_key"].tolist())}
    peer_keys = set(peer_scope["_university_key"])
    peer_subject_lookup = peer_scope.set_index("_university_key")[
        ["_peer_subject_raw", "_peer_subject_norm", "_peer_subject_alias"]
    ].to_dict(orient="index")
    indicators = filter_indicators_for_subject(read_indicators(), subject, source)
    if indicators.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing indicators: {source}"}
    latest_release = indicators["release_year"].max()
    latest_ranking = indicators[indicators["release_year"] == latest_release]["ranking_year"].max()
    indicators = indicators[(indicators["release_year"] == latest_release) & (indicators["ranking_year"] == latest_ranking)].copy()
    indicators["display_university"] = indicators["university_name_cn"].where(
        indicators["university_name_cn"].astype(str).str.len() > 0,
        indicators["university_name_en"],
    )
    indicators["_university_key"] = indicators.apply(university_identity, axis=1)
    indicators["_peer_subject_raw"] = indicators["_university_key"].map(
        lambda key: peer_subject_lookup.get(key, {}).get("_peer_subject_raw", "")
    )
    indicators["_peer_subject_norm"] = indicators["_university_key"].map(
        lambda key: peer_subject_lookup.get(key, {}).get("_peer_subject_norm", "")
    )
    indicators["_peer_subject_alias"] = indicators["_university_key"].map(
        lambda key: peer_subject_lookup.get(key, {}).get("_peer_subject_alias", "")
    )
    ranking_subject_raw = indicators.get("ranking_subject_raw", pd.Series([""] * len(indicators), index=indicators.index)).map(clean_text)
    ranking_subject_norm = indicators.get("ranking_subject_norm", pd.Series([""] * len(indicators), index=indicators.index)).map(clean_text)
    ranking_subject_alias = indicators.get("ranking_subject_alias", pd.Series([""] * len(indicators), index=indicators.index)).map(clean_text)
    subject_matches_peer_scope = (
        (indicators["_peer_subject_raw"] != "")
        & (
            (ranking_subject_raw == indicators["_peer_subject_raw"])
            | (ranking_subject_norm == indicators["_peer_subject_norm"])
            | (ranking_subject_alias == indicators["_peer_subject_alias"])
        )
    )
    comparison = indicators[
        (indicators["_university_key"].isin(peer_keys) & subject_matches_peer_scope)
        | indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"])
    ].copy()
    metric_type = "rank" if rank_mode else "score"
    comparison = comparison[comparison["metric_type"] == metric_type].copy()
    indicator_text = comparison["indicator_name"].astype(str)
    comparison = comparison[~indicator_text.str.contains("总得分", na=False)].copy()
    value_column = "metric_rank_midpoint" if rank_mode else "metric_value"
    comparison[value_column] = pd.to_numeric(comparison[value_column], errors="coerce")
    comparison = comparison.dropna(subset=[value_column])
    if comparison.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"no {metric_type} metrics for comparison"}
    comparison["_alias_specificity_score"] = comparison.apply(lambda row: alias_specificity_score(row, subject, source), axis=1)
    comparison["_metric_sort"] = pd.to_numeric(comparison[value_column], errors="coerce")
    comparison = comparison.sort_values(
        ["indicator_name", "_university_key", "_alias_specificity_score", "_metric_sort"],
        ascending=[True, True, True, rank_mode],
        na_position="last",
    )
    comparison = comparison.drop_duplicates(subset=["indicator_name", "_university_key"], keep="first").copy()
    if "is_tongji" in peer_scope.columns:
        expected_peer_scope_size = peer_scope[
            ~peer_scope["is_tongji"].astype(str).str.lower().isin(["true", "1"])
        ]["_university_key"].nunique()
    else:
        expected_peer_scope_size = peer_scope["_university_key"].nunique()
    min_peer_coverage = max(3, int(expected_peer_scope_size * 0.5))

    rows = []
    plot_rows = []
    for indicator, group in comparison.groupby("indicator_name"):
        display_name = peer_indicator_display_name(source, indicator, rank_mode)
        tongji = group[group["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        peers = group[~group["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        if tongji.empty or peers.empty:
            continue
        peer_n = peers["_university_key"].nunique()
        if peer_n < min_peer_coverage:
            continue
        tongji_value = float(tongji.iloc[0][value_column])
        plot_group = group.copy()
        if rank_mode:
            plot_group["display_rank"] = pd.to_numeric(plot_group[value_column], errors="coerce")
        else:
            plot_group["display_rank"] = pd.to_numeric(plot_group[value_column], errors="coerce").rank(
                ascending=False,
                method="min",
            )
        plot_group["peer_order"] = plot_group["_university_key"].map(lambda key: peer_order_lookup.get(key, len(peer_order_lookup) + 1))
        plot_group["display_rank"] = plot_group["display_rank"].round(1)
        plot_records = plot_group[
            [
                "indicator_name",
                "display_university",
                "display_rank",
                "peer_order",
                "is_tongji",
                "_university_key",
                "ranking_subject_raw",
                "source_file",
                "source_sheet",
                "source_row",
            ]
        ].to_dict("records")
        for item in plot_records:
            item["display_indicator_name"] = display_name
        plot_rows.extend(plot_records)
        if rank_mode:
            rel = relative_rank(peers[value_column], tongji_value, higher_better=False)
            rows.append(
                {
                    "indicator_name": indicator,
                    "indicator_short_name": indicator.replace("排名", "")[:8],
                    "indicator_short_name": display_name,
                    "display_indicator_name": display_name,
                    "indicator_group": clean_text(group.iloc[0].get("indicator_group", "")),
                    "peer_scope_size": peer_n,
                    "comparison_scope_size": peer_n + 1,
                    "peer_best_indicator_rank": float(peers[value_column].min()),
                    "peer_median_indicator_rank": float(peers[value_column].median()),
                    "peer_worst_indicator_rank": float(peers[value_column].max()),
                    "tongji_indicator_rank": tongji_value,
                    "tongji_relative_rank_with_peer_reference": rel,
                    "tongji_percentile_from_top": round((peer_n + 1 - rel) / max(1, peer_n) * 100, 1),
                    "tongji_in_peer_scope": clean_text(tongji.iloc[0]["_university_key"]) in peer_keys,
                }
            )
        else:
            rel = relative_rank(peers[value_column], tongji_value, higher_better=True)
            rows.append(
                {
                    "indicator_name": indicator,
                    "indicator_short_name": indicator[:8],
                    "indicator_short_name": display_name,
                    "display_indicator_name": display_name,
                    "indicator_group": clean_text(group.iloc[0].get("indicator_group", "")),
                    "peer_scope_size": peer_n,
                    "comparison_scope_size": peer_n + 1,
                    "peer_best_score": float(peers[value_column].max()),
                    "peer_median_score": float(peers[value_column].median()),
                    "peer_worst_score": float(peers[value_column].min()),
                    "tongji_score": tongji_value,
                    "tongji_relative_rank_with_peer_reference": rel,
                    "tongji_percentile_from_top": round((peer_n + 1 - rel) / max(1, peer_n) * 100, 1),
                    "tongji_in_peer_scope": clean_text(tongji.iloc[0]["_university_key"]) in peer_keys,
                }
            )
    if not rows:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "no indicators with both peers and Tongji"}
    chart_df = pd.DataFrame(rows)
    plot_df = (
        pd.DataFrame(plot_rows).sort_values(["display_indicator_name", "peer_order", "display_university"])
        if plot_rows
        else pd.DataFrame()
    )
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    plot_df.to_csv(out / "chart_plot_data.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(out / "peer_indicator_long.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_peer_indicator_summary_chart(chart_df, title, out / "chart.png")
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(chart_df),
        len(comparison),
        {
            "ranking_source": source,
            "peer_artifact_id": peer_artifact_id,
            "metric_type": metric_type,
            "chart_type": "template-style peer indicator relative ranking strips",
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(chart_df), "output_dir": str(out)}


def render_table(df: pd.DataFrame, title: str, out_path: Path, max_rows: int = 32) -> None:
    cols = [str(col) for col in df.columns.tolist()]
    display_df = df.head(max_rows).fillna("").copy()
    display_df.columns = cols
    rows = display_df.to_dict("records")
    row_h = 52
    left, top = 54, 124
    image_probe = Image.new("RGB", (10, 10), "#FFFFFF")
    probe = ImageDraw.Draw(image_probe)
    font_title = load_font(31, True)
    font_header = load_font(16, True)
    font_cell = load_font(15)

    col_widths: list[int] = []
    for idx, col in enumerate(cols):
        sample_values = [col] + [clean_text(row.get(col, "")) for row in rows[:18]]
        longest = max((text_size(probe, value, font_cell)[0] for value in sample_values), default=80)
        if idx == 0 and any(col in name for name in ["序号", "排名", "榜单"]):
            width = 100
        elif any(key in col for key in ["学校", "指标"]):
            width = max(240, min(410, longest + 34))
        else:
            width = max(120, min(210, longest + 34))
        col_widths.append(width)
    total_width = sum(col_widths)
    max_table_width = 1780
    if total_width > max_table_width:
        scale = max_table_width / total_width
        col_widths = [max(92, int(width * scale)) for width in col_widths]
    title_width = text_size(probe, title, font_title)[0]
    width = max(left * 2 + sum(col_widths), left * 2 + title_width + 8)
    height = top + row_h * (len(rows) + 1) + 46
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.text((left, 36), title, font=font_title, fill="#16202A")

    x = left
    for idx, col in enumerate(cols):
        w = col_widths[idx]
        draw.rectangle((x, top, x + w, top + row_h), fill="#E6ECF3", outline="#C7D0DD")
        draw_text_box(draw, (x, top, x + w, top + row_h), col, font_header, "#16202A", "center", max_lines=2)
        x += w

    left_align_cols = {"学校", "指标"}
    for ridx, row in enumerate(rows):
        y = top + (ridx + 1) * row_h
        fill = "#FFFFFF" if ridx % 2 == 0 else "#F8FAFC"
        x = left
        for cidx, col in enumerate(cols):
            w = col_widths[cidx]
            draw.rectangle((x, y, x + w, y + row_h), fill=fill, outline="#D8DEE8")
            align = "left" if any(key in col for key in left_align_cols) else "center"
            color = "#1F2933" if align == "left" else "#374151"
            draw_text_box(draw, (x, y, x + w, y + row_h), row.get(col, ""), font_cell, color, align, max_lines=2)
            x += w
    save_png(image, out_path)


def build_table_04(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "table_04_mainland_rank_band_distribution"
    out = artifact_dir(run_dir, artifact_id)
    bands = [(1, 50, "1-50"), (51, 100, "51-100"), (101, 200, "101-200")]
    rows = []
    peer_records = []
    ranked_sources = ranked_sources_with_peer_latest(run_dir)
    for source in RANKING_SOURCES:
        if source not in ranked_sources:
            continue
        latest = latest_selected_source_rows(records, subject, source)
        mainland = latest[latest.apply(is_mainland, axis=1)].copy() if not latest.empty else latest
        mainland["_rank_midpoint_num"] = pd.to_numeric(mainland["rank_midpoint"], errors="coerce")
        top200 = mainland[mainland["_rank_midpoint_num"] <= TOP_RANK_MIDPOINT].copy()
        top200, _ = dedupe_university_rows(top200, subject, source)
        top200["_rank_midpoint_num"] = pd.to_numeric(top200["rank_midpoint"], errors="coerce")
        peer_records.extend(top200.drop(columns=["_rank_midpoint_num"], errors="ignore").to_dict("records"))
        for lo, hi, label in bands:
            count = len(top200[(top200["_rank_midpoint_num"] >= lo) & (top200["_rank_midpoint_num"] <= hi)])
            rows.append({"榜单": source, "位次区间": label, "高校数量": count})
        rows.append({"榜单": source, "位次区间": "1-200合计", "高校数量": len(top200)})
    if not rows:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "no ranked sources with latest mainland peer records"}
    df = pd.DataFrame(rows)
    peer_df = pd.DataFrame(peer_records)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    peer_df.to_csv(out / "peer_records_top200.csv", index=False, encoding="utf-8-sig")
    peer_df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(df, f"{clean_text(subject['target_subject'])}四大排名内地高校位次分布", out / "table.png")
    (out / "table.md").write_text(dataframe_to_markdown(df), encoding="utf-8", newline="\n")
    write_common_outputs(out, artifact_id, "table", len(df), len(peer_df))
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def build_peer_table(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame, source: str, artifact_id: str) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    latest = latest_selected_source_rows(records, subject, source)
    mainland = latest[latest.apply(is_mainland, axis=1)].copy() if not latest.empty else latest
    top = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= TOP_RANK_MIDPOINT].copy()
    top, duplicate_rows = dedupe_university_rows(top, subject, source)
    top["_rank_midpoint_sort"] = pd.to_numeric(top["rank_midpoint"], errors="coerce")
    top = (
        top.sort_values(["_rank_midpoint_sort", "university_name_cn", "university_name_en"], na_position="last")
        .drop(columns=["_rank_midpoint_sort"])
        .reset_index(drop=True)
    )
    if top.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"no {source} top200 mainland peers"}
    full_top = top.copy()
    top = compact_peer_scope_for_word(top)
    word_rows = len(top)
    tongji_appended = bool(top.get("_word_row_kind", pd.Series(dtype=str)).astype(str).eq("tongji_reference").any())
    source_records = filter_to_selected_source_area(records[records["ranking_source"] == source].copy(), subject, source)
    table, history = build_peer_history_matrix(source_records, top, source)
    if table.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"no {source} peer history"}
    history.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    table.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    top.to_csv(out / "latest_peer_records.csv", index=False, encoding="utf-8-sig")
    full_top.to_csv(out / "latest_peer_records_full_top200.csv", index=False, encoding="utf-8-sig")
    duplicate_rows.to_csv(out / "deduped_duplicate_records.csv", index=False, encoding="utf-8-sig")
    history.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(table, f"{source}{clean_text(subject['target_subject'])}内地高校排名历史（前{MAIN_WORD_PEER_TABLE_MAX_ROWS}名样本，同济不在前{MAIN_WORD_PEER_TABLE_MAX_ROWS}时另列参照）", out / "table.png", max_rows=word_rows)
    (out / "table.md").write_text(dataframe_to_markdown(table), encoding="utf-8", newline="\n")
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(table),
        len(history) + len(duplicate_rows),
        {
            "ranking_source": source,
            "table_shape": "compact peer multi-year history",
            "top_rows": MAIN_WORD_PEER_TABLE_MAX_ROWS,
            "word_rows": len(table),
            "tongji_appended": tongji_appended,
            "comparison_note": f"Rows numbered 1-{MAIN_WORD_PEER_TABLE_MAX_ROWS} are the latest-year top sample; a Tongji reference row is not a rank-order row.",
            "full_top200_rows": len(full_top),
            "deduped_duplicate_rows": len(duplicate_rows),
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(table), "output_dir": str(out)}


def build_the_indicator_history(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    return build_processed_indicator_history_table(run_dir, subject, "table_03_the_tongji_indicator_history", "THE")
    artifact_id = "table_03_the_tongji_indicator_history"
    out = artifact_dir(run_dir, artifact_id)
    indicators = read_indicators()
    aliases = set(subject.get("alias_summary", {}).get("THE", []))
    df = indicators[
        (indicators["ranking_source"] == "THE")
        & (indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"]))
        & (indicators["ranking_subject_raw"].isin(aliases) | indicators["ranking_subject_norm"].isin(aliases))
    ].copy()
    if df.empty or df["ranking_year"].nunique() < 2:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "THE indicator history is missing or single-year only"}
    df = df.sort_values(["ranking_year", "metric_type", "indicator_name"])
    df["display_indicator_name"] = df["indicator_name"].map(lambda value: canonical_indicator_name("THE", value))
    df = df[df["display_indicator_name"].astype(str).str.len() > 0].copy()
    years = sorted(int(x) for x in df["ranking_year"].dropna().unique())
    rows = []
    for indicator in df["display_indicator_name"].drop_duplicates().tolist():
        row = {"指标": indicator}
        for year in years:
            value = df[(df["display_indicator_name"] == indicator) & (df["ranking_year"] == year)]["metric_raw"]
            row[str(year)] = clean_text(value.iloc[0]) if not value.empty else display_missing_label("not_measured")
        rows.append(row)
    matrix = pd.DataFrame(rows)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"THE {clean_text(subject['target_subject'])}同济分项指标历史", out / "table.png")
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    write_common_outputs(out, artifact_id, "table", len(df), len(df), {"years": years})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def select_processed_tongji_indicator_history(subject: dict[str, Any], source_name: str) -> pd.DataFrame:
    indicators = read_indicators()
    df = indicators[
        (indicators["ranking_source"] == source_name)
        & (indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"]))
    ].copy()
    df = filter_to_selected_source_area(df, subject, source_name)
    if df.empty:
        return df
    df["display_indicator_name"] = df["indicator_name"].map(lambda value: canonical_indicator_name(source_name, value))
    df = df[df["display_indicator_name"].astype(str).str.len() > 0].copy()
    df["indicator_value"] = df["metric_raw"].map(clean_text)
    empty_value_mask = df["indicator_value"].astype(str).str.len() == 0
    if empty_value_mask.any():
        df.loc[empty_value_mask, "indicator_value"] = df.loc[empty_value_mask, "metric_value"].map(clean_text)
    df["indicator_value_num"] = pd.to_numeric(df["metric_value"], errors="coerce")
    if "metric_rank_midpoint" in df.columns:
        rank_midpoint = pd.to_numeric(df["metric_rank_midpoint"], errors="coerce")
        rank_mask = df["metric_type"].astype(str).str.lower().eq("rank")
        df.loc[rank_mask, "indicator_value_num"] = rank_midpoint.loc[rank_mask].fillna(df.loc[rank_mask, "indicator_value_num"])
    legacy_keys = {
        normalize_text_key("\u7bc7\u5747\u88ab\u5f15"),
        normalize_text_key("\u7bc7\u5747\u88ab\u5f15\u6392\u540d"),
        normalize_text_key("\u7814\u7a76"),
        normalize_text_key("\u7814\u7a76\u6392\u540d"),
    }
    df["_canonical_priority"] = df["indicator_name"].map(lambda value: 1 if normalize_text_key(value) in legacy_keys else 0)
    return df.sort_values(["ranking_year", "display_indicator_name", "_canonical_priority", "metric_type", "indicator_name"]).copy()


def year_int(value: Any) -> int | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return int(number)


def indicator_history_year_label(row: pd.Series, source_name: str) -> str:
    release_year = year_int(row.get("release_year"))
    ranking_year = year_int(row.get("ranking_year"))
    if source_name == "US News" and release_year and ranking_year and release_year != ranking_year:
        return f"{release_year}-{ranking_year}"
    if ranking_year:
        return str(ranking_year)
    if release_year:
        return str(release_year)
    return ""


def add_indicator_history_display_years(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    work = df.copy()
    if source_name == "US News":
        work["_display_year_sort"] = pd.to_numeric(work.get("release_year", pd.Series(dtype=str)), errors="coerce")
        work["_display_year_sort"] = work["_display_year_sort"].fillna(
            pd.to_numeric(work.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
        )
    else:
        work["_display_year_sort"] = pd.to_numeric(work.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
        work["_display_year_sort"] = work["_display_year_sort"].fillna(
            pd.to_numeric(work.get("release_year", pd.Series(dtype=str)), errors="coerce")
        )
    work["_display_year_label"] = work.apply(lambda row: indicator_history_year_label(row, source_name), axis=1)
    return work


def ordered_display_years(df: pd.DataFrame) -> list[tuple[str, float]]:
    pairs = (
        df[["_display_year_label", "_display_year_sort"]]
        .dropna(subset=["_display_year_sort"])
        .drop_duplicates()
        .sort_values("_display_year_sort")
        .itertuples(index=False, name=None)
    )
    return [(clean_text(label), float(sort_value)) for label, sort_value in pairs if clean_text(label)]


def build_processed_indicator_history_table(
    run_dir: Path,
    subject: dict[str, Any],
    artifact_id: str,
    source_name: str,
) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    df = select_processed_tongji_indicator_history(subject, source_name)
    if df.empty or df["ranking_year"].nunique() < 2:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"{source_name} indicator history is missing or single-year only"}
    df = add_indicator_history_display_years(df, source_name)
    display_years = ordered_display_years(df)
    rows = []
    for indicator in df["display_indicator_name"].drop_duplicates().tolist():
        row = {"\u6307\u6807": indicator}
        for label, _ in display_years:
            value = df[(df["display_indicator_name"] == indicator) & (df["_display_year_label"] == label)]["indicator_value"]
            measured = [clean_text(item) for item in value.tolist() if clean_text(item)]
            row[label] = measured[0] if measured else display_missing_label("not_measured")
        rows.append(row)
    matrix = pd.DataFrame(rows)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"{source_name} {clean_text(subject['target_subject'])} Tongji indicator history", out / "table.png")
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    source_files = sorted({clean_text(value) for value in df.get("source_file", pd.Series(dtype=str)).tolist() if clean_text(value)})
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(df),
        len(df),
        {
            "ranking_source": source_name,
            "years": [label for label, _ in display_years],
            "year_axis": "release_year-ranking_year" if source_name == "US News" else "ranking_year",
            "source_files": source_files,
            "data_source": "processed/fact_ranking_indicator.csv",
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def build_usnews_indicator_history(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    return build_processed_indicator_history_table(run_dir, subject, "table_02_usnews_tongji_indicator_history", "US News")


def build_external_indicator_history_table(
    run_dir: Path,
    subject: dict[str, Any],
    artifact_id: str,
    source_name: str,
    source_path: Path,
    missing_years: list[int] | None = None,
) -> dict[str, Any]:
    is_subject_history = "subject_indicator_history" in source_path.name
    if not is_subject_history and not is_math_subject(subject):
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "external indicator history is math-only"}
    out = artifact_dir(run_dir, artifact_id)
    df = read_external_csv(source_path)
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing external history: {source_path}"}
    if is_subject_history:
        df = filter_external_subject_history(df, subject, source_name)
        if df.empty:
            return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing external history for subject: {source_name}/{clean_text(subject.get('target_subject'))}"}
        df = normalize_external_history_subject_display(df, subject, source_name)
    df["ranking_year"] = pd.to_numeric(df["ranking_year"], errors="coerce")
    df["indicator_value_num"] = pd.to_numeric(df["indicator_value"], errors="coerce")
    df["display_indicator_name"] = df["indicator_name"].map(lambda value: canonical_indicator_name(source_name, value))
    df = df[df["display_indicator_name"].astype(str).str.len() > 0].copy()
    years = sorted(int(x) for x in df["ranking_year"].dropna().unique())
    all_years = sorted(set(years + (missing_years or [])))
    rows = []
    for indicator in df["display_indicator_name"].drop_duplicates().tolist():
        row = {"指标": indicator}
        for year in all_years:
            value = df[(df["display_indicator_name"] == indicator) & (df["ranking_year"] == year)]["indicator_value"]
            row[str(year)] = clean_text(value.iloc[0]) if not value.empty else display_missing_label("not_measured")
        rows.append(row)
    matrix = pd.DataFrame(rows)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"{source_name} {clean_text(subject['target_subject'])}同济分项指标历史", out / "table.png")
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(df),
        len(df),
        {"ranking_source": source_name, "years": all_years, "external_source": str(source_path)},
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def normalize_ascii_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def normalize_subject_history_key(value: Any) -> str:
    text = clean_text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def filter_external_subject_history(df: pd.DataFrame, subject: dict[str, Any], source_name: str) -> pd.DataFrame:
    if df.empty:
        return df
    raw_keys = df.get("ranking_subject_raw", pd.Series([""] * len(df))).map(normalize_subject_history_key)
    en_keys = df.get("ranking_subject_en", pd.Series([""] * len(df))).map(normalize_subject_history_key)
    norm_keys = df.get("ranking_subject_norm", pd.Series([""] * len(df))).map(normalize_subject_history_key)
    preferred = clean_text(subject.get("usnews_subject_name" if source_name == "US News" else "arwu_subject_name"))
    override = subject.get("source_runtime_overrides", {}).get(source_name, {})
    preferred_values: list[Any] = [
        override.get("ranking_subject_or_area"),
        override.get("weight_subject_or_area"),
        subject.get("target_subject"),
        preferred,
    ]
    preferred_values.extend(candidate_subject_areas(preferred))
    preferred_values.extend(candidate_subject_areas(override.get("ranking_subject_or_area")))
    preferred_values.extend(candidate_subject_areas(override.get("weight_subject_or_area")))
    for preferred_value in ordered_unique([valid_mapping_value(value) for value in preferred_values]):
        preferred_key = normalize_subject_history_key(preferred_value)
        if not preferred_key:
            continue
        preferred_df = df[(raw_keys == preferred_key) | (en_keys == preferred_key) | (norm_keys == preferred_key)].copy()
        if not preferred_df.empty:
            matched_keys = {preferred_key}
            matched_keys.update(preferred_df.get("ranking_subject_en", pd.Series(dtype=str)).map(normalize_subject_history_key).tolist())
            matched_keys.update(preferred_df.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_subject_history_key).tolist())
            return df[raw_keys.isin(matched_keys) | en_keys.isin(matched_keys) | norm_keys.isin(matched_keys)].copy()

    aliases = {normalize_subject_history_key(value) for value in subject_alias_values(subject, source_name)}
    aliases.update(normalize_subject_history_key(value) for value in [subject.get("target_subject"), preferred] if clean_text(value))
    return df[raw_keys.isin(aliases) | en_keys.isin(aliases) | norm_keys.isin(aliases)].copy()


def normalize_external_history_subject_display(df: pd.DataFrame, subject: dict[str, Any], source_name: str) -> pd.DataFrame:
    if df.empty:
        return df
    display_area = expected_ranking_area(subject, source_name) or clean_text(subject.get("target_subject"))
    if not display_area:
        return df
    result = df.copy()
    if "ranking_subject_raw" in result.columns and "source_ranking_subject_raw" not in result.columns:
        result["source_ranking_subject_raw"] = result["ranking_subject_raw"]
    for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias", "ranking_subject_or_area"]:
        if column in result.columns:
            result[column] = display_area
    return result


def english_alias_keys_for_subject(subject: dict[str, Any]) -> set[str]:
    subject_id = clean_text(subject.get("subject_id"))
    aliases = read_external_csv(PROCESSED_DIR / "dim_subject_alias.csv")
    values: set[str] = set()
    if not aliases.empty and subject_id:
        subject_aliases = aliases[aliases["subject_id"] == subject_id]
        for value in subject_aliases.get("ranking_subject_alias", pd.Series(dtype=str)).tolist():
            if re.search(r"[A-Za-z]", clean_text(value)):
                key = normalize_ascii_key(value)
                if key and key not in {"engineering", "science", "physicalsciences", "socialsciences"}:
                    values.add(key)
    for field in ["arwu_subject_name", "qs_subject_name", "usnews_subject_name", "the_subject_area", "target_subject"]:
        value = clean_text(subject.get(field))
        if re.search(r"[A-Za-z]", value):
            key = normalize_ascii_key(value)
            if key:
                values.add(key)
    for value in public_supplements.arwu_public_aliases(subject):
        key = normalize_ascii_key(value)
        if key:
            values.add(key)
    for row in subject.get("public_supplements", []):
        if clean_text(row.get("ranking_source")) != "软科":
            continue
        if bool(row.get("requires_disclosure")):
            continue
        for field in ["subject_or_area", "subject_or_area_en"]:
            key = normalize_ascii_key(row.get(field))
            if key:
                values.add(key)
    return values


def build_arwu_public_indicator_history_table(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "table_01_arwu_tongji_indicator_history"
    out = artifact_dir(run_dir, artifact_id)
    public_df = read_external_csv(ARWU_PUBLIC_TONGJI_LONG_CSV)
    if public_df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing ARWU public Tongji history"}
    alias_keys = english_alias_keys_for_subject(subject)
    if not alias_keys:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing English subject alias for ARWU public history"}
    public_df["subject_key"] = public_df["arwu_subject_name_en"].apply(normalize_ascii_key)
    matched_keys = {
        key
        for key in public_df["subject_key"].drop_duplicates().tolist()
        if any(key == alias or key in alias or alias in key for alias in alias_keys)
    }
    df = public_df[public_df["subject_key"].isin(matched_keys)].copy()
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "no matching ARWU public subject history"}
    local_indicators = read_indicators()
    local_df = pd.DataFrame()
    if not local_indicators.empty:
        raw_aliases = {clean_text(value) for value in subject.get("alias_summary", {}).get("软科", []) if clean_text(value)}
        norm_aliases = {normalize_text_key(value) for value in raw_aliases if normalize_text_key(value)}
        local_df = local_indicators[
            (local_indicators["ranking_source"] == "软科")
            & (local_indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"]))
            & (
                local_indicators["ranking_subject_raw"].map(clean_text).isin(raw_aliases)
                | local_indicators["ranking_subject_norm"].map(clean_text).isin(norm_aliases)
            )
            & (local_indicators["metric_type"] == "score")
        ].copy()
        local_df["display_indicator_name"] = local_df["indicator_name"].map(lambda value: canonical_indicator_name("软科", value))
        local_df = local_df[
            local_df["display_indicator_name"].isin(
                ["高质量研究", "研究影响", "国际合作", "世界一流产出", "世界一流师资"]
            )
        ].copy()
        if not local_df.empty:
            local_df = pd.DataFrame(
                {
                    "ranking_source": "软科",
                    "ranking_year": local_df["ranking_year"],
                    "arwu_subject_code": "",
                    "arwu_subject_name_en": local_df["ranking_subject_raw"],
                    "world_rank": local_df["world_rank_raw"],
                    "university_name_en": local_df["university_name_en"],
                    "university_slug": "",
                    "university_code": "",
                    "region": local_df["country_or_region"],
                    "region_rank": "",
                    "total_score": "",
                    "source_url": "",
                    "indicator_code": local_df["indicator_norm"],
                    "indicator_name": local_df["indicator_name"],
                    "indicator_value": local_df["metric_raw"],
                    "source_file": local_df["source_file"],
                    "source_sheet": local_df["source_sheet"],
                    "source_row": local_df["source_row"],
                    "display_indicator_name": local_df["display_indicator_name"],
                }
            )
    df["ranking_year"] = pd.to_numeric(df["ranking_year"], errors="coerce")
    df["indicator_value_num"] = pd.to_numeric(df["indicator_value"], errors="coerce")
    df["display_indicator_name"] = df["indicator_name"].map(lambda value: canonical_indicator_name("ARWU GRAS public web", value))
    df = df[df["display_indicator_name"].astype(str).str.len() > 0].copy()
    df["_source_priority"] = 1
    if not local_df.empty:
        local_df["ranking_year"] = pd.to_numeric(local_df["ranking_year"], errors="coerce")
        local_df["indicator_value_num"] = pd.to_numeric(local_df["indicator_value"], errors="coerce")
        local_df["_source_priority"] = 0
        for column in df.columns:
            if column not in local_df.columns:
                local_df[column] = ""
        for column in local_df.columns:
            if column not in df.columns:
                df[column] = ""
        df = pd.concat([df, local_df[df.columns]], ignore_index=True, sort=False)
        df = df.sort_values(["ranking_year", "display_indicator_name", "_source_priority", "ranking_source"])
        df = df.drop_duplicates(subset=["ranking_year", "display_indicator_name"], keep="first").copy()
    source_files = sorted({clean_text(value) for value in df.get("source_file", pd.Series(dtype=str)).tolist() if clean_text(value)})
    public_rows_used = df["ranking_source"].map(clean_text).eq("ARWU GRAS public web").any() if "ranking_source" in df.columns else False
    df = df.drop(columns=["_source_priority"], errors="ignore")
    years = sorted(int(x) for x in df["ranking_year"].dropna().unique())
    if len(years) < 2:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "ARWU public history is single-year only"}
    rows = []
    for indicator in df["display_indicator_name"].drop_duplicates().tolist():
        row = {"指标": indicator}
        for year in years:
            value = df[(df["display_indicator_name"] == indicator) & (df["ranking_year"] == year)]["indicator_value"]
            row[str(year)] = clean_text(value.iloc[0]) if not value.empty else display_missing_label("not_measured")
        rows.append(row)
    matrix = pd.DataFrame(rows)
    df.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"ARWU GRAS {clean_text(subject['target_subject'])}同济分项指标历史", out / "table.png")
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    extra = {
        "ranking_source": "软科",
        "years": years,
        "matched_subjects": sorted({clean_text(value) for value in df["arwu_subject_name_en"].tolist() if clean_text(value)}),
        "data_source": "processed/fact_ranking_indicator.csv" if source_files else "",
        "source_files": source_files,
        "public_web_rows_used": bool(public_rows_used),
    }
    if public_rows_used:
        extra["external_source"] = str(ARWU_PUBLIC_TONGJI_LONG_CSV)
    write_common_outputs(out, artifact_id, "table", len(df), len(df), extra)
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def render_indicator_trend(df: pd.DataFrame, title: str, out_path: Path) -> None:
    plot = df.copy()
    plot["ranking_year"] = pd.to_numeric(plot["ranking_year"], errors="coerce")
    if "_display_year_sort" not in plot.columns:
        plot["_display_year_sort"] = plot["ranking_year"]
    else:
        plot["_display_year_sort"] = pd.to_numeric(plot["_display_year_sort"], errors="coerce")
    if "_display_year_label" not in plot.columns:
        plot["_display_year_label"] = plot["ranking_year"].map(lambda value: str(int(value)) if pd.notna(value) else "")
    if "indicator_value_num" in plot.columns:
        numeric_values = pd.to_numeric(plot["indicator_value_num"], errors="coerce")
    else:
        numeric_values = pd.Series([None] * len(plot), index=plot.index, dtype="float64")
    fallback_values = pd.to_numeric(
        plot.get("indicator_value", pd.Series(dtype=str)).astype(str).str.replace("#", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    )
    plot["_plot_value"] = numeric_values.fillna(fallback_values)
    plot = plot.dropna(subset=["_display_year_sort", "_plot_value"])
    indicators = plot["indicator_name"].drop_duplicates().tolist()
    year_pairs = ordered_display_years(plot)
    years = [sort_value for _, sort_value in year_pairs]
    year_labels = {sort_value: label for label, sort_value in year_pairs}
    if len(indicators) > 8:
        cols = 2
        rows = math.ceil(len(indicators) / cols)
        image = Image.new("RGB", (1900, 220 + rows * 284), "#FFFFFF")
    else:
        image = Image.new("RGB", (1900, 940), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(40, True)
    font_sub = load_font(23)
    font_axis = load_font(23, True)
    font_label = load_font(22, True)
    draw.text((62, 36), title, font=font_title, fill="#16202A")
    draw.text((62, 88), "U.S. News 分项指标排名趋势，数值越小表示相对排名越靠前", font=font_sub, fill="#5A6573")
    if not years or not indicators:
        save_png(image, out_path)
        return
    max_v = max(400, int(math.ceil(plot["_plot_value"].max() / 100.0) * 100))
    palette = ["#315D9C", "#C64B46", "#3C8D5A", "#7B5CA8", "#D68A35", "#6B7280", "#C85D7B", "#4C72B0", "#059669", "#A855F7", "#0F766E", "#B45309"]

    if len(indicators) > 8:
        mini_w, mini_h = 740, 172
        start_x, start_y = 112, 178
        gap_x, gap_y = 112, 86

        def mini_xp(year: float, left: int) -> float:
            return left + (year - min(years)) / max(1, max(years) - min(years)) * mini_w

        def mini_yp(value: float, top: int) -> float:
            return top + value / max(1, max_v) * mini_h

        for idx, indicator in enumerate(indicators):
            col = idx % cols
            row = idx // cols
            left = start_x + col * (mini_w + gap_x)
            top = start_y + row * (mini_h + gap_y)
            right = left + mini_w
            bottom = top + mini_h
            color = palette[idx % len(palette)]
            draw.rounded_rectangle((left - 24, top - 46, right + 28, bottom + 56), radius=18, fill="#FFFFFF", outline="#D8DEE8", width=2)
            draw_text_box(draw, (left - 8, top - 40, right + 18, top - 8), clean_text(indicator), font_label, "#243241", "left", max_lines=1)
            for tick in range(0, max_v + 1, 200):
                y = mini_yp(tick, top)
                draw.line((left, y, right, y), fill="#EEF2F6", width=2)
                if tick in {0, max_v}:
                    draw_text_right(draw, left - 12, y - 10, str(tick), load_font(17, True), "#697586")
            draw.line((left, top, left, bottom), fill="#A0AAB7", width=2)
            draw.line((left, bottom, right, bottom), fill="#A0AAB7", width=2)
            group = plot[plot["indicator_name"] == indicator].sort_values("_display_year_sort")
            points = [(mini_xp(float(item["_display_year_sort"]), left), mini_yp(float(item["_plot_value"]), top)) for _, item in group.iterrows()]
            if len(points) > 1:
                draw.line(points, fill=color, width=6)
            for point_x, point_y in points:
                draw.ellipse((point_x - 9, point_y - 9, point_x + 9, point_y + 9), fill=color, outline="#FFFFFF", width=3)
            if points:
                last_row = group.iloc[-1]
                draw.text((points[-1][0] + 10, max(top, points[-1][1] - 16)), f"{float(last_row['_plot_value']):g}", font=load_font(18, True), fill=color)
            for year in years:
                x = mini_xp(year, left)
                draw_center(draw, (x - 58, bottom + 14, x + 58, bottom + 42), year_labels.get(year, str(int(year))), load_font(16, True), "#52606D")
        draw.text((62, image.height - 48), f"注：本图以小多图展示全部 {len(indicators)} 个分项指标，避免多线叠加造成遮挡；纵轴统一为排名数值。", font=load_font(20), fill="#697586")
        save_png(image, out_path)
        return

    left, top, right, bottom = 142, 150, 1320, 770

    def xp(year: float) -> float:
        return left + (year - min(years)) / max(1, max(years) - min(years)) * (right - left)

    def yp(value: float) -> float:
        return top + value / max(1, max_v) * (bottom - top)

    for tick in range(0, max_v + 1, 100):
        y = yp(tick)
        draw.line((left, y, right, y), fill="#E5E7EB", width=2)
        draw_text_right(draw, left - 18, y - 13, str(tick), font_axis, "#52606D")
    draw.line((left, top, left, bottom), fill="#8792A0", width=3)
    draw.line((left, bottom, right, bottom), fill="#8792A0", width=3)
    for year in years:
        x = xp(year)
        draw_center(draw, (x - 70, bottom + 18, x + 70, bottom + 54), year_labels.get(year, str(int(year))), load_font(20, True), "#52606D")
    for idx, indicator in enumerate(indicators):
        color = palette[idx % len(palette)]
        group = plot[plot["indicator_name"] == indicator].sort_values("_display_year_sort")
        points = [(xp(float(row["_display_year_sort"])), yp(float(row["_plot_value"]))) for _, row in group.iterrows()]
        if len(points) > 1:
            draw.line(points, fill=color, width=6)
        for x, y in points:
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=color, outline="#FFFFFF", width=3)
        ly = 154 + idx * 58
        draw.line((1360, ly + 14, 1410, ly + 14), fill=color, width=7)
        draw.text((1424, ly), indicator[:20], font=font_label, fill="#374151")
    save_png(image, out_path)


def build_usnews_indicator_history_trend(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_10_usnews_indicator_history_trend"
    out = artifact_dir(run_dir, artifact_id)
    df = select_processed_tongji_indicator_history(subject, "US News")
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing US News processed indicator history for subject: {clean_text(subject.get('target_subject'))}"}
    df = df[df["metric_type"].astype(str).str.lower().eq("rank")].copy()
    if df.empty or df["ranking_year"].nunique() < 2:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "US News processed rank indicator history is missing or single-year only"}
    df = add_indicator_history_display_years(df, "US News")
    df["indicator_name"] = df["display_indicator_name"]
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_indicator_trend(df, f"U.S. News {clean_text(subject['target_subject'])}同济分项指标历史趋势", out / "chart.png")
    display_years = ordered_display_years(df)
    indicator_count = int(df["indicator_name"].map(clean_text).replace("", pd.NA).dropna().nunique()) if "indicator_name" in df.columns else 0
    ranking_subjects = sorted({clean_text(value) for value in df.get("ranking_subject_raw", pd.Series(dtype=str)).tolist() if clean_text(value)})
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(df),
        len(df),
        {
            "ranking_source": "US News",
            "years": [label for label, _ in display_years],
            "year_axis": "release_year-ranking_year",
            "indicator_count": indicator_count,
            "ranking_subjects": ranking_subjects,
            "rendering_strategy": "all_indicator_small_multiples" if indicator_count > 8 else "single_panel_all_indicators",
            "numeric_value_source": "processed_fact_ranking_indicator.metric_rank_midpoint",
            "data_source": "processed/fact_ranking_indicator.csv",
            "source_files": sorted({clean_text(value) for value in df.get("source_file", pd.Series(dtype=str)).tolist() if clean_text(value)}),
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def build_usnews_candidate_weight(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_05_usnews_indicator_weight"
    if not is_math_subject(subject):
        return {
            "artifact_id": artifact_id,
            "status": "skipped",
            "reason": "missing official US News matching-subject weight; math-only candidate weight is intentionally not reused",
        }
    out = artifact_dir(run_dir, artifact_id)
    df = read_external_csv(USNEWS_WEIGHT_CANDIDATE_CSV)
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing US News candidate weight file"}
    df["weight_percent"] = pd.to_numeric(df["weight_percent"], errors="coerce").fillna(0.0)
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "chart_plot_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    tree_df = build_weight_tree_data(df[df["weight_percent"] > 0].copy())
    tree_df.to_csv(out / "chart_tree_data.csv", index=False, encoding="utf-8-sig")
    render_weight_tree(tree_df, f"U.S. News {clean_text(subject['target_subject'])}指标权重候选口径", out / "chart.png")
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(df),
        len(df),
        {
            "ranking_source": "US News",
            "evidence_status": "candidate_indirect",
            "external_source": str(USNEWS_WEIGHT_CANDIDATE_CSV),
            "must_confirm_before_word": True,
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out), "candidate_only": True}


def read_current_run_peer_scope(run_dir: Path) -> pd.DataFrame:
    peer_source_files = [
        "artifacts/table_04_mainland_rank_band_distribution/peer_records_top200.csv",
        "artifacts/table_05_arwu_mainland_peer_ranking/latest_peer_records.csv",
        "artifacts/table_06_usnews_mainland_peer_ranking/latest_peer_records.csv",
        "artifacts/table_07_qs_mainland_peer_ranking/latest_peer_records.csv",
        "artifacts/table_08_the_mainland_peer_ranking/latest_peer_records.csv",
    ]
    frames = []
    for rel_path in peer_source_files:
        path = run_dir / rel_path
        if not path.exists():
            continue
        frame = read_external_csv(path)
        keep = [col for col in ["university_name_cn", "university_name_en"] if col in frame.columns]
        if keep:
            frames.append(frame[keep].copy())
    if not frames:
        return pd.DataFrame(columns=["university_name_cn", "university_name_en"])
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def select_wos_peer_rows(run_dir: Path, subject: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    preprocess_status = ensure_wos_subject_paper_csv()
    mapping = {
        "source_system": "Web of Science subject paper metrics",
        "source_file": str(WOS_SUBJECT_PAPER_CSV),
        "source_workbook_status": preprocess_status,
        "scope_type": "wos_37_double_first_class_universities_by_ministry_subject_code",
        "expected_university_count": 37,
        "evidence_level": "derived_from_local_workbook",
        "requires_disclosure": "no",
    }
    if not WOS_SUBJECT_PAPER_CSV.exists():
        mapping["reason"] = "missing cleaned WOS subject paper CSV"
        return pd.DataFrame(), mapping
    code = subject_code(subject)
    df = read_external_csv(WOS_SUBJECT_PAPER_CSV)
    if df.empty:
        mapping["reason"] = "empty cleaned WOS subject paper CSV"
        return df, mapping
    if "ministry_subject_code" not in df.columns:
        mapping["reason"] = "missing ministry_subject_code column"
        return pd.DataFrame(), mapping
    df = df[df["ministry_subject_code"].astype(str).str.zfill(4) == code].copy()
    if df.empty:
        mapping["reason"] = f"no WOS rows for ministry_subject_code={code}"
        return df, mapping
    metric_columns = [
        "WOS_documents",
        "times_cited",
        "citation_impact",
        "pct_docs_cited",
        "CNCI",
        "documents_top_1",
        "pct_documents_top_1",
        "documents_top_10",
        "pct_documents_top_10",
        "highly_cited_papers",
        "pct_highly_cited_papers",
        "international_documents",
        "pct_international_documents",
        "collab_CNCI",
    ]
    for column in metric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["included_in_wos_37_scope"] = True
    df["matched_current_subject_peer"] = True
    mapping["matched_peer_rows"] = int(len(df))
    mapping["field_rows"] = int(len(df))
    mapping["university_count"] = int(df.get("university_name_cn", pd.Series(dtype=str)).nunique())
    mapping["paper_field"] = clean_text(df.iloc[0].get("paper_field", "")) if not df.empty else ""
    mapping["subject_code_match_rule"] = "extract leading 4 digits from 教育部一级学科 and compare to ministry_subject_code"
    return df, mapping


def select_cwts_peer_rows(run_dir: Path, subject: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    mapping = cwts_field_for_subject(subject)
    cwts_field = clean_text(mapping.get("cwts_field"))
    if not cwts_field:
        return pd.DataFrame(), mapping
    df = read_external_csv(CWTS_CHINA_ALL_FIELDS_CSV)
    if df.empty:
        df = read_external_csv(CWTS_MATH_PEER_CSV)
    if df.empty:
        return df, mapping
    if "Field" in df.columns:
        df = df[df["Field"] == cwts_field].copy()
    if df.empty:
        return df, mapping
    for column in ["P", "TCS", "TNCS", "MCS", "MNCS", "P_top_1", "P_top_10", "PP_top_1", "PP_top_10", "P_int_collab", "PP_int_collab"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    peers = read_current_run_peer_scope(run_dir)
    peer_names_en = set(peers.get("university_name_en", pd.Series(dtype=str)).dropna().astype(str).str.lower().str.strip())
    peer_names_cn = set(peers.get("university_name_cn", pd.Series(dtype=str)).dropna().astype(str).str.strip())
    matched = pd.DataFrame()
    if "University" in df.columns and peer_names_en:
        matched = df[df["University"].astype(str).str.lower().str.strip().isin(peer_names_en)].copy()
        matched["matched_current_peer_by_en"] = True
    if "university_name_cn" in df.columns and peer_names_cn:
        matched_cn = df[df["university_name_cn"].astype(str).str.strip().isin(peer_names_cn)].copy()
        matched_cn["matched_current_peer_by_cn"] = True
        matched = pd.concat([matched, matched_cn], ignore_index=True, sort=False)
    if not matched.empty:
        matched = matched.drop_duplicates(subset=["University", "Field", "Period"])
        matched["matched_current_subject_peer"] = True
    tongji = df[df["University"].apply(is_tongji_name)].copy() if "University" in df.columns else pd.DataFrame()
    if not tongji.empty:
        tongji["matched_current_subject_peer"] = True
        matched = pd.concat([matched, tongji], ignore_index=True, sort=False).drop_duplicates(subset=["University", "Field", "Period"])
    if matched.empty:
        matched = df.copy()
        matched["matched_current_subject_peer"] = False
    mapping["matched_peer_rows"] = int(len(matched))
    mapping["field_rows"] = int(len(df))
    return matched, mapping


def rank_for_metric(df: pd.DataFrame, metric: str, higher_better: bool = True) -> pd.Series:
    return pd.to_numeric(df[metric], errors="coerce").rank(ascending=not higher_better, method="min").astype("Int64")


def render_paper_bar_chart(
    df: pd.DataFrame,
    title: str,
    metrics: list[tuple[str, str]],
    out_path: Path,
    note: str,
    *,
    tall: bool = False,
) -> None:
    row_count = max(1, len(df))
    image_h = max(2400, min(3600, 500 + row_count * 65)) if tall else max(1280, min(2000, 330 + row_count * 42))
    image = Image.new("RGB", (1780, image_h), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(42, True)
    font_sub = load_font(23)
    font_label = load_font(19, True)
    font_small = load_font(18, True)
    draw.text((58, 30), title, font=font_title, fill="#16202A")
    draw_text_box(draw, (52, 78, 1710, 126), note, font_sub, "#5A6573", "left", max_lines=2)
    panels = len(metrics)
    panel_w = int((1600 - (panels - 1) * 54) / max(1, panels))
    panel_h = image_h - 330
    top = 220
    for idx, (metric, label) in enumerate(metrics):
        panel_left = 70 + idx * (panel_w + 50)
        panel_right = panel_left + panel_w
        values = pd.to_numeric(df[metric], errors="coerce").fillna(0)
        top_df = df.assign(_value=values).sort_values("_value", ascending=False).copy()
        max_v = max(1.0, float(top_df["_value"].max()))
        draw.text((panel_left, top - 42), label, font=load_font(28, True), fill="#1F2933")
        draw.text((panel_right - 150, top - 36), f"{len(top_df)}所高校", font=font_small, fill="#697586")
        if tall:
            row_step = max(34, min(50, int(panel_h / max(1, len(top_df)))))
            bar_h = max(14, min(28, row_step - 14))
        else:
            row_step = max(22, min(32, int(panel_h / max(1, len(top_df)))))
            bar_h = max(10, min(20, row_step - 10))
        bar_left = panel_left + 182
        bar_right = panel_right - 112
        for ridx, (_, row) in enumerate(top_df.iterrows()):
            y = top + ridx * row_step
            name = short_university_name(row)
            value = float(row["_value"])
            bar_w = max(3.0, (bar_right - bar_left) * value / max_v) if value > 0 else 0
            color = "#C64B46" if is_tongji_name(name) or is_tongji_name(row.get("University", "")) else "#315D9C"
            label_fill = "#C64B46" if color == "#C64B46" else "#374151"
            label_text = ellipsize_text(draw, name, font_label, bar_left - panel_left - 12)
            draw.text((panel_left, y), label_text, font=font_label, fill=label_fill)
            if bar_w > 0:
                draw.rounded_rectangle((bar_left, y + 2, bar_left + bar_w, y + 2 + bar_h), radius=4, fill=color)
            value_text = f"{value:,.0f}" if abs(value) >= 100 else f"{value:.1f}"
            draw_text_right(draw, panel_right - 6, y, value_text, font_small, label_fill)
    save_png(image, out_path)


def metric_display_label(metric: str) -> str:
    labels = {
        "citation_impact": "篇均被引",
        "CNCI": "CNCI",
        "MCS": "篇均被引 MCS",
        "MNCS": "归一化影响 MNCS",
    }
    return labels.get(metric, metric)


def render_paper_scatter(df: pd.DataFrame, title: str, x_metric: str, y_metric: str, out_path: Path, note: str) -> None:
    image = Image.new("RGB", (1760, 980), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(42, True)
    font_sub = load_font(23)
    font_axis = load_font(25, True)
    font_tick = load_font(21, True)
    font_label = load_font(22, True)
    draw.text((58, 30), title, font=font_title, fill="#16202A")
    draw_text_box(draw, (52, 78, 1690, 126), note, font_sub, "#5A6573", "left", max_lines=2)
    plot = df.dropna(subset=[x_metric, y_metric]).copy()
    left, top, right, bottom = 158, 154, 1592, 820
    x_vals = pd.to_numeric(plot[x_metric], errors="coerce")
    y_vals = pd.to_numeric(plot[y_metric], errors="coerce")
    x_min, x_max = float(x_vals.min()), float(x_vals.max())
    y_min, y_max = float(y_vals.min()), float(y_vals.max())
    if x_min == x_max:
        x_max += 1
    if y_min == y_max:
        y_max += 1
    pad_x = (x_max - x_min) * 0.06
    pad_y = (y_max - y_min) * 0.08
    x_min, x_max = max(0.0, x_min - pad_x), x_max + pad_x
    y_min, y_max = max(0.0, y_min - pad_y), y_max + pad_y
    draw.rectangle((left, top, right, bottom), outline="#CBD2D9", width=3)
    x_med = float(x_vals.median())
    y_med = float(y_vals.median())
    for i in range(6):
        x = left + i / 5 * (right - left)
        y = top + i / 5 * (bottom - top)
        draw.line((x, top, x, bottom), fill="#EEF2F7", width=2)
        draw.line((left, y, right, y), fill="#EEF2F7", width=2)
        xv = x_min + i / 5 * (x_max - x_min)
        yv = y_max - i / 5 * (y_max - y_min)
        draw_text_right(draw, x, bottom + 14, f"{xv:.1f}", font_tick, "#697586")
        draw_text_right(draw, left - 12, y - 9, f"{yv:.1f}", font_tick, "#697586")

    def xpos(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (right - left)

    def ypos(value: float) -> float:
        return bottom - (value - y_min) / (y_max - y_min) * (bottom - top)

    draw.line((xpos(x_med), top, xpos(x_med), bottom), fill="#B8C2D0", width=3)
    draw.line((left, ypos(y_med), right, ypos(y_med)), fill="#B8C2D0", width=3)
    draw.text((xpos(x_med) + 8, top + 8), "中位线", font=font_tick, fill="#697586")

    plot["_xv"] = pd.to_numeric(plot[x_metric], errors="coerce")
    plot["_yv"] = pd.to_numeric(plot[y_metric], errors="coerce")
    label_candidates = plot.sort_values("_yv", ascending=False).head(4)
    tongji_candidates = plot[plot.apply(lambda row: is_tongji_name(short_university_name(row)) or is_tongji_name(row.get("University", "")), axis=1)]
    label_indices = set(label_candidates.index.tolist() + tongji_candidates.index.tolist())
    for row_index, row in plot.iterrows():
        xv = to_float(row[x_metric])
        yv = to_float(row[y_metric])
        x = xpos(xv)
        y = ypos(yv)
        name = short_university_name(row)
        color = "#C64B46" if is_tongji_name(name) or is_tongji_name(row.get("University", "")) else "#315D9C"
        radius = 14 if color == "#C64B46" else 8
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#FFFFFF", width=2)
        if row_index in label_indices:
            label_fill = "#C64B46" if color == "#C64B46" else "#374151"
            draw.text((min(x + 12, right - 120), max(top + 4, y - 12)), name[:10], font=font_label, fill=label_fill)
    draw_center(draw, (left, bottom + 48, right, bottom + 84), metric_display_label(x_metric), font_axis, "#52606D")
    draw.text((62, top - 18), metric_display_label(y_metric), font=font_axis, fill="#52606D")
    save_png(image, out_path)


def build_cwts_paper_artifact(run_dir: Path, subject: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    df, cwts_mapping = select_cwts_peer_rows(run_dir, subject)
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing CWTS broad-field proxy data"}
    cwts_field = clean_text(cwts_mapping.get("cwts_field"))
    title_prefix = "对标高校"
    note_prefix = f"CWTS Leiden Ranking Traditional Edition 2025，{cwts_field} 宽领域，2020-2023。"
    metric_map = {
        "figure_13_paper_output_citation_relative_rank": {
            "metrics": [("P", "论文量 P"), ("TCS", "总被引 TCS")],
            "title": f"{title_prefix}论文及被引总量相对表现",
            "note": note_prefix,
            "renderer": "bar",
        },
        "figure_14_paper_cnci_cpp_relative_rank": {
            "metrics": [("MCS", "篇均被引 MCS"), ("MNCS", "归一化影响 MNCS")],
            "title": f"{title_prefix}篇均被引与归一化影响相对表现",
            "note": "MNCS/MCS 为 CWTS 公开替代口径，不等同 InCites CNCI 原始导出。",
            "renderer": "scatter",
        },
        "figure_15_paper_highly_cited_relative_rank": {
            "metrics": [("P_top_1", "Top 1%论文数"), ("P_top_10", "Top 10%论文数")],
            "title": f"{title_prefix}高被引论文相对表现",
            "note": "CWTS 高被引口径：P_top_1 / P_top_10 及对应占比字段。",
            "renderer": "bar",
        },
        "figure_16_paper_international_collab_relative_rank": {
            "metrics": [("P_int_collab", "国际合著论文数"), ("PP_int_collab", "国际合著占比")],
            "title": f"{title_prefix}国际合著论文相对表现",
            "note": "CWTS 国际合作口径：P_int_collab / PP_int_collab。",
            "renderer": "bar",
        },
    }
    spec = metric_map[artifact_id]
    metrics = spec["metrics"]
    for metric, _ in metrics:
        df[f"{metric}_relative_rank"] = rank_for_metric(df, metric, higher_better=True)
    data_cols = [
        "University",
        "university_name_cn",
        "Country",
        "Field",
        "Period",
        "matched_current_math_peer",
        "matched_current_subject_peer",
    ] + [item for metric, _ in metrics for item in [metric, f"{metric}_relative_rank"] if item in df.columns]
    data_cols = [col for col in data_cols if col in df.columns]
    chart_df = df[data_cols].copy()
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    if spec["renderer"] == "scatter":
        render_paper_scatter(df, spec["title"], metrics[0][0], metrics[1][0], out / "chart.png", spec["note"])
    else:
        render_paper_bar_chart(
            df,
            spec["title"],
            metrics,
            out / "chart.png",
            spec["note"],
            tall=artifact_id in {
                "figure_15_paper_highly_cited_relative_rank",
                "figure_16_paper_international_collab_relative_rank",
            },
        )
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(chart_df),
        len(df),
        {
            "source_system": "CWTS Leiden Ranking Traditional Edition 2025",
            "field": cwts_field,
            "period": "2020-2023",
            "metrics": [metric for metric, _ in metrics],
            "external_source": str(CWTS_CHINA_ALL_FIELDS_CSV),
            "subject_field_mapping": cwts_mapping,
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(chart_df), "output_dir": str(out)}


def build_subject_paper_artifact(run_dir: Path, subject: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    df, paper_mapping = select_wos_peer_rows(run_dir, subject)
    source_kind = "wos"
    if df.empty:
        reason = clean_text(paper_mapping.get("reason")) or "missing WOS subject data for this ministry subject code"
        return {"artifact_id": artifact_id, "status": "skipped", "reason": reason, "source_kind": "wos"}

    title_prefix = "当前学科 WoS 论文表现（37校对比）"
    if source_kind == "wos":
        note_prefix = f"口径：{clean_text(paper_mapping.get('paper_field'))}；每行代表该学科下的一所高校，非学校整体论文汇总。"
        metric_map = {
            "figure_13_paper_output_citation_relative_rank": {
                "metrics": [("WOS_documents", "论文总量"), ("times_cited", "总被引")],
                "title": f"{title_prefix}：论文及被引总量",
                "note": note_prefix,
                "renderer": "bar",
            },
            "figure_14_paper_cnci_cpp_relative_rank": {
                "metrics": [("citation_impact", "篇均被引"), ("CNCI", "CNCI")],
                "title": f"{title_prefix}：篇均被引与 CNCI",
                "note": note_prefix,
                "renderer": "scatter",
            },
            "figure_15_paper_highly_cited_relative_rank": {
                "metrics": [("documents_top_1", "前1%论文数"), ("highly_cited_papers", "ESI高被引论文数")],
                "title": f"{title_prefix}：高被引论文",
                "note": note_prefix,
                "renderer": "bar",
            },
            "figure_16_paper_international_collab_relative_rank": {
                "metrics": [("international_documents", "国际合作论文数"), ("pct_international_documents", "国际合作论文占比")],
                "title": f"{title_prefix}：国际合作论文",
                "note": note_prefix,
                "renderer": "bar",
            },
        }
    else:
        cwts_field = clean_text(paper_mapping.get("cwts_field"))
        metric_map = {
            "figure_13_paper_output_citation_relative_rank": {
                "metrics": [("P", "论文量 P"), ("TCS", "总被引 TCS")],
                "title": f"{title_prefix}论文及被引总量相对表现",
                "note": f"CWTS Leiden Ranking Traditional Edition 2025：{cwts_field} 宽领域代理，2020-2023。",
                "renderer": "bar",
            },
            "figure_14_paper_cnci_cpp_relative_rank": {
                "metrics": [("MCS", "篇均被引 MCS"), ("MNCS", "归一化影响 MNCS")],
                "title": f"{title_prefix}篇均被引与归一化影响相对表现",
                "note": "MNCS/MCS 为 CWTS 公开替代口径，不等同 InCites CNCI 原始导出。",
                "renderer": "scatter",
            },
            "figure_15_paper_highly_cited_relative_rank": {
                "metrics": [("P_top_1", "Top 1%论文数"), ("P_top_10", "Top 10%论文数")],
                "title": f"{title_prefix}高被引论文相对表现",
                "note": "CWTS 高被引口径：P_top_1 / P_top_10 及对应占比字段。",
                "renderer": "bar",
            },
            "figure_16_paper_international_collab_relative_rank": {
                "metrics": [("P_int_collab", "国际合著论文数"), ("PP_int_collab", "国际合著占比")],
                "title": f"{title_prefix}国际合著论文相对表现",
                "note": "CWTS 国际合作口径：P_int_collab / PP_int_collab。",
                "renderer": "bar",
            },
        }

    spec = metric_map[artifact_id]
    metrics = spec["metrics"]
    for metric, _ in metrics:
        df[f"{metric}_relative_rank"] = rank_for_metric(df, metric, higher_better=True)
    base_cols = [
        "University",
        "university_name_cn",
        "university_name_en",
        "Country",
        "country_or_region",
        "Field",
        "paper_field",
        "ministry_subject_code",
        "Period",
        "period",
        "matched_current_math_peer",
        "matched_current_subject_peer",
        "included_in_wos_37_scope",
    ]
    data_cols = base_cols + [item for metric, _ in metrics for item in [metric, f"{metric}_relative_rank"] if item in df.columns]
    data_cols = [col for col in data_cols if col in df.columns]
    chart_df = df[data_cols].copy()
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    if spec["renderer"] == "scatter":
        render_paper_scatter(df, spec["title"], metrics[0][0], metrics[1][0], out / "chart.png", spec["note"])
    else:
        render_paper_bar_chart(
            df,
            spec["title"],
            metrics,
            out / "chart.png",
            spec["note"],
            tall=artifact_id in {
                "figure_15_paper_highly_cited_relative_rank",
                "figure_16_paper_international_collab_relative_rank",
            },
        )
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(chart_df),
        len(df),
        {
            "source_system": "Web of Science subject paper metrics" if source_kind == "wos" else "CWTS Leiden Ranking Traditional Edition 2025",
            "source_kind": source_kind,
            "field": clean_text(paper_mapping.get("paper_field") or paper_mapping.get("cwts_field")),
            "period": "period_not_in_source_file" if source_kind == "wos" else "2020-2023",
            "metrics": [metric for metric, _ in metrics],
            "external_source": str(WOS_SUBJECT_PAPER_CSV if source_kind == "wos" else CWTS_CHINA_ALL_FIELDS_CSV),
            "subject_field_mapping": paper_mapping,
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(chart_df), "output_dir": str(out)}


def build_appendix(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "table_09_peer_full_ranking_history_appendix"
    out = artifact_dir(run_dir, artifact_id)
    province_map = load_university_province_map()
    source_artifacts = [
        ("US News", "table_06_usnews_mainland_peer_ranking"),
        ("软科", "table_05_arwu_mainland_peer_ranking"),
        ("THE", "table_08_the_mainland_peer_ranking"),
        ("QS", "table_07_qs_mainland_peer_ranking"),
    ]
    records_df = dedupe_records(records)
    long_parts = []
    wide: pd.DataFrame | None = None
    latest_rank_values: dict[str, list[float]] = {}
    source_years: dict[str, set[str]] = {}
    for source, source_artifact in source_artifacts:
        latest_peer_path = artifact_dir(run_dir, source_artifact) / "latest_peer_records.csv"
        if not latest_peer_path.exists():
            continue
        latest_peers = pd.read_csv(latest_peer_path, dtype=str).fillna("")
        source_records = records_df[records_df["ranking_source"] == source].copy()
        matrix, history = build_peer_history_matrix(source_records, latest_peers, source, include_source_prefix=True)
        if history.empty:
            continue
        history["学校"] = history.apply(display_university, axis=1)
        long = history[
            [
                "ranking_source",
                "ranking_year",
                "release_year",
                "学校",
                "university_name_cn",
                "university_name_en",
                "rank_raw",
                "rank_midpoint",
                "total_score",
                "source_file",
                "source_sheet",
                "source_row",
            ]
        ].sort_values(["ranking_source", "学校", "ranking_year"])
        long_parts.append(long)
        source_years[source] = {str(year) for year in history["ranking_year"].dropna().astype(str).tolist()}
        for _, row in latest_peers.iterrows():
            name = display_university(row)
            midpoint = to_float(row.get("rank_midpoint"), default=math.nan)
            if name and not math.isnan(midpoint):
                latest_rank_values.setdefault(name, []).append(midpoint)
        keep_cols = [col for col in matrix.columns if col not in {"序号", "序号/说明", "省份"}]
        matrix = matrix[keep_cols].copy()
        wide = matrix if wide is None else wide.merge(matrix, on="学校名称", how="outer")

    if not long_parts:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "no peer table matrices found"}
    table_data = pd.concat(long_parts, ignore_index=True, sort=False).fillna("")
    matrix = wide.fillna("") if wide is not None else pd.DataFrame()
    source_cols = [col for col in matrix.columns if col != "学校名称"]
    for col in source_cols:
        source = next((name for name, _ in source_artifacts if col.startswith(f"{name} ")), "")
        year_text = col.replace(f"{source} ", "", 1) if source else ""
        for idx, row in matrix.iterrows():
            if clean_text(row.get(col, "")):
                continue
            label = display_missing_label("not_listed") if year_text in source_years.get(source, set()) else display_missing_label("not_published")
            matrix.at[idx, col] = label
    matrix.insert(0, "序号/说明", range(1, len(matrix) + 1))
    matrix.insert(2, "省份", matrix["学校名称"].map(lambda name: lookup_province(province_map, name)))
    matrix["排名平均位次"] = matrix["学校名称"].map(
        lambda name: round(sum(latest_rank_values.get(clean_text(name), [])) / len(latest_rank_values.get(clean_text(name), [])), 1)
        if latest_rank_values.get(clean_text(name))
        else ""
    )
    avg_sort = pd.to_numeric(matrix["排名平均位次"], errors="coerce")
    matrix = matrix.assign(_avg_sort=avg_sort).sort_values(["_avg_sort", "学校名称"], na_position="last").drop(columns=["_avg_sort"])
    # Word 版附表控制在模板接近的篇幅内；完整长表仍保留在 table_data/source_trace 中。
    max_word_rows = APPENDIX_WORD_MAX_ROWS
    tongji_appended = False
    if len(matrix) > max_word_rows:
        tongji_rows = matrix[matrix["学校名称"].astype(str).str.contains("同济", na=False)].copy()
        compact_matrix = matrix.head(max_word_rows).copy()
        if not tongji_rows.empty and not compact_matrix["学校名称"].astype(str).str.contains("同济", na=False).any():
            compact_matrix = pd.concat([compact_matrix, tongji_rows.head(1)], ignore_index=True)
            tongji_appended = True
        matrix = compact_matrix.copy()
    row_labels = [str(index + 1) for index in range(len(matrix))]
    if tongji_appended and row_labels:
        row_labels[-1] = "同济参照"
    matrix["序号/说明"] = row_labels
    ordered_cols = ["序号/说明", "学校名称", "省份"] + source_cols + ["排名平均位次"]
    matrix = matrix[ordered_cols]
    table_data.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    table_data.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"{clean_text(subject['target_subject'])}对标高校排名历史附表（前{max_word_rows}名样本，同济不在前{max_word_rows}时另列参照）", out / "table.png", max_rows=len(matrix))
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(matrix),
        len(table_data),
        {
            "table_shape": "template-like wide peer history",
            "top_rows": max_word_rows,
            "word_rows": len(matrix),
            "tongji_appended": tongji_appended,
            "comparison_note": f"Rows numbered 1-{max_word_rows} are the compact comparison sample; a Tongji reference row is not a rank-order row.",
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(matrix), "output_dir": str(out)}


def build_subject_run_artifacts(
    run_dir: Path,
    subject: dict[str, Any],
    records: pd.DataFrame,
    readiness_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ready_ids = {row["artifact_id"] for row in readiness_rows if row["readiness_status"] == "ready"}
    results: list[dict[str, Any]] = []

    if "figure_01_tongji_subject_ranking_overview" in ready_ids:
        append_builder_result(results, "figure_01_tongji_subject_ranking_overview", lambda: build_figure_01(run_dir, subject, records))
    if "figure_02_ranking_indicator_commonality" in ready_ids:
        append_builder_result(results, "figure_02_ranking_indicator_commonality", lambda: build_figure_02(run_dir, subject))
    if "figure_03_arwu_indicator_weight" in ready_ids:
        append_builder_result(
            results,
            "figure_03_arwu_indicator_weight",
            lambda: build_weight_artifact(run_dir, subject, "软科", "figure_03_arwu_indicator_weight", "软科"),
        )
    if "figure_04_qs_indicator_weight" in ready_ids:
        append_builder_result(
            results,
            "figure_04_qs_indicator_weight",
            lambda: build_weight_artifact(run_dir, subject, "QS", "figure_04_qs_indicator_weight", "QS"),
        )
    if "figure_05_usnews_indicator_weight" in ready_ids:
        append_builder_result(
            results,
            "figure_05_usnews_indicator_weight",
            lambda: build_weight_artifact(run_dir, subject, "US News", "figure_05_usnews_indicator_weight", "U.S. News"),
        )
    elif USNEWS_WEIGHT_CANDIDATE_CSV.exists():
        append_builder_result(results, "figure_05_usnews_indicator_weight_candidate", lambda: build_usnews_candidate_weight(run_dir, subject))
    if "figure_06_the_indicator_weight" in ready_ids:
        append_builder_result(
            results,
            "figure_06_the_indicator_weight",
            lambda: build_weight_artifact(run_dir, subject, "THE", "figure_06_the_indicator_weight", "THE"),
        )
    if "figure_07_all_rankings_history" in ready_ids:
        append_builder_result(results, "figure_07_all_rankings_history", lambda: build_figure_07(run_dir, subject, records))
    if "table_04_mainland_rank_band_distribution" in ready_ids:
        append_builder_result(results, "table_04_mainland_rank_band_distribution", lambda: build_table_04(run_dir, subject, records))

    peer_specs = [
        ("软科", "table_05_arwu_mainland_peer_ranking"),
        ("US News", "table_06_usnews_mainland_peer_ranking"),
        ("QS", "table_07_qs_mainland_peer_ranking"),
        ("THE", "table_08_the_mainland_peer_ranking"),
    ]
    for source, artifact_id in peer_specs:
        if artifact_id in ready_ids:
            append_builder_result(results, artifact_id, lambda source=source, artifact_id=artifact_id: build_peer_table(run_dir, subject, records, source, artifact_id))

    if "table_03_the_tongji_indicator_history" in ready_ids:
        append_builder_result(results, "table_03_the_tongji_indicator_history", lambda: build_the_indicator_history(run_dir, subject))
    if "table_01_arwu_tongji_indicator_history" in ready_ids and ARWU_PUBLIC_TONGJI_LONG_CSV.exists():
        append_builder_result(results, "table_01_arwu_tongji_indicator_history", lambda: build_arwu_public_indicator_history_table(run_dir, subject))
    elif "table_01_arwu_tongji_indicator_history" in ready_ids and ARWU_HISTORY_CSV.exists():
        append_builder_result(
            results,
            "table_01_arwu_tongji_indicator_history",
            lambda: build_external_indicator_history_table(
                run_dir,
                subject,
                "table_01_arwu_tongji_indicator_history",
                "软科",
                ARWU_HISTORY_CSV,
                missing_years=[2024],
            )
        )
    if "table_02_usnews_tongji_indicator_history" in ready_ids:
        append_builder_result(results, "table_02_usnews_tongji_indicator_history", lambda: build_usnews_indicator_history(run_dir, subject))
    if "figure_10_usnews_indicator_history_trend" in ready_ids:
        append_builder_result(results, "figure_10_usnews_indicator_history_trend", lambda: build_usnews_indicator_history_trend(run_dir, subject))
    if "table_09_peer_full_ranking_history_appendix" in ready_ids:
        append_builder_result(results, "table_09_peer_full_ranking_history_appendix", lambda: build_appendix(run_dir, subject, records))

    peer_indicator_specs = [
        (
            "软科",
            "table_05_arwu_mainland_peer_ranking",
            "figure_09_arwu_peer_indicator_relative_rank",
            f"软科排名前200位内地高校{source_title_subject_label(subject, '软科')}分项指标相对表现",
            False,
        ),
        (
            "QS",
            "table_07_qs_mainland_peer_ranking",
            "figure_10_qs_peer_indicator_relative_rank",
            f"QS排名前200位内地高校{source_title_subject_label(subject, 'QS')}分项指标相对表现",
            False,
        ),
        (
            "US News",
            "table_06_usnews_mainland_peer_ranking",
            "figure_11_usnews_peer_indicator_relative_rank",
            f"U.S. News 排名前200位内地高校{source_title_subject_label(subject, 'US News')}分项指标相对排名",
            True,
        ),
        (
            "THE",
            "table_08_the_mainland_peer_ranking",
            "figure_12_the_peer_indicator_relative_rank",
            f"THE排名前200位内地高校{source_title_subject_label(subject, 'THE')}分项指标相对排名",
            True,
        ),
    ]
    for source, peer_artifact_id, artifact_id, title, rank_mode in peer_indicator_specs:
        if artifact_id in ready_ids:
            append_builder_result(
                results,
                artifact_id,
                lambda source=source, peer_artifact_id=peer_artifact_id, artifact_id=artifact_id, title=title, rank_mode=rank_mode: build_peer_indicator_figure(
                    run_dir,
                    subject,
                    source,
                    peer_artifact_id,
                    artifact_id,
                    title,
                    rank_mode,
                ),
            )

    if WOS_SUBJECT_PAPER_CSV.exists() or CWTS_CHINA_ALL_FIELDS_CSV.exists() or CWTS_MATH_PEER_CSV.exists():
        for paper_artifact_id in [
            "figure_13_paper_output_citation_relative_rank",
            "figure_14_paper_cnci_cpp_relative_rank",
            "figure_15_paper_highly_cited_relative_rank",
            "figure_16_paper_international_collab_relative_rank",
        ]:
            append_builder_result(
                results,
                paper_artifact_id,
                lambda paper_artifact_id=paper_artifact_id: build_subject_paper_artifact(run_dir, subject, paper_artifact_id),
            )

    generated = [row for row in results if row["status"] == "generated"]
    skipped = [row for row in results if row["status"] not in {"generated", "error"}]
    errors = [row for row in results if row["status"] == "error"]
    summary = {
        "generated_at": now_text(),
        "attempted_count": len(results),
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "results": results,
    }
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "artifact_generation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    if errors:
        (artifacts_dir / "artifact_generation_errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
    return summary
