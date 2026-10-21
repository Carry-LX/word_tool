from __future__ import annotations

import csv
import json
import platform
import re
import sqlite3
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

import agent_runtime
import ranking_public_supplements as public_supplements
from pipeline_observer import report_progress


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
QS_USNEWS_RANKING_FILE = "2021-2026年中国内地QS&US世界学科排名数据（20260603更新）.xlsx"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
FACT_RANKING_SUBJECT_BRIDGE_CSV = PROCESSED_DIR / "fact_ranking_subject_bridge.csv"
FACT_INDICATOR_SUBJECT_BRIDGE_CSV = PROCESSED_DIR / "fact_ranking_indicator_subject_bridge.csv"
LOGICAL_SLOT_MAPPING_CSV = CONFIG_DIR / "template_slot_inventory" / "logical_slot_artifact_mapping.csv"
CURRENT_REQUEST_JSON = CONFIG_DIR / "runtime" / "current_subject_request.json"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"
THE_RANKING_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_ranking_area_crosswalk.json"
MANUAL_SUBJECT_ALIASES_JSON = CONFIG_DIR / "runtime" / "manual_subject_aliases.json"
README_PATH = PROJECT_DIR / "README.md"
RECOMMENDED_PYTHON = agent_runtime.resolve_project_path(
    RUNTIME_PROFILE.get("recommended_python"),
    Path(r"E:\conda_envs\graph-rag\python.exe"),
)

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
        return {"status": "rebuilt", "source_file": newest_source.name, "rows": int(len(frame))}
    except Exception as exc:
        return {"status": "rebuild_failed", "source_file": newest_source.name, "error": str(exc)}


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

RANKING_SOURCES = agent_runtime.normalize_ranking_sources(
    SUBJECT_REQUEST.get("ranking_sources"),
    agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", agent_runtime.SUPPORTED_RANKING_SOURCES),
)
TOP_RANK_MIDPOINT = agent_runtime.profile_int(RUNTIME_PROFILE, "execution.top_rank_midpoint", 200)
PROXY_POLICY = agent_runtime.request_value(
    SUBJECT_REQUEST,
    "proxy_policy",
    agent_runtime.deep_get(RUNTIME_PROFILE, "governance.proxy_policy", "allow_with_disclosure"),
)
ALLOW_AREA_MAPPING = agent_runtime.request_bool(SUBJECT_REQUEST, "allow_area_mapping", True)
PEER_SCOPE = agent_runtime.request_value(SUBJECT_REQUEST, "peer_scope", "mainland_top200_by_ranking")


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


def proxy_allowed() -> bool:
    return PROXY_POLICY != "disallow"


def supplement_allowed(row: dict[str, Any]) -> bool:
    # Keep Word reports on explicit ministry-to-ranking mappings. Public
    # supplements may add direct aliases, but close-subject or broad-field
    # proxies stay in diagnostics and must not silently expand report scope.
    return not bool(row.get("requires_disclosure"))


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


def add_alias_values(subject: dict[str, Any], source: str, values: list[Any]) -> int:
    aliases = subject.setdefault("alias_summary", {})
    current = list(aliases.get(source, []))
    merged = ordered_unique(current + [valid_mapping_value(value) for value in values])
    aliases[source] = merged
    return max(0, len(merged) - len(current))


def slug_text(value: str) -> str:
    text = normalize_key(value)
    return text or "subject"


def subject_code(subject: dict[str, Any]) -> str:
    return clean_text(subject.get("target_subject_code")) or clean_text(subject.get("ministry_subject_code"))


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
        "ranking_sources": RANKING_SOURCES,
        "proxy_policy": PROXY_POLICY,
        "allow_area_mapping": ALLOW_AREA_MAPPING,
        "peer_scope": PEER_SCOPE,
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
        "fact_ranking_subject_bridge": FACT_RANKING_SUBJECT_BRIDGE_CSV,
        "fact_ranking_indicator_subject_bridge": FACT_INDICATOR_SUBJECT_BRIDGE_CSV,
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
    alias_details = alias_rows.to_dict(orient="records")
    subject = {
        "target_university": TARGET_UNIVERSITY,
        "target_subject": TARGET_SUBJECT,
        "target_subject_code": TARGET_SUBJECT_CODE,
        "report_year": REPORT_YEAR,
        "ranking_sources": RANKING_SOURCES,
        "proxy_policy": PROXY_POLICY,
        "allow_area_mapping": ALLOW_AREA_MAPPING,
        "peer_scope": PEER_SCOPE,
        "subject_id": row["subject_id"],
        "ministry_subject_name": row["ministry_subject_name"],
        "subject_short_name": row.get("subject_short_name", ""),
        "tongji_college": row.get("tongji_college", ""),
        "arwu_subject_name": row.get("arwu_subject_name", ""),
        "qs_subject_name": row.get("qs_subject_name", ""),
        "usnews_subject_name": row.get("usnews_subject_name", ""),
        "the_subject_area": row.get("the_subject_area", ""),
        "alias_summary": alias_summary,
        "alias_details": alias_details,
        "alias_row_count": len(alias_rows),
    }
    public_records = public_supplements.public_supplement_records(subject)
    allowed_public_records = [row for row in public_records if supplement_allowed(row)]
    public_alias_count = 0
    for row in allowed_public_records:
        source = clean_text(row.get("ranking_source"))
        values = [row.get("subject_or_area"), row.get("subject_or_area_en")]
        public_alias_count += add_alias_values(subject, source, values)
    subject["public_supplements"] = allowed_public_records
    subject["public_supplement_alias_count"] = public_alias_count
    subject["source_runtime_overrides"] = {}
    subject["proxy_policy_decisions"] = [
        {
            "policy": PROXY_POLICY,
            "allow_area_mapping": ALLOW_AREA_MAPPING,
            "peer_scope": PEER_SCOPE,
            "decision": "proxy_supplements_enabled" if proxy_allowed() else "proxy_supplements_disabled",
        }
    ]
    return subject


def source_alias_display(subject: dict[str, Any], source: str) -> str:
    aliases = [valid_mapping_value(value) for value in subject.get("alias_summary", {}).get(source, [])]
    aliases = [value for value in ordered_unique(aliases) if value]
    return "、".join(aliases)


