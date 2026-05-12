from __future__ import annotations

import csv
import json
import math
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
EXTERNAL_DATA_DIR = PROJECT_DIR / "external_data"
EXTERNAL_PROCESSED_DIR = EXTERNAL_DATA_DIR / "processed"
EXTERNAL_REPORT_DIR = EXTERNAL_DATA_DIR / "reports"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"
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

RANKING_SOURCES = ["软科", "QS", "US News", "THE"]
TOP_RANK_MIDPOINT = 200
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
        "highqualityresearch": "\u9ad8\u8d28\u91cf\u7814\u7a76",
        "cnci": "\u7814\u7a76\u5f71\u54cd",
        "researchimpact": "\u7814\u7a76\u5f71\u54cd",
        "ic": "\u56fd\u9645\u5408\u4f5c",
        "internationalcollaboration": "\u56fd\u9645\u5408\u4f5c",
        "top": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "worldclassoutput": "\u4e16\u754c\u4e00\u6d41\u4ea7\u51fa",
        "award": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
        "worldclassfaculty": "\u4e16\u754c\u4e00\u6d41\u5e08\u8d44",
    }
    the_map = {
        "\u7bc7\u5747\u88ab\u5f15": "\u79d1\u7814\u8d28\u91cf",
        "\u7bc7\u5747\u88ab\u5f15\u6392\u540d": "\u79d1\u7814\u8d28\u91cf\u6392\u540d",
    }
    if source in {"ARWU", "\u8f6f\u79d1", "ARWU GRAS public web"}:
        return arwu_map.get(key, name)
    if source == "THE":
        return the_map.get(name, name)
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


def elide_text(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont, max_width: int) -> str:
    value = clean_text(text)
    if text_size(draw, value, font)[0] <= max_width:
        return value
    ellipsis = "…"
    while value and text_size(draw, value + ellipsis, font)[0] > max_width:
        value = value[:-1]
    return value + ellipsis if value else ellipsis


def wrap_text(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont, max_width: int, max_lines: int = 2) -> list[str]:
    value = clean_text(text)
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


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    with Image.open(path) as check:
        check.verify()


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
    if source == "软科":
        return clean_text(subject.get("arwu_subject_name")) or clean_text(subject.get("target_subject"))
    if source == "QS":
        return clean_text(subject.get("qs_subject_name")) or clean_text(subject.get("target_subject"))
    if source == "US News":
        return clean_text(subject.get("usnews_subject_name")) or clean_text(subject.get("target_subject"))
    area = clean_text(subject.get("the_subject_area"))
    if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        if area in crosswalk:
            return crosswalk[area]
    return area or "自然科学"


def candidate_subject_areas(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    normalized = re.sub(r"[、，,;；/]+", " ", text)
    parts = [part.strip() for part in normalized.split() if part.strip()] if re.search("[\u4e00-\u9fff]", normalized) else [text]
    return parts or [text]


def subject_alias_values(subject: dict[str, Any], source: str) -> set[str]:
    values = {clean_text(value) for value in subject.get("alias_summary", {}).get(source, []) if clean_text(value)}
    target = clean_text(subject.get("target_subject"))
    if target:
        values.add(target)
    return values


def normalize_commonality_group(value: Any) -> str:
    text = clean_text(value)
    mapping = json.loads(INDICATOR_GROUP_CROSSWALK_JSON.read_text(encoding="utf-8")) if INDICATOR_GROUP_CROSSWALK_JSON.exists() else {}
    return mapping.get(text, text or "其他")


def filter_indicators_for_subject(indicators: pd.DataFrame, subject: dict[str, Any], source: str) -> pd.DataFrame:
    aliases = subject_alias_values(subject, source)
    df = indicators[indicators["ranking_source"] == source].copy()
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


def render_cards(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 900), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(38, True)
    font_sub = load_font(22)
    font_source = load_font(30, True)
    font_rank = load_font(56, True)
    font_meta = load_font(19)
    draw.text((85, 52), f"同济大学{subject_name}学科国际排名概览", font=font_title, fill="#16202A")
    draw.text((85, 102), "四大国际排名最新发布年份口径，排名区间保留原始表达", font=font_sub, fill="#5A6573")
    card_w, card_h, gap = 330, 420, 42
    for idx, source in enumerate(RANKING_SOURCES):
        row = df[df["ranking_source"] == source]
        if row.empty:
            continue
        item = row.iloc[0]
        x, y = 85 + idx * (card_w + gap), 185
        color = SOURCE_COLORS[source]
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill="#F8FAFC", outline="#D8DEE8", width=2)
        draw.rectangle((x, y, x + card_w, y + 12), fill=color)
        draw.text((x + 30, y + 42), source, font=font_source, fill=color)
        draw.text((x + 30, y + 118), clean_text(item["rank_raw"]), font=font_rank, fill="#111827")
        draw.text((x + 30, y + 214), f"发布年份：{int(item['release_year'])}", font=font_meta, fill="#374151")
        draw.text((x + 30, y + 252), f"排名年份：{int(item['ranking_year'])}", font=font_meta, fill="#374151")
        draw.text((x + 30, y + 292), f"排名口径：{clean_text(item['ranking_subject_raw'])}"[:24], font=font_meta, fill="#4B5563")
        score = clean_text(item.get("total_score", ""))
        if score:
            draw.text((x + 30, y + 354), f"总分：{score}", font=font_meta, fill="#4B5563")
    save_png(image, out_path)


