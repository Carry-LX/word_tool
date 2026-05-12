from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUT_DIR = CONFIG_DIR / "pre_word_pipeline_qa"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
THE_WEIGHT_AREA_CROSSWALK_JSON = CONFIG_DIR / "runtime" / "the_weight_area_crosswalk.json"

# 迁移 smoke test，不走命令行参数。这里放典型学科，覆盖理学、工学、医学交叉类。
SUBJECTS_TO_TEST = [
    {"subject_code": "0701", "subject_name": "数学"},
    {"subject_code": "0702", "subject_name": "物理学"},
    {"subject_code": "0703", "subject_name": "化学"},
    {"subject_code": "0814", "subject_name": "土木工程"},
    {"subject_code": "0831", "subject_name": "生物医学工程"},
]
RANKING_SOURCES = ["软科", "QS", "US News", "THE"]


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def candidate_subject_areas(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    normalized = re.sub(r"[\u3001\uff0c,;\uff1b/]+", " ", text)
    if re.search("[\u4e00-\u9fff]", normalized):
        return [part.strip() for part in normalized.split() if part.strip()]
    return [text]


def read_crosswalk() -> dict[str, str]:
    if THE_WEIGHT_AREA_CROSSWALK_JSON.exists():
        return json.loads(THE_WEIGHT_AREA_CROSSWALK_JSON.read_text(encoding="utf-8"))
    return {}


def latest_tongji_sources(subject_id: str) -> set[str]:
    query = """
    SELECT DISTINCT f.ranking_source
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
      AND f.is_tongji = 1
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        return {row[0] for row in conn.execute(query, [subject_id]).fetchall()}


def peer_sources(subject_id: str) -> set[str]:
    query = """
    SELECT f.ranking_source, f.release_year, f.ranking_year, f.rank_midpoint, f.country_or_region, f.is_mainland_china
    FROM fact_ranking f
    JOIN dim_subject_alias a
      ON f.ranking_source = a.ranking_source
     AND f.ranking_subject_norm = a.ranking_subject_norm
    WHERE a.subject_id = ?
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=[subject_id])
    if df.empty:
        return set()
    sources = set()
    for source, group in df.groupby("ranking_source"):
        latest_release = pd.to_numeric(group["release_year"], errors="coerce").max()
        latest = group[pd.to_numeric(group["release_year"], errors="coerce") == latest_release].copy()
        latest_ranking = pd.to_numeric(latest["ranking_year"], errors="coerce").max()
        latest = latest[pd.to_numeric(latest["ranking_year"], errors="coerce") == latest_ranking].copy()
        country = latest["country_or_region"].astype(str).str.lower()
        mainland = latest[
            latest["is_mainland_china"].astype(str).str.lower().isin(["1", "true"])
            | country.isin(["china", "中国", "中国内地", "中国大陆", "china (mainland)"])
        ].copy()
        top = mainland[pd.to_numeric(mainland["rank_midpoint"], errors="coerce") <= 200]
        if len(top) > 0:
            sources.add(source)
    return sources


def expected_weight_area(row: pd.Series, source: str, crosswalk: dict[str, str]) -> str:
    if source == "软科":
        return clean_text(row.get("arwu_subject_name")) or clean_text(row.get("ministry_subject_name"))
    if source == "QS":
        return clean_text(row.get("qs_subject_name")) or clean_text(row.get("ministry_subject_name"))
    if source == "US News":
        return clean_text(row.get("usnews_subject_name")) or clean_text(row.get("ministry_subject_name"))
    area = clean_text(row.get("the_subject_area"))
    return crosswalk.get(area, area or "自然科学")


