from __future__ import annotations

import csv
import json
import platform
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_agent_runs"
LOG_DIR = PROJECT_DIR / "logs"
EXTERNAL_DATA_DIR = PROJECT_DIR / "external_data"
EXTERNAL_GAP_STATUS_JSON = EXTERNAL_DATA_DIR / "reports" / "external_gap_resolution_status.json"
CWTS_SUBJECT_FIELD_CROSSWALK_CSV = EXTERNAL_DATA_DIR / "processed" / "cwts_subject_field_crosswalk.csv"
CWTS_CHINA_ALL_FIELDS_CSV = EXTERNAL_DATA_DIR / "processed" / "cwts_traditional_2025_china_latest_all_fields.csv"
WOS_SUBJECT_PAPER_CSV = EXTERNAL_DATA_DIR / "processed" / "wos_37_university_subject_paper_metrics_20260511.csv"
ARWU_PUBLIC_TONGJI_LONG_CSV = EXTERNAL_DATA_DIR / "processed" / "arwu_gras_public_tongji_history_2023_2025_long.csv"
USNEWS_TONGJI_HISTORY_CSV = EXTERNAL_DATA_DIR / "processed" / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
LOGICAL_SLOT_MAPPING_CSV = CONFIG_DIR / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"
CURRENT_REQUEST_JSON = CONFIG_DIR / "runtime" / "current_subject_request.json"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"
README_PATH = PROJECT_DIR / "README.md"
RECOMMENDED_PYTHON = Path(r"E:\conda_envs\graph-rag\python.exe")

# 这个脚本是“换学科 agent”的单一入口。
# 用户不需要命令行传参；换学科时只改这里的显式变量即可。
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "计算机科学与技术"
TARGET_SUBJECT_CODE = "0812"
REPORT_YEAR = 2026

# True 表示当目标仍是数学时，额外调用当前已验证的数学 artifact 生成流水线。
# 换成其他学科时，本脚本会先生成可用性计划和缺口报告，不会误跑仍未完全参数化的旧脚本。
RUN_VERIFIED_MATH_ARTIFACT_PIPELINE = False
BUILD_PARAMETERIZED_READY_ARTIFACTS = True
AUDIT_PARAMETERIZED_ARTIFACTS = True

# 默认不写入 tracked 的 configs/runtime/current_subject_request.json，避免每次运行只改时间戳就污染 Git。
# 每个 run 目录都会写一份 current_subject_request.json；确实需要给旧脚本共享全局请求时再改成 True。
WRITE_GLOBAL_CURRENT_REQUEST = False

# README 是交接文档，不应被每次运行自动重写；需要更新文档时人工修改。
UPDATE_README_ON_RUN = False

RANKING_SOURCES = ["软科", "QS", "US News", "THE"]
TOP_RANK_MIDPOINT = 200


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def candidate_subject_areas(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    normalized = re.sub(r"[、，,;；/]+", " ", text)
    parts = [part.strip() for part in normalized.split() if part.strip()] if re.search("[\u4e00-\u9fff]", normalized) else [text]
    return parts or [text]


def slug_text(value: str) -> str:
    text = normalize_key(value)
    return text or "subject"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def runtime_context() -> dict[str, Any]:
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "recommended_python": str(RECOMMENDED_PYTHON),
        "using_recommended_python": Path(sys.executable).resolve() == RECOMMENDED_PYTHON.resolve()
        if RECOMMENDED_PYTHON.exists()
        else False,
    }


def validate_required_inputs() -> list[dict[str, str]]:
    required = {
        "ranking sqlite": SQLITE_PATH,
        "dim_subject": DIM_SUBJECT_CSV,
        "dim_subject_alias": DIM_ALIAS_CSV,
        "fact_indicator_weight": FACT_WEIGHT_CSV,
        "fact_ranking_indicator": FACT_INDICATOR_CSV,
    }
    issues = []
    for label, path in required.items():
        if not path.exists():
            issues.append({"label": label, "path": str(path), "status": "missing"})
    return issues