def build_figure_01(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "figure_01_tongji_subject_ranking_overview"
    out = artifact_dir(run_dir, artifact_id)
    rows = []
    traces = []
    for source in RANKING_SOURCES:
        latest = latest_source_rows(records, source)
        tongji = latest[latest["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        if tongji.empty:
            continue
        tongji = dedupe_subject_rows_by_period(tongji, subject)
        item = tongji.iloc[0].to_dict()
        rows.append(item)
        traces.extend(tongji.to_dict("records"))
    chart_df = pd.DataFrame(rows)
    trace_df = pd.DataFrame(traces)
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    trace_df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_cards(chart_df, clean_text(subject["target_subject"]), out / "chart.png")
    write_common_outputs(out, artifact_id, "chart", len(chart_df), len(trace_df), {"chart_type": "ranking cards"})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(chart_df), "output_dir": str(out)}


def render_history(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 920), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(36, True)
    font_sub = load_font(21)
    font_axis = load_font(18)
    font_label = load_font(15)
    left, top, right, bottom = 140, 150, 1320, 740
    draw.text((90, 48), f"同济大学{subject_name}学科四大国际排名历史趋势", font=font_title, fill="#16202A")
    draw.text((90, 94), "排名区间按中间位次绘图，数值越小表示排名越靠前", font=font_sub, fill="#5A6573")
    years = sorted(int(x) for x in df["release_year"].dropna().unique())
    values = [to_float(x) for x in df["rank_midpoint"].dropna()]
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
        draw.line((left, y, right, y), fill="#E5E7EB")
        draw.text((left - 62, y - 10), str(tick), font=font_axis, fill="#697586")
    draw.line((left, top, left, bottom), fill="#9AA5B1", width=2)
    draw.line((left, bottom, right, bottom), fill="#9AA5B1", width=2)
    for year in years:
        x = xp(year)
        draw_center(draw, (x - 34, bottom + 16, x + 34, bottom + 44), str(year), font_axis, "#52606D")
    for source, group in df.groupby("ranking_source"):
        group = group.sort_values(["release_year", "ranking_year"])
        color = SOURCE_COLORS.get(source, "#333333")
        points = [(xp(int(row["release_year"])), yp(float(row["rank_midpoint"]))) for _, row in group.iterrows()]
        if len(points) > 1:
            draw.line(points, fill=color, width=4)
        for (_, row), (x, y) in zip(group.iterrows(), points):
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color, outline="#FFFFFF", width=2)
            draw.text((x + 9, y - 20), clean_text(row["rank_raw"]), font=font_label, fill=color)
    lx, ly = 1360, 176
    for idx, source in enumerate(RANKING_SOURCES):
        y = ly + idx * 48
        color = SOURCE_COLORS[source]
        draw.line((lx, y + 12, lx + 40, y + 12), fill=color, width=5)
        draw.text((lx + 54, y), source, font=font_axis, fill="#374151")
    save_png(image, out_path)


def build_figure_07(run_dir: Path, subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    artifact_id = "figure_07_all_rankings_history"
    out = artifact_dir(run_dir, artifact_id)
    df = dedupe_records(records)
    tongji = df[df["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    tongji = dedupe_subject_rows_by_period(tongji, subject)
    tongji = tongji.sort_values(["ranking_source", "release_year", "ranking_year"])
    tongji.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    tongji.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_history(tongji, clean_text(subject["target_subject"]), out / "chart.png")
    write_common_outputs(out, artifact_id, "chart", len(tongji), len(tongji), {"chart_type": "multi-source history line"})
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(tongji), "output_dir": str(out)}


def render_weight(df: pd.DataFrame, title: str, out_path: Path) -> None:
    image = Image.new("RGB", (1500, 900), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(36, True)
    font_sub = load_font(20)
    font_label = load_font(18)
    draw.text((72, 42), title, font=font_title, fill="#16202A")
    draw.text((72, 88), "按一级指标权重汇总展示，环形图中心为权重合计", font=font_sub, fill="#5A6573")
    rows = df.sort_values("weight_percent", ascending=False).to_dict("records")
    total = sum(to_float(row["weight_percent"]) for row in rows) or 100.0
    palette = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD", "#E17C05", "#937860", "#8C8C8C"]
    box = (92, 170, 732, 810)
    start = -90.0
    for idx, row in enumerate(rows):
        pct = to_float(row["weight_percent"])
        extent = 360.0 * pct / total
        draw.pieslice(box, start, start + extent, fill=palette[idx % len(palette)], outline="#FFFFFF", width=2)
        start += extent
    draw.ellipse((255, 333, 569, 647), fill="#FFFFFF")
    draw_center(draw, (270, 405, 554, 455), f"{total:.0f}%", load_font(30, True), "#16202A")
    x0, y0 = 820, 175
    for idx, row in enumerate(rows[:10]):
        y = y0 + idx * 64
        draw.rounded_rectangle((x0, y, x0 + 28, y + 28), radius=6, fill=palette[idx % len(palette)])
        draw_text_box(draw, (x0 + 46, y - 10, x0 + 485, y + 42), row["indicator_name"], font_label, "#1F2933", "left", max_lines=2)
        draw.text((x0 + 510, y - 2), f"{to_float(row['weight_percent']):.1f}%", font=font_label, fill="#374151")
    save_png(image, out_path)


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
    parent_order = parent_order[:6]
    work = work[work["parent_indicator"].isin(parent_order)].copy()

    leaf_count = sum(min(8, len(work[work["parent_indicator"] == parent])) for parent in parent_order)
    row_h = 48
    group_gap = 30
    top = 164
    bottom = 64
    height = max(980, top + leaf_count * row_h + max(0, len(parent_order) - 1) * group_gap + bottom)
    image = Image.new("RGB", (1680, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(40, True)
    font_sub = load_font(22)
    font_root = load_font(26, True)
    font_parent = load_font(23, True)
    font_leaf = load_font(23)
    font_pct = load_font(22, True)
    font_note = load_font(17)
    draw.text((54, 36), title, font=font_title, fill="#16202A")
    draw.text((54, 88), "按一级维度展开到二级指标；左侧为一级权重，右侧为具体指标权重", font=font_sub, fill="#5A6573")

    root_box = (54, top + 44, 256, top + 156)
    root_total = work.groupby("parent_indicator")["parent_weight_percent"].max().sum()
    if root_total <= 0:
        root_total = work["weight_percent"].sum()
    draw.rounded_rectangle(root_box, radius=14, fill="#F8FAFC", outline="#16202A", width=3)
    draw_text_box(draw, (root_box[0] + 8, root_box[1] + 12, root_box[2] - 8, root_box[3] - 42), "指标体系", font_root, "#16202A", max_lines=2)
    draw_center(draw, (root_box[0], root_box[3] - 44, root_box[2], root_box[3] - 8), f"{root_total:.1f}%", font_pct, "#52606D")

    palette = ["#315D9C", "#C64B46", "#3C8D5A", "#7B5CA8", "#D68A35", "#6B7280"]
    current_y = top
    parent_boxes: dict[str, tuple[float, float, float, float]] = {}
    for idx, parent in enumerate(parent_order):
        parent_rows = work[work["parent_indicator"] == parent].sort_values("weight_percent", ascending=False).head(8)
        weight = float(work[work["parent_indicator"] == parent]["parent_weight_percent"].max())
        block_h = max(72, len(parent_rows) * row_h)
        box = (316, current_y + max(0, (block_h - 78) / 2), 650, current_y + max(0, (block_h - 78) / 2) + 78)
        color = palette[idx % len(palette)]
        parent_boxes[parent] = box
        width = max(2, min(12, int(weight / max(root_total, 1) * 22)))
        draw.line((root_box[2], (root_box[1] + root_box[3]) / 2, box[0], (box[1] + box[3]) / 2), fill=color, width=width)
        draw.rounded_rectangle(box, radius=12, fill="#FFFFFF", outline=color, width=3)
        draw_text_box(draw, (box[0] + 12, box[1] + 8, box[2] - 92, box[3] - 8), parent, font_parent, color, "left", max_lines=2)
        draw_center(draw, (box[2] - 88, box[1], box[2] - 8, box[3]), f"{weight:.1f}%", font_pct, color)

        leaf_x0 = 742
        leaf_x1 = 1530
        parent_rows = work[work["parent_indicator"] == parent].sort_values("weight_percent", ascending=False).head(8)
        block_top = current_y
        for leaf_idx, (_, leaf) in enumerate(parent_rows.iterrows()):
            y = block_top + leaf_idx * row_h
            weight = float(leaf["weight_percent"])
            line_w = max(1, min(8, int(weight / max(root_total, 1) * 22)))
            draw.line((box[2], (box[1] + box[3]) / 2, leaf_x0 - 22, y + row_h / 2), fill=color, width=line_w)
            draw.rounded_rectangle((leaf_x0 - 24, y + 11, leaf_x1, y + 39), radius=10, fill="#FFFFFF", outline="#E1E7EF", width=1)
            draw.ellipse((leaf_x0 - 32, y + 18, leaf_x0 - 18, y + 32), fill=color)
            label = clean_text(leaf["indicator_name"])
            draw_text_box(draw, (leaf_x0 - 4, y + 4, leaf_x1 - 110, y + 46), label, font_leaf, "#1F2933", "left", max_lines=2)
            draw_text_right(draw, leaf_x1 - 14, y + 10, f"{weight:.1f}%", font_pct, "#52606D")
        current_y += block_h + group_gap
    if len(work) > leaf_count:
        draw.text((54, height - 38), "注：图中展示主要一级维度下权重较高的二级指标，完整权重明细保留在数据文件中。", font=font_note, fill="#697586")
    save_png(image, out_path)


def build_weight_artifact(run_dir: Path, subject: dict[str, Any], source: str, artifact_id: str, title_source: str) -> dict[str, Any]:
    out = artifact_dir(run_dir, artifact_id)
    weights = read_weights()
    area = expected_weight_area(subject, source)
    df = pd.DataFrame()
    for candidate in candidate_subject_areas(area):
        df = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)].copy()
        if not df.empty:
            area = candidate
            break
    if df.empty and source == "THE":
        area = "自然科学"
        df = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == area)].copy()
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing weight: {source}/{area}"}
    plot_df = df
    if "indicator_level" in df.columns:
        first_level = df[df["indicator_level"] == "一级指标"].copy()
        if not first_level.empty:
            plot_df = first_level
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    plot_df.to_csv(out / "chart_plot_data.csv", index=False, encoding="utf-8-sig")
    df[["source_file", "source_sheet", "source_row", "ranking_source", "ranking_subject_or_area", "indicator_name", "weight_percent"]].to_csv(
        out / "source_trace.csv", index=False, encoding="utf-8-sig"
    )
    if source in {"US News", "THE"}:
        tree_df = build_weight_tree_data(df)
        tree_df.to_csv(out / "chart_tree_data.csv", index=False, encoding="utf-8-sig")
        render_weight_tree(tree_df, f"{title_source}{clean_text(subject['target_subject'])}指标权重", out / "chart.png")
        chart_type = "hierarchical weight tree"
    else:
        render_weight(plot_df, f"{title_source}{clean_text(subject['target_subject'])}指标权重", out / "chart.png")
        chart_type = "donut weight chart"
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(df),
        len(df),
        {
            "ranking_source": source,
            "ranking_subject_or_area": area,
            "plot_rows": len(plot_df),
            "plot_weight_total": float(plot_df["weight_percent"].sum()),
            "chart_type": chart_type,
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def render_commonality_flow(df: pd.DataFrame, subject_name: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 940), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(36, True)
    font_sub = load_font(20)
    font_node = load_font(20, True)
    font_small = load_font(15)
    draw.text((70, 42), f"{subject_name}学科四大国际排名指标共性", font=font_title, fill="#16202A")
    draw.text((70, 88), "按指标组归并；有权重时使用权重百分比，缺权重时使用指标覆盖数量", font=font_sub, fill="#5A6573")

    groups = sorted(df["indicator_group"].dropna().unique().tolist(), key=lambda g: (-df[df["indicator_group"] == g]["link_value"].sum(), g))
    source_y = {source: 190 + idx * 150 for idx, source in enumerate(RANKING_SOURCES)}
    group_step = min(92, 590 // max(1, len(groups)))
    group_y = {group: 155 + idx * group_step for idx, group in enumerate(groups)}
    sx, gx = 155, 1120
    for source in RANKING_SOURCES:
        color = SOURCE_COLORS[source]
        y = source_y[source]
        draw.rounded_rectangle((sx, y, sx + 210, y + 70), radius=12, fill="#F8FAFC", outline=color, width=3)
        draw_center(draw, (sx, y, sx + 210, y + 70), source, font_node, color)
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
    draw.text((70, 850), "注：US News 若缺少目标学科权重，本图仅展示分项指标覆盖关系，不解释为权重。", font=font_small, fill="#697586")
    save_png(image, out_path)


def build_figure_02(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_02_ranking_indicator_commonality"
    out = artifact_dir(run_dir, artifact_id)
    weights = read_weights()
    indicators = read_indicators()
    parts = []
    for source in RANKING_SOURCES:
        area = expected_weight_area(subject, source)
        subset = pd.DataFrame()
        for candidate in candidate_subject_areas(area):
            subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)].copy()
            if not subset.empty:
                area = candidate
                break
        if subset.empty and source == "THE":
            area = "自然科学"
            subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == area)].copy()
        if not subset.empty:
            plot_subset = subset
            first_level = subset[subset.get("indicator_level", "") == "一级指标"].copy() if "indicator_level" in subset.columns else pd.DataFrame()
            if source == "THE" and not first_level.empty:
                plot_subset = first_level
            plot_subset = plot_subset.copy()
            plot_subset["basis"] = "weight_percent"
            plot_subset["link_value"] = plot_subset["weight_percent"]
            parts.append(plot_subset[["ranking_source", "ranking_subject_or_area", "indicator_name", "indicator_group", "basis", "link_value", "source_file", "source_sheet", "source_row"]])
        else:
            ind = filter_indicators_for_subject(indicators, subject, source)
            tongji = ind[ind["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
            if not tongji.empty:
                latest_release = tongji["release_year"].max()
                latest_ranking = tongji[tongji["release_year"] == latest_release]["ranking_year"].max()
                tongji = tongji[(tongji["release_year"] == latest_release) & (tongji["ranking_year"] == latest_ranking)].copy()
                tongji = tongji[tongji["metric_type"].isin(["score", "rank"])].copy()
                tongji["ranking_subject_or_area"] = clean_text(subject.get("target_subject"))
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
    bottom = 88
    column_gap = 18
    column_w = 228 if len(indicators) <= 5 else 208 if len(indicators) <= 7 else 184
    width = max(1350, left + right + len(indicators) * column_w + (len(indicators) - 1) * column_gap)
    row_step = 17 if name_count <= 45 else 12 if name_count <= 75 else 9
    plot_h = max(520, min(940, row_step * max(1, name_count - 1)))
    height = top + plot_h + bottom

    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    title_font_size = 34
    font_title = load_font(title_font_size, True)
    font_sub = load_font(17)
    font_indicator = load_font(13 if len(indicators) >= 8 else 14, True)
    font_axis = load_font(12)
    font_name = load_font(12 if name_count <= 70 else 10)
    font_value = load_font(11)
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
        draw.line((x0 - 9, top - 8, x0 - 9, plot_bottom + 26), fill="#D7DEE8", width=2)
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
            draw.line((x, top, x, plot_bottom), fill="#EEF2F7", width=1)
        draw.line((x0, top, x0, plot_bottom), fill="#C7D0DD", width=1)
        draw.line((x0, plot_bottom, x1, plot_bottom), fill="#C7D0DD", width=1)

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
            draw.line([(x, y) for x, y, _ in points], fill="#6EA0E6", width=3)
        for x, y, item in points:
            is_tongji = str(item.get("is_tongji", "")).lower() in {"true", "1"}
            color = "#C64B46" if is_tongji else "#4F83CC"
            radius = 6 if is_tongji else 3
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#FFFFFF", width=1)
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
    size_col = "comparison_scope_size" if "comparison_scope_size" in work.columns else "peer_scope_size"
    work[rank_col] = pd.to_numeric(work[rank_col], errors="coerce")
    work[size_col] = pd.to_numeric(work[size_col], errors="coerce")
    work = work.dropna(subset=[rank_col, size_col]).copy()
    if work.empty:
        return
    work = work.sort_values([rank_col, "display_indicator_name" if "display_indicator_name" in work.columns else "indicator_name"])

    width = 1760
    row_h = 72
    top = 166
    bottom = 86
    height = max(860, top + len(work) * row_h + bottom)
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(38, True)
    font_sub = load_font(21)
    font_label = load_font(22, True)
    font_small = load_font(19)
    font_value = load_font(20, True)
    draw.text((58, 34), title, font=font_title, fill="#16202A")
    draw.text((58, 86), "每条标尺表示一个分项指标的对标范围；红点越靠左，说明同济大学相对位次越靠前。", font=font_sub, fill="#5A6573")

    label_left = 70
    label_right = 520
    track_left = 590
    track_right = 1450
    value_left = 1490
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
        draw.line((track_left, y + 18, track_right, y + 18), fill="#D7DEE8", width=10)
        draw.line((track_left, y + 18, marker_x, y + 18), fill=color, width=10)
        for frac, text in [(0, "靠前"), (0.5, "中位"), (1, "靠后")]:
            x = track_left + frac * (track_right - track_left)
            draw.line((x, y + 4, x, y + 32), fill="#AAB4C3", width=2)
            if idx == 0:
                draw_center(draw, (x - 38, y - 48, x + 38, y - 18), text, font_small, "#697586")
        draw.ellipse((marker_x - 13, y + 5, marker_x + 13, y + 31), fill="#C64B46", outline="#FFFFFF", width=3)
        draw.text((value_left, y + 2), f"第{int(rank)} / {int(size)}位", font=font_value, fill="#C64B46")
        draw.text((value_left, y + 30), f"前{percentile * 100:.1f}%", font=font_small, fill="#52606D")

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
        row = {"序号": idx + 1, "学校名称": name, "省份": lookup_province(province_map, name)}
        for year in year_cols:
            values = peer_history[peer_history["_year"] == year]["rank_raw"]
            col_name = f"{source} {year}" if include_source_prefix else year
            if not values.empty:
                row[col_name] = clean_text(values.iloc[0])
            else:
                row[col_name] = display_missing_label("not_listed") if year in published_years else display_missing_label("not_published")
        rows.append(row)
    return pd.DataFrame(rows), history


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
    for source in RANKING_SOURCES:
        latest = latest_source_rows(records, source)
        mainland = latest[latest.apply(is_mainland, axis=1)].copy() if not latest.empty else latest
        top200 = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= TOP_RANK_MIDPOINT].copy()
        top200, _ = dedupe_university_rows(top200, subject, source)
        peer_records.extend(top200.to_dict("records"))
        for lo, hi, label in bands:
            count = len(mainland[(mainland["rank_midpoint"] >= lo) & (mainland["rank_midpoint"] <= hi)])
            rows.append({"榜单": source, "位次区间": label, "高校数量": count})
        rows.append({"榜单": source, "位次区间": "1-200合计", "高校数量": len(top200)})
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
    latest = latest_source_rows(records, source)
    mainland = latest[latest.apply(is_mainland, axis=1)].copy() if not latest.empty else latest
    top = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= TOP_RANK_MIDPOINT].copy()
    top, duplicate_rows = dedupe_university_rows(top, subject, source)
    top = top.sort_values(["rank_midpoint", "university_name_cn", "university_name_en"]).reset_index(drop=True)
    if top.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"no {source} top200 mainland peers"}
    source_records = records[records["ranking_source"] == source].copy()
    table, history = build_peer_history_matrix(source_records, top, source)
    if table.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"no {source} peer history"}
    history.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    table.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    top.to_csv(out / "latest_peer_records.csv", index=False, encoding="utf-8-sig")
    duplicate_rows.to_csv(out / "deduped_duplicate_records.csv", index=False, encoding="utf-8-sig")
    history.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(table, f"{source}{clean_text(subject['target_subject'])}内地高校排名历史（前32项）", out / "table.png", max_rows=32)
    (out / "table.md").write_text(dataframe_to_markdown(table), encoding="utf-8", newline="\n")
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(table),
        len(history) + len(duplicate_rows),
        {"ranking_source": source, "table_shape": "peer multi-year history", "deduped_duplicate_rows": len(duplicate_rows)},
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(table), "output_dir": str(out)}


