from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import ranking_source_inputs
import subject_bridge_utils


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "arwu_source_upgrade_20260915"
SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
MAPPING_WORKBOOK_PATH = DATA_DIR / "教育部学科与四大国际学科排名映射关系.xlsx"
MAPPING_SHEET_NAME = "学科映射关系"
SOURCE_LABEL = "软科"
SOURCE_KEY = "arwu"
TONGJI_NAME = "同济大学"


def clean_text(value: Any) -> str:
    return subject_bridge_utils.clean_text(value)


def normalize_key(value: Any) -> str:
    return subject_bridge_utils.normalize_key(value)


def load_source(path: Path, sheet_name: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet_name, dtype=object).dropna(how="all").copy()
    frame.columns = [clean_text(column) for column in frame.columns]
    frame["发布年度"] = pd.to_numeric(frame["发布年度"], errors="coerce").astype("Int64")
    return frame


def normalized_history(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in frame.columns if column != "序号"]
    result = frame[columns].copy()
    for column in columns:
        result[column] = result[column].map(clean_text)
    return result.sort_values(columns).reset_index(drop=True)


def query_counts(connection: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(
        f"""
        SELECT release_year,
               COUNT(*) AS row_count,
               COUNT(DISTINCT ranking_subject_raw) AS subject_count,
               SUM(CASE WHEN is_tongji = 1 THEN 1 ELSE 0 END) AS tongji_row_count
        FROM {table}
        WHERE ranking_source = ?
        GROUP BY release_year
        ORDER BY release_year
        """,
        connection,
        params=[SOURCE_LABEL],
    )


def mapping_coverage(latest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    aliases = pd.read_csv(DIM_ALIAS_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    subjects = pd.read_csv(DIM_SUBJECT_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    aliases = aliases[aliases["ranking_source"].eq(SOURCE_LABEL)].copy()
    subject_names = dict(zip(subjects["subject_id"], subjects["ministry_subject_name"]))
    alias_groups = aliases.groupby("ranking_subject_norm")["subject_id"].apply(
        lambda values: sorted(set(clean_text(value) for value in values if clean_text(value)))
    )

    rows: list[dict[str, Any]] = []
    for (raw, norm), part in latest.groupby(["ranking_subject_raw", "ranking_subject_norm"], dropna=False):
        subject_ids = alias_groups.get(clean_text(norm), [])
        rows.append(
            {
                "ranking_subject_raw": clean_text(raw),
                "ranking_subject_norm": clean_text(norm),
                "latest_row_count": int(len(part)),
                "latest_tongji_row_count": int(part["is_tongji"].astype(bool).sum()),
                "mapped_subject_count": len(subject_ids),
                "mapped_subject_ids": "；".join(subject_ids),
                "mapped_subject_names": "；".join(subject_names.get(subject_id, "") for subject_id in subject_ids),
            }
        )
    coverage = pd.DataFrame(rows).sort_values("ranking_subject_raw").reset_index(drop=True)
    tongji = latest[latest["is_tongji"].astype(bool)].copy()
    tongji = tongji.merge(
        coverage[
            [
                "ranking_subject_norm",
                "mapped_subject_count",
                "mapped_subject_ids",
                "mapped_subject_names",
            ]
        ],
        on="ranking_subject_norm",
        how="left",
    )
    return coverage, tongji


def authoritative_forward_arwu_subjects() -> set[str]:
    mapping = pd.read_excel(
        MAPPING_WORKBOOK_PATH,
        sheet_name=MAPPING_SHEET_NAME,
        dtype=object,
    ).dropna(how="all")
    column = "软科世界一流学科对应名称"
    subjects: set[str] = set()
    for value in mapping[column].tolist():
        text = clean_text(value)
        if not text:
            continue
        subjects.update(
            clean_text(part)
            for part in re.split(r"[、，,;；\n\r]+", text)
            if clean_text(part)
        )
    return subjects


def main() -> None:
    spec = ranking_source_inputs.source_spec(SOURCE_KEY)
    active_name = ranking_source_inputs.resolve_data_file_name(DATA_DIR, SOURCE_KEY, "")
    active_path = DATA_DIR / active_name
    active_sheet = ranking_source_inputs.resolve_sheet_name(active_path, SOURCE_KEY, "2021-2025")
    fallback_paths = [DATA_DIR / clean_text(value) for value in spec.get("fallback_files", [])]
    fallback_path = next((path for path in fallback_paths if path.exists()), None)
    active = load_source(active_path, active_sheet)
    latest_year = int(active["发布年度"].max())
    latest_source = active[active["发布年度"].eq(latest_year)].copy()
    previous_source = active[active["发布年度"].eq(latest_year - 1)].copy()

    historical_equal = None
    if fallback_path is not None:
        fallback_sheet = ranking_source_inputs.resolve_sheet_name(fallback_path, SOURCE_KEY, "2021-2025")
        fallback = load_source(fallback_path, fallback_sheet)
        active_history = active[active["发布年度"].le(int(fallback["发布年度"].max()))].copy()
        historical_equal = normalized_history(active_history).equals(normalized_history(fallback))

    connection = sqlite3.connect(SQLITE_PATH)
    fact_counts = query_counts(connection, "fact_ranking")
    indicator_counts = query_counts(connection, "fact_ranking_indicator")
    latest_facts = pd.read_sql_query(
        """
        SELECT fact_id, ranking_subject_raw, ranking_subject_norm,
               university_name_cn, country_or_region, is_mainland_china,
               is_tongji, rank_raw, rank_midpoint, total_score,
               source_file, source_sheet, source_row
        FROM fact_ranking
        WHERE ranking_source = ? AND release_year = ? AND ranking_year = ?
        """,
        connection,
        params=[SOURCE_LABEL, latest_year, latest_year],
    )
    latest_indicator_count = int(
        pd.read_sql_query(
            """
            SELECT COUNT(*) AS row_count
            FROM fact_ranking_indicator
            WHERE ranking_source = ? AND release_year = ? AND ranking_year = ?
            """,
            connection,
            params=[SOURCE_LABEL, latest_year, latest_year],
        ).iloc[0]["row_count"]
    )
    connection.close()

    coverage, latest_tongji = mapping_coverage(latest_facts)
    latest_subjects = set(latest_source["学科名称"].map(clean_text))
    previous_subjects = set(previous_source["学科名称"].map(clean_text))
    authoritative_subjects = authoritative_forward_arwu_subjects()
    unmapped_latest_subjects = set(
        coverage.loc[coverage["mapped_subject_count"].eq(0), "ranking_subject_raw"].map(clean_text)
    )
    unmapped_authoritative_subjects = sorted(
        unmapped_latest_subjects & authoritative_subjects
    )
    source_file_values = sorted(set(latest_facts["source_file"].map(clean_text)))
    expected_year = ranking_source_inputs.expected_latest_year(SOURCE_KEY)
    core_indicator_columns = [
        "世界一流教师",
        "世界一流成果",
        "高水平研究成果/重要期刊论文数",
        "科研影响力/论文标准化影响力",
        "国际合作/国际合作论文比例",
    ]
    checks = {
        "configured_source_file_used": source_file_values == [active_name],
        "latest_year_matches_config": expected_year is None or latest_year == expected_year,
        "historical_rows_unchanged": historical_equal is not False,
        "latest_subject_set_stable": latest_subjects == previous_subjects,
        "authoritative_forward_subjects_all_mapped": not unmapped_authoritative_subjects,
        "latest_tongji_subjects_all_mapped": bool((latest_tongji["mapped_subject_count"] > 0).all()),
        "latest_core_indicators_complete": all(int(latest_source[column].notna().sum()) == len(latest_source) for column in core_indicator_columns),
        "processed_latest_row_count_matches_source": len(latest_facts) == len(latest_source),
    }
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_source_file": active_name,
        "active_source_sheet": active_sheet,
        "fallback_source_file": fallback_path.name if fallback_path else "",
        "source_columns": list(active.columns),
        "source_row_count": int(len(active)),
        "latest_year": latest_year,
        "latest_row_count": int(len(latest_source)),
        "latest_subject_count": len(latest_subjects),
        "latest_tongji_row_count": int(len(latest_tongji)),
        "latest_indicator_fact_count": latest_indicator_count,
        "subjects_added_vs_previous": sorted(latest_subjects - previous_subjects),
        "subjects_removed_vs_previous": sorted(previous_subjects - latest_subjects),
        "historical_rows_unchanged": historical_equal,
        "authoritative_forward_subject_count": len(authoritative_subjects),
        "latest_authoritative_forward_subject_count": len(latest_subjects & authoritative_subjects),
        "fact_ranking_counts_by_year": fact_counts.to_dict("records"),
        "fact_indicator_counts_by_year": indicator_counts.to_dict("records"),
        "unmapped_latest_subjects": sorted(unmapped_latest_subjects),
        "unmapped_authoritative_forward_subjects": unmapped_authoritative_subjects,
        "unmapped_latest_tongji_subjects": latest_tongji.loc[latest_tongji["mapped_subject_count"].eq(0), "ranking_subject_raw"].tolist(),
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(OUTPUT_DIR / "arwu_2026_subject_mapping_coverage.csv", index=False, encoding="utf-8-sig")
    latest_tongji.to_csv(OUTPUT_DIR / "arwu_2026_tongji_records.csv", index=False, encoding="utf-8-sig")
    (OUTPUT_DIR / "arwu_source_upgrade_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 软科 2026 数据源接入审计",
        "",
        f"- 状态：{summary['status']}",
        f"- 当前源文件：{active_name}",
        f"- 实际工作表：{active_sheet}",
        f"- 总记录：{len(active)}；最新年 {latest_year}：{len(latest_source)}",
        f"- 最新年学科：{len(latest_subjects)}；同济记录：{len(latest_tongji)}",
        f"- 最新年分项指标事实：{latest_indicator_count}",
        f"- 历史 2021-2025 与上一版一致：{historical_equal}",
        "",
        "## 质量闸门",
        "",
    ]
    lines.extend(f"- {key}: {'pass' if value else 'fail'}" for key, value in checks.items())
    (OUTPUT_DIR / "arwu_source_upgrade_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