@lru_cache(maxsize=1)
def load_usnews_bilingual_subject_aliases() -> dict[str, tuple[str, ...]]:
    pairs: dict[str, set[str]] = {}

    def add_pair(left: Any, right: Any) -> None:
        left_text = clean_text(left)
        right_text = clean_text(right)
        if not left_text or not right_text or normalize_key(left_text) == normalize_key(right_text):
            return
        pairs.setdefault(normalize_key(left_text), set()).add(right_text)
        pairs.setdefault(normalize_key(right_text), set()).add(left_text)

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
            expanded.extend(aliases.get(normalize_key(item), ()))
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
            available_keys.update(normalize_key(value) for value in df[column].tolist() if normalize_key(value))
    if not available_keys:
        return set()
    scored_matches: list[tuple[int, int, int, set[str]]] = []
    for preferred in primary_source_area_values(subject, source):
        equivalent_values = expand_usnews_bilingual_values([preferred])
        equivalent_keys = {normalize_key(value) for value in equivalent_values if normalize_key(value)}
        equivalent_keys.update(key.replace("/", "") for key in list(equivalent_keys) if "/" in key)
        matched_keys = equivalent_keys & available_keys
        if matched_keys:
            masks = []
            for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
                if column in df.columns:
                    masks.append(df[column].map(normalize_key).isin(matched_keys))
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
    source_aliases = {
        source: {normalize_key(value) for value in alias_summary.get(source, []) if normalize_key(value)}
        for source in RANKING_SOURCES
    }
    if "THE" in source_aliases:
        expanded = set(source_aliases["THE"])
        override = subject.get("source_runtime_overrides", {}).get("THE", {})
        values = list(alias_summary.get("THE", [])) + [
            subject.get("the_subject_area"),
            override.get("ranking_subject_or_area"),
            override.get("weight_subject_or_area"),
        ]
        for value in values:
            expanded.update(normalize_key(item) for item in the_ranking_area_candidates(value) if normalize_key(item))
        source_aliases["THE"] = expanded
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
            matched["alias_type"] = "runtime_alias_supplement"
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


def rank_midpoint_from_raw(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"未进入", "滑落"}:
        return None
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if not numbers:
        return None
    if len(numbers) >= 2 and ("-" in text or "–" in text):
        return (min(numbers[0], numbers[1]) + max(numbers[0], numbers[1])) / 2
    return float(numbers[0])


def supplement_the_tongji_history_records(records: pd.DataFrame, subject: dict[str, Any]) -> pd.DataFrame:
    paths = sorted(DATA_DIR.glob("*THE*2023-2026*.xlsx"))
    if not paths:
        return records
    try:
        history = pd.read_excel(paths[0], sheet_name="同济历史", dtype=str).fillna("")
    except Exception:
        return records
    if history.empty:
        return records

    candidates = {
        valid_mapping_value(subject.get("the_subject_area")),
    }
    candidates.update(valid_mapping_value(value) for value in subject.get("alias_summary", {}).get("THE", []))
    candidate_keys = {normalize_key(canonical_the_area(value)) for value in candidates if value}
    if not candidate_keys:
        return records

    area_col = "THE学科领域" if "THE学科领域" in history.columns else history.columns[0]
    matched = history[history[area_col].map(lambda value: normalize_key(canonical_the_area(value))).isin(candidate_keys)].copy()
    if matched.empty:
        return records

    existing_keys = set()
    if not records.empty:
        the_records = records[records.get("ranking_source", pd.Series(dtype=str)).map(clean_text) == "THE"].copy()
        for _, row in the_records.iterrows():
            existing_keys.add(
                (
                    int(float(row.get("ranking_year"))) if clean_text(row.get("ranking_year")) else None,
                    normalize_key(canonical_the_area(row.get("ranking_subject_raw"))),
                )
            )

    additions: list[dict[str, Any]] = []
    row = matched.iloc[0]
    source_area = clean_text(row.get(area_col))
    display_area = expected_ranking_area(subject, "THE") or source_area
    area_key = normalize_key(canonical_the_area(source_area) or source_area)
    for column in history.columns:
        match = re.search(r"(20\d{2}).*排名", clean_text(column))
        if not match:
            continue
        year = int(match.group(1))
        if year < 2023 or year > 2026:
            continue
        if (year, area_key) in existing_keys:
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
                "ranking_subject_norm": normalize_key(display_area),
                "university_name_cn": clean_text(subject.get("target_university")) or TARGET_UNIVERSITY,
                "university_name_en": "Tongji University",
                "country_or_region": "中国内地",
                "is_mainland_china": "1",
                "is_tongji": "1",
                "rank_raw": rank_raw,
                "rank_midpoint": midpoint,
                "total_score": "",
                "source_file": paths[0].name,
                "source_sheet": "同济历史",
                "source_row": int(row.name) + 2,
                "ranking_subject_alias": display_area,
                "source_ranking_subject_raw": source_area,
                "alias_type": "the_tongji_history_sheet",
            }
        )
    if not additions:
        return records
    return pd.concat([records, pd.DataFrame(additions)], ignore_index=True, sort=False).fillna("")


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
        return valid_mapping_value(subject.get("arwu_subject_name")) or clean_text(subject.get("target_subject"))
    if source == "QS":
        return source_alias_display(subject, source)
    if source == "US News":
        return valid_mapping_value(subject.get("usnews_subject_name")) or source_alias_display(subject, source)
    if source == "THE":
        return source_alias_display(subject, source)
    return clean_text(subject.get("target_subject"))


def source_area_candidates(subject: dict[str, Any], source: str) -> list[str]:
    values = [expected_ranking_area(subject, source)]
    values.extend(candidate_subject_areas(subject.get("source_runtime_overrides", {}).get(source, {}).get("weight_subject_or_area")))
    values.extend(subject.get("alias_summary", {}).get(source, []))
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
    alias_by_key = {normalize_key(alias): alias for alias in aliases}
    ordered: list[str] = []
    for item in candidate_subject_areas(configured_value):
        matched = alias_by_key.get(normalize_key(item))
        if matched and matched not in ordered:
            ordered.append(matched)
    return ordered + [alias for alias in aliases if alias not in ordered]


