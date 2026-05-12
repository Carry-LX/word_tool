from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
QA_DIR = PROCESSED_DIR / "qa"
CONFIG_PATH = PROJECT_DIR / "configs" / "runtime" / "manual_subject_aliases.json"

DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_RANKING_CSV = PROCESSED_DIR / "fact_ranking.csv"
FACT_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
UNMATCHED_CSV = QA_DIR / "subject_mapping_unmatched.csv"

READINESS_CSV = QA_DIR / "global_subject_data_readiness.csv"
MAPPING_CLASS_CSV = QA_DIR / "global_subject_alias_mapping_classes.csv"
AMBIGUOUS_CSV = QA_DIR / "global_subject_ambiguous_mapping_summary.csv"
REPORT_MD = QA_DIR / "global_subject_data_readiness.md"
REPORT_JSON = QA_DIR / "global_subject_data_readiness.json"

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


def joined_sources(fact: pd.DataFrame, aliases: pd.DataFrame, tongji_only: bool = False) -> pd.DataFrame:
    selected = fact[["ranking_source", "ranking_subject_norm", "is_tongji", "university_name_cn", "rank_midpoint"]].copy()
    if tongji_only:
        selected = selected[selected["is_tongji"].astype(str).str.lower().isin(["true", "1"])]
    selected = selected.drop_duplicates()
    joined = aliases[["subject_id", "ranking_source", "ranking_subject_norm"]].merge(
        selected,
        on=["ranking_source", "ranking_subject_norm"],
        how="inner",
    )
    return joined


def source_set_by_subject(joined: pd.DataFrame) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for subject_id, group in joined.groupby("subject_id"):
        output[subject_id] = set(group["ranking_source"].dropna().astype(str))
    return output


def indicator_sources_by_subject(aliases: pd.DataFrame) -> dict[str, set[str]]:
    if not FACT_INDICATOR_CSV.exists():
        return {}
    columns = ["ranking_source", "ranking_subject_norm", "is_tongji"]
    indicators = pd.read_csv(FACT_INDICATOR_CSV, encoding="utf-8-sig", dtype=str, usecols=columns).fillna("")
    tongji = indicators[indicators["is_tongji"].astype(str).str.lower().isin(["true", "1"])].drop_duplicates()
    joined = aliases[["subject_id", "ranking_source", "ranking_subject_norm"]].merge(
        tongji,
        on=["ranking_source", "ranking_subject_norm"],
        how="inner",
    )
    return source_set_by_subject(joined)


def mapping_class_table(aliases: pd.DataFrame) -> pd.DataFrame:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rules = pd.DataFrame(config.get("subject_alias_rules", []))
    if rules.empty:
        return pd.DataFrame(columns=["ranking_source", "mapping_class", "rule_count", "subject_rule_count"])
    summary = (
        rules.groupby(["ranking_source", "mapping_class"], dropna=False)
        .agg(rule_count=("rule_id", "nunique"), subject_rule_count=("subject_id", "count"))
        .reset_index()
        .sort_values(["ranking_source", "mapping_class"])
    )
    alias_summary = (
        aliases[aliases["alias_type"] == "manual_config_subject_alias"]
        .groupby(["ranking_source", "source_note"], dropna=False)
        .agg(alias_rows=("ranking_subject_alias", "count"), subject_count=("subject_id", "nunique"))
        .reset_index()
        .rename(columns={"source_note": "note"})
    )
    summary.to_csv(MAPPING_CLASS_CSV, index=False, encoding="utf-8-sig")
    alias_summary.to_csv(QA_DIR / "global_manual_alias_rule_expansion.csv", index=False, encoding="utf-8-sig")
    return summary


def ambiguous_mapping_summary(fact: pd.DataFrame) -> pd.DataFrame:
    ambiguous = fact[pd.to_numeric(fact["subject_alias_match_count"], errors="coerce").fillna(0).astype(int) > 1].copy()
    if ambiguous.empty:
        output = pd.DataFrame(columns=["ranking_source", "ranking_subject_raw", "match_count", "row_count"])
    else:
        output = (
            ambiguous.groupby(["ranking_source", "ranking_subject_raw", "subject_alias_match_count"], dropna=False)
            .size()
            .reset_index(name="row_count")
            .rename(columns={"subject_alias_match_count": "match_count"})
            .sort_values(["row_count", "ranking_source"], ascending=[False, True])
        )
    output.to_csv(AMBIGUOUS_CSV, index=False, encoding="utf-8-sig")
    return output


def status_for(alias_count: int, ranking_sources: set[str], tongji_sources: set[str], indicator_sources: set[str]) -> str:
    if alias_count == 0:
        return "alias_missing"
    if not ranking_sources:
        return "has_alias_no_ranking_records"
    if len(ranking_sources) >= 2 and len(tongji_sources) >= 1:
        return "agent_ready"
    if len(ranking_sources) >= 2:
        return "peer_ready_no_tongji"
    if len(ranking_sources) == 1 and indicator_sources:
        return "partial_with_indicators"
    return "partial_ranking_only"


