from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import ranking_public_supplements as public_supplements


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
COVERAGE_CSV = PROJECT_DIR / "outputs" / "subject_coverage_audit" / "tongji_49_academic_degree_generation_coverage_after_supplement.csv"
DIM_ALIAS_CSV = PROJECT_DIR / "processed" / "dim_subject_alias.csv"
DIAGNOSTICS_CSV = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit" / "subject_49_mapping_gap_diagnostics.csv"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "subject_49_data_layer_audit"
RANKING_SOURCES = ["软科", "QS", "US News", "THE"]

SOURCE_FILE_PATTERNS = {
    "软科": ["软科世界一流学科排名"],
    "QS": ["QS世界学科排名", "QS世界大学学科排名"],
    "US News": ["US News世界学科排名"],
    "THE": ["THE世界学科排名"],
}

TARGET_UNIVERSITY_TOKENS = ["同济", "Tongji", "tongji"]


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


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def source_files(source: str) -> list[Path]:
    patterns = SOURCE_FILE_PATTERNS[source]
    files = []
    for path in DATA_DIR.glob("*.xlsx"):
        name = path.name
        if any(pattern in name for pattern in patterns):
            files.append(path)
    return sorted(files)


def subject_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "subject_id": clean_text(row.get("subject_id")),
        "target_subject": clean_text(row.get("source_subject_name") or row.get("ministry_subject_name")),
        "target_subject_code": clean_text(row.get("ministry_subject_code")).zfill(4),
        "ministry_subject_name": clean_text(row.get("ministry_subject_name")),
        "arwu_subject_name": clean_text(row.get("arwu_mapping")),
        "qs_subject_name": clean_text(row.get("qs_mapping")),
        "usnews_subject_name": clean_text(row.get("usnews_mapping")),
        "the_subject_area": clean_text(row.get("the_mapping")),
        "alias_summary": {},
    }


def load_alias_summary(alias_df: pd.DataFrame, subject: dict[str, Any]) -> dict[str, list[str]]:
    rows = alias_df[alias_df["subject_id"] == subject["subject_id"]].copy() if not alias_df.empty else pd.DataFrame()
    summary: dict[str, list[str]] = {}
    if not rows.empty:
        for source, group in rows.groupby("ranking_source"):
            values = sorted({clean_text(value) for value in group["ranking_subject_alias"].tolist() if clean_text(value)})
            if values:
                summary[clean_text(source)] = values
    if public_supplements.qs_proxy(subject):
        summary["QS"] = sorted(set(summary.get("QS", []) + public_supplements.qs_proxy_aliases(subject)))
    arwu_aliases = public_supplements.arwu_public_aliases(subject)
    if arwu_aliases:
        summary["软科"] = sorted(set(summary.get("软科", []) + arwu_aliases))
    for source in RANKING_SOURCES:
        aliases = public_supplements.source_aliases(subject, source)
        if aliases:
            summary[source] = sorted(set(summary.get(source, []) + aliases))
    return summary


def alias_values(subject: dict[str, Any], source: str) -> list[str]:
    field = {
        "软科": "arwu_subject_name",
        "QS": "qs_subject_name",
        "US News": "usnews_subject_name",
        "THE": "the_subject_area",
    }.get(source, "")
    values = set(subject.get("alias_summary", {}).get(source, []))
    values.add(subject.get("target_subject", ""))
    if field:
        values.add(subject.get(field, ""))
    rows = []
    seen = set()
    for value in values:
        text = public_supplements.valid_mapping_value(value)
        key = normalize_key(text)
        if key and key not in seen and len(key) >= 2:
            rows.append(text)
            seen.add(key)
    return sorted(rows, key=lambda x: (len(x), x), reverse=True)


def row_text_frame(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)
    safe = df.fillna("").astype(str)
    return safe.apply(lambda row: " | ".join(clean_text(value) for value in row.tolist() if clean_text(value)), axis=1)


def normalized_column_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", clean_text(value).lower())