def exact_subject_mask(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    alias_keys = {normalize_key(alias) for alias in aliases if normalize_key(alias)}
    for column in ["ranking_subject_raw", "ranking_subject_norm"]:
        if column in df.columns:
            mask = mask | df[column].map(normalize_key).isin(alias_keys)
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


@lru_cache(maxsize=1)
def manual_subject_alias_rule_notes() -> dict[str, str]:
    if not MANUAL_SUBJECT_ALIASES_JSON.exists():
        return {}
    payload = json.loads(MANUAL_SUBJECT_ALIASES_JSON.read_text(encoding="utf-8"))
    return {
        clean_text(row.get("rule_id")): clean_text(row.get("note"))
        for row in payload.get("subject_alias_rules", [])
        if clean_text(row.get("rule_id"))
    }


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
            note = manual_subject_alias_rule_notes().get(rule_id, "")
            if mapping_class not in {"deterministic", "broad_multi_subject"}:
                continue
        elif source == "THE" and (
            "the_ranking_area_crosswalk" in alias_type
            or "manual_area_alias_rule" in alias_type
        ):
            mapping_class = "deterministic_area_crosswalk"
            rule_id = "THE_AREA_NAME_CROSSWALK"
            note = "THE排名数据与映射表使用了同一领域的不同规范名称，仅作领域名称归一化。"
        else:
            continue
        if rule_id == "USNEWS_ENGINEERING_BROAD":
            continue
        alias = valid_mapping_value(row.get("ranking_subject_alias"))
        if not alias:
            continue
        item = grouped.setdefault(
            rule_id,
            {
                "rule_id": rule_id,
                "mapping_class": mapping_class,
                "note": note,
                "aliases": [],
            },
        )
        item["aliases"].append(alias)
    return [
        {**item, "aliases": ordered_unique(item["aliases"])}
        for item in grouped.values()
    ]


def select_source_area(df: pd.DataFrame, subject: dict[str, Any], source: str) -> dict[str, Any]:
    mapping_candidates = mapping_table_aliases(subject, source)
    primary = selected_exact_mapping_candidate(df, subject, source)
    if primary:
        return {
            "selection_mode": "mapping_table_candidate",
            "selected_ranking_subject_or_area": primary,
            "mapping_candidates": mapping_candidates,
            "fallback_rule_id": "",
            "fallback_mapping_class": "",
            "fallback_mapping_note": "",
        }
    fallback_scores: list[tuple[int, int, int, int, int, str, dict[str, Any]]] = []
    for rule_index, rule in enumerate(reasonable_fallback_rules(subject, source)):
        for score in score_exact_subject_aliases(df, rule["aliases"]):
            class_priority = 1 if rule["mapping_class"] in {"deterministic", "deterministic_area_crosswalk"} else 0
            fallback_scores.append((*score[:3], class_priority, -rule_index, score[4], rule))
    if fallback_scores:
        fallback_scores.sort(reverse=True, key=lambda item: item[:5])
        selected = fallback_scores[0]
        rule = selected[6]
        return {
            "selection_mode": "fallback_mapping",
            "selected_ranking_subject_or_area": selected[5],
            "mapping_candidates": mapping_candidates,
            "fallback_rule_id": rule["rule_id"],
            "fallback_mapping_class": rule["mapping_class"],
            "fallback_mapping_note": rule["note"],
        }
    return {
        "selection_mode": "missing",
        "selected_ranking_subject_or_area": "",
        "mapping_candidates": mapping_candidates,
        "fallback_rule_id": "",
        "fallback_mapping_class": "",
        "fallback_mapping_note": "",
    }


def stored_source_selection(subject: dict[str, Any], source: str) -> dict[str, Any]:
    selections = subject.get("ranking_selection_by_source", {})
    return selections.get(source, {}) if isinstance(selections, dict) else {}


def filter_to_selected_source_area(df: pd.DataFrame, subject: dict[str, Any], source: str) -> pd.DataFrame:
    if df.empty:
        return df
    stored_selection = stored_source_selection(subject, source)
    if stored_selection:
        selected = clean_text(stored_selection.get("selected_ranking_subject_or_area"))
        if not selected:
            return df.iloc[0:0].copy()
        return df[exact_subject_mask(df, [selected])].copy()
    mapping_candidates = mapping_table_aliases(subject, source)
    if mapping_candidates:
        selection = select_source_area(df, subject, source)
        selected = clean_text(selection.get("selected_ranking_subject_or_area"))
        if not selected:
            return df.iloc[0:0].copy()
        return df[exact_subject_mask(df, [selected])].copy()
    primary_keys = primary_source_area_keys_for_frame(df, subject, source)
    if primary_keys:
        masks = []
        for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
            if column in df.columns:
                masks.append(df[column].map(normalize_key).isin(primary_keys))
        if masks:
            mask = masks[0]
            for item in masks[1:]:
                mask = mask | item
            matched = df[mask].copy()
            if not matched.empty:
                return matched
    candidate_keys = {normalize_key(value) for value in source_area_candidates(subject, source) if normalize_key(value)}
    if not candidate_keys:
        return df.iloc[0:0].copy()
    masks = []
    for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
        if column in df.columns:
            masks.append(df[column].map(normalize_key).isin(candidate_keys))
    if not masks:
        return df
    mask = masks[0]
    for item in masks[1:]:
        mask = mask | item
    return df[mask].copy()


def build_ranking_availability(subject: dict[str, Any], records: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"sources_with_tongji": 0, "sources_with_peer_top200": 0}
    base_records = records
    records = supplement_the_tongji_history_records(records, subject)
    for source in RANKING_SOURCES:
        source_records = records[records["ranking_source"] == source].copy()
        source_base_records = base_records[base_records["ranking_source"] == source].copy()
        selection = select_source_area(source_records, subject, source)
        selected_area = clean_text(selection.get("selected_ranking_subject_or_area"))
        selected_records = source_records[exact_subject_mask(source_records, [selected_area])].copy() if selected_area else source_records.iloc[0:0].copy()
        selected_base_records = source_base_records[exact_subject_mask(source_base_records, [selected_area])].copy() if selected_area else source_base_records.iloc[0:0].copy()
        latest = latest_source_rows(selected_records, source)
        latest_for_peer = latest_source_rows(selected_base_records, source)
        tongji = latest[latest["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
        mainland = latest_for_peer[latest_for_peer.apply(is_mainland, axis=1)].copy() if not latest_for_peer.empty else latest_for_peer
        top200 = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= TOP_RANK_MIDPOINT].copy()
        candidate_statuses = []
        for candidate in mapping_table_aliases(subject, source):
            matched = source_base_records[exact_subject_mask(source_base_records, [candidate])].copy()
            years = sorted(
                {
                    int(value)
                    for value in pd.to_numeric(matched.get("ranking_year"), errors="coerce").dropna().tolist()
                }
            )
            latest_candidate = latest_source_rows(matched, source)
            latest_mainland = (
                latest_candidate[latest_candidate.apply(is_mainland, axis=1)].copy()
                if not latest_candidate.empty
                else latest_candidate
            )
            latest_top200 = latest_mainland[
                pd.to_numeric(latest_mainland.get("rank_midpoint"), errors="coerce") <= TOP_RANK_MIDPOINT
            ].copy()
            candidate_tongji = matched[
                matched.get("is_tongji", pd.Series([""] * len(matched), index=matched.index))
                .astype(str)
                .str.lower()
                .isin(["true", "1"])
            ]
            latest_tongji = latest_source_rows(candidate_tongji, source)
            candidate_statuses.append(
                {
                    "candidate": candidate,
                    "has_data": not matched.empty,
                    "total_rows": int(len(matched)),
                    "first_year": years[0] if years else "",
                    "latest_year": years[-1] if years else "",
                    "latest_rows": int(len(latest_candidate)),
                    "latest_mainland_rows": int(len(latest_mainland)),
                    "latest_mainland_top200_rows": int(len(latest_top200)),
                    "tongji_rows": int(len(candidate_tongji)),
                    "tongji_latest_rank": clean_text(latest_tongji.iloc[0]["rank_raw"]) if not latest_tongji.empty else "",
                }
            )
        observed_latest_area = ""
        if not latest.empty:
            observed_areas = ordered_unique(
                [
                    clean_text(value)
                    for value in latest.get("ranking_subject_raw", pd.Series(dtype=str)).tolist()
                    if clean_text(value)
                ]
            )
            if observed_areas:
                observed_latest_area = "；".join(observed_areas[:4])
        row = {
            "ranking_source": source,
            "selected_ranking_subject_or_area": selected_area,
            "selection_mode": selection["selection_mode"],
            "mapping_candidate_subjects": "；".join(selection["mapping_candidates"]),
            "mapping_candidate_status_json": json.dumps(candidate_statuses, ensure_ascii=False),
            "fallback_rule_id": selection["fallback_rule_id"],
            "fallback_mapping_class": selection["fallback_mapping_class"],
            "fallback_mapping_note": selection["fallback_mapping_note"],
            "observed_latest_subject_or_area": observed_latest_area,
            "latest_release_year": int(latest["release_year"].max()) if not latest.empty else "",
            "latest_ranking_year": int(latest["ranking_year"].max()) if not latest.empty else "",
            "latest_rows": len(latest),
            "tongji_latest_rows": len(tongji),
            "tongji_latest_rank": clean_text(tongji.iloc[0]["rank_raw"]) if not tongji.empty else "",
            "mainland_top200_rows": len(top200),
            "data_status": "available" if not tongji.empty else "missing_selected_subject_latest",
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
    values: list[Any] = [overrides.get("ranking_subject_or_area"), overrides.get("weight_subject_or_area")]
    if source == "软科":
        values.extend([subject.get("arwu_subject_name"), TARGET_SUBJECT])
    elif source == "QS":
        values.extend([subject.get("qs_subject_name")])
    elif source == "US News":
        values.extend([subject.get("usnews_subject_name")])
    elif source == "THE":
        area = clean_text(subject.get("the_subject_area"))
        if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
            crosswalk = json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
            area = crosswalk.get(area, area)
        values.extend([area])
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


def latest_tongji_ranking_subject_area(records: pd.DataFrame, source: str, subject: dict[str, Any] | None = None) -> str:
    if records is None or records.empty:
        return ""
    latest = latest_source_rows(records, source)
    if latest.empty:
        return ""
    tongji = latest[latest["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
    if tongji.empty:
        return ""
    primary_keys = primary_source_area_keys_for_frame(tongji, subject, source) if subject else set()
    if primary_keys:
        masks = []
        for column in ["ranking_subject_raw", "ranking_subject_norm", "ranking_subject_alias"]:
            if column in tongji.columns:
                masks.append(tongji[column].map(normalize_key).isin(primary_keys))
        if masks:
            mask = masks[0]
            for item in masks[1:]:
                mask = mask | item
            primary = tongji[mask].copy()
            if not primary.empty:
                tongji = primary
    tongji["_rank_sort"] = pd.to_numeric(tongji.get("rank_midpoint", pd.Series(dtype=str)), errors="coerce")
    broad_keys = {"engineering", "工程", "工程学", "natural sciences", "physical sciences", "social sciences"}
    tongji["_broad_subject"] = tongji.get("ranking_subject_raw", pd.Series([""] * len(tongji))).map(
        lambda value: 1 if clean_text(value).lower() in broad_keys else 0
    )
    tongji = tongji.sort_values(["_broad_subject", "_rank_sort"], ascending=[True, True], na_position="last")
    return clean_text(tongji.iloc[0].get("ranking_subject_raw", ""))


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
        subject.setdefault("proxy_policy_decisions", []).append(
            {
                "ranking_source": "QS",
                "decision": "proxy_override_skipped",
                "reason": "ranking_subject_display_must_follow_ministry_mapping_workbook",
                "source_key": clean_text(qs_proxy.get("source_key")),
            }
        )

    strategy = public_supplements.usnews_weight_strategy()
    if strategy.get("prefer_actual_ranking_subject"):
        weights = read_weight_data()
        actual_ranking_area = latest_tongji_ranking_subject_area(records, "US News", subject)
        candidates = ordered_unique(candidate_subject_areas(actual_ranking_area) + weight_candidate_values(subject, "US News", records))
        subset, matched_area = find_weight_subset(weights, "US News", candidates)
        requires_disclosure = bool(strategy.get("requires_disclosure_when_inferred"))
        if not subset.empty and not requires_disclosure:
            subject["source_runtime_overrides"]["US News"] = {
                "ranking_subject_or_area": actual_ranking_area or matched_area,
                "weight_subject_or_area": matched_area,
                "proxy_level": "actual_matched_ranking_subject",
                "requires_disclosure": requires_disclosure,
                "reason": clean_text(strategy.get("reason")),
            }
        elif not subset.empty:
            subject.setdefault("proxy_policy_decisions", []).append(
                {
                    "ranking_source": "US News",
                    "decision": "actual_ranking_subject_weight_override_skipped",
                    "reason": "proxy_policy=disallow",
                }
            )
    if records is not None and not records.empty:
        supplement_rows = records[records.get("alias_type", pd.Series(dtype=str)).astype(str).eq("runtime_alias_supplement")].copy()
        for source in sorted(supplement_rows.get("ranking_source", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()):
            if source in subject["source_runtime_overrides"]:
                continue
            source_rows = supplement_rows[supplement_rows["ranking_source"] == source].copy()
            if source_rows.empty:
                continue
            all_source_rows = records[records.get("ranking_source", pd.Series(dtype=str)).astype(str).eq(source)].copy()
            primary_keys = primary_source_area_keys_for_frame(all_source_rows, subject, source)
            if primary_keys:
                primary_rows = filter_to_selected_source_area(all_source_rows, subject, source)
            else:
                primary_rows = source_rows
            if not primary_rows.empty:
                primary_rows = primary_rows.copy()
                primary_rows["_sort_ranking_year"] = pd.to_numeric(primary_rows.get("ranking_year", pd.Series(dtype=str)), errors="coerce")
                primary_rows["_sort_release_year"] = pd.to_numeric(primary_rows.get("release_year", pd.Series(dtype=str)), errors="coerce")
                primary_rows = primary_rows.sort_values(["_sort_ranking_year", "_sort_release_year"], ascending=[False, False])
            primary_area = clean_text(
                (primary_rows.get("ranking_subject_raw", pd.Series(dtype=str)).dropna().astype(str).tolist() or [""])[0]
            )
            supplemental_areas = ordered_unique(
                [
                    clean_text(value)
                    for value in source_rows.get("ranking_subject_raw", pd.Series(dtype=str)).dropna().astype(str).tolist()
                    if clean_text(value)
                ]
            )
            subject["source_runtime_overrides"][source] = {
                "ranking_subject_or_area": primary_area,
                "supplemental_subject_or_areas": "；".join([area for area in supplemental_areas if normalize_key(area) not in primary_keys][:12]),
                "proxy_level": "runtime_direct_alias_supplement",
                "requires_disclosure": False,
                "reason": "本地事实表存在同济记录，但原始学科口径未能通过 subject_id 直接 join；已按映射表或公开直接别名补入，不作为代理口径。",
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
        selected_source_df = filter_to_selected_source_area(source_df, subject, source)
        if not selected_source_df.empty or source_area_candidates(subject, source):
            source_df = selected_source_df
        elif alias_values:
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


def truthy(value: Any) -> bool:
    return agent_runtime.coerce_bool(value, False)


def build_source_decision_matrix(
    subject: dict[str, Any],
    ranking_rows: list[dict[str, Any]],
    weight_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranking_by_source = {row["ranking_source"]: row for row in ranking_rows}
    weight_by_source = {row["ranking_source"]: row for row in weight_rows}
    indicator_by_source = {row["ranking_source"]: row for row in indicator_rows}
    supplements = subject.get("public_supplements", [])
    overrides = subject.get("source_runtime_overrides", {})
    rows: list[dict[str, Any]] = []
    for source in RANKING_SOURCES:
        ranking = ranking_by_source.get(source, {})
        weight = weight_by_source.get(source, {})
        indicator = indicator_by_source.get(source, {})
        source_supplements = [row for row in supplements if clean_text(row.get("ranking_source")) == source]
        source_override = overrides.get(source, {})
        has_tongji = int(ranking.get("tongji_latest_rows") or 0) > 0
        has_peer = int(ranking.get("mainland_top200_rows") or 0) > 0
        has_weight = int(weight.get("weight_rows") or 0) > 0
        has_indicator = int(indicator.get("tongji_indicator_rows") or 0) > 0
        uses_proxy = truthy(source_override.get("requires_disclosure")) or any(
            truthy(row.get("requires_disclosure")) for row in source_supplements
        )
        requires_disclosure = any(
            [
                truthy(source_override.get("requires_disclosure")),
                any(truthy(row.get("requires_disclosure")) for row in source_supplements),
            ]
        )
        if has_tongji and has_peer and (has_weight or has_indicator):
            status = "ready"
            recommendation = "use_in_core_report"
        elif has_tongji and (has_weight or has_indicator):
            status = "partial_peer_gap"
            recommendation = "use_for_tongji_only_views"
        elif has_tongji:
            status = "partial_metric_gap"
            recommendation = "use_ranking_only_or_add_metrics"
        else:
            status = "blocked_ranking_gap"
            recommendation = "add_subject_alias_or_ranking_records"
        rows.append(
            {
                "ranking_source": source,
                "has_tongji_latest_rank": has_tongji,
                "has_mainland_peer_top200": has_peer,
                "has_weight": has_weight,
                "has_indicator": has_indicator,
                "indicator_year_count": int(indicator.get("year_count") or 0),
                "uses_proxy_or_external_supplement": uses_proxy,
                "requires_disclosure": requires_disclosure,
                "proxy_policy": PROXY_POLICY,
                "runtime_override": clean_text(source_override.get("proxy_level")),
                "supplement_count": len(source_supplements),
                "overall_status": status,
                "recommendation": recommendation,
            }
        )
    return rows


def build_agent_decision_summary(source_rows: list[dict[str, Any]], readiness_rows: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    ready_artifact_count = sum(1 for row in readiness_rows if row["readiness_status"] == "ready")
    critical_blocked = [
        row
        for row in readiness_rows
        if row.get("blocking_level") == "P1" and row.get("readiness_status") != "ready"
    ]
    disclosure_required = any(truthy(row.get("requires_disclosure")) for row in source_rows)
    ready_sources = [row for row in source_rows if row.get("overall_status") == "ready"]
    if critical_blocked:
        agent_mode = "partial_blocked"
    elif disclosure_required:
        agent_mode = "full_with_disclosure"
    elif ready_artifact_count == len(readiness_rows):
        agent_mode = "full_ready"
    else:
        agent_mode = "partial_noncritical_gaps"
    return {
        "generated_at": now_text(),
        "agent_mode": agent_mode,
        "proxy_policy": PROXY_POLICY,
        "allow_area_mapping": ALLOW_AREA_MAPPING,
        "peer_scope": PEER_SCOPE,
        "source_count": len(source_rows),
        "ready_source_count": len(ready_sources),
        "proxy_or_external_source_count": sum(truthy(row.get("uses_proxy_or_external_supplement")) for row in source_rows),
        "disclosure_required": disclosure_required,
        "ready_artifact_count": ready_artifact_count,
        "artifact_count": len(readiness_rows),
        "blocked_or_partial_count": len(gaps),
        "critical_blocked_count": len(critical_blocked),
        "critical_blocked_artifacts": [row["artifact_id"] for row in critical_blocked],
    }


def detect_paper_metric_sources() -> dict[str, Any]:
    preprocess_status = ensure_wos_subject_paper_csv()
    keywords = ["论文", "被引", "CNCI", "篇均", "高被引", "国际合著", "国际合作", "WOS", "Web of Science", "InCites", "ESI"]
    matches = []
    for path in DATA_DIR.glob("*"):
        if not path.is_file():
            continue
        name = path.name
        if any(keyword.lower() in name.lower() for keyword in keywords):
            matches.append(name)
    external_matches = []
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
        "has_paper_metric_source": wos_subject_available,
        "preferred_source": "wos_subject_paper_metrics" if wos_subject_available else "missing_wos_subject_paper_metrics",
        "matched_files": matches,
        "external_matched_files": external_matches,
        "wos_subject_rows": wos_subject_rows,
        "wos_preprocess_status": preprocess_status,
        "subject_code_match_rule": "extract leading 4 digits from 教育部一级学科 and compare to target_subject_code",
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

    def has_peer_with_tongji(source: str) -> bool:
        return has_tongji(source) and has_peer(source)

    def has_weight(source: str) -> bool:
        return int(weight_by_source.get(source, {}).get("weight_rows") or 0) > 0

    def has_indicators(source: str) -> bool:
        return int(indicator_by_source.get(source, {}).get("tongji_indicator_rows") or 0) > 0

    def has_indicator_years(source: str, min_years: int) -> bool:
        if source == "US News" and not has_tongji(source):
            return False
        return int(indicator_by_source.get(source, {}).get("year_count") or 0) >= min_years

    if not has_tongji("软科"):
        external_status_by_artifact.pop("table_01_arwu_tongji_indicator_history", None)
    elif ARWU_PUBLIC_TONGJI_LONG_CSV.exists():
        external_status_by_artifact["table_01_arwu_tongji_indicator_history"] = "ready_from_arwu_gras_public_web_common"

    has_paper_metrics = bool(paper_metric_sources.get("has_paper_metric_source"))
    overview_source_count = sum(has_tongji(s) for s in RANKING_SOURCES)
    commonality_source_count = sum(has_tongji(s) and (has_weight(s) or has_indicators(s)) for s in RANKING_SOURCES)
    readiness_specs = [
        (
            "figure_01_tongji_subject_ranking_overview",
            "chart",
            "多榜单排名概览",
            overview_source_count >= 1,
            f"至少一个榜单有同济最新排名即可生成概览；当前可用 {overview_source_count} 个榜单，缺失榜单应在图注或数据缺口中说明。",
        ),
        (
            "figure_02_ranking_indicator_commonality",
            "chart",
            "指标共性图",
            commonality_source_count >= 2,
            f"至少两个有同济最新综合排名的榜单具备权重或同济分项指标即可生成共性图；当前可用 {commonality_source_count} 个榜单，未形成同济最新排名的榜单不纳入主图。",
        ),
        ("figure_03_arwu_indicator_weight", "chart", "软科权重图", has_tongji("软科") and has_weight("软科"), "需要软科对应口径权重，且同济在该口径下有最新综合排名。"),
        ("figure_04_qs_indicator_weight", "chart", "QS 权重图", has_tongji("QS") and has_weight("QS"), "需要 QS 对应口径权重，且同济在该口径下有最新综合排名；否则不纳入主报告权重图。"),
        ("figure_05_usnews_indicator_weight", "chart", "US News 权重图", has_tongji("US News") and has_weight("US News"), "需要 US News 对应口径权重，且同济在该口径下有最新综合排名。"),
        ("figure_06_the_indicator_weight", "chart", "THE 权重图", has_tongji("THE") and has_weight("THE"), "需要 THE 对应领域权重，且同济在该口径下有最新综合排名。"),
        ("figure_07_all_rankings_history", "chart", "四大排名历史趋势", sum(has_tongji(s) for s in RANKING_SOURCES) >= 1, "至少一个榜单有同济历史排名即可生成历史图；单榜单时用于展示当前可核验历史，缺失榜单不补造。"),
        ("table_04_mainland_rank_band_distribution", "table", "内地高校位次分布", sum(has_peer(s) for s in RANKING_SOURCES) >= 2, "需要各榜单最新内地高校排名样本；同济缺位的榜单仍可展示总体分布，但必须明确数据缺口。"),
        ("table_05_arwu_mainland_peer_ranking", "table", "软科 peer 排名表", has_peer("软科"), "需要软科前200内地高校样本；同济不在该口径时不追加虚构参照行。"),
        ("table_06_usnews_mainland_peer_ranking", "table", "US News peer 排名表", has_peer("US News"), "需要 US News 前200内地高校样本；同济不在该口径时仍展示前列高校，并明确同济缺位。"),
        ("table_07_qs_mainland_peer_ranking", "table", "QS peer 排名表", has_peer("QS"), "需要 QS 前200内地高校样本；同济不在该口径时不追加虚构参照行。"),
        ("table_08_the_mainland_peer_ranking", "table", "THE peer 排名表", has_peer("THE"), "需要 THE 前200内地高校样本；同济不在该口径时不追加虚构参照行。"),
        ("table_01_arwu_tongji_indicator_history", "table", "软科同济分项指标历史表", has_tongji("软科") and has_indicator_years("软科", 2), "需要同济在软科对应口径下有最新综合排名，并具备软科多年分项指标；否则不使用近邻学科或外部候选口径替代。"),
        ("table_02_usnews_tongji_indicator_history", "table", "US News 同济分项指标历史表", has_indicator_years("US News", 2), "模板要求多年历史；当前若只有单年，只能降级为最新年表。"),
        ("figure_10_usnews_indicator_history_trend", "chart", "US News 分项指标历史趋势图", has_indicator_years("US News", 2), "趋势图需要 US News 多年分项指标。"),
        ("table_03_the_tongji_indicator_history", "table", "THE 分项指标历史表", has_indicator_years("THE", 2), "需要 THE 同济分项指标多年份数据。"),
        ("figure_09_arwu_peer_indicator_relative_rank", "chart", "软科 peer 分项相对排名", has_peer_with_tongji("软科") and has_indicators("软科"), "需要 peer 样本和分项指标。"),
        ("figure_10_qs_peer_indicator_relative_rank", "chart", "QS peer 分项相对排名", has_peer_with_tongji("QS") and has_indicators("QS"), "需要 QS peer 样本和最新年分项指标；多年趋势另需多年度分项指标。"),
        ("figure_11_usnews_peer_indicator_relative_rank", "chart", "US News peer 分项相对排名", has_peer_with_tongji("US News") and has_indicators("US News"), "需要 peer 样本和分项指标。"),
        ("figure_12_the_peer_indicator_relative_rank", "chart", "THE peer 分项相对排名", has_peer_with_tongji("THE") and has_indicators("THE"), "需要 peer 样本和分项指标。"),
        ("figure_13_paper_output_citation_relative_rank", "chart", "论文及被引总量相对排名图", has_paper_metrics, "需要 WoS 37校论文数据中存在当前教育部一级学科代码，不能由排名表或宽口径代理数据臆造。"),
        ("figure_14_paper_cnci_cpp_relative_rank", "chart", "CNCI 及篇均被引相对排名图", has_paper_metrics, "需要 WoS 37校论文数据中存在当前教育部一级学科代码，并含 CNCI 与篇均被引字段。"),
        ("figure_15_paper_highly_cited_relative_rank", "chart", "高被引 TOP 论文量相对排名图", has_paper_metrics, "需要 WoS 37校论文数据中存在当前教育部一级学科代码，并含 TOP1%/TOP10% 高被引论文字段。"),
        ("figure_16_paper_international_collab_relative_rank", "chart", "国际合著论文占比相对排名图", has_paper_metrics, "需要 WoS 37校论文数据中存在当前教育部一级学科代码，并含国际合作论文数或占比字段。"),
        ("table_09_peer_full_ranking_history_appendix", "table", "对标高校排名历史附表", sum(has_peer_with_tongji(s) for s in RANKING_SOURCES) >= 2, "由各榜单 peer 表和历史排名合并生成。"),
    ]
    critical_artifacts = {
        "figure_01_tongji_subject_ranking_overview",
        "figure_02_ranking_indicator_commonality",
        "figure_07_all_rankings_history",
        "table_04_mainland_rank_band_distribution",
    }
    readiness_rows = []
    gaps = []
    for artifact_id, artifact_type, label, ready, note in readiness_specs:
        external_status = external_status_by_artifact.get(artifact_id, "")
        readiness_scope = "direct_data"
        if artifact_id.startswith("figure_1") and "paper_" in artifact_id and not has_paper_metrics:
            external_status = ""
        if external_status and external_status != "candidate_indirect_not_auto_merge":
            ready = True
            note = f"{note} external_data补源状态：{external_status}。"
            readiness_scope = "external_supplement"
        elif external_status:
            note = f"{note} external_data已生成候选口径：{external_status}，进入Word前需要人工确认。"
            readiness_scope = "candidate_needs_review"
        status = "ready" if ready else "blocked_or_partial"
        blocking_level = "none" if ready else ("P1" if artifact_id in critical_artifacts else "P2")
        recommended_action = (
            "build_artifact"
            if ready
            else (
                "review_external_candidate"
                if readiness_scope == "candidate_needs_review"
                else "supplement_source_data_or_adjust_subject_mapping"
            )
        )
        readiness_rows.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "label": label,
                "readiness_status": status,
                "readiness_scope": readiness_scope,
                "blocking_level": blocking_level,
                "recommended_action": recommended_action,
                "include_in_word_candidate": ready,
                "note": note,
            }
        )
        if not ready:
            gaps.append(
                {
                    "artifact_id": artifact_id,
                    "label": label,
                    "gap_type": "data_or_parameterization_gap",
                    "blocking_level": blocking_level,
                    "recommended_action": recommended_action,
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
            "ranking_sources": RANKING_SOURCES,
            "proxy_policy": PROXY_POLICY,
            "allow_area_mapping": ALLOW_AREA_MAPPING,
            "peer_scope": PEER_SCOPE,
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
    source_decision_rows: list[dict[str, Any]],
    agent_decision_summary: dict[str, Any],
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
        f"- agent_mode: {agent_decision_summary.get('agent_mode', '')}",
        f"- proxy_policy: {PROXY_POLICY}",
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
    lines.extend(["", "## 榜单源决策矩阵", "", "| 榜单 | 核心状态 | 代理/外部补源 | 需披露 | 建议 |", "| --- | --- | --- | --- | --- |"])
    for row in source_decision_rows:
        lines.append(
            f"| {row['ranking_source']} | {row['overall_status']} | "
            f"{row['uses_proxy_or_external_supplement']} | {row['requires_disclosure']} | {row['recommendation']} |"
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
    lines.extend(["", "## Artifact 就绪判断", "", "| artifact | 类型 | 说明 | 状态 | 阻塞级别 | 建议动作 |", "| --- | --- | --- | --- | --- | --- |"])
    for row in readiness_rows:
        lines.append(
            f"| {row['artifact_id']} | {row['artifact_type']} | {row['label']} | "
            f"{row['readiness_status']} | {row.get('blocking_level', '')} | {row.get('recommended_action', '')} |"
        )
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
    source_decision_rows: list[dict[str, Any]],
    agent_decision_summary: dict[str, Any],
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
        "agent_decision_summary": agent_decision_summary,
        "counts": {
            "ranking_sources": len(ranking_rows),
            "weight_sources": len(weight_rows),
            "indicator_sources": len(indicator_rows),
            "ready_sources": sum(1 for row in source_decision_rows if row.get("overall_status") == "ready"),
            "ready_artifacts": sum(1 for row in readiness_rows if row["readiness_status"] == "ready"),
            "artifact_count": len(readiness_rows),
            "gap_count": len(gaps),
        },
        "run_files": {
            "agent_run_report": str(run_dir / "agent_run_report.md"),
            "ranking_availability": str(run_dir / "ranking_availability.csv"),
            "weight_availability": str(run_dir / "weight_availability.csv"),
            "indicator_availability": str(run_dir / "indicator_availability.csv"),
            "source_decision_matrix": str(run_dir / "source_decision_matrix.csv"),
            "agent_decision_summary": str(run_dir / "agent_decision_summary.json"),
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
    report_progress("data", "running", "正在检查数据与请求")
    input_issues = validate_required_inputs()
    if input_issues:
        raise FileNotFoundError(json.dumps(input_issues, ensure_ascii=False, indent=2))

    report_progress("data", "success", "核心数据检查通过", checked_inputs=7)
    report_progress("resolve", "running", "正在关联目标学科与榜单记录")
    subject = resolve_subject()
    run_slug = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{TARGET_SUBJECT_CODE}_{slug_text(TARGET_SUBJECT)}"
    run_dir = OUTPUT_DIR / run_slug
    run_dir.mkdir(parents=True, exist_ok=True)

    records = combine_ranking_records(query_ranking_records(subject["subject_id"]), query_supplemental_ranking_records(subject))
    matched_sources = [{"source": str(source), "records": int(len(group))}
                       for source, group in records.groupby("ranking_source")]
    report_progress("resolve", "success", "学科记录关联完成", ranking_records=int(len(records)), subject_code=str(TARGET_SUBJECT_CODE), run_dir=str(run_dir), matched_sources=matched_sources)
    report_progress("sources", "running", "正在确定各榜单的可用口径", run_dir=str(run_dir))
    subject = attach_runtime_public_supplements(subject, records)
    ranking_rows, ranking_summary = build_ranking_availability(subject, records)
    subject["ranking_selection_by_source"] = {
        row["ranking_source"]: {
            key: row.get(key, "")
            for key in [
                "selection_mode",
                "selected_ranking_subject_or_area",
                "mapping_candidate_subjects",
                "fallback_rule_id",
                "fallback_mapping_class",
                "fallback_mapping_note",
            ]
        }
        for row in ranking_rows
    }
    request_info = write_current_request(run_dir, subject)
    weight_rows = build_weight_availability(subject, records)
    indicator_rows = build_indicator_availability(subject)
    paper_metric_sources = detect_paper_metric_sources()
    readiness_rows, gaps = build_artifact_readiness(ranking_rows, weight_rows, indicator_rows, paper_metric_sources)
    source_decision_rows = build_source_decision_matrix(subject, ranking_rows, weight_rows, indicator_rows)
    agent_decision_summary = build_agent_decision_summary(source_decision_rows, readiness_rows, gaps)
    report_progress("sources", "success", "来源决策完成", available_sources=int(agent_decision_summary.get("ready_source_count", 0)), ready_artifacts=int(agent_decision_summary.get("ready_artifact_count", 0)), disclosed_gaps=int(len(gaps)), run_dir=str(run_dir), source_rows=ranking_rows)

    write_csv(run_dir / "ranking_availability.csv", ranking_rows, list(ranking_rows[0].keys()))
    write_csv(run_dir / "weight_availability.csv", weight_rows, list(weight_rows[0].keys()))
    write_csv(run_dir / "indicator_availability.csv", indicator_rows, list(indicator_rows[0].keys()))
    write_csv(run_dir / "source_decision_matrix.csv", source_decision_rows, list(source_decision_rows[0].keys()))
    write_json(run_dir / "source_decision_matrix.json", {"generated_at": now_text(), "sources": source_decision_rows})
    write_json(run_dir / "agent_decision_summary.json", agent_decision_summary)
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
        write_csv(run_dir / "data_gap_report.csv", [], ["artifact_id", "label", "gap_type", "blocking_level", "recommended_action", "reason"])

    write_markdown_report(
        run_dir,
        subject,
        ranking_rows,
        weight_rows,
        indicator_rows,
        source_decision_rows,
        agent_decision_summary,
        readiness_rows,
        gaps,
    )
    run_manifest = write_run_manifest(
        run_dir,
        subject,
        request_info,
        input_issues,
        ranking_rows,
        weight_rows,
        indicator_rows,
        source_decision_rows,
        agent_decision_summary,
        readiness_rows,
        gaps,
    )
    parameterized_artifacts = {"generated_count": 0, "attempted_count": 0, "skipped_count": 0, "results": []}
    report_progress("artifacts", "running", "正在生成图表与分析素材")
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
        "agent_decision_summary": agent_decision_summary,
        "source_decision_matrix": source_decision_rows,
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
            "source_decision_matrix": str(run_dir / "source_decision_matrix.csv"),
            "agent_decision_summary": str(run_dir / "agent_decision_summary.json"),
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
    report_progress("artifacts", "success", "图表与素材审计完成", generated_artifacts=int(parameterized_artifacts.get("generated_count", 0)), audit_failures=int(summary.get("subject_artifact_audit", {}).get("fail_count", 0)))
    append_run_log(run_dir, ready_count, len(readiness_rows), len(gaps))
    if UPDATE_README_ON_RUN:
        update_readme_agent_section()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run_subject_agent()
