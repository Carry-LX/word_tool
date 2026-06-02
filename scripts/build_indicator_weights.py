from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
QA_DIR = PROCESSED_DIR / "qa" / "indicator_weights"
LOG_DIR = PROJECT_DIR / "logs"

WEIGHT_FILE = next(
    path.name
    for path in DATA_DIR.glob("*.xlsx")
    if path.name.startswith("\u56db\u5927") and "\u6743\u91cd" in path.name
)
SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"

FACT_INDICATOR_WEIGHT_CSV = PROCESSED_DIR / "fact_indicator_weight.csv"
DIM_INDICATOR_CSV = PROCESSED_DIR / "dim_indicator.csv"
RUN_LOG = LOG_DIR / "indicator_weight_run_log.md"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text


def as_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"不适用", "NA", "N/A", "-"}:
        return None
    try:
        return float(text)
    except Exception:
        return None


def to_percent(value: float | None) -> float | None:
    if value is None:
        return None
    if 0 <= value <= 1:
        return value * 100
    return value


def indicator_group_for(source: str, indicator_name: str, raw_group: str = "") -> str:
    text = normalize_key(indicator_name + raw_group)
    if any(key in text for key in ["声誉", "reputation", "雇主"]):
        return "声誉"
    if any(key in text for key in ["国际", "international", "irn", "合作"]):
        return "国际化/合作"
    if any(key in text for key in ["教学", "teaching", "环境"]):
        return "教学/环境"
    if any(key in text for key in ["商业", "产业", "收入", "转化", "industry"]):
        return "产业/转化"
    if any(key in text for key in ["论文", "引用", "出版", "高被引", "h指数", "h-index", "citation", "publications", "research", "科研", "成果", "期刊", "图书", "会议", "cnci"]):
        return "科研/论文"
    if any(key in text for key in ["教师", "校友", "获奖", "award"]):
        return "人才/奖项"
    return raw_group or "其他"


def record(
    ranking_source: str,
    ranking_subject_or_area: str,
    indicator_name: str,
    weight_value: float | None,
    source_sheet: str,
    source_row: int,
    raw_group: str = "",
    raw_indicator_name: str = "",
    notes: str = "",
    indicator_level: str = "指标",
) -> dict[str, Any]:
    percent = to_percent(weight_value)
    return {
        "ranking_source": ranking_source,
        "ranking_subject_or_area": ranking_subject_or_area,
        "ranking_subject_norm": normalize_key(ranking_subject_or_area),
        "indicator_name": indicator_name,
        "indicator_norm": normalize_key(indicator_name),
        "indicator_group": indicator_group_for(ranking_source, indicator_name, raw_group),
        "indicator_level": indicator_level,
        "raw_group": raw_group,
        "raw_indicator_name": raw_indicator_name or indicator_name,
        "weight_raw": weight_value,
        "weight_percent": percent,
        "source_file": WEIGHT_FILE,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "notes": notes,
    }


def parse_arwu() -> list[dict[str, Any]]:
    raw = pd.read_excel(DATA_DIR / WEIGHT_FILE, sheet_name="软科", header=None, dtype=object)
    records: list[dict[str, Any]] = []
    group_row = raw.iloc[0].tolist()
    indicator_row = raw.iloc[1].tolist()
    indicator_cols = list(range(2, 11))
    for row_idx in range(2, len(raw)):
        row = raw.iloc[row_idx]
        subject_area = clean_text(row.iloc[0])
        subject_name = clean_text(row.iloc[1])
        if not subject_name:
            continue
        total = as_float(row.iloc[11]) if len(row) > 11 else None
        for col_idx in indicator_cols:
            indicator_name = clean_text(indicator_row[col_idx])
            raw_group = clean_text(group_row[col_idx])
            value = as_float(row.iloc[col_idx])
            if not indicator_name or value is None:
                continue
            percent = value / total * 100 if total else value
            records.append(
                record(
                    ranking_source="软科",
                    ranking_subject_or_area=subject_name,
                    indicator_name=indicator_name,
                    weight_value=percent,
                    source_sheet="软科",
                    source_row=row_idx + 1,
                    raw_group=raw_group,
                    notes=f"原始权重={value}; 合计={total}; 已归一为百分比",
                    indicator_level="二级指标",
                )
            )
    return records