def indicator_sources(subject_id: str) -> set[str]:
    aliases = pd.read_csv(DIM_ALIAS_CSV, dtype=str).fillna("")
    alias_rows = aliases[aliases["subject_id"] == subject_id]
    indicators = pd.read_csv(FACT_INDICATOR_CSV, dtype=str).fillna("")
    sources = set()
    for source in RANKING_SOURCES:
        values = set(alias_rows[alias_rows["ranking_source"] == source]["ranking_subject_alias"].tolist())
        source_df = indicators[indicators["ranking_source"] == source].copy()
        matched = source_df[source_df["ranking_subject_raw"].isin(values) | source_df["ranking_subject_norm"].isin(values)]
        tongji = matched[matched["is_tongji"].astype(str).str.lower().isin(["true", "1"])]
        if len(tongji) > 0:
            sources.add(source)
    return sources


def run_smoke_test() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dim = pd.read_csv(DIM_SUBJECT_CSV, dtype=str).fillna("")
    aliases = pd.read_csv(DIM_ALIAS_CSV, dtype=str).fillna("")
    weights = pd.read_csv(FACT_WEIGHT_CSV, dtype=str).fillna("")
    crosswalk = read_crosswalk()
    rows = []
    for item in SUBJECTS_TO_TEST:
        subject_rows = dim[
            (dim["ministry_subject_code"] == item["subject_code"])
            | (dim["ministry_subject_name"] == item["subject_name"])
        ]
        if subject_rows.empty:
            rows.append({"subject_code": item["subject_code"], "subject_name": item["subject_name"], "status": "missing_dim_subject"})
            continue
        row = subject_rows.iloc[0]
        subject_id = row["subject_id"]
        alias_count = len(aliases[aliases["subject_id"] == subject_id])
        tongji = latest_tongji_sources(subject_id)
        peers = peer_sources(subject_id)
        ind_sources = indicator_sources(subject_id)
        weight_available = []
        weight_missing = []
        for source in RANKING_SOURCES:
            area = expected_weight_area(row, source, crosswalk)
            subset = pd.DataFrame()
            matched_area = area
            for candidate in candidate_subject_areas(area):
                subset = weights[(weights["ranking_source"] == source) & (weights["ranking_subject_or_area"] == candidate)]
                if len(subset) > 0:
                    matched_area = candidate
                    break
            if len(subset) > 0:
                weight_available.append(source)
            else:
                weight_missing.append(f"{source}:{matched_area}")
        ready_like = len(tongji) >= 2 and len(peers) >= 2
        rows.append(
            {
                "subject_code": item["subject_code"],
                "subject_name": item["subject_name"],
                "subject_id": subject_id,
                "alias_count": alias_count,
                "tongji_sources": ";".join(sorted(tongji)),
                "peer_sources": ";".join(sorted(peers)),
                "indicator_sources": ";".join(sorted(ind_sources)),
                "weight_available_sources": ";".join(sorted(weight_available)),
                "weight_missing": ";".join(weight_missing),
                "ready_like_for_agent": ready_like,
                "status": "ok",
            }
        )
    df = pd.DataFrame(rows)
    csv_path = OUTPUT_DIR / "subject_migration_smoke_test.csv"
    md_path = OUTPUT_DIR / "subject_migration_smoke_test.md"
    json_path = OUTPUT_DIR / "subject_migration_smoke_test.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    lines = [
        "# Subject Migration Smoke Test",
        "",
        f"- generated_at: {now_text()}",
        f"- tested_subjects: {len(df)}",
        "",
        "| code | subject | aliases | tongji sources | peer sources | indicator sources | missing weights | status |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for _, row in df.iterrows():
        lines.append(
            f"| {row.get('subject_code','')} | {row.get('subject_name','')} | {row.get('alias_count','')} | "
            f"{row.get('tongji_sources','')} | {row.get('peer_sources','')} | {row.get('indicator_sources','')} | "
            f"{row.get('weight_missing','')} | {row.get('status','')} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    json_path.write_text(json.dumps({"generated_at": now_text(), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({"tested_subjects": len(df), "csv": str(csv_path), "md": str(md_path)}, ensure_ascii=False, indent=2))
    return {"rows": rows, "csv": str(csv_path), "md": str(md_path)}


if __name__ == "__main__":
    run_smoke_test()