def subject_columns(source: str, columns: list[Any]) -> list[Any]:
    """Return columns that describe the ranking subject itself.

    This deliberately excludes broad-area columns such as QS "学科领域" so the
    raw Excel verification cannot turn a broad faculty area into a fake subject
    ranking recovery.
    """
    exact_by_source = {
        "QS": {
            "学科",
            "学科中文",
            "学科英文",
            "subject",
            "subjectname",
            "subjectenglish",
            "subjecten",
            "rankingsubject",
        },
        "软科": {
            "学科",
            "学科名称",
            "学科中文",
            "学科英文",
            "subject",
            "subjectname",
            "grasfield",
        },
        "US News": {
            "学科",
            "学科名称",
            "学科中文",
            "学科英文",
            "subject",
            "subjectname",
            "category",
        },
        "THE": {
            "学科",
            "学科名称",
            "学科中文",
            "学科英文",
            "subject",
            "subjectname",
        },
    }
    excluded_tokens = {
        "学科领域",
        "领域",
        "门类",
        "area",
        "broadarea",
        "facultyarea",
        "categorygroup",
    }
    exact_names = exact_by_source.get(source, set())
    selected = []
    for column in columns:
        key = normalized_column_name(column)
        if not key:
            continue
        if key in excluded_tokens:
            continue
        if key in exact_names:
            selected.append(column)
    return selected


def selected_columns_text(df: pd.DataFrame, columns: list[Any]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)
    if not columns:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    safe = df.loc[:, columns].fillna("").astype(str)
    return safe.apply(lambda row: " | ".join(clean_text(value) for value in row.tolist() if clean_text(value)), axis=1)


def match_alias(text: str, aliases: list[str]) -> str:
    text_key = normalize_key(text)
    for alias in aliases:
        alias_key = normalize_key(alias)
        if alias_key and (alias_key in text_key or clean_text(alias).lower() in text.lower()):
            return alias
    return ""


def load_source_tongji_rows(source: str) -> pd.DataFrame:
    cache_rows: list[dict[str, Any]] = []
    for path in source_files(source):
        try:
            sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        except Exception as exc:
            cache_rows.append(
                {
                    "source": source,
                    "file": path.name,
                    "sheet": "",
                    "status": f"read_error_{type(exc).__name__}",
                    "row_text": "",
                }
            )
            continue
        for sheet_name, df in sheets.items():
            if df.empty:
                continue
            row_text = row_text_frame(df)
            subject_col_names = subject_columns(source, list(df.columns))
            subject_text = selected_columns_text(df, subject_col_names)
            if row_text.empty:
                continue
            tongji_mask = row_text.map(lambda text: any(token.lower() in text.lower() for token in TARGET_UNIVERSITY_TOKENS))
            for index, text in row_text[tongji_mask].items():
                subject_only_text = clean_text(subject_text.get(index, ""))
                cache_rows.append(
                    {
                        "source": source,
                        "file": path.name,
                        "sheet": str(sheet_name),
                        "status": "loaded",
                        "subject_columns": " | ".join(clean_text(column) for column in subject_col_names),
                        "subject_text": subject_only_text,
                        "match_text": subject_only_text or clean_text(text),
                        "match_scope": "subject_columns" if subject_only_text else "row_text_fallback",
                        "row_text": clean_text(text),
                    }
                )
    return pd.DataFrame(cache_rows)


