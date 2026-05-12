from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
EXTERNAL_PROCESSED_DIR = PROJECT_DIR / "external_data" / "processed"
QA_DIR = PROCESSED_DIR / "qa" / "data_layer_v2"
SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
WOS_SUBJECT_PAPER_GLOB = "*web of science*20260511.xlsx"
WOS_SUBJECT_PAPER_PROCESSED_CSV = EXTERNAL_PROCESSED_DIR / "wos_37_university_subject_paper_metrics_20260511.csv"

DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_SUBJECT_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
DIM_INDICATOR_CSV = PROCESSED_DIR / "dim_indicator.csv"
DIM_UNIVERSITY_PROVINCE_CSV = PROCESSED_DIR / "dim_university_province.csv"
FACT_RANKING_CSV = PROCESSED_DIR / "fact_ranking.csv"
FACT_RANKING_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"

DOMESTIC_ROUND34_XLSX = PROJECT_DIR / "data" / "全国高校第四轮&第三轮学科评估结果.xlsx"
DOMESTIC_ROUND5_ANALYSIS_XLSX = PROJECT_DIR / "data" / "副本第五轮评估结果（不完全）20260508(分析).xlsx"
DOUBLE_FIRST_CLASS_XLSX = PROJECT_DIR / "data" / "全国双一流学科明细表2022&2017.v2.xlsx"
TONGJI_DOMESTIC_STATUS_XLSX = PROJECT_DIR / "data" / "同济大学第五轮学科评估结果+双一流+高峰高原.xlsx"

MANUAL_SUBJECT_ALIASES_JSON = CONFIG_DIR / "runtime" / "manual_subject_aliases.json"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"
INDICATOR_GROUP_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "indicator_group_crosswalk.json"
LOGICAL_SLOT_MAPPING_CSV = CONFIG_DIR / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"

ARWU_TONGJI_HISTORY_CSV = EXTERNAL_PROCESSED_DIR / "arwu_gras_public_tongji_history_2023_2025_long.csv"
USNEWS_TONGJI_HISTORY_CSV = EXTERNAL_PROCESSED_DIR / "usnews_tongji_subject_indicator_history_2022_2026_long.csv"
CWTS_LATEST_ALL_FIELDS_CSV = EXTERNAL_PROCESSED_DIR / "cwts_traditional_2025_china_latest_all_fields.csv"
CWTS_SUBJECT_FIELD_CROSSWALK_CSV = EXTERNAL_PROCESSED_DIR / "cwts_subject_field_crosswalk.csv"

OUTPUT_DIM_UNIVERSITY_CSV = PROCESSED_DIR / "dim_university.csv"
OUTPUT_MAPPING_REGISTRY_CSV = PROCESSED_DIR / "mapping_registry.csv"
OUTPUT_EXTERNAL_SOURCE_REGISTRY_CSV = PROCESSED_DIR / "external_source_registry.csv"
OUTPUT_FACT_EXTERNAL_INDICATOR_HISTORY_CSV = PROCESSED_DIR / "fact_external_indicator_history.csv"
OUTPUT_FACT_PAPER_METRIC_CSV = PROCESSED_DIR / "fact_paper_metric.csv"
OUTPUT_FACT_DOMESTIC_EVALUATION_CSV = PROCESSED_DIR / "fact_domestic_evaluation.csv"
OUTPUT_FACT_DOMESTIC_STATUS_CSV = PROCESSED_DIR / "fact_domestic_status.csv"
OUTPUT_ARTIFACT_DATA_CONTRACT_CSV = PROCESSED_DIR / "artifact_data_contract.csv"