def build_the_indicator_history(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
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
    preferred_keys = {normalize_subject_history_key(preferred)} if preferred else set()
    preferred_df = df[raw_keys.isin(preferred_keys) | en_keys.isin(preferred_keys) | norm_keys.isin(preferred_keys)].copy()
    if not preferred_df.empty:
        preferred_keys.update(preferred_df.get("ranking_subject_en", pd.Series(dtype=str)).map(normalize_subject_history_key).tolist())
        preferred_keys.update(preferred_df.get("ranking_subject_raw", pd.Series(dtype=str)).map(normalize_subject_history_key).tolist())
        return df[raw_keys.isin(preferred_keys) | en_keys.isin(preferred_keys) | norm_keys.isin(preferred_keys)].copy()

    aliases = {normalize_subject_history_key(value) for value in subject_alias_values(subject, source_name)}
    aliases.update(normalize_subject_history_key(value) for value in [subject.get("target_subject"), preferred] if clean_text(value))
    return df[raw_keys.isin(aliases) | en_keys.isin(aliases) | norm_keys.isin(aliases)].copy()


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
    df["ranking_year"] = pd.to_numeric(df["ranking_year"], errors="coerce")
    df["indicator_value_num"] = pd.to_numeric(df["indicator_value"], errors="coerce")
    df["display_indicator_name"] = df["indicator_name"].map(lambda value: canonical_indicator_name("ARWU GRAS public web", value))
    df = df[df["display_indicator_name"].astype(str).str.len() > 0].copy()
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
    write_common_outputs(
        out,
        artifact_id,
        "table",
        len(df),
        len(df),
        {
            "ranking_source": "ARWU GRAS public web",
            "years": years,
            "matched_public_subjects": sorted(set(df["arwu_subject_name_en"].tolist())),
            "external_source": str(ARWU_PUBLIC_TONGJI_LONG_CSV),
        },
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def render_indicator_trend(df: pd.DataFrame, title: str, out_path: Path) -> None:
    image = Image.new("RGB", (1600, 940), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(34, True)
    font_sub = load_font(19)
    font_axis = load_font(16)
    font_label = load_font(14)
    draw.text((70, 40), title, font=font_title, fill="#16202A")
    draw.text((70, 82), "US News 分项指标排名趋势，数值越小表示相对排名越靠前", font=font_sub, fill="#5A6573")
    plot = df.copy()
    plot["ranking_year"] = pd.to_numeric(plot["ranking_year"], errors="coerce")
    plot["indicator_value_num"] = pd.to_numeric(plot["indicator_value"], errors="coerce")
    plot = plot.dropna(subset=["ranking_year", "indicator_value_num"])
    indicators = plot["indicator_name"].drop_duplicates().tolist()[:8]
    years = sorted(int(x) for x in plot["ranking_year"].dropna().unique())
    if not years or not indicators:
        save_png(image, out_path)
        return
    left, top, right, bottom = 145, 145, 1280, 760
    max_v = max(400, int(math.ceil(plot["indicator_value_num"].max() / 100.0) * 100))

    def xp(year: int) -> float:
        return left + (year - min(years)) / max(1, max(years) - min(years)) * (right - left)

    def yp(value: float) -> float:
        return top + value / max(1, max_v) * (bottom - top)

    for tick in range(0, max_v + 1, 100):
        y = yp(tick)
        draw.line((left, y, right, y), fill="#E5E7EB")
        draw.text((left - 70, y - 9), str(tick), font=font_axis, fill="#697586")
    draw.line((left, top, left, bottom), fill="#9AA5B1", width=2)
    draw.line((left, bottom, right, bottom), fill="#9AA5B1", width=2)
    for year in years:
        x = xp(year)
        draw_center(draw, (x - 36, bottom + 16, x + 36, bottom + 44), str(year), font_axis, "#52606D")
    palette = ["#315D9C", "#C64B46", "#3C8D5A", "#7B5CA8", "#D68A35", "#6B7280", "#C85D7B", "#4C72B0"]
    for idx, indicator in enumerate(indicators):
        color = palette[idx % len(palette)]
        group = plot[plot["indicator_name"] == indicator].sort_values("ranking_year")
        points = [(xp(int(row["ranking_year"])), yp(float(row["indicator_value_num"]))) for _, row in group.iterrows()]
        if len(points) > 1:
            draw.line(points, fill=color, width=3)
        for x, y in points:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color, outline="#FFFFFF", width=2)
        ly = 160 + idx * 52
        draw.line((1325, ly + 10, 1360, ly + 10), fill=color, width=4)
        draw.text((1370, ly), indicator[:18], font=font_label, fill="#374151")
    save_png(image, out_path)


def build_usnews_indicator_history_trend(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_10_usnews_indicator_history_trend"
    out = artifact_dir(run_dir, artifact_id)
    df = read_external_csv(USNEWS_HISTORY_CSV)
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing US News external indicator history"}
    df = filter_external_subject_history(df, subject, "US News")
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": f"missing US News external indicator history for subject: {clean_text(subject.get('target_subject'))}"}
    df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_indicator_trend(df, f"US News {clean_text(subject['target_subject'])}同济分项指标历史趋势", out / "chart.png")
    years = sorted(pd.to_numeric(df["ranking_year"], errors="coerce").dropna().astype(int).unique().tolist())
    write_common_outputs(
        out,
        artifact_id,
        "chart",
        len(df),
        len(df),
        {"ranking_source": "US News", "years": years, "external_source": str(USNEWS_HISTORY_CSV)},
    )
    return {"artifact_id": artifact_id, "status": "generated", "rows": len(df), "output_dir": str(out)}


def build_usnews_candidate_weight(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    artifact_id = "figure_05_usnews_indicator_weight"
    if not is_math_subject(subject):
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "US News candidate weight is math-only"}
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
    render_weight_tree(tree_df, f"US News {clean_text(subject['target_subject'])}指标权重候选口径", out / "chart.png")
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
    mapping = {
        "source_system": "Web of Science subject paper metrics",
        "source_file": str(WOS_SUBJECT_PAPER_CSV),
        "scope_type": "ministry_first_level_subject",
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
    peers = read_current_run_peer_scope(run_dir)
    peer_names_en = set(peers.get("university_name_en", pd.Series(dtype=str)).dropna().astype(str).str.lower().str.strip())
    peer_names_cn = set(peers.get("university_name_cn", pd.Series(dtype=str)).dropna().astype(str).str.strip())
    matched = pd.DataFrame()
    if "university_name_en" in df.columns and peer_names_en:
        matched = df[df["university_name_en"].astype(str).str.lower().str.strip().isin(peer_names_en)].copy()
        matched["matched_current_peer_by_en"] = True
    if "university_name_cn" in df.columns and peer_names_cn:
        matched_cn = df[df["university_name_cn"].astype(str).str.strip().isin(peer_names_cn)].copy()
        matched_cn["matched_current_peer_by_cn"] = True
        matched = pd.concat([matched, matched_cn], ignore_index=True, sort=False)
    if not matched.empty:
        matched = matched.drop_duplicates(subset=["university_name_cn", "university_name_en", "ministry_subject_code"])
        matched["matched_current_subject_peer"] = True
    tongji = df[
        df.get("university_name_cn", pd.Series([""] * len(df))).apply(is_tongji_name)
        | df.get("university_name_en", pd.Series([""] * len(df))).apply(is_tongji_name)
    ].copy()
    if not tongji.empty:
        tongji["matched_current_subject_peer"] = True
        matched = pd.concat([matched, tongji], ignore_index=True, sort=False).drop_duplicates(
            subset=["university_name_cn", "university_name_en", "ministry_subject_code"]
        )
    if matched.empty:
        matched = df.copy()
        matched["matched_current_subject_peer"] = False
    mapping["matched_peer_rows"] = int(len(matched))
    mapping["field_rows"] = int(len(df))
    mapping["paper_field"] = clean_text(df.iloc[0].get("paper_field", "")) if not df.empty else ""
    return matched, mapping


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


def render_paper_bar_chart(df: pd.DataFrame, title: str, metrics: list[tuple[str, str]], out_path: Path, note: str) -> None:
    image = Image.new("RGB", (1780, 1040), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(38, True)
    font_sub = load_font(21)
    font_label = load_font(20)
    font_small = load_font(18)
    draw.text((70, 40), title, font=font_title, fill="#16202A")
    draw_text_box(draw, (62, 84, 1700, 132), note, font_sub, "#5A6573", "left", max_lines=2)
    panels = len(metrics)
    panel_w = int((1600 - (panels - 1) * 54) / max(1, panels))
    panel_h = 760
    top = 182
    for idx, (metric, label) in enumerate(metrics):
        panel_left = 70 + idx * (panel_w + 50)
        panel_right = panel_left + panel_w
        values = pd.to_numeric(df[metric], errors="coerce").fillna(0)
        top_df = df.assign(_value=values).sort_values("_value", ascending=False).head(14).copy()
        tongji_rows = df[df.apply(lambda row: is_tongji_name(short_university_name(row)) or is_tongji_name(row.get("University", "")), axis=1)].assign(_value=values)
        if not tongji_rows.empty and not top_df.index.isin(tongji_rows.index).any():
            top_df = pd.concat([top_df.iloc[:13], tongji_rows.head(1)]).copy()
        max_v = max(1.0, float(top_df["_value"].max()))
        draw.text((panel_left, top - 42), label, font=load_font(24, True), fill="#1F2933")
        bar_h = min(38, int(panel_h / max(1, len(top_df)) - 10))
        for ridx, (_, row) in enumerate(top_df.iterrows()):
            y = top + ridx * (bar_h + 14)
            name = short_university_name(row)
            value = float(row["_value"])
            bar_w = (panel_w - 260) * value / max_v
            color = "#C64B46" if is_tongji_name(name) or is_tongji_name(row.get("University", "")) else "#315D9C"
            label_fill = "#C64B46" if color == "#C64B46" else "#374151"
            draw.text((panel_left, y + 6), name[:13], font=font_label, fill=label_fill)
            draw.rounded_rectangle((panel_left + 172, y, panel_left + 172 + bar_w, y + bar_h), radius=6, fill=color)
            draw.text((panel_right - 88, y + 6), f"{value:.1f}", font=font_small, fill=label_fill)
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
    image = Image.new("RGB", (1760, 1040), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_title = load_font(38, True)
    font_sub = load_font(21)
    font_axis = load_font(20, True)
    font_tick = load_font(17)
    font_label = load_font(18, True)
    draw.text((70, 40), title, font=font_title, fill="#16202A")
    draw_text_box(draw, (62, 84, 1680, 132), note, font_sub, "#5A6573", "left", max_lines=2)
    plot = df.dropna(subset=[x_metric, y_metric]).copy()
    left, top, right, bottom = 180, 172, 1510, 835
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
    draw.rectangle((left, top, right, bottom), outline="#CBD2D9", width=2)
    x_med = float(x_vals.median())
    y_med = float(y_vals.median())
    for i in range(6):
        x = left + i / 5 * (right - left)
        y = top + i / 5 * (bottom - top)
        draw.line((x, top, x, bottom), fill="#EEF2F7")
        draw.line((left, y, right, y), fill="#EEF2F7")
        xv = x_min + i / 5 * (x_max - x_min)
        yv = y_max - i / 5 * (y_max - y_min)
        draw_text_right(draw, x, bottom + 14, f"{xv:.1f}", font_tick, "#697586")
        draw_text_right(draw, left - 12, y - 9, f"{yv:.1f}", font_tick, "#697586")

    def xpos(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (right - left)

    def ypos(value: float) -> float:
        return bottom - (value - y_min) / (y_max - y_min) * (bottom - top)

    draw.line((xpos(x_med), top, xpos(x_med), bottom), fill="#B8C2D0", width=2)
    draw.line((left, ypos(y_med), right, ypos(y_med)), fill="#B8C2D0", width=2)
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
        radius = 11 if color == "#C64B46" else 6
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#FFFFFF", width=1)
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
        render_paper_bar_chart(df, spec["title"], metrics, out / "chart.png", spec["note"])
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
        df, paper_mapping = select_cwts_peer_rows(run_dir, subject)
        source_kind = "cwts"
    if df.empty:
        return {"artifact_id": artifact_id, "status": "skipped", "reason": "missing WOS subject data and CWTS broad-field proxy data"}

    title_prefix = "对标高校"
    if source_kind == "wos":
        note_prefix = f"Web of Science 一级学科口径：{clean_text(paper_mapping.get('paper_field'))}；原表未提供统计年份字段。"
        metric_map = {
            "figure_13_paper_output_citation_relative_rank": {
                "metrics": [("WOS_documents", "论文总量"), ("times_cited", "总被引")],
                "title": f"{title_prefix}论文及被引总量相对表现",
                "note": note_prefix,
                "renderer": "bar",
            },
            "figure_14_paper_cnci_cpp_relative_rank": {
                "metrics": [("citation_impact", "篇均被引"), ("CNCI", "CNCI")],
                "title": f"{title_prefix}篇均被引与 CNCI 相对表现",
                "note": note_prefix,
                "renderer": "scatter",
            },
            "figure_15_paper_highly_cited_relative_rank": {
                "metrics": [("documents_top_1", "前1%论文数"), ("highly_cited_papers", "ESI高被引论文数")],
                "title": f"{title_prefix}高被引论文相对表现",
                "note": note_prefix,
                "renderer": "bar",
            },
            "figure_16_paper_international_collab_relative_rank": {
                "metrics": [("international_documents", "国际合作论文数"), ("pct_international_documents", "国际合作论文占比")],
                "title": f"{title_prefix}国际合作论文相对表现",
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
    ]
    data_cols = base_cols + [item for metric, _ in metrics for item in [metric, f"{metric}_relative_rank"] if item in df.columns]
    data_cols = [col for col in data_cols if col in df.columns]
    chart_df = df[data_cols].copy()
    chart_df.to_csv(out / "chart_data.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    if spec["renderer"] == "scatter":
        render_paper_scatter(df, spec["title"], metrics[0][0], metrics[1][0], out / "chart.png", spec["note"])
    else:
        render_paper_bar_chart(df, spec["title"], metrics, out / "chart.png", spec["note"])
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
        keep_cols = [col for col in matrix.columns if col not in {"序号", "省份"}]
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
    matrix.insert(0, "序号", range(1, len(matrix) + 1))
    matrix.insert(2, "省份", matrix["学校名称"].map(lambda name: lookup_province(province_map, name)))
    matrix["排名平均位次"] = matrix["学校名称"].map(
        lambda name: round(sum(latest_rank_values.get(clean_text(name), [])) / len(latest_rank_values.get(clean_text(name), [])), 1)
        if latest_rank_values.get(clean_text(name))
        else ""
    )
    avg_sort = pd.to_numeric(matrix["排名平均位次"], errors="coerce")
    matrix = matrix.assign(_avg_sort=avg_sort).sort_values(["_avg_sort", "学校名称"], na_position="last").drop(columns=["_avg_sort"])
    # Word 版附表控制在模板接近的篇幅内；完整长表仍保留在 table_data/source_trace 中。
    max_word_rows = 50
    if len(matrix) > max_word_rows:
        tongji_rows = matrix[matrix["学校名称"].astype(str).str.contains("同济", na=False)].copy()
        compact_matrix = matrix.head(max_word_rows).copy()
        if not tongji_rows.empty and not compact_matrix["学校名称"].astype(str).str.contains("同济", na=False).any():
            compact_matrix = pd.concat([compact_matrix.head(max_word_rows - 1), tongji_rows.head(1)], ignore_index=True)
        matrix = compact_matrix.copy()
    matrix["序号"] = range(1, len(matrix) + 1)
    ordered_cols = ["序号", "学校名称", "省份"] + source_cols + ["排名平均位次"]
    matrix = matrix[ordered_cols]
    table_data.to_csv(out / "table_data.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(out / "table_matrix.csv", index=False, encoding="utf-8-sig")
    table_data.to_csv(out / "source_trace.csv", index=False, encoding="utf-8-sig")
    render_table(matrix, f"{clean_text(subject['target_subject'])}对标高校排名历史附表（前32项）", out / "table.png", max_rows=32)
    (out / "table.md").write_text(dataframe_to_markdown(matrix), encoding="utf-8", newline="\n")
    write_common_outputs(out, artifact_id, "table", len(matrix), len(table_data), {"table_shape": "template-like wide peer history"})
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
            lambda: build_weight_artifact(run_dir, subject, "US News", "figure_05_usnews_indicator_weight", "US News"),
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
    if ARWU_PUBLIC_TONGJI_LONG_CSV.exists():
        append_builder_result(results, "table_01_arwu_tongji_indicator_history", lambda: build_arwu_public_indicator_history_table(run_dir, subject))
    elif ARWU_HISTORY_CSV.exists():
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
    if USNEWS_HISTORY_CSV.exists():
        append_builder_result(
            results,
            "table_02_usnews_tongji_indicator_history",
            lambda: build_external_indicator_history_table(
                run_dir,
                subject,
                "table_02_usnews_tongji_indicator_history",
                "US News",
                USNEWS_HISTORY_CSV,
            )
        )
        append_builder_result(results, "figure_10_usnews_indicator_history_trend", lambda: build_usnews_indicator_history_trend(run_dir, subject))
    if "table_09_peer_full_ranking_history_appendix" in ready_ids:
        append_builder_result(results, "table_09_peer_full_ranking_history_appendix", lambda: build_appendix(run_dir, subject, records))

    peer_indicator_specs = [
        (
            "软科",
            "table_05_arwu_mainland_peer_ranking",
            "figure_09_arwu_peer_indicator_relative_rank",
            f"软科排名前200位内地高校{clean_text(subject['target_subject'])}分项指标相对表现",
            False,
        ),
        (
            "US News",
            "table_06_usnews_mainland_peer_ranking",
            "figure_11_usnews_peer_indicator_relative_rank",
            f"US News排名前200位内地高校{clean_text(subject['target_subject'])}分项指标相对排名",
            True,
        ),
        (
            "THE",
            "table_08_the_mainland_peer_ranking",
            "figure_12_the_peer_indicator_relative_rank",
            f"THE排名前200位内地高校{clean_text(subject['target_subject'])}分项指标相对排名",
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
