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

import agent_runtime
import ranking_public_supplements as public_supplements


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = agent_runtime.load_runtime_profile()
SUBJECT_REQUEST = agent_runtime.load_subject_request(RUNTIME_PROFILE)
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUT_DIR = agent_runtime.profile_path(
    RUNTIME_PROFILE,
    "paths.subject_agent_runs_dir",
    PROJECT_DIR / "outputs" / "subject_agent_runs",
)
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
RECOMMENDED_PYTHON = agent_runtime.resolve_project_path(
    RUNTIME_PROFILE.get("recommended_python"),
    Path(r"E:\conda_envs\graph-rag\python.exe"),
)

# 这个脚本仍然不使用命令行传参；换学科优先改 configs/runtime/current_subject_request.json。
# 下面保留显式变量兜底，方便用户直接阅读和局部调试。
TARGET_UNIVERSITY = agent_runtime.request_value(SUBJECT_REQUEST, "target_university", "同济大学")
TARGET_SUBJECT = agent_runtime.request_value(SUBJECT_REQUEST, "target_subject", "")
TARGET_SUBJECT_CODE = agent_runtime.request_value(SUBJECT_REQUEST, "target_subject_code", "")
REPORT_YEAR = int(agent_runtime.request_value(SUBJECT_REQUEST, "report_year", 2026))

# True 表示当目标仍是数学时，额外调用当前已验证的数学 artifact 生成流水线。
# 换成其他学科时，本脚本会先生成可用性计划和缺口报告，不会误跑仍未完全参数化的旧脚本。
RUN_VERIFIED_MATH_ARTIFACT_PIPELINE = agent_runtime.profile_bool(
    RUNTIME_PROFILE,
    "execution.run_verified_math_artifact_pipeline",
    False,
)
BUILD_PARAMETERIZED_READY_ARTIFACTS = agent_runtime.profile_bool(
    RUNTIME_PROFILE,
    "execution.build_parameterized_ready_artifacts",
    True,
)
AUDIT_PARAMETERIZED_ARTIFACTS = agent_runtime.profile_bool(
    RUNTIME_PROFILE,
    "execution.audit_parameterized_artifacts",
    True,
)

# 默认不写入 tracked 的 configs/runtime/current_subject_request.json，避免每次运行只改时间戳就污染 Git。
# 每个 run 目录都会写一份 current_subject_request.json；确实需要给旧脚本共享全局请求时再改成 True。
WRITE_GLOBAL_CURRENT_REQUEST = agent_runtime.profile_bool(
    RUNTIME_PROFILE,
    "execution.write_global_current_request",
    False,
)

# README 是交接文档，不应被每次运行自动重写；需要更新文档时人工修改。
UPDATE_README_ON_RUN = agent_runtime.profile_bool(
    RUNTIME_PROFILE,
    "execution.update_readme_on_run",
    False,
)

RANKING_SOURCES = SUBJECT_REQUEST.get(
    "ranking_sources",
    agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", ["软科", "QS", "US News", "THE"]),
)
TOP_RANK_MIDPOINT = agent_runtime.profile_int(RUNTIME_PROFILE, "execution.top_rank_midpoint", 200)


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