def parse_usnews() -> list[dict[str, Any]]:
    df = pd.read_excel(DATA_DIR / WEIGHT_FILE, sheet_name="usnews", dtype=object)
    df.columns = [clean_text(column) for column in df.columns]
    records: list[dict[str, Any]] = []
    area_column = df.columns[0]
    subject_column = df.columns[1]
    indicator_cols = [column for column in df.columns[2:] if clean_text(column)]
    last_area = ""
    last_weights: dict[str, float] = {}
    for idx, row in df.iterrows():
        raw_area = clean_text(row.get(area_column))
        area = raw_area or last_area
        if raw_area:
            last_area = raw_area
        subject = clean_text(row.get(subject_column))
        if not subject:
            continue
        row_weights = {column: as_float(row.get(column)) for column in indicator_cols}
        numeric_weights = {column: value for column, value in row_weights.items() if value is not None}
        if numeric_weights:
            last_weights = numeric_weights
        weights_to_use = numeric_weights or last_weights
        for column in indicator_cols:
            value = weights_to_use.get(column)
            if value is None:
                continue
            records.append(
                record(
                    ranking_source="US News",
                    ranking_subject_or_area=subject,
                    indicator_name=column,
                    weight_value=value,
                    source_sheet="usnews",
                    source_row=idx + 2,
                    raw_group=area,
                    raw_indicator_name=column,
                    notes="同一 US News 权重组内空白学科行继承上一条非空权重模板。" if not numeric_weights else "",
                    indicator_level="二级指标",
                )
            )
    return records


def parse_the() -> list[dict[str, Any]]:
    raw = pd.read_excel(DATA_DIR / WEIGHT_FILE, sheet_name="the", header=None, dtype=object)
    records: list[dict[str, Any]] = []
    subject_headers = {col: clean_text(raw.iloc[0, col]) for col in range(4, raw.shape[1]) if clean_text(raw.iloc[0, col])}
    for row_idx in range(2, len(raw)):
        row = raw.iloc[row_idx]
        group = clean_text(row.iloc[1])
        second_level = clean_text(row.iloc[2])
        indicator = second_level or group
        if not group and not indicator:
            continue
        indicator_level = "一级指标" if not second_level else "二级指标"
        for col_idx, subject_area in subject_headers.items():
            value = as_float(row.iloc[col_idx])
            if value is None:
                continue
            records.append(
                record(
                    ranking_source="THE",
                    ranking_subject_or_area=subject_area,
                    indicator_name=indicator,
                    weight_value=value,
                    source_sheet="the",
                    source_row=row_idx + 1,
                    raw_group=group,
                    indicator_level=indicator_level,
                )
            )
    return records


def parse_qs() -> list[dict[str, Any]]:
    raw = pd.read_excel(DATA_DIR / WEIGHT_FILE, sheet_name="QS", header=None, dtype=object)
    header = [clean_text(value) for value in raw.iloc[1].tolist()]
    records: list[dict[str, Any]] = []
    indicator_cols = []
    for name in ["学术声誉", "雇主声誉", "篇均被引", "H指数", "IRN"]:
        if name in header:
            indicator_cols.append((header.index(name), name))
    for row_idx in range(2, len(raw)):
        row = raw.iloc[row_idx]
        subject_name = clean_text(row.iloc[3])
        if not subject_name:
            continue
        area = clean_text(row.iloc[0])
        for col_idx, indicator_name in indicator_cols:
            value = as_float(row.iloc[col_idx])
            if value is None:
                continue
            records.append(
                record(
                    ranking_source="QS",
                    ranking_subject_or_area=subject_name,
                    indicator_name=indicator_name,
                    weight_value=to_percent(value),
                    source_sheet="QS",
                    source_row=row_idx + 1,
                    raw_group=area,
                    indicator_level="一级指标",
                )
            )
    return records


def build_weights() -> pd.DataFrame:
    records = []
    records.extend(parse_arwu())
    records.extend(parse_usnews())
    records.extend(parse_the())
    records.extend(parse_qs())
    df = pd.DataFrame(records)
    df.insert(0, "weight_id", [f"weight_{idx + 1:06d}" for idx in range(len(df))])
    return df


def build_dim_indicator(weights: pd.DataFrame) -> pd.DataFrame:
    dim = (
        weights[["ranking_source", "indicator_name", "indicator_norm", "indicator_group"]]
        .drop_duplicates()
        .sort_values(["ranking_source", "indicator_group", "indicator_name"])
        .reset_index(drop=True)
    )
    dim.insert(0, "indicator_id", [f"indicator_{idx + 1:04d}" for idx in range(len(dim))])
    return dim