def scan_source_subject(source_rows: pd.DataFrame, source: str, subject: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = alias_values(subject, source)
    if not aliases or source_rows.empty:
        return []
    matches: list[dict[str, Any]] = []
    for (file_name, sheet_name), group in source_rows.groupby(["file", "sheet"]):
        match_text = group["match_text"].fillna("").astype(str)
        alias_hits = match_text.map(lambda text: match_alias(text, aliases))
        hit_rows = group.loc[alias_hits.astype(str).str.len() > 0].copy()
        if hit_rows.empty:
            continue
        matched_aliases = sorted({alias for alias in alias_hits.tolist() if alias})
        match_scopes = sorted({clean_text(value) for value in hit_rows.get("match_scope", pd.Series(dtype=str)).tolist() if clean_text(value)})
        matches.append(
            {
                "source": source,
                "file": file_name,
                "sheet": sheet_name,
                "status": "matched",
                "raw_tongji_alias_rows": len(hit_rows),
                "matched_aliases": " | ".join(matched_aliases[:12]),
                "match_scope": " | ".join(match_scopes),
                "subject_columns": clean_text(hit_rows.iloc[0].get("subject_columns", "")),
                "sample_subject_text": clean_text(hit_rows.iloc[0].get("subject_text", ""))[:500],
                "sample_row_text": clean_text(hit_rows.iloc[0].get("row_text", ""))[:1000],
            }
        )
    return matches


def verify() -> dict[str, Any]:
    coverage = read_csv(COVERAGE_CSV)
    aliases = read_csv(DIM_ALIAS_CSV)
    diagnostics = read_csv(DIAGNOSTICS_CSV)
    if diagnostics.empty:
        raise FileNotFoundError(f"missing diagnostics: {DIAGNOSTICS_CSV}")

    check_keys = diagnostics[diagnostics["diagnosis"].isin(["weight_only_no_local_ranking_fact", "no_local_weight_or_ranking_fact"])].copy()
    subject_lookup = {}
    for _, row in coverage.iterrows():
        subject = subject_from_row(row)
        subject["alias_summary"] = load_alias_summary(aliases, subject)
        subject_lookup[(subject["target_subject_code"], subject["target_subject"])] = subject
    source_row_cache = {source: load_source_tongji_rows(source) for source in RANKING_SOURCES}
    cache_summary = []
    for source, df in source_row_cache.items():
        cache_summary.append({"ranking_source": source, "tongji_raw_rows": len(df)})
    pd.DataFrame(cache_summary).to_csv(OUTPUT_DIR / "subject_49_raw_excel_tongji_row_cache_summary.csv", index=False, encoding="utf-8-sig")

    rows: list[dict[str, Any]] = []
    for _, gap in check_keys.iterrows():
        key = (clean_text(gap.get("ministry_subject_code")).zfill(4), clean_text(gap.get("subject_name")))
        subject = subject_lookup.get(key)
        if not subject:
            continue
        source = clean_text(gap.get("ranking_source"))
        source_matches = scan_source_subject(source_row_cache.get(source, pd.DataFrame()), source, subject)
        if not source_matches:
            rows.append(
                {
                    "ministry_subject_code": subject["target_subject_code"],
                    "subject_name": subject["target_subject"],
                    "ranking_source": source,
                    "diagnosis_before_raw_scan": clean_text(gap.get("diagnosis")),
                    "raw_scan_status": "no_raw_tongji_alias_match",
                    "file": "",
                    "sheet": "",
                    "raw_tongji_alias_rows": 0,
                    "matched_aliases": "",
                    "match_scope": "",
                    "subject_columns": "",
                    "sample_subject_text": "",
                    "sample_row_text": "",
                }
            )
            continue
        for match in source_matches:
            rows.append(
                {
                    "ministry_subject_code": subject["target_subject_code"],
                    "subject_name": subject["target_subject"],
                    "ranking_source": source,
                    "diagnosis_before_raw_scan": clean_text(gap.get("diagnosis")),
                    "raw_scan_status": match["status"],
                    "file": match["file"],
                    "sheet": match["sheet"],
                    "raw_tongji_alias_rows": match["raw_tongji_alias_rows"],
                    "matched_aliases": match["matched_aliases"],
                    "match_scope": match["match_scope"],
                    "subject_columns": match["subject_columns"],
                    "sample_subject_text": match["sample_subject_text"],
                    "sample_row_text": match["sample_row_text"],
                }
            )
    out = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = OUTPUT_DIR / "subject_49_raw_excel_gap_verification.csv"
    out.to_csv(detail_path, index=False, encoding="utf-8-sig")
    raw_recoveries = out[out["raw_scan_status"] == "matched"].copy() if not out.empty else pd.DataFrame()
    recovery_path = OUTPUT_DIR / "subject_49_raw_excel_possible_recoveries.csv"
    raw_recoveries.to_csv(recovery_path, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at": now_text(),
        "checked_gap_rows": int(len(check_keys)),
        "raw_scan_rows": int(len(out)),
        "raw_recovery_rows": int(len(raw_recoveries)),
        "raw_recovery_subject_source_count": int(raw_recoveries[["ministry_subject_code", "subject_name", "ranking_source"]].drop_duplicates().shape[0]) if not raw_recoveries.empty else 0,
        "detail_csv": str(detail_path),
        "raw_recovery_csv": str(recovery_path),
    }
    (OUTPUT_DIR / "subject_49_raw_excel_gap_verification_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    verify()