def add_alias_values(subject: dict[str, Any], source: str, values: list[Any]) -> int:
    aliases = subject.setdefault("alias_summary", {})
    current = list(aliases.get(source, []))
    merged = ordered_unique(current + [valid_mapping_value(value) for value in values])
    aliases[source] = merged
    return max(0, len(merged) - len(current))


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
        "runtime_profile": RUNTIME_PROFILE.get("_profile_path", ""),
        "subject_request": SUBJECT_REQUEST.get("_request_path", ""),
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
    for issue in agent_runtime.validate_subject_request(SUBJECT_REQUEST):
        issues.append(
            {
                "label": f"subject request {issue['field']}",
                "path": SUBJECT_REQUEST.get("_request_path", ""),
                "status": issue["message"],
            }
        )
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
    subject = {
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
    public_alias_count = 0
    public_alias_count += add_alias_values(subject, "QS", public_supplements.qs_proxy_aliases(subject))
    public_alias_count += add_alias_values(subject, "软科", public_supplements.arwu_public_aliases(subject))
    for source in RANKING_SOURCES:
        public_alias_count += add_alias_values(subject, source, public_supplements.source_aliases(subject, source))
    subject["public_supplements"] = public_supplements.public_supplement_records(subject)
    subject["public_supplement_alias_count"] = public_alias_count
    subject["source_runtime_overrides"] = {}
    return subject


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


def query_supplemental_ranking_records(subject: dict[str, Any]) -> pd.DataFrame:
    alias_summary = subject.get("alias_summary", {})
    supplement_records = subject.get("public_supplements", [])
    supplement_sources = {
        clean_text(row.get("ranking_source"))
        for row in supplement_records
        if clean_text(row.get("ranking_source"))
    }
    source_aliases = {
        source: {normalize_key(value) for value in alias_summary.get(source, []) if normalize_key(value)}
        for source in supplement_sources
    }
    source_aliases = {source: aliases for source, aliases in source_aliases.items() if aliases}
    if not source_aliases:
        return pd.DataFrame()

    placeholders = ",".join(["?"] * len(source_aliases))
    query = f"""
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
      f.ranking_subject_norm
    FROM fact_ranking f
    WHERE f.ranking_source IN ({placeholders})
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=list(source_aliases))
    if df.empty:
        return df
    for column in ["release_year", "ranking_year", "rank_midpoint"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    matched_parts = []
    for source, aliases in source_aliases.items():
        source_df = df[df["ranking_source"] == source].copy()
        raw_keys = source_df["ranking_subject_raw"].map(normalize_key)
        norm_keys = source_df["ranking_subject_norm"].map(normalize_key)
        matched = source_df[raw_keys.isin(aliases) | norm_keys.isin(aliases)].copy()
        if not matched.empty:
            matched["ranking_subject_alias"] = matched["ranking_subject_raw"]
            matched["alias_type"] = "runtime_public_supplement"
            matched_parts.append(matched.drop(columns=["ranking_subject_norm"]))
    if not matched_parts:
        return pd.DataFrame()
    return pd.concat(matched_parts, ignore_index=True).fillna("")


def combine_ranking_records(primary: pd.DataFrame, supplemental: pd.DataFrame) -> pd.DataFrame:
    if supplemental.empty:
        return primary
    if primary.empty:
        return supplemental
    combined = pd.concat([primary, supplemental], ignore_index=True).fillna("")
    if "fact_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["fact_id"], keep="first").copy()
    return combined


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


def weight_candidate_values(subject: dict[str, Any], source: str, records: pd.DataFrame | None = None) -> list[str]:
    overrides = subject.get("source_runtime_overrides", {}).get(source, {})
    values: list[Any] = [overrides.get("weight_subject_or_area")]
    if source == "软科":
        values.extend([subject.get("arwu_subject_name"), TARGET_SUBJECT])
    elif source == "QS":
        values.extend([subject.get("qs_subject_name"), TARGET_SUBJECT])
        values.extend(public_supplements.qs_proxy_aliases(subject))
    elif source == "US News":
        values.extend([subject.get("usnews_subject_name"), TARGET_SUBJECT])
    elif source == "THE":
        area = clean_text(subject.get("the_subject_area"))
        if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
            crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
            area = crosswalk.get(area, area)
        values.extend([area, "自然科学"])
    values.extend(subject.get("alias_summary", {}).get(source, []))
    if records is not None and not records.empty:
        source_records = records[records["ranking_source"] == source].copy()
        if not source_records.empty:
            latest = latest_source_rows(source_records, source)
            values.extend(latest.get("ranking_subject_raw", pd.Series(dtype=str)).tolist())
            values.extend(latest.get("ranking_subject_alias", pd.Series(dtype=str)).tolist())
    candidates: list[str] = []
    for value in ordered_unique([valid_mapping_value(value) for value in values]):
        candidates.extend(candidate_subject_areas(value))
    return ordered_unique(candidates)


def find_weight_subset(weights: pd.DataFrame, source: str, candidates: list[str]) -> tuple[pd.DataFrame, str]:
    weight_keys = {
        normalize_key(area): area
        for area in weights[weights["ranking_source"] == source]["ranking_subject_or_area"].drop_duplicates().tolist()
        if clean_text(area)
    }
    for candidate in candidates:
        direct = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)].copy()
        if not direct.empty:
            return direct, candidate
        mapped_area = weight_keys.get(normalize_key(candidate), "")
        if mapped_area:
            mapped = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == mapped_area)].copy()
            if not mapped.empty:
                return mapped, mapped_area
    return pd.DataFrame(), candidates[0] if candidates else ""


def attach_runtime_public_supplements(subject: dict[str, Any], records: pd.DataFrame) -> dict[str, Any]:
    subject["source_runtime_overrides"] = dict(subject.get("source_runtime_overrides", {}))
    qs_proxy = public_supplements.qs_proxy(subject)
    if qs_proxy:
        subject["source_runtime_overrides"]["QS"] = {
            "weight_subject_or_area": valid_mapping_value(qs_proxy.get("proxy_subject_or_area")),
            "ranking_subject_or_area": valid_mapping_value(qs_proxy.get("proxy_subject_or_area")),
            "proxy_subject_en": valid_mapping_value(qs_proxy.get("proxy_subject_en")),
            "proxy_level": clean_text(qs_proxy.get("proxy_level")),
            "requires_disclosure": bool(qs_proxy.get("requires_disclosure")),
            "reason": clean_text(qs_proxy.get("reason")),
            "source_key": clean_text(qs_proxy.get("source_key")),
        }

    strategy = public_supplements.usnews_weight_strategy()
    if strategy.get("prefer_actual_ranking_subject"):
        weights = read_weight_data()
        candidates = weight_candidate_values(subject, "US News", records)
        subset, matched_area = find_weight_subset(weights, "US News", candidates)
        if not subset.empty:
            subject["source_runtime_overrides"]["US News"] = {
                "weight_subject_or_area": matched_area,
                "proxy_level": "actual_matched_ranking_subject",
                "requires_disclosure": bool(strategy.get("requires_disclosure_when_inferred")),
                "reason": clean_text(strategy.get("reason")),
            }
    return subject


def build_weight_availability(subject: dict[str, Any], records: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    weights = read_weight_data()
    rows = []
    for source in RANKING_SOURCES:
        candidates = weight_candidate_values(subject, source, records)
        subset, matched_area = find_weight_subset(weights, source, candidates)
        if subset.empty and source == "THE":
            subset, matched_area = find_weight_subset(weights, source, ["自然科学"])
        primary_subset = subset
        if not subset.empty and "indicator_level" in subset.columns:
            first_level = subset[subset["indicator_level"] == "一级指标"].copy()
            if not first_level.empty:
                primary_subset = first_level
        rows.append(
            {
                "ranking_source": source,
                "expected_subject_or_area": matched_area,
                "candidate_subject_or_areas": " | ".join(candidates[:10]),
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
    overview_source_count = sum(has_tongji(s) for s in RANKING_SOURCES)
    commonality_source_count = sum((has_weight(s) or has_indicators(s)) for s in RANKING_SOURCES)
    readiness_specs = [
        (
            "figure_01_tongji_subject_ranking_overview",
            "chart",
            "多榜单排名概览",
            overview_source_count >= 2,
            f"至少两个榜单有同济最新排名即可生成概览；当前可用 {overview_source_count} 个榜单，缺失榜单应在图注或数据缺口中说明。",
        ),
        (
            "figure_02_ranking_indicator_commonality",
            "chart",
            "指标共性图",
            commonality_source_count >= 2,
            f"至少两个榜单有权重或同济分项指标即可生成共性图；当前可用 {commonality_source_count} 个榜单，缺权重来源按指标覆盖数量展示。",
        ),
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
            "change_subject_by_editing": [
                "configs/runtime/current_subject_request.json",
                "configs/runtime/agent_runtime_profile.json",
            ],
            "change_subject_by_editing_top_level_variables": False,
            "runtime_request_is_run_scoped": not WRITE_GLOBAL_CURRENT_REQUEST,
            "path_output_policy": agent_runtime.deep_get(
                RUNTIME_PROFILE,
                "governance.path_output_policy",
                "plain_text_windows_paths",
            ),
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
        f"- public_supplement_alias_count: {subject.get('public_supplement_alias_count', 0)}",
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
    public_records = subject.get("public_supplements", [])
    if public_records:
        lines.extend(["", "## 公开来源补充", "", "| 榜单 | 补充类型 | 学科/领域 | 口径级别 | 是否披露 | 依据 |", "| --- | --- | --- | --- | --- | --- |"])
        for row in public_records:
            lines.append(
                f"| {row.get('ranking_source', '')} | {row.get('supplement_type', '')} | "
                f"{row.get('subject_or_area', '')} | {row.get('proxy_level', '')} | "
                f"{row.get('requires_disclosure', '')} | {row.get('source_key', '')} |"
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
            "public_ranking_source_supplements": str(run_dir / "public_ranking_source_supplements.csv"),
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

    records = combine_ranking_records(query_ranking_records(subject["subject_id"]), query_supplemental_ranking_records(subject))
    subject = attach_runtime_public_supplements(subject, records)
    request_info = write_current_request(run_dir, subject)
    ranking_rows, ranking_summary = build_ranking_availability(records)
    weight_rows = build_weight_availability(subject, records)
    indicator_rows = build_indicator_availability(subject)
    paper_metric_sources = detect_paper_metric_sources()
    readiness_rows, gaps = build_artifact_readiness(ranking_rows, weight_rows, indicator_rows, paper_metric_sources)

    write_csv(run_dir / "ranking_availability.csv", ranking_rows, list(ranking_rows[0].keys()))
    write_csv(run_dir / "weight_availability.csv", weight_rows, list(weight_rows[0].keys()))
    write_csv(run_dir / "indicator_availability.csv", indicator_rows, list(indicator_rows[0].keys()))
    write_csv(run_dir / "artifact_readiness.csv", readiness_rows, list(readiness_rows[0].keys()))
    public_rows = subject.get("public_supplements", [])
    if public_rows:
        write_csv(run_dir / "public_ranking_source_supplements.csv", public_rows, list(public_rows[0].keys()))
    else:
        write_csv(
            run_dir / "public_ranking_source_supplements.csv",
            [],
            [
                "ranking_source",
                "supplement_type",
                "subject_or_area",
                "subject_or_area_en",
                "proxy_level",
                "requires_disclosure",
                "reason",
                "source_key",
            ],
        )
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