def resolve_subject() -> dict[str, Any]:
    dim_subject = pd.read_csv(DIM_SUBJECT_CSV, dtype=str).fillna("")
    candidates = dim_subject[
        (dim_subject["ministry_subject_code"] == TARGET_SUBJECT_CODE)
        | (dim_subject["ministry_subject_name"] == TARGET_SUBJECT)
        | (dim_subject["subject_short_name"] == TARGET_SUBJECT)
    ].copy()
    if candidates.empty:
        raise RuntimeError(f"未在 dim_subject 中找到目标学科：{TARGET_SUBJECT} / {TARGET_SUBJECT_CODE}")
    row = candidates.iloc[0].to_dict()
    aliases = pd.read_csv(DIM_ALIAS_CSV, dtype=str).fillna("")
    alias_rows = aliases[aliases["subject_id"] == row["subject_id"]].copy()
    alias_summary = (
        alias_rows.groupby("ranking_source")["ranking_subject_alias"]
        .apply(lambda s: sorted({clean_text(x) for x in s if clean_text(x)}))
        .to_dict()
    )
    return {
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "report_year": REPORT_YEAR,
        "subject_id": row["subject_id"],
        "ministry_subject_name": row["ministry_subject_name"],
        "subject_short_name": row.get("subject_short_name", ""),
        "tongji_college": row.get("tongji_college", ""),
        "arwu_subject_name": row.get("arwu_subject_name", ""),
        "qs_subject_name": row.get("qs_subject_name", ""),
        "usnews_subject_name": row.get("usnews_subject_name", ""),
        "the_subject_area": row.get("the_subject_area", ""),
        "alias_summary": alias_summary,
        "alias_row_count": len(alias_rows),
    }


def query_ranking_records(subject_id: str) -> pd.DataFrame:
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
      f.is_mainland_china,
      f.is_tongji,
      f.rank_raw,
      f.rank_midpoint,
      f.total_score,
      f.source_file,
      f.source_sheet,
      f.source_row,
      a.ranking_subject_alias,
      a.alias_type
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[subject_id])
    for column in ["release_year", "ranking_year", "rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.fillna("")


def is_mainland(row: pd.Series) -> bool:
    flag = clean_text(row.get("is_mainland_china", "")).lower()
    country = clean_text(row.get("country_or_region", "")).lower()
    return flag in {"1", "true"} or country in {"china", "中国", "中国内地", "中国大陆", "china (mainland)"}


def latest_source_rows(df: pd.DataFrame, source: str) -> pd.DataFrame:
    source_df = df[df["ranking_source"] == source].copy()
    if source_df.empty:
        return source_df
    if "fact_id" in source_df.columns:
        source_df = source_df.drop_duplicates(subset=["fact_id"]).copy()
    latest_release = source_df["release_year"].max()
    source_df = source_df[source_df["release_year"] == latest_release].copy()
    latest_ranking = source_df["ranking_year"].max()
    return source_df[source_df["ranking_year"] == latest_ranking].copy()


def build_ranking_availability(records: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"sources_with_tongji": 0, "sources_with_peer_top200": 0}
    for source in RANKING_SOURCES:
        latest = latest_source_rows(records, source)
        tongji = latest[latest["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        mainland = latest[latest.apply(is_mainland, axis=1)].copy() if not latest.empty else latest
        top200 = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= TOP_RANK_MIDPOINT].copy()
        row = {
            "ranking_source": source,
            "latest_release_year": int(latest["release_year"].max()) if not latest.empty else "",
            "latest_ranking_year": int(latest["ranking_year"].max()) if not latest.empty else "",
            "latest_rows": len(latest),
            "tongji_latest_rows": len(tongji),
            "tongji_latest_rank": clean_text(tongji.iloc[0]["rank_raw"]) if not tongji.empty else "",
            "mainland_top200_rows": len(top200),
            "data_status": "available" if not tongji.empty else "missing_tongji_latest",
        }
        rows.append(row)
        if not tongji.empty:
            summary["sources_with_tongji"] += 1
        if len(top200) > 0:
            summary["sources_with_peer_top200"] += 1
    return rows, summary


def read_indicator_data() -> pd.DataFrame:
    df = pd.read_csv(FACT_INDICATOR_CSV, dtype=str).fillna("")
    for column in ["release_year", "ranking_year", "metric_value", "metric_rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def read_weight_data() -> pd.DataFrame:
    df = pd.read_csv(FACT_WEIGHT_CSV, dtype=str).fillna("")
    df["weight_percent"] = pd.to_numeric(df["weight_percent"], errors="coerce").fillna(0.0)
    return df


def build_weight_availability(subject: dict[str, Any]) -> list[dict[str, Any]]:
    weights = read_weight_data()
    expected = {
        "软科": clean_text(subject.get("arwu_subject_name")) or TARGET_SUBJECT,
        "QS": clean_text(subject.get("qs_subject_name")) or TARGET_SUBJECT,
        "US News": clean_text(subject.get("usnews_subject_name")) or TARGET_SUBJECT,
        "THE": clean_text(subject.get("the_subject_area")) or "自然科学",
    }
    if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        expected["THE"] = crosswalk.get(expected["THE"], expected["THE"])
    rows = []
    for source, subject_area in expected.items():
        subset = pd.DataFrame()
        matched_area = subject_area
        for candidate in candidate_subject_areas(subject_area):
            subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)].copy()
            if not subset.empty:
                matched_area = candidate
                break
        if subset.empty and source == "THE":
            subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == "自然科学")].copy()
            matched_area = "自然科学" if not subset.empty else matched_area
        primary_subset = subset
        if not subset.empty and "indicator_level" in subset.columns:
            first_level = subset[subset["indicator_level"] == "一级指标"].copy()
            if not first_level.empty:
                primary_subset = first_level
        rows.append(
            {
                "ranking_source": source,
                "expected_subject_or_area": matched_area if not subset.empty else subject_area,
                "weight_rows": len(subset),
                "weight_total": round(float(primary_subset["weight_percent"].sum()), 4) if not primary_subset.empty else 0,
                "data_status": "available" if not subset.empty else "missing_weight",
            }
        )
    return rows