ARTIFACT_CONTRACT_ROWS = [
    ("figure_01_tongji_subject_ranking_overview", "fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "blocked", "四大排名概览。"),
    ("figure_02_ranking_indicator_commonality", "fact_indicator_weight;dim_indicator", "official_raw;derived_from_local_workbook", "no", "no", "degraded_available", "US News 权重缺失时可降级为指标覆盖数量。"),
    ("figure_03_arwu_indicator_weight", "fact_indicator_weight", "official_raw;derived_from_local_workbook", "no", "no", "blocked", "软科权重图。"),
    ("figure_04_qs_indicator_weight", "fact_indicator_weight", "official_raw;derived_from_local_workbook", "no", "no", "blocked", "QS 权重图。"),
    ("figure_05_usnews_indicator_weight", "fact_indicator_weight", "official_raw;derived_from_local_workbook;candidate_indirect", "no", "yes", "blocked", "candidate_indirect 只能候选展示，进入 Word 前需确认。"),
    ("figure_06_the_indicator_weight", "fact_indicator_weight", "official_raw;derived_from_local_workbook", "no", "no", "blocked", "THE 权重图，领域口径需要披露。"),
    ("figure_07_all_rankings_history", "fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "partial", "四大榜单历史趋势。"),
    ("table_01_arwu_tongji_indicator_history", "fact_external_indicator_history;fact_ranking_indicator", "official_public_page;official_raw;derived_from_local_workbook", "no", "no", "partial", "软科同济分项历史。"),
    ("table_02_usnews_tongji_indicator_history", "fact_external_indicator_history;fact_ranking_indicator", "official_raw;derived_from_local_workbook", "no", "no", "partial", "US News 同济分项历史。"),
    ("table_03_the_tongji_indicator_history", "fact_ranking_indicator", "official_raw;derived_from_local_workbook", "no", "no", "partial", "THE 同济分项历史，领域口径需要披露。"),
    ("table_04_mainland_rank_band_distribution", "fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "blocked", "四大榜单内地高校位次分布。"),
    ("table_05_arwu_mainland_peer_ranking", "fact_ranking;dim_university", "official_raw;derived_from_local_workbook", "no", "no", "partial", "软科对标高校历史表。"),
    ("table_06_usnews_mainland_peer_ranking", "fact_ranking;dim_university", "official_raw;derived_from_local_workbook", "no", "no", "partial", "US News 对标高校历史表。"),
    ("table_07_qs_mainland_peer_ranking", "fact_ranking;dim_university", "official_raw;derived_from_local_workbook", "no", "no", "partial", "QS 对标高校历史表。"),
    ("table_08_the_mainland_peer_ranking", "fact_ranking;dim_university", "official_raw;derived_from_local_workbook", "no", "no", "partial", "THE 对标高校历史表，领域口径需要披露。"),
    ("figure_09_arwu_peer_indicator_relative_rank", "fact_ranking_indicator;fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "partial", "软科 peer 分项指标相对排名。"),
    ("figure_10_usnews_indicator_history_trend", "fact_external_indicator_history", "official_raw;derived_from_local_workbook", "no", "no", "partial", "US News 同济分项历史趋势。"),
    ("figure_11_usnews_peer_indicator_relative_rank", "fact_ranking_indicator;fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "partial", "US News peer 分项指标相对排名。"),
    ("figure_12_the_peer_indicator_relative_rank", "fact_ranking_indicator;fact_ranking", "official_raw;derived_from_local_workbook", "no", "no", "partial", "THE peer 分项指标相对排名。"),
    ("figure_13_paper_output_citation_relative_rank", "fact_paper_metric", "external_proxy", "yes", "no", "degraded_available", "CWTS 宽领域论文代理，必须披露。"),
    ("figure_14_paper_cnci_cpp_relative_rank", "fact_paper_metric", "external_proxy", "yes", "no", "degraded_available", "CWTS 宽领域论文代理，必须披露。"),
    ("figure_15_paper_highly_cited_relative_rank", "fact_paper_metric", "external_proxy", "yes", "no", "degraded_available", "CWTS 宽领域论文代理，必须披露。"),
    ("figure_16_paper_international_collab_relative_rank", "fact_paper_metric", "external_proxy", "yes", "no", "degraded_available", "CWTS 宽领域论文代理，必须披露。"),
    ("table_09_peer_full_ranking_history_appendix", "fact_ranking;dim_university", "official_raw;derived_from_local_workbook", "no", "no", "partial", "四榜单对标高校排名历史附表。"),
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


def clean_university_cn(value: Any) -> str:
    text = clean_text(value)
    return re.sub(r"20\d{6}$", "", text).strip()


def resolve_wos_subject_paper_xlsx() -> Path | None:
    matches = sorted((PROJECT_DIR / "data").glob(WOS_SUBJECT_PAPER_GLOB))
    return matches[0] if matches else None


def norm_key(value: Any) -> str:
    text = clean_text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "||".join(clean_text(part) for part in parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def read_csv(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, usecols=usecols).fillna("")


def read_excel(path: Path, sheet_name: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name=sheet_name, dtype=str).fillna("")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def subject_lookup() -> tuple[dict[str, str], dict[str, str]]:
    subjects = read_csv(DIM_SUBJECT_CSV)
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    if subjects.empty:
        return by_code, by_name
    for _, row in subjects.iterrows():
        subject_id = clean_text(row.get("subject_id"))
        code = clean_text(row.get("ministry_subject_code"))
        name = clean_text(row.get("ministry_subject_name"))
        if subject_id and code:
            by_code[code] = subject_id
        if subject_id and name:
            by_name[norm_key(name)] = subject_id
    return by_code, by_name


def build_dim_university() -> pd.DataFrame:
    ranking_cols = ["university_name_cn", "university_name_en", "country_or_region", "is_mainland_china", "is_tongji"]
    ranking = read_csv(FACT_RANKING_CSV, usecols=ranking_cols)
    indicator = read_csv(
        FACT_RANKING_INDICATOR_CSV,
        usecols=["university_name_cn", "university_name_en", "country_or_region", "is_mainland_china", "is_tongji"],
    )
    wos = read_csv(
        WOS_SUBJECT_PAPER_PROCESSED_CSV,
        usecols=["university_name_cn", "university_name_en", "country_or_region"],
    )
    if not wos.empty:
        wos["is_mainland_china"] = "True"
        wos["is_tongji"] = wos["university_name_cn"].map(lambda value: "True" if clean_university_cn(value) == "同济大学" else "False")
    cwts = read_csv(CWTS_LATEST_ALL_FIELDS_CSV, usecols=["University", "Country", "university_name_cn"])
    if not cwts.empty:
        cwts = cwts.rename(columns={"University": "university_name_en", "Country": "country_or_region"})
        cwts["is_mainland_china"] = cwts["country_or_region"].map(lambda value: "True" if clean_text(value).lower() == "china" else "False")
        cwts["is_tongji"] = cwts["university_name_en"].map(lambda value: "True" if norm_key(value) == "tongjiuniversity" else "False")
    province = read_csv(DIM_UNIVERSITY_PROVINCE_CSV)

    frames = [df for df in [ranking, indicator, wos, cwts] if not df.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    combined["university_name_cn"] = combined["university_name_cn"].map(clean_text)
    combined["university_name_en"] = combined["university_name_en"].map(clean_text)
    combined["university_key"] = combined.apply(
        lambda row: norm_key(row["university_name_cn"]) or norm_key(row["university_name_en"]),
        axis=1,
    )
    combined = combined[combined["university_key"].astype(str).str.len() > 0].copy()

    province_map = {}
    province_source_map = {}
    if not province.empty:
        for _, row in province.iterrows():
            key = norm_key(row.get("university_key")) or norm_key(row.get("university_name_cn"))
            if key:
                province_map[key] = clean_text(row.get("province"))
                province_source_map[key] = clean_text(row.get("source_files"))

    rows = []
    for key, group in combined.groupby("university_key", dropna=False):
        cn_values = [clean_text(value) for value in group["university_name_cn"].tolist() if clean_text(value)]
        en_values = [clean_text(value) for value in group["university_name_en"].tolist() if clean_text(value)]
        country_values = [clean_text(value) for value in group["country_or_region"].tolist() if clean_text(value)]
        is_tongji = any(clean_text(value).lower() in {"true", "1"} for value in group.get("is_tongji", pd.Series(dtype=str)).tolist())
        mainland = any(clean_text(value).lower() in {"true", "1"} for value in group.get("is_mainland_china", pd.Series(dtype=str)).tolist())
        rows.append(
            {
                "university_id": stable_id("univ", key),
                "university_key": key,
                "university_name_cn": Counter(cn_values).most_common(1)[0][0] if cn_values else "",
                "university_name_en": Counter(en_values).most_common(1)[0][0] if en_values else "",
                "country_or_region": Counter(country_values).most_common(1)[0][0] if country_values else "",
                "province": province_map.get(key, ""),
                "city": "",
                "is_mainland_china": str(mainland),
                "is_tongji": str(is_tongji),
                "name_aliases": "；".join(sorted(set(cn_values + en_values))),
                "province_source": province_source_map.get(key, ""),
                "evidence_level": "derived_from_local_workbook",
            }
        )
    return pd.DataFrame(rows).sort_values(["is_tongji", "country_or_region", "province", "university_name_cn"], ascending=[False, True, True, True])


def add_registry_row(rows: list[dict[str, Any]], **kwargs: Any) -> None:
    rows.append(
        {
            "mapping_id": stable_id("map", kwargs.get("mapping_type"), kwargs.get("source_system"), kwargs.get("source_value"), kwargs.get("target_value"), kwargs.get("subject_id")),
            "mapping_type": kwargs.get("mapping_type", ""),
            "source_system": kwargs.get("source_system", ""),
            "source_value": kwargs.get("source_value", ""),
            "source_norm": norm_key(kwargs.get("source_value", "")),
            "target_type": kwargs.get("target_type", ""),
            "target_value": kwargs.get("target_value", ""),
            "subject_id": kwargs.get("subject_id", ""),
            "ranking_source": kwargs.get("ranking_source", ""),
            "confidence": kwargs.get("confidence", ""),
            "scope_type": kwargs.get("scope_type", ""),
            "evidence_level": kwargs.get("evidence_level", ""),
            "requires_disclosure": kwargs.get("requires_disclosure", "no"),
            "source_file": kwargs.get("source_file", ""),
            "note": kwargs.get("note", ""),
        }
    )


def build_mapping_registry() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    aliases = read_csv(DIM_SUBJECT_ALIAS_CSV)
    for _, row in aliases.iterrows():
        alias_type = clean_text(row.get("alias_type"))
        scope_type = "exact_subject"
        confidence = "high"
        requires_disclosure = "no"
        if "manual" in alias_type:
            confidence = "medium"
        add_registry_row(
            rows,
            mapping_type="subject_alias",
            source_system=clean_text(row.get("ranking_source")),
            source_value=clean_text(row.get("ranking_subject_alias")),
            target_type="subject_id",
            target_value=clean_text(row.get("subject_id")),
            subject_id=clean_text(row.get("subject_id")),
            ranking_source=clean_text(row.get("ranking_source")),
            confidence=confidence,
            scope_type=scope_type,
            evidence_level="derived_from_local_workbook",
            requires_disclosure=requires_disclosure,
            source_file="processed/dim_subject_alias.csv",
            note=clean_text(row.get("source_note")),
        )

    if MANUAL_SUBJECT_ALIASES_JSON.exists():
        config = json.loads(MANUAL_SUBJECT_ALIASES_JSON.read_text(encoding="utf-8"))
        for rule in config.get("subject_alias_rules", []):
            mapping_class = clean_text(rule.get("mapping_class"))
            confidence = "high" if mapping_class == "deterministic" else "medium" if mapping_class == "broad_multi_subject" else "low"
            scope_type = "exact_subject" if mapping_class == "deterministic" else "broad_subject"
            requires_disclosure = "yes" if mapping_class in {"broad_multi_subject", "approximate"} else "no"
            subject_ids = rule.get("subject_ids") or [rule.get("subject_id")]
            for alias in rule.get("aliases", []):
                for subject_id in subject_ids:
                    subject_id = clean_text(subject_id)
                    if not subject_id:
                        continue
                    add_registry_row(
                        rows,
                        mapping_type="subject_alias_rule",
                        source_system=clean_text(rule.get("ranking_source")),
                        source_value=alias,
                        target_type="subject_id",
                        target_value=subject_id,
                        subject_id=subject_id,
                        ranking_source=clean_text(rule.get("ranking_source")),
                        confidence=confidence,
                        scope_type=scope_type,
                        evidence_level="manual_override",
                        requires_disclosure=requires_disclosure,
                        source_file="configs/runtime/manual_subject_aliases.json",
                        note=clean_text(rule.get("note")),
                    )

    if CWTS_SUBJECT_FIELD_CROSSWALK_CSV.exists():
        cwts = read_csv(CWTS_SUBJECT_FIELD_CROSSWALK_CSV)
        for _, row in cwts.iterrows():
            add_registry_row(
                rows,
                mapping_type="subject_to_cwts_field",
                source_system="CWTS",
                source_value=clean_text(row.get("ministry_subject_name")),
                target_type="cwts_field",
                target_value=clean_text(row.get("cwts_field")),
                subject_id=clean_text(row.get("subject_id")),
                ranking_source="CWTS",
                confidence=clean_text(row.get("mapping_confidence")),
                scope_type="broad_field_proxy",
                evidence_level="external_proxy",
                requires_disclosure="yes",
                source_file="external_data/processed/cwts_subject_field_crosswalk.csv",
                note=clean_text(row.get("proxy_scope_note")) or clean_text(row.get("mapping_rationale")),
            )

    if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        data = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
        for subject_key, area in data.items():
            add_registry_row(
                rows,
                mapping_type="the_weight_area",
                source_system="THE",
                source_value=subject_key,
                target_type="the_weight_area",
                target_value=area,
                ranking_source="THE",
                confidence="medium",
                scope_type="ranking_area",
                evidence_level="manual_override",
                requires_disclosure="yes",
                source_file="configs/runtime/the_weight_area_crosswalk.json",
                note="THE 权重为领域口径。",
            )

    if INDICATOR_GROUP_CROSSWALK_JSON.exists():
        data = json.loads(INDICATOR_GROUP_CROSSWALK_JSON.read_text(encoding="utf-8"))
        for source_value, target_value in data.items():
            add_registry_row(
                rows,
                mapping_type="indicator_group",
                source_system="internal",
                source_value=source_value,
                target_type="indicator_group",
                target_value=target_value,
                confidence="high",
                scope_type="indicator_normalization",
                evidence_level="manual_override",
                requires_disclosure="no",
                source_file="configs/runtime/indicator_group_crosswalk.json",
                note="指标组归并规则。",
            )

    return pd.DataFrame(rows).drop_duplicates(subset=["mapping_id"]).sort_values(["mapping_type", "ranking_source", "subject_id", "source_value"])


def build_external_source_registry() -> pd.DataFrame:
    rows = []
    for path in sorted(EXTERNAL_PROCESSED_DIR.glob("*.csv")):
        name = path.name
        evidence_level = "external_supplement"
        source_role = "external_processed_csv"
        requires_disclosure = "no"
        allowed_for_word = "yes"
        note = ""
        lower = name.lower()
        if "candidate" in lower:
            evidence_level = "candidate_indirect"
            source_role = "candidate_data"
            requires_disclosure = "yes"
            allowed_for_word = "requires_confirmation"
            note = "候选/间接口径，不能默认进入正式 Word。"
        elif "wos_37_university_subject_paper_metrics" in lower:
            evidence_level = "derived_from_local_workbook"
            source_role = "paper_metric_subject_wos"
            requires_disclosure = "no"
            allowed_for_word = "yes"
            note = "Web of Science/InCites 一级学科论文指标清洗表；学校名已去除日期后缀，CNCI 等缺失值保留为空。"
        elif "cwts" in lower:
            evidence_level = "external_proxy"
            source_role = "paper_metric_proxy"
            requires_disclosure = "yes"
            allowed_for_word = "degraded_with_disclosure"
            note = "CWTS 宽领域代理，不是教育部一级学科精确论文统计。"
        elif "arwu_gras_public" in lower:
            evidence_level = "official_public_page"
            source_role = "arwu_public_web_supplement"
            note = "软科公开网页补源。"
        elif "usnews_tongji_subject_indicator_history" in lower:
            evidence_level = "derived_from_local_workbook"
            source_role = "usnews_indicator_history_supplement"
            note = "从本地 US News 明细源抽取的同济分项历史。"
        rows.append(
            {
                "source_id": stable_id("extsrc", name),
                "source_name": name,
                "path": str(path),
                "source_role": source_role,
                "evidence_level": evidence_level,
                "requires_disclosure": requires_disclosure,
                "allowed_for_word": allowed_for_word,
                "size_bytes": path.stat().st_size,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def build_fact_external_indicator_history() -> pd.DataFrame:
    rows = []
    usnews = read_csv(USNEWS_TONGJI_HISTORY_CSV)
    for _, row in usnews.iterrows():
        rows.append(
            {
                "external_indicator_history_id": stable_id(
                    "eih",
                    "US News",
                    row.get("release_year"),
                    row.get("ranking_subject_norm"),
                    row.get("indicator_norm"),
                    row.get("metric_type"),
                ),
                "ranking_source": "US News",
                "release_year": clean_text(row.get("release_year")),
                "ranking_year": clean_text(row.get("ranking_year")),
                "ranking_subject_raw": clean_text(row.get("ranking_subject_raw")),
                "ranking_subject_norm": clean_text(row.get("ranking_subject_norm")),
                "ranking_subject_en": clean_text(row.get("ranking_subject_en")),
                "university_name_cn": clean_text(row.get("university_name_cn")) or "同济大学",
                "university_name_en": clean_text(row.get("university_name_en")) or "Tongji University",
                "world_rank_raw": clean_text(row.get("world_rank_raw")),
                "world_rank_midpoint": clean_text(row.get("world_rank_midpoint")),
                "indicator_name": clean_text(row.get("indicator_name")),
                "indicator_norm": clean_text(row.get("indicator_norm")),
                "metric_type": clean_text(row.get("metric_type")),
                "indicator_value": clean_text(row.get("indicator_value")),
                "indicator_value_num": clean_text(row.get("indicator_value_num")),
                "evidence_level": "derived_from_local_workbook",
                "requires_disclosure": "no",
                "source_file": clean_text(row.get("source_file")),
                "source_sheet": clean_text(row.get("source_sheet")),
                "source_row": clean_text(row.get("source_row")),
                "source_url": "",
            }
        )

    arwu = read_csv(ARWU_TONGJI_HISTORY_CSV)
    for _, row in arwu.iterrows():
        ranking_subject_raw = clean_text(row.get("arwu_subject_name_en"))
        rows.append(
            {
                "external_indicator_history_id": stable_id(
                    "eih",
                    "软科",
                    row.get("ranking_year"),
                    ranking_subject_raw,
                    row.get("indicator_code"),
                ),
                "ranking_source": "软科",
                "release_year": clean_text(row.get("ranking_year")),
                "ranking_year": clean_text(row.get("ranking_year")),
                "ranking_subject_raw": ranking_subject_raw,
                "ranking_subject_norm": norm_key(ranking_subject_raw),
                "ranking_subject_en": ranking_subject_raw,
                "university_name_cn": "同济大学",
                "university_name_en": clean_text(row.get("university_name_en")) or "Tongji University",
                "world_rank_raw": clean_text(row.get("world_rank")),
                "world_rank_midpoint": "",
                "indicator_name": clean_text(row.get("indicator_name")),
                "indicator_norm": norm_key(row.get("indicator_name")),
                "metric_type": "score",
                "indicator_value": clean_text(row.get("indicator_value")),
                "indicator_value_num": clean_text(row.get("indicator_value")),
                "evidence_level": "official_public_page",
                "requires_disclosure": "no",
                "source_file": "arwu_gras_public_tongji_history_2023_2025_long.csv",
                "source_sheet": "",
                "source_row": "",
                "source_url": clean_text(row.get("source_url")),
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["external_indicator_history_id"])


def build_wos_subject_paper_wide() -> pd.DataFrame:
    source_path = resolve_wos_subject_paper_xlsx()
    if source_path is None:
        return pd.DataFrame()
    by_code, _ = subject_lookup()
    df = pd.read_excel(source_path, sheet_name=0)
    df.columns = [clean_text(col) for col in df.columns]
    if df.empty:
        return pd.DataFrame()
    column_map = {
        "中文名称": "university_name_cn",
        "教育部一级学科": "paper_field",
        "英文名称": "university_name_en",
        "总论文（Web of Science Documents）": "WOS_documents",
        "总被引（Times Cited）": "times_cited",
        "篇均被引（Citation Impact）": "citation_impact",
        "有被引的论文占比（% Docs Cited）": "pct_docs_cited",
        "CNCI（Category Normalized Citation Impact）": "CNCI",
        "前1%论文数 （Documents in Top 1%）": "documents_top_1",
        "前1%论文占比（% Documents in Top 1%）": "pct_documents_top_1",
        "前10%论文数（Documents in Top 10%）": "documents_top_10",
        "前10%论文占比（% Documents in Top 10%）": "pct_documents_top_10",
        "ESI高被引论文数（Highly Cited Papers）": "highly_cited_papers",
        "ESI高被引论文占比（% Highly Cited Papers）": "pct_highly_cited_papers",
        "国际合作论文数量（International Documents）": "international_documents",
        "国际合作论文占比（% International Documents）": "pct_international_documents",
        "国际合作论文CNCI（Collab-CNCI）": "collab_CNCI",
    }
    keep = [col for col in column_map if col in df.columns]
    df = df[keep].rename(columns=column_map).copy()
    df["university_name_cn"] = df["university_name_cn"].map(clean_university_cn)
    df["university_name_en"] = df["university_name_en"].map(clean_text)
    df["paper_field"] = df["paper_field"].map(clean_text)
    df["ministry_subject_code"] = df["paper_field"].str.extract(r"^(\d{4})", expand=False).fillna("")
    df["ministry_subject_name_en"] = df["paper_field"].str.replace(r"^\d{4}\s*", "", regex=True).map(clean_text)
    df["subject_id"] = df["ministry_subject_code"].map(lambda code: by_code.get(clean_text(code), ""))
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
    df["source_system"] = "Web of Science subject paper metrics"
    df["period"] = "period_not_in_source_file"
    df["fractional_counting"] = ""
    df["country_or_region"] = "China"
    df["evidence_level"] = "derived_from_local_workbook"
    df["requires_disclosure"] = "no"
    df["proxy_scope_note"] = "Web of Science/InCites/ESI 一级学科口径；原表未提供统计年份字段，文件日期为 20260511。"
    df["source_file"] = source_path.name
    df["source_sheet"] = "37所一流高校学科论文数据web of science"
    df["source_row"] = [str(idx + 2) for idx in range(len(df))]
    ordered = [
        "source_system",
        "university_name_cn",
        "university_name_en",
        "country_or_region",
        "paper_field",
        "ministry_subject_code",
        "ministry_subject_name_en",
        "subject_id",
        "period",
        "fractional_counting",
    ] + metric_columns + [
        "evidence_level",
        "requires_disclosure",
        "proxy_scope_note",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    result = df[[col for col in ordered if col in df.columns]].drop_duplicates(
        subset=["university_name_cn", "university_name_en", "ministry_subject_code"],
        keep="first",
    )
    write_csv(WOS_SUBJECT_PAPER_PROCESSED_CSV, result)
    return result


def wos_subject_paper_long_rows(wos: pd.DataFrame) -> list[dict[str, Any]]:
    if wos.empty:
        return []
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
    rows: list[dict[str, Any]] = []
    for _, row in wos.iterrows():
        for metric_name in metric_columns:
            if metric_name not in row:
                continue
            metric_value = clean_text(row.get(metric_name))
            if not metric_value:
                continue
            rows.append(
                {
                    "paper_metric_id": stable_id(
                        "pm",
                        row.get("source_system"),
                        row.get("university_name_en"),
                        row.get("ministry_subject_code"),
                        metric_name,
                    ),
                    "source_system": clean_text(row.get("source_system")),
                    "university_name_cn": clean_text(row.get("university_name_cn")),
                    "university_name_en": clean_text(row.get("university_name_en")),
                    "ror_id": "",
                    "country_or_region": clean_text(row.get("country_or_region")) or "China",
                    "paper_field": clean_text(row.get("paper_field")),
                    "period": clean_text(row.get("period")),
                    "fractional_counting": clean_text(row.get("fractional_counting")),
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "metric_value_num": metric_value,
                    "evidence_level": clean_text(row.get("evidence_level")),
                    "requires_disclosure": clean_text(row.get("requires_disclosure")),
                    "proxy_scope_note": clean_text(row.get("proxy_scope_note")),
                    "source_file": clean_text(row.get("source_file")),
                }
            )
    return rows


def build_fact_paper_metric() -> pd.DataFrame:
    cwts = read_csv(CWTS_LATEST_ALL_FIELDS_CSV)
    wos = build_wos_subject_paper_wide()
    rows = wos_subject_paper_long_rows(wos)
    if cwts.empty:
        return pd.DataFrame(rows)
    metric_columns = [
        "P",
        "TCS",
        "TNCS",
        "P_top_1",
        "P_top_5",
        "P_top_10",
        "P_collab",
        "P_int_collab",
        "MCS",
        "MNCS",
        "PP_top_1",
        "PP_top_5",
        "PP_top_10",
        "PP_collab",
        "PP_int_collab",
    ]
    keep_columns = ["University", "university_name_cn", "ROR_ID", "Country", "Field", "Period", "Frac_counting"] + metric_columns
    cwts = cwts[[col for col in keep_columns if col in cwts.columns]].copy()
    for _, row in cwts.iterrows():
        for metric_name in metric_columns:
            if metric_name not in row:
                continue
            metric_value = clean_text(row.get(metric_name))
            if not metric_value:
                continue
            rows.append(
                {
                    "paper_metric_id": stable_id("pm", row.get("University"), row.get("Field"), row.get("Period"), metric_name),
                    "source_system": "CWTS Leiden Ranking 2025",
                    "university_name_cn": clean_text(row.get("university_name_cn")),
                    "university_name_en": clean_text(row.get("University")),
                    "ror_id": clean_text(row.get("ROR_ID")),
                    "country_or_region": clean_text(row.get("Country")),
                    "paper_field": clean_text(row.get("Field")),
                    "period": clean_text(row.get("Period")),
                    "fractional_counting": clean_text(row.get("Frac_counting")),
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "metric_value_num": metric_value,
                    "evidence_level": "external_proxy",
                    "requires_disclosure": "yes",
                    "proxy_scope_note": "CWTS 为五大宽领域代理，不是严格教育部一级学科论文统计。",
                    "source_file": "cwts_traditional_2025_china_latest_all_fields.csv",
                }
            )
    return pd.DataFrame(rows)


def domestic_eval_row(
    source_file: str,
    source_sheet: str,
    source_row: int,
    university_name_cn: Any,
    university_code: Any,
    subject_code: Any,
    subject_name: Any,
    subject_id: Any,
    evaluation_round: str,
    evaluation_result: Any,
    score: Any,
    province: Any,
    city: Any,
    tags: Any,
) -> dict[str, Any]:
    return {
        "domestic_evaluation_id": stable_id("deval", source_file, source_row, university_name_cn, subject_code, evaluation_round),
        "university_name_cn": clean_text(university_name_cn),
        "university_code": clean_text(university_code),
        "subject_code": clean_text(subject_code),
        "subject_name": clean_text(subject_name),
        "subject_id": clean_text(subject_id),
        "evaluation_round": evaluation_round,
        "evaluation_result": clean_text(evaluation_result),
        "score": clean_text(score),
        "province": clean_text(province),
        "city": clean_text(city),
        "university_tags": clean_text(tags),
        "evidence_level": "derived_from_local_workbook",
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": str(source_row),
    }


def build_fact_domestic_evaluation() -> pd.DataFrame:
    by_code, by_name = subject_lookup()
    rows: list[dict[str, Any]] = []

    round34 = read_excel(DOMESTIC_ROUND34_XLSX, "数据")
    for idx, row in round34.iterrows():
        source_row = idx + 2
        subject_code = clean_text(row.get("一级学科代码"))
        subject_name = clean_text(row.get("一级学科名称")) or clean_text(row.get("一级学科名称.1"))
        subject_id = by_code.get(subject_code) or by_name.get(norm_key(subject_name), "")
        base = {
            "source_file": DOMESTIC_ROUND34_XLSX.name,
            "source_sheet": "数据",
            "source_row": source_row,
            "university_name_cn": row.get("学校名称"),
            "university_code": row.get("学校代码"),
            "subject_code": subject_code,
            "subject_name": subject_name,
            "subject_id": subject_id,
            "province": row.get("省份"),
            "city": row.get("城市"),
            "tags": "；".join(clean_text(row.get(col)) for col in ["属性1", "属性2", "双一流"] if clean_text(row.get(col))),
        }
        if clean_text(row.get("第四轮评估结果")):
            rows.append(domestic_eval_row(evaluation_round="第四轮", evaluation_result=row.get("第四轮评估结果"), score="", **base))
        if clean_text(row.get("第三轮等级")) or clean_text(row.get("第三轮得分")):
            rows.append(domestic_eval_row(evaluation_round="第三轮", evaluation_result=row.get("第三轮等级"), score=row.get("第三轮得分"), **base))

    round5 = read_excel(DOMESTIC_ROUND5_ANALYSIS_XLSX, "数据")
    for idx, row in round5.iterrows():
        source_row = idx + 2
        subject_code = clean_text(row.get("学科代码.1")) or clean_text(row.get("学科代码"))
        subject_name = clean_text(row.get("一级学科"))
        subject_id = by_code.get(subject_code) or by_name.get(norm_key(subject_name), "")
        base = {
            "source_file": DOMESTIC_ROUND5_ANALYSIS_XLSX.name,
            "source_sheet": "数据",
            "source_row": source_row,
            "university_name_cn": row.get("单位名称"),
            "university_code": "",
            "subject_code": subject_code,
            "subject_name": subject_name,
            "subject_id": subject_id,
            "province": row.get("省份"),
            "city": row.get("城市"),
            "tags": "；".join(clean_text(row.get(col)) for col in ["属性1", "属性2", "双一流"] if clean_text(row.get(col))),
        }
        if clean_text(row.get("第五轮评估结果")):
            rows.append(domestic_eval_row(evaluation_round="第五轮", evaluation_result=row.get("第五轮评估结果"), score="", **base))
        if clean_text(row.get("第四轮学科评估结果")):
            rows.append(domestic_eval_row(evaluation_round="第四轮", evaluation_result=row.get("第四轮学科评估结果"), score="", **base))
        if clean_text(row.get("第三轮等级")) or clean_text(row.get("第三轮学科得分")):
            rows.append(domestic_eval_row(evaluation_round="第三轮", evaluation_result=row.get("第三轮等级"), score=row.get("第三轮学科得分"), **base))

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["domestic_evaluation_id"])


def status_row(
    source_file: str,
    source_sheet: str,
    source_row: int,
    university_name_cn: Any,
    subject_code: Any,
    subject_name: Any,
    subject_id: Any,
    status_type: str,
    status_value: Any,
    batch: Any,
    year: Any,
    province: Any,
    note: Any,
) -> dict[str, Any]:
    return {
        "domestic_status_id": stable_id("dstat", source_file, source_row, university_name_cn, subject_code, status_type, status_value),
        "university_name_cn": clean_text(university_name_cn),
        "subject_code": clean_text(subject_code),
        "subject_name": clean_text(subject_name),
        "subject_id": clean_text(subject_id),
        "status_type": status_type,
        "status_value": clean_text(status_value),
        "batch": clean_text(batch),
        "year": clean_text(year),
        "province": clean_text(province),
        "note": clean_text(note),
        "evidence_level": "derived_from_local_workbook",
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": str(source_row),
    }


def build_fact_domestic_status() -> pd.DataFrame:
    by_code, by_name = subject_lookup()
    rows: list[dict[str, Any]] = []
    double_first = read_excel(DOUBLE_FIRST_CLASS_XLSX, "双一流学科（第二轮-不含清北）明细")
    for idx, row in double_first.iterrows():
        subject_name = clean_text(row.get("一级学科"))
        subject_id = by_name.get(norm_key(subject_name), "")
        rows.append(
            status_row(
                source_file=DOUBLE_FIRST_CLASS_XLSX.name,
                source_sheet="双一流学科（第二轮-不含清北）明细",
                source_row=idx + 2,
                university_name_cn=row.get("学校名称"),
                subject_code="",
                subject_name=subject_name,
                subject_id=subject_id,
                status_type="double_first_class",
                status_value="是",
                batch=row.get("批次"),
                year=row.get("年份"),
                province=row.get("省份"),
                note=row.get("备注"),
            )
        )

    tongji = read_excel(TONGJI_DOMESTIC_STATUS_XLSX, "Sheet1")
    for idx, row in tongji.iterrows():
        subject_code = clean_text(row.get("学科代码（2018版）"))
        subject_name = clean_text(row.get("学科名称"))
        subject_id = by_code.get(subject_code) or by_name.get(norm_key(subject_name), "")
        if clean_text(row.get("是否双一流学科")):
            rows.append(
                status_row(
                    source_file=TONGJI_DOMESTIC_STATUS_XLSX.name,
                    source_sheet="Sheet1",
                    source_row=idx + 2,
                    university_name_cn=row.get("学校名称"),
                    subject_code=subject_code,
                    subject_name=subject_name,
                    subject_id=subject_id,
                    status_type="tongji_double_first_class",
                    status_value=row.get("是否双一流学科"),
                    batch="",
                    year="",
                    province="上海",
                    note="同济校内汇总表",
                )
            )
        if clean_text(row.get("上海市高峰高原")):
            rows.append(
                status_row(
                    source_file=TONGJI_DOMESTIC_STATUS_XLSX.name,
                    source_sheet="Sheet1",
                    source_row=idx + 2,
                    university_name_cn=row.get("学校名称"),
                    subject_code=subject_code,
                    subject_name=subject_name,
                    subject_id=subject_id,
                    status_type="shanghai_peak_plateau",
                    status_value=row.get("上海市高峰高原"),
                    batch="",
                    year="",
                    province="上海",
                    note="同济校内汇总表",
                )
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["domestic_status_id"])


def build_artifact_data_contract() -> pd.DataFrame:
    rows = []
    for artifact_id, required_tables, allowed_evidence, allow_proxy, allow_candidate, missing_policy, note in ARTIFACT_CONTRACT_ROWS:
        if artifact_id in {
            "figure_13_paper_output_citation_relative_rank",
            "figure_14_paper_cnci_cpp_relative_rank",
            "figure_15_paper_highly_cited_relative_rank",
            "figure_16_paper_international_collab_relative_rank",
        }:
            allowed_evidence = "derived_from_local_workbook;official_raw;external_proxy"
            allow_proxy = "yes"
            missing_policy = "prefer_subject_wos_else_cwts_proxy"
            note = "优先使用 Web of Science 一级学科论文指标；目标学科缺失时才降级使用 CWTS 宽领域代理并披露。"
        rows.append(
            {
                "artifact_id": artifact_id,
                "required_tables": required_tables,
                "allowed_evidence_levels": allowed_evidence,
                "allow_proxy": allow_proxy,
                "allow_candidate": allow_candidate,
                "missing_data_policy": missing_policy,
                "requires_disclosure": "yes" if allow_proxy == "yes" or allow_candidate == "yes" or "THE" in note else "no",
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def write_sqlite_tables(tables: dict[str, pd.DataFrame]) -> None:
    with sqlite3.connect(SQLITE_PATH) as con:
        for name, df in tables.items():
            df.to_sql(name, con, if_exists="replace", index=False)


def write_summary(tables: dict[str, pd.DataFrame]) -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for name, df in tables.items():
        summary_rows.append(
            {
                "table_name": name,
                "row_count": len(df),
                "column_count": len(df.columns),
                "output_csv": str(PROCESSED_DIR / f"{name}.csv"),
            }
        )
    summary_df = pd.DataFrame(summary_rows)
    write_csv(QA_DIR / "data_layer_v2_table_summary.csv", summary_df)

    issue_rows = []
    mapping = tables.get("mapping_registry", pd.DataFrame())
    if not mapping.empty:
        broad_count = int((mapping["requires_disclosure"] == "yes").sum())
        issue_rows.append(
            {
                "severity": "INFO",
                "area": "mapping_registry",
                "issue": f"{broad_count} 条映射需要披露，主要是宽领域、代理或人工近似规则。",
            }
        )
    paper = tables.get("fact_paper_metric", pd.DataFrame())
    if not paper.empty:
        source_counts = paper["source_system"].value_counts().to_dict() if "source_system" in paper.columns else {}
        issue_rows.append(
            {
                "severity": "INFO",
                "area": "paper_metric",
                "issue": f"fact_paper_metric 已接入论文指标源：{source_counts}。WOS 一级学科数据优先；CWTS 仅作宽领域代理兜底。",
            }
        )
    domestic_eval = tables.get("fact_domestic_evaluation", pd.DataFrame())
    if not domestic_eval.empty:
        missing_subject = int((domestic_eval.get("subject_id", pd.Series(dtype=str)).astype(str).str.len() == 0).sum())
        issue_rows.append(
            {
                "severity": "INFO" if missing_subject == 0 else "WARN",
                "area": "domestic_evaluation",
                "issue": f"fact_domestic_evaluation 中 subject_id 缺失 {missing_subject} 行；国内评估可用于省份/层次/对标，但进入报告前仍需按目标学科核验。",
            }
        )
    write_csv(QA_DIR / "data_layer_v2_known_limits.csv", pd.DataFrame(issue_rows))

    payload = {
        "generated_at": now_text(),
        "tables": summary_rows,
        "known_limits": issue_rows,
        "sqlite_path": str(SQLITE_PATH),
    }
    (QA_DIR / "data_layer_v2_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    lines = [
        "# data_layer_v2 构建记录",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- SQLite：`{SQLITE_PATH}`",
        "",
        "## 输出表",
        "",
    ]
    for row in summary_rows:
        lines.append(f"- `{row['table_name']}`：{row['row_count']} 行，{row['column_count']} 列")
    lines.extend(["", "## 已知边界", ""])
    for row in issue_rows:
        lines.append(f"- {row['severity']} / {row['area']}：{row['issue']}")
    (QA_DIR / "data_layer_v2_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    build_wos_subject_paper_wide()
    tables = {
        "dim_university": build_dim_university(),
        "mapping_registry": build_mapping_registry(),
        "external_source_registry": build_external_source_registry(),
        "fact_external_indicator_history": build_fact_external_indicator_history(),
        "fact_paper_metric": build_fact_paper_metric(),
        "fact_domestic_evaluation": build_fact_domestic_evaluation(),
        "fact_domestic_status": build_fact_domestic_status(),
        "artifact_data_contract": build_artifact_data_contract(),
    }
    output_paths = {
        "dim_university": OUTPUT_DIM_UNIVERSITY_CSV,
        "mapping_registry": OUTPUT_MAPPING_REGISTRY_CSV,
        "external_source_registry": OUTPUT_EXTERNAL_SOURCE_REGISTRY_CSV,
        "fact_external_indicator_history": OUTPUT_FACT_EXTERNAL_INDICATOR_HISTORY_CSV,
        "fact_paper_metric": OUTPUT_FACT_PAPER_METRIC_CSV,
        "fact_domestic_evaluation": OUTPUT_FACT_DOMESTIC_EVALUATION_CSV,
        "fact_domestic_status": OUTPUT_FACT_DOMESTIC_STATUS_CSV,
        "artifact_data_contract": OUTPUT_ARTIFACT_DATA_CONTRACT_CSV,
    }
    for name, df in tables.items():
        write_csv(output_paths[name], df)
    write_sqlite_tables(tables)
    write_summary(tables)
    print((QA_DIR / "data_layer_v2_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