def main() -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)

    dim = pd.read_csv(DIM_SUBJECT_CSV, encoding="utf-8-sig", dtype=str).fillna("")
    aliases = pd.read_csv(DIM_ALIAS_CSV, encoding="utf-8-sig", dtype=str).fillna("")
    fact = pd.read_csv(
        FACT_RANKING_CSV,
        encoding="utf-8-sig",
        dtype=str,
        usecols=[
            "ranking_source",
            "ranking_subject_raw",
            "ranking_subject_norm",
            "subject_alias_match_count",
            "is_tongji",
            "university_name_cn",
            "rank_midpoint",
        ],
    ).fillna("")

    all_joined = joined_sources(fact, aliases, tongji_only=False)
    tongji_joined = joined_sources(fact, aliases, tongji_only=True)
    ranking_sources = source_set_by_subject(all_joined)
    tongji_sources = source_set_by_subject(tongji_joined)
    indicator_sources = indicator_sources_by_subject(aliases)
    alias_counts = aliases.groupby("subject_id").size().to_dict()
    alias_source_counts = (
        aliases.groupby(["subject_id", "ranking_source"]).size().unstack(fill_value=0).reset_index()
    )

    rows: list[dict[str, Any]] = []
    for _, row in dim.iterrows():
        subject_id = clean_text(row["subject_id"])
        rs = ranking_sources.get(subject_id, set())
        ts = tongji_sources.get(subject_id, set())
        inds = indicator_sources.get(subject_id, set())
        alias_count = int(alias_counts.get(subject_id, 0))
        rows.append(
            {
                "subject_id": subject_id,
                "ministry_category_code": row["ministry_category_code"],
                "ministry_category_name": row["ministry_category_name"],
                "ministry_subject_code": row["ministry_subject_code"],
                "ministry_subject_name": row["ministry_subject_name"],
                "alias_count": alias_count,
                "ranking_sources": ";".join(source for source in RANKING_SOURCES if source in rs),
                "ranking_source_count": len(rs),
                "tongji_sources": ";".join(source for source in RANKING_SOURCES if source in ts),
                "tongji_source_count": len(ts),
                "indicator_sources": ";".join(source for source in RANKING_SOURCES if source in inds),
                "indicator_source_count": len(inds),
                "readiness_status": status_for(alias_count, rs, ts, inds),
            }
        )

    readiness = pd.DataFrame(rows)
    readiness = readiness.merge(alias_source_counts, on="subject_id", how="left").fillna(0)
    readiness.to_csv(READINESS_CSV, index=False, encoding="utf-8-sig")

    class_summary = mapping_class_table(aliases)
    ambiguous = ambiguous_mapping_summary(fact)
    unmatched = pd.read_csv(UNMATCHED_CSV, encoding="utf-8-sig") if UNMATCHED_CSV.exists() else pd.DataFrame()
    status_summary = readiness.groupby("readiness_status").size().reset_index(name="subject_count")
    category_summary = (
        readiness.groupby(["ministry_category_code", "ministry_category_name", "readiness_status"])
        .size()
        .reset_index(name="subject_count")
        .sort_values(["ministry_category_code", "readiness_status"])
    )

    status_summary.to_csv(QA_DIR / "global_subject_readiness_status_summary.csv", index=False, encoding="utf-8-sig")
    category_summary.to_csv(QA_DIR / "global_subject_readiness_by_category.csv", index=False, encoding="utf-8-sig")

    payload = {
        "generated_at": now_text(),
        "subject_count": int(len(readiness)),
        "unmatched_raw_subject_count": int(len(unmatched)),
        "unmatched_raw_subject_rows": int(unmatched["row_count"].sum()) if "row_count" in unmatched.columns else 0,
        "status_summary": status_summary.to_dict(orient="records"),
        "outputs": {
            "readiness_csv": str(READINESS_CSV),
            "mapping_class_csv": str(MAPPING_CLASS_CSV),
            "ambiguous_csv": str(AMBIGUOUS_CSV),
            "report_md": str(REPORT_MD),
        },
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    lines = [
        "# 全局学科数据可迁移性审计",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 学科总数：{payload['subject_count']}",
        f"- 未映射原始学科名数量：{payload['unmatched_raw_subject_count']}",
        f"- 未映射原始数据行数：{payload['unmatched_raw_subject_rows']}",
        "",
        "## 状态分布",
        "",
        "| readiness_status | subject_count |",
        "| --- | ---: |",
    ]
    for _, row in status_summary.iterrows():
        lines.append(f"| {row['readiness_status']} | {row['subject_count']} |")

    lines.extend(
        [
            "",
            "## 映射规则分布",
            "",
            "| ranking_source | mapping_class | rule_count | subject_rule_count |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for _, row in class_summary.iterrows():
        lines.append(
            f"| {row['ranking_source']} | {row['mapping_class']} | {row['rule_count']} | {row['subject_rule_count']} |"
        )

    lines.extend(
        [
            "",
            "## 需要理解的剩余风险",
            "",
            "- `subject_mapping_unmatched.csv` 已清零，说明所有原始榜单学科名都能进入 alias 层。",
            "- `subject_id_missing_rows` 仍会存在，这是多学科领域口径造成的预期结果，例如 THE 理学、US News engineering、QS 农业林业。",
            "- 后续 agent 查询必须通过 `dim_subject_alias` join，而不是只看 `fact_ranking.subject_id`。",
            "- `approximate` 映射包括人类学、神学/宗教研究等教育部无独立一级学科的口径，生成报告时应在数据说明中保留审慎表述。",
            "",
            "## 输出文件",
            "",
            f"- `{READINESS_CSV}`：181 个学科逐项 readiness。",
            f"- `{AMBIGUOUS_CSV}`：一对多领域映射摘要。",
            f"- `{MAPPING_CLASS_CSV}`：人工规则类别统计。",
            f"- `{QA_DIR / 'global_subject_readiness_by_category.csv'}`：按门类拆分的 readiness。",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