def write_sqlite(weights: pd.DataFrame, dim_indicator: pd.DataFrame) -> None:
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS fact_indicator_weight")
        conn.execute("DROP TABLE IF EXISTS dim_indicator")
        dim_indicator.to_sql("dim_indicator", conn, index=False)
        weights.to_sql("fact_indicator_weight", conn, index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_indicator_weight_source_subject ON fact_indicator_weight(ranking_source, ranking_subject_norm)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_indicator_weight_indicator ON fact_indicator_weight(ranking_source, indicator_norm)")


def qa_reports(weights: pd.DataFrame, dim_indicator: pd.DataFrame) -> dict[str, Any]:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    by_source = weights.groupby("ranking_source").size().to_dict()
    totals_base = weights[
        ((weights["ranking_source"] == "THE") & (weights["indicator_level"] == "一级指标"))
        | (weights["ranking_source"] != "THE")
    ].copy()
    totals = (
        totals_base.groupby(["ranking_source", "ranking_subject_or_area"], dropna=False)["weight_percent"]
        .sum()
        .reset_index(name="weight_percent_sum")
        .sort_values(["ranking_source", "ranking_subject_or_area"])
    )
    totals.to_csv(QA_DIR / "indicator_weight_totals.csv", index=False, encoding="utf-8-sig")

    suspicious = totals[
        (totals["weight_percent_sum"] < 95)
        | (totals["weight_percent_sum"] > 105)
    ].copy()
    suspicious.to_csv(QA_DIR / "indicator_weight_total_exceptions.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "fact_indicator_weight_rows": int(len(weights)),
        "dim_indicator_rows": int(len(dim_indicator)),
        "rows_by_source": by_source,
        "subject_or_area_count_by_source": weights.groupby("ranking_source")["ranking_subject_or_area"].nunique().to_dict(),
        "total_exception_rows": int(len(suspicious)),
        "outputs": {
            "fact_indicator_weight": str(FACT_INDICATOR_WEIGHT_CSV),
            "dim_indicator": str(DIM_INDICATOR_CSV),
            "indicator_weight_totals": str(QA_DIR / "indicator_weight_totals.csv"),
            "indicator_weight_total_exceptions": str(QA_DIR / "indicator_weight_total_exceptions.csv"),
        },
    }
    (QA_DIR / "indicator_weight_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# 指标权重结构化 QA",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- fact_indicator_weight 行数：{summary['fact_indicator_weight_rows']}",
        f"- dim_indicator 行数：{summary['dim_indicator_rows']}",
        f"- 权重合计异常行数：{summary['total_exception_rows']}",
        "",
        "## rows by source",
        "",
    ]
    for source, count in by_source.items():
        lines.append(f"- {source}: {count}")
    lines.extend(["", "## subject/area count by source", ""])
    for source, count in summary["subject_or_area_count_by_source"].items():
        lines.append(f"- {source}: {count}")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 软科原始表权重合计不是100，本脚本按每个学科原始合计归一到百分比。",
            "- QS和THE原始权重多为0-1小数，本脚本转换为百分比。",
            "- US News原始权重一般已经是百分比。",
        ]
    )
    (QA_DIR / "indicator_weight_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def append_run_log(summary: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# 指标权重过程留档\n", encoding="utf-8", newline="\n")
    lines = [
        "",
        f"## {summary['generated_at']} indicator weights",
        "",
        "### 目标",
        "",
        "结构化清洗四大世界学科排名指标权重，生成 `fact_indicator_weight` 与 `dim_indicator`。",
        "",
        "### 输入",
        "",
        f"- `{DATA_DIR / WEIGHT_FILE}`",
        "",
        "### 输出",
        "",
        f"- `{FACT_INDICATOR_WEIGHT_CSV}`",
        f"- `{DIM_INDICATOR_CSV}`",
        f"- `{QA_DIR / 'indicator_weight_summary.md'}`",
        "",
        "### 核验摘要",
        "",
        f"- fact_indicator_weight 行数：{summary['fact_indicator_weight_rows']}",
        f"- dim_indicator 行数：{summary['dim_indicator_rows']}",
        f"- 权重合计异常行数：{summary['total_exception_rows']}",
        "",
    ]
    with RUN_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    weights = build_weights()
    dim_indicator = build_dim_indicator(weights)
    weights.to_csv(FACT_INDICATOR_WEIGHT_CSV, index=False, encoding="utf-8-sig")
    dim_indicator.to_csv(DIM_INDICATOR_CSV, index=False, encoding="utf-8-sig")
    write_sqlite(weights, dim_indicator)
    summary = qa_reports(weights, dim_indicator)
    append_run_log(summary)
    print((QA_DIR / "indicator_weight_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