def build_indicator_availability(subject: dict[str, Any]) -> list[dict[str, Any]]:
    indicators = read_indicator_data()
    aliases = subject.get("alias_summary", {})
    rows = []
    for source in RANKING_SOURCES:
        alias_values = set(aliases.get(source, []))
        source_df = indicators[indicators["ranking_source"] == source].copy()
        if alias_values:
            source_df = source_df[source_df["ranking_subject_raw"].isin(alias_values) | source_df["ranking_subject_norm"].isin(alias_values)].copy()
        else:
            source_df = source_df[source_df["ranking_subject_raw"].isin([TARGET_SUBJECT]) | source_df["ranking_subject_norm"].isin([TARGET_SUBJECT])].copy()
        tongji = source_df[source_df["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        external_tongji = pd.DataFrame()
        if source == "US News" and USNEWS_TONGJI_HISTORY_CSV.exists():
            external = pd.read_csv(USNEWS_TONGJI_HISTORY_CSV, dtype=str, encoding="utf-8-sig").fillna("")
            external_aliases = {normalize_key(value) for value in alias_values}
            external_aliases.update(
                normalize_key(value)
                for value in [subject.get("target_subject"), subject.get("usnews_subject_name")]
                if clean_text(value)
            )
            raw_keys = external.get("ranking_subject_raw", pd.Series([""] * len(external))).map(normalize_key)
            en_keys = external.get("ranking_subject_en", pd.Series([""] * len(external))).map(normalize_key)
            norm_keys = external.get("ranking_subject_norm", pd.Series([""] * len(external))).map(normalize_key)
            external_tongji = external[raw_keys.isin(external_aliases) | en_keys.isin(external_aliases) | norm_keys.isin(external_aliases)].copy()
        years = sorted({int(x) for x in tongji["ranking_year"].dropna().tolist()})
        if not external_tongji.empty:
            years = sorted(
                set(years)
                | {
                    int(float(x))
                    for x in external_tongji["ranking_year"].dropna().tolist()
                    if clean_text(x)
                }
            )
        rank_metrics = tongji[tongji["metric_type"] == "rank"]
        score_metrics = tongji[tongji["metric_type"] == "score"]
        external_rank_metrics = external_tongji[external_tongji.get("metric_type", "") == "rank"] if not external_tongji.empty else pd.DataFrame()
        external_score_metrics = external_tongji[external_tongji.get("metric_type", "") == "score"] if not external_tongji.empty else pd.DataFrame()
        rows.append(
            {
                "ranking_source": source,
                "indicator_rows": len(source_df) + len(external_tongji),
                "tongji_indicator_rows": len(tongji) + len(external_tongji),
                "ranking_years": ";".join(str(x) for x in years),
                "year_count": len(years),
                "rank_metric_rows": len(rank_metrics) + len(external_rank_metrics),
                "score_metric_rows": len(score_metrics) + len(external_score_metrics),
                "data_status": "available" if len(tongji) + len(external_tongji) > 0 else "missing_indicator_data",
            }
        )
    return rows


def detect_paper_metric_sources() -> dict[str, Any]:
    keywords = ["论文", "被引", "CNCI", "篇均", "高被引", "国际合著", "国际合作", "WOS", "Web of Science", "InCites", "ESI"]
    matches = []
    for path in DATA_DIR.glob("*"):
        if not path.is_file():
            continue
        name = path.name
        if any(keyword.lower() in name.lower() for keyword in keywords):
            matches.append(name)
    external_matches = []
    cwts_field_mapping = {}
    if CWTS_SUBJECT_FIELD_CROSSWALK_CSV.exists():
        crosswalk = pd.read_csv(CWTS_SUBJECT_FIELD_CROSSWALK_CSV, dtype=str, encoding="utf-8-sig").fillna("")
        if "ministry_subject_code" in crosswalk.columns:
            matched = crosswalk[crosswalk["ministry_subject_code"].astype(str).str.zfill(4) == TARGET_SUBJECT_CODE]
            if not matched.empty:
                cwts_field_mapping = matched.iloc[0].to_dict()
    if CWTS_CHINA_ALL_FIELDS_CSV.exists() and cwts_field_mapping.get("cwts_field"):
        external_matches.append(str(CWTS_CHINA_ALL_FIELDS_CSV.relative_to(PROJECT_DIR)))
        external_matches.append(str(CWTS_SUBJECT_FIELD_CROSSWALK_CSV.relative_to(PROJECT_DIR)))
    wos_subject_rows = 0
    wos_subject_available = False
    if WOS_SUBJECT_PAPER_CSV.exists():
        wos = pd.read_csv(WOS_SUBJECT_PAPER_CSV, dtype=str, encoding="utf-8-sig").fillna("")
        if "ministry_subject_code" in wos.columns:
            matched_wos = wos[wos["ministry_subject_code"].astype(str).str.zfill(4) == TARGET_SUBJECT_CODE].copy()
            wos_subject_rows = len(matched_wos)
            wos_subject_available = wos_subject_rows > 0
            if wos_subject_available:
                external_matches.insert(0, str(WOS_SUBJECT_PAPER_CSV.relative_to(PROJECT_DIR)))
    return {
        "has_paper_metric_source": len(matches) > 0 or len(external_matches) > 0 or wos_subject_available,
        "preferred_source": "wos_subject_paper_metrics" if wos_subject_available else "cwts_broad_field_proxy" if external_matches else "raw_data_scan_only",
        "matched_files": matches,
        "external_matched_files": external_matches,
        "wos_subject_rows": wos_subject_rows,
        "cwts_field_mapping": cwts_field_mapping,
    }


def load_external_gap_status() -> dict[str, str]:
    if not EXTERNAL_GAP_STATUS_JSON.exists():
        return {}
    payload = json.loads(EXTERNAL_GAP_STATUS_JSON.read_text(encoding="utf-8"))
    return {row["artifact_id"]: row["status"] for row in payload.get("status_by_slot", [])}


def build_artifact_readiness(
    ranking_rows: list[dict[str, Any]],
    weight_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
    paper_metric_sources: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranking_by_source = {row["ranking_source"]: row for row in ranking_rows}
    weight_by_source = {row["ranking_source"]: row for row in weight_rows}
    indicator_by_source = {row["ranking_source"]: row for row in indicator_rows}
    external_status_by_artifact = load_external_gap_status()
    if ARWU_PUBLIC_TONGJI_LONG_CSV.exists():
        external_status_by_artifact["table_01_arwu_tongji_indicator_history"] = "ready_from_arwu_gras_public_web_common"
    if TARGET_SUBJECT_CODE != "0701":
        math_only_artifacts = {
            "figure_05_usnews_indicator_weight",
            "table_02_usnews_tongji_indicator_history",
            "figure_10_usnews_indicator_history_trend",
        }
        if not ARWU_PUBLIC_TONGJI_LONG_CSV.exists():
            math_only_artifacts.add("table_01_arwu_tongji_indicator_history")
        external_status_by_artifact = {
            artifact_id: status
            for artifact_id, status in external_status_by_artifact.items()
            if artifact_id not in math_only_artifacts
        }
    def has_tongji(source: str) -> bool:
        return int(ranking_by_source.get(source, {}).get("tongji_latest_rows") or 0) > 0

    def has_peer(source: str) -> bool:
        return int(ranking_by_source.get(source, {}).get("mainland_top200_rows") or 0) > 0

    def has_weight(source: str) -> bool:
        return int(weight_by_source.get(source, {}).get("weight_rows") or 0) > 0

    def has_indicators(source: str) -> bool:
        return int(indicator_by_source.get(source, {}).get("tongji_indicator_rows") or 0) > 0

    def has_indicator_years(source: str, min_years: int) -> bool:
        return int(indicator_by_source.get(source, {}).get("year_count") or 0) >= min_years

    has_paper_metrics = bool(paper_metric_sources.get("has_paper_metric_source"))
    readiness_specs = [
        ("figure_01_tongji_subject_ranking_overview", "chart", "四大排名概览", all(has_tongji(s) for s in RANKING_SOURCES), "需要四大榜单均有同济最新排名。"),
        ("figure_02_ranking_indicator_commonality", "chart", "指标共性图", has_weight("软科") and has_weight("QS") and has_weight("THE"), "US News 权重缺失时只能展示指标覆盖，不能展示权重。"),
        ("figure_03_arwu_indicator_weight", "chart", "软科权重图", has_weight("软科"), "需要软科目标学科权重。"),
        ("figure_04_qs_indicator_weight", "chart", "QS 权重图", has_weight("QS"), "需要 QS 目标学科权重。"),
        ("figure_05_usnews_indicator_weight", "chart", "US News 权重图", has_weight("US News"), "需要 US News 目标学科权重。"),
        ("figure_06_the_indicator_weight", "chart", "THE 权重图", has_weight("THE"), "需要 THE 对应领域权重。"),
        ("figure_07_all_rankings_history", "chart", "四大排名历史趋势", sum(has_tongji(s) for s in RANKING_SOURCES) >= 2, "至少两个榜单有同济历史排名才有趋势价值。"),
        ("table_04_mainland_rank_band_distribution", "table", "内地高校位次分布", sum(has_peer(s) for s in RANKING_SOURCES) >= 2, "需要各榜单最新内地高校排名样本。"),
        ("table_05_arwu_mainland_peer_ranking", "table", "软科 peer 排名表", has_peer("软科"), "需要软科前200内地高校样本。"),
        ("table_06_usnews_mainland_peer_ranking", "table", "US News peer 排名表", has_peer("US News"), "需要 US News 前200内地高校样本。"),
        ("table_07_qs_mainland_peer_ranking", "table", "QS peer 排名表", has_peer("QS"), "需要 QS 前200内地高校样本。"),
        ("table_08_the_mainland_peer_ranking", "table", "THE peer 排名表", has_peer("THE"), "需要 THE 前200内地高校样本。"),
        ("table_01_arwu_tongji_indicator_history", "table", "软科同济分项指标历史表", has_indicator_years("软科", 2), "模板要求多年历史；当前若只有单年，只能降级为最新年表。"),
        ("table_02_usnews_tongji_indicator_history", "table", "US News 同济分项指标历史表", has_indicator_years("US News", 2), "模板要求多年历史；当前若只有单年，只能降级为最新年表。"),
        ("figure_10_usnews_indicator_history_trend", "chart", "US News 分项指标历史趋势图", has_indicator_years("US News", 2), "趋势图需要 US News 多年分项指标。"),
        ("table_03_the_tongji_indicator_history", "table", "THE 分项指标历史表", has_indicator_years("THE", 2), "需要 THE 同济分项指标多年份数据。"),
        ("figure_09_arwu_peer_indicator_relative_rank", "chart", "软科 peer 分项相对排名", has_peer("软科") and has_indicators("软科"), "需要 peer 样本和分项指标。"),
        ("figure_11_usnews_peer_indicator_relative_rank", "chart", "US News peer 分项相对排名", has_peer("US News") and has_indicators("US News"), "需要 peer 样本和分项指标。"),
        ("figure_12_the_peer_indicator_relative_rank", "chart", "THE peer 分项相对排名", has_peer("THE") and has_indicators("THE"), "需要 peer 样本和分项指标。"),
        ("figure_13_paper_output_citation_relative_rank", "chart", "论文及被引总量相对排名图", has_paper_metrics, "需要独立论文指标数据源，不能由排名表臆造。"),
        ("figure_14_paper_cnci_cpp_relative_rank", "chart", "CNCI 及篇均被引相对排名图", has_paper_metrics, "需要 CNCI 与篇均被引字段。"),
        ("figure_15_paper_highly_cited_relative_rank", "chart", "高被引 TOP 论文量相对排名图", has_paper_metrics, "需要 TOP1%/TOP10% 高被引论文字段。"),
        ("figure_16_paper_international_collab_relative_rank", "chart", "国际合著论文占比相对排名图", has_paper_metrics, "需要国际合著论文数或占比字段。"),
        ("table_09_peer_full_ranking_history_appendix", "table", "对标高校排名历史附表", sum(has_peer(s) for s in RANKING_SOURCES) >= 2, "由各榜单 peer 表和历史排名合并生成。"),
    ]
    readiness_rows = []
    gaps = []
    for artifact_id, artifact_type, label, ready, note in readiness_specs:
        external_status = external_status_by_artifact.get(artifact_id, "")
        if external_status and external_status != "candidate_indirect_not_auto_merge":
            ready = True
            note = f"{note} external_data补源状态：{external_status}。"
        elif external_status:
            note = f"{note} external_data已生成候选口径：{external_status}，进入Word前需要人工确认。"
        status = "ready" if ready else "blocked_or_partial"
        readiness_rows.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "label": label,
                "readiness_status": status,
                "note": note,
            }
        )
        if not ready:
            gaps.append(
                {
                    "artifact_id": artifact_id,
                    "label": label,
                    "gap_type": "data_or_parameterization_gap",
                    "reason": note,
                }
            )
    return readiness_rows, gaps


def build_request_payload(subject: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "generated_at": now_text(),
        "request": {
            "target_university": TARGET_UNIVERSITY,
            "target_subject": TARGET_SUBJECT,
            "target_subject_code": TARGET_SUBJECT_CODE,
            "report_year": REPORT_YEAR,
        },
        "resolved_subject": subject,
        "agent_contract": {
            "single_entrypoint": "scripts/run_subject_agent.py",
            "no_cli_args": True,
            "change_subject_by_editing_top_level_variables": True,
            "runtime_request_is_run_scoped": not WRITE_GLOBAL_CURRENT_REQUEST,
        },
    }
    return payload


def write_current_request(run_dir: Path, subject: dict[str, Any]) -> dict[str, Any]:
    payload = build_request_payload(subject)
    run_request_path = run_dir / "current_subject_request.json"
    write_json(run_request_path, payload)
    written_paths = [str(run_request_path)]
    if WRITE_GLOBAL_CURRENT_REQUEST:
        write_json(CURRENT_REQUEST_JSON, payload)
        written_paths.append(str(CURRENT_REQUEST_JSON))
    return {"payload": payload, "written_paths": written_paths}


def write_markdown_report(
    run_dir: Path,
    subject: dict[str, Any],
    ranking_rows: list[dict[str, Any]],
    weight_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
    readiness_rows: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> None:
    ready_count = sum(1 for row in readiness_rows if row["readiness_status"] == "ready")
    lines = [
        "# Subject Agent Run Report",
        "",
        f"- generated_at: {now_text()}",
        f"- target_university: {TARGET_UNIVERSITY}",
        f"- target_subject: {TARGET_SUBJECT}",
        f"- target_subject_code: {TARGET_SUBJECT_CODE}",
        f"- subject_id: {subject['subject_id']}",
        f"- alias_row_count: {subject['alias_row_count']}",
        f"- ready_artifacts: {ready_count}/{len(readiness_rows)}",
        "",
        "## 一句话结论",
        "",
        f"本报告由单一 agent 入口生成，用来判断 `{TARGET_SUBJECT}` 是否可以直接进入图表生成，以及哪些图表需要补数据或补参数化能力。",
        "",
        "## 榜单排名可用性",
        "",
        "| 榜单 | 最新发布年 | 最新排名年 | 同济排名 | 前200内地样本 | 状态 |",
        "| --- | ---: | ---: | --- | ---: | --- |",
    ]
    for row in ranking_rows:
        lines.append(
            f"| {row['ranking_source']} | {row['latest_release_year']} | {row['latest_ranking_year']} | "
            f"{row['tongji_latest_rank']} | {row['mainland_top200_rows']} | {row['data_status']} |"
        )
    lines.extend(["", "## 权重数据可用性", "", "| 榜单 | 预期学科/领域 | 权重行数 | 权重合计 | 状态 |", "| --- | --- | ---: | ---: | --- |"])
    for row in weight_rows:
        lines.append(
            f"| {row['ranking_source']} | {row['expected_subject_or_area']} | {row['weight_rows']} | "
            f"{row['weight_total']} | {row['data_status']} |"
        )
    lines.extend(["", "## 分项指标可用性", "", "| 榜单 | 同济分项行数 | 年份 | 年份数 | 状态 |", "| --- | ---: | --- | ---: | --- |"])
    for row in indicator_rows:
        lines.append(
            f"| {row['ranking_source']} | {row['tongji_indicator_rows']} | {row['ranking_years']} | "
            f"{row['year_count']} | {row['data_status']} |"
        )
    lines.extend(["", "## Artifact 就绪判断", "", "| artifact | 类型 | 说明 | 状态 |", "| --- | --- | --- | --- |"])
    for row in readiness_rows:
        lines.append(f"| {row['artifact_id']} | {row['artifact_type']} | {row['label']} | {row['readiness_status']} |")
    if gaps:
        lines.extend(["", "## 当前阻塞或半阻塞项", "", "| artifact | 对象 | 原因 |", "| --- | --- | --- |"])
        for gap in gaps:
            lines.append(f"| {gap['artifact_id']} | {gap['label']} | {gap['reason']} |")
    lines.extend(
        [
            "",
            "## Agent 操作约定",
            "",
            "1. 换学科时只改 `scripts/run_subject_agent.py` 顶部的目标学科变量。",
            "2. 先运行本 agent 入口，得到本报告和结构化 readiness/gap 文件。",
            "3. 只有 readiness 为 ready 的 artifact 才允许自动生成；blocked_or_partial 必须先补数据或补脚本参数化。",
            "4. 后续要把所有旧 artifact 脚本逐步改成读取 `configs/runtime/current_subject_request.json`，避免再出现数学硬编码。",
            "",
        ]
    )
    (run_dir / "agent_run_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def update_readme_agent_section() -> None:
    section_title = "## 换学科 Agent 入口"
    block = [
        section_title,
        "",
        "现在换学科不应该再让人手动记多步脚本。新的控制入口是：",
        "",
        "```powershell",
        "$py='E:\\conda_envs\\graph-rag\\python.exe'",
        "& $py scripts\\run_subject_agent.py",
        "```",
        "",
        "换学科时只改 `scripts/run_subject_agent.py` 顶部的显式变量：",
        "",
        "```python",
        'TARGET_UNIVERSITY = "同济大学"',
        'TARGET_SUBJECT = "数学"',
        'TARGET_SUBJECT_CODE = "0701"',
        "REPORT_YEAR = 2026",
        "```",
        "",
        "该 agent 会自动完成：学科解析、四大榜单别名核验、同济排名可用性、内地 peer 样本可用性、权重数据可用性、分项指标可用性、artifact readiness 判断、数据缺口报告生成。",
        "",
        "重要边界：当前已有部分旧 artifact 脚本仍有数学硬编码，不能直接拿去跑其他学科。后续改造目标是让所有 artifact 脚本读取 `configs/runtime/current_subject_request.json`，由 `run_subject_agent.py` 统一调度。",
        "",
    ]
    text = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else "# word_tool\n"
    if section_title in text:
        text = text.split(section_title)[0].rstrip() + "\n\n" + "\n".join(block)
    else:
        text = text.rstrip() + "\n\n" + "\n".join(block)
    README_PATH.write_text(text, encoding="utf-8", newline="\n")


def append_run_log(run_dir: Path, ready_count: int, total_count: int, gap_count: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "subject_agent_run_log.md"
    if not log_path.exists():
        log_path.write_text("# Subject Agent 运行留档\n", encoding="utf-8", newline="\n")
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"\n## {now_text()} {TARGET_SUBJECT}\n\n"
            f"- target_subject_code: {TARGET_SUBJECT_CODE}\n"
            f"- run_dir: `{run_dir}`\n"
            f"- ready_artifacts: {ready_count}/{total_count}\n"
            f"- blocked_or_partial: {gap_count}\n"
        )


def write_run_manifest(
    run_dir: Path,
    subject: dict[str, Any],
    request_info: dict[str, Any],
    input_issues: list[dict[str, str]],
    ranking_rows: list[dict[str, Any]],
    weight_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
    readiness_rows: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "generated_at": now_text(),
        "project_dir": str(PROJECT_DIR),
        "runtime": runtime_context(),
        "request_paths": request_info.get("written_paths", []),
        "input_issues": input_issues,
        "subject": subject,
        "counts": {
            "ranking_sources": len(ranking_rows),
            "weight_sources": len(weight_rows),
            "indicator_sources": len(indicator_rows),
            "ready_artifacts": sum(1 for row in readiness_rows if row["readiness_status"] == "ready"),
            "artifact_count": len(readiness_rows),
            "gap_count": len(gaps),
        },
        "run_files": {
            "agent_run_report": str(run_dir / "agent_run_report.md"),
            "ranking_availability": str(run_dir / "ranking_availability.csv"),
            "weight_availability": str(run_dir / "weight_availability.csv"),
            "indicator_availability": str(run_dir / "indicator_availability.csv"),
            "artifact_readiness": str(run_dir / "artifact_readiness.csv"),
            "data_gap_report": str(run_dir / "data_gap_report.csv"),
            "artifacts_dir": str(run_dir / "artifacts"),
        },
    }
    write_json(run_dir / "run_manifest.json", manifest)
    return manifest


def maybe_run_math_pipeline() -> dict[str, Any]:
    if not RUN_VERIFIED_MATH_ARTIFACT_PIPELINE:
        return {"pipeline_ran": False, "reason": "RUN_VERIFIED_MATH_ARTIFACT_PIPELINE is False"}
    if TARGET_SUBJECT != "数学" or TARGET_SUBJECT_CODE != "0701":
        return {"pipeline_ran": False, "reason": "verified artifact pipeline is currently only safe for mathematics"}
    from build_ready_artifacts import build_all_ready_artifacts

    summary = build_all_ready_artifacts()
    return {"pipeline_ran": True, "summary": summary}


def run_subject_agent() -> dict[str, Any]:
    input_issues = validate_required_inputs()
    if input_issues:
        raise FileNotFoundError(json.dumps(input_issues, ensure_ascii=False, indent=2))

    subject = resolve_subject()
    run_slug = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{TARGET_SUBJECT_CODE}_{slug_text(TARGET_SUBJECT)}"
    run_dir = OUTPUT_DIR / run_slug
    run_dir.mkdir(parents=True, exist_ok=True)
    request_info = write_current_request(run_dir, subject)

    records = query_ranking_records(subject["subject_id"])
    ranking_rows, ranking_summary = build_ranking_availability(records)
    weight_rows = build_weight_availability(subject)
    indicator_rows = build_indicator_availability(subject)
    paper_metric_sources = detect_paper_metric_sources()
    readiness_rows, gaps = build_artifact_readiness(ranking_rows, weight_rows, indicator_rows, paper_metric_sources)

    write_csv(run_dir / "ranking_availability.csv", ranking_rows, list(ranking_rows[0].keys()))
    write_csv(run_dir / "weight_availability.csv", weight_rows, list(weight_rows[0].keys()))
    write_csv(run_dir / "indicator_availability.csv", indicator_rows, list(indicator_rows[0].keys()))
    write_csv(run_dir / "artifact_readiness.csv", readiness_rows, list(readiness_rows[0].keys()))
    (run_dir / "paper_metric_source_scan.json").write_text(json.dumps(paper_metric_sources, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    if gaps:
        write_csv(run_dir / "data_gap_report.csv", gaps, list(gaps[0].keys()))
    else:
        write_csv(run_dir / "data_gap_report.csv", [], ["artifact_id", "label", "gap_type", "reason"])

    write_markdown_report(run_dir, subject, ranking_rows, weight_rows, indicator_rows, readiness_rows, gaps)
    run_manifest = write_run_manifest(
        run_dir,
        subject,
        request_info,
        input_issues,
        ranking_rows,
        weight_rows,
        indicator_rows,
        readiness_rows,
        gaps,
    )
    parameterized_artifacts = {"generated_count": 0, "attempted_count": 0, "skipped_count": 0, "results": []}
    if BUILD_PARAMETERIZED_READY_ARTIFACTS:
        from subject_artifact_builders import build_subject_run_artifacts

        parameterized_artifacts = build_subject_run_artifacts(run_dir, subject, records, readiness_rows)

    ready_count = sum(1 for row in readiness_rows if row["readiness_status"] == "ready")
    summary = {
        "generated_at": now_text(),
        "run_dir": str(run_dir),
        "request": {
            "target_university": TARGET_UNIVERSITY,
            "target_subject": TARGET_SUBJECT,
            "target_subject_code": TARGET_SUBJECT_CODE,
            "report_year": REPORT_YEAR,
        },
        "resolved_subject": subject,
        "ranking_summary": ranking_summary,
        "ready_artifact_count": ready_count,
        "artifact_count": len(readiness_rows),
        "blocked_or_partial_count": len(gaps),
        "paper_metric_sources": paper_metric_sources,
        "parameterized_artifacts": parameterized_artifacts,
        "math_pipeline": maybe_run_math_pipeline(),
        "runtime": runtime_context(),
        "request_paths": request_info["written_paths"],
        "outputs": {
            "agent_run_report": str(run_dir / "agent_run_report.md"),
            "run_manifest": str(run_dir / "run_manifest.json"),
            "artifact_readiness": str(run_dir / "artifact_readiness.csv"),
            "data_gap_report": str(run_dir / "data_gap_report.csv"),
            "generated_artifacts": str(run_dir / "artifacts"),
            "current_request": request_info["written_paths"][0],
        },
    }
    (run_dir / "agent_run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    if AUDIT_PARAMETERIZED_ARTIFACTS and parameterized_artifacts.get("generated_count", 0):
        from audit_subject_agent_run import build_audit

        audit_report = build_audit(run_dir)
        summary["subject_artifact_audit"] = {
            "artifact_count": audit_report["artifact_count"],
            "pass_count": audit_report["pass_count"],
            "fail_count": audit_report["fail_count"],
            "report": str(run_dir / "audit" / "subject_artifact_audit.md"),
            "visual_contact_sheet": audit_report.get("visual_contact_sheet", ""),
        }
        (run_dir / "agent_run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    append_run_log(run_dir, ready_count, len(readiness_rows), len(gaps))
    if UPDATE_README_ON_RUN:
        update_readme_agent_section()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run_subject_agent()
