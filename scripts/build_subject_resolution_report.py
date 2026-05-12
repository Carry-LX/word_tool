from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_DIR / "processed"
QA_DIR = PROCESSED_DIR / "qa" / "subject_resolution"
LOG_DIR = PROJECT_DIR / "logs"

DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_SUBJECT_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_RANKING_CSV = PROCESSED_DIR / "fact_ranking.csv"
SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
MANUAL_ALIASES_PATH = PROJECT_DIR / "configs" / "runtime" / "manual_subject_aliases.json"

RUN_LOG = LOG_DIR / "subject_resolution_run_log.md"

RANKING_SOURCES = ["软科", "QS", "US News", "THE"]
TARGET_UNIVERSITY = "同济大学"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def has_value(value: Any) -> bool:
    return bool(clean_text(value))


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dim_subject = pd.read_csv(DIM_SUBJECT_CSV, dtype=str).fillna("")
    dim_alias = pd.read_csv(DIM_SUBJECT_ALIAS_CSV, dtype=str).fillna("")
    fact_ranking = pd.read_csv(FACT_RANKING_CSV, dtype=str).fillna("")
    return dim_subject, dim_alias, fact_ranking


def load_manual_config() -> dict[str, Any]:
    if not MANUAL_ALIASES_PATH.exists():
        return {"confirmed_no_mapping": []}
    return json.loads(MANUAL_ALIASES_PATH.read_text(encoding="utf-8"))


def confirmed_no_mapping_set(manual_config: dict[str, Any]) -> set[tuple[str, str]]:
    result = set()
    for item in manual_config.get("confirmed_no_mapping", []):
        subject = clean_text(item.get("subject_name"))
        source = clean_text(item.get("ranking_source"))
        if subject and source:
            result.add((subject, source))
    return result


def tongji_subjects(dim_subject: pd.DataFrame) -> pd.DataFrame:
    markers = [
        "tongji_college",
        "tongji_academic_degree",
        "tongji_professional_degree",
        "tongji_undergraduate_major",
        "tongji_round5_result",
        "tongji_is_double_first_class",
        "tongji_shanghai_peak_plateau",
        "tongji_arwu_subject",
        "tongji_qs_subject",
        "tongji_usnews_subject",
        "tongji_the_area",
    ]
    existing = [column for column in markers if column in dim_subject.columns]
    mask = dim_subject[existing].apply(lambda row: any(has_value(value) for value in row), axis=1)
    return dim_subject[mask].copy()


def build_reports(dim_subject: pd.DataFrame, dim_alias: pd.DataFrame, fact_ranking: pd.DataFrame) -> dict[str, Any]:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    manual_config = load_manual_config()
    confirmed_no_mapping = confirmed_no_mapping_set(manual_config)
    subjects = tongji_subjects(dim_subject)

    fact_ranking["release_year_num"] = pd.to_numeric(fact_ranking["release_year"], errors="coerce")
    fact_ranking["ranking_year_num"] = pd.to_numeric(fact_ranking["ranking_year"], errors="coerce")
    fact_ranking["rank_midpoint_num"] = pd.to_numeric(fact_ranking["rank_midpoint"], errors="coerce")

    rows = []
    issue_rows = []
    latest_rows = []

    for _, subject in subjects.iterrows():
        subject_id = subject["subject_id"]
        subject_alias = dim_alias[dim_alias["subject_id"] == subject_id].copy()
        for source in RANKING_SOURCES:
            aliases = subject_alias[subject_alias["ranking_source"] == source].copy()
            alias_norms = sorted(set(aliases["ranking_subject_norm"]))
            alias_names = sorted(set(aliases["ranking_subject_alias"]))

            facts = fact_ranking[
                (fact_ranking["ranking_source"] == source)
                & (fact_ranking["ranking_subject_norm"].isin(alias_norms))
            ].copy()
            tongji_facts = facts[facts["is_tongji"].astype(str).str.lower().isin(["true", "1"])].copy()
            mainland_facts = facts[facts["is_mainland_china"].astype(str).str.lower().isin(["true", "1"])].copy()

            if not tongji_facts.empty:
                tongji_sorted = tongji_facts.sort_values(["release_year_num", "ranking_year_num"], na_position="first")
                latest = tongji_sorted.tail(1).iloc[0].to_dict()
                latest_rows.append(
                    {
                        "subject_id": subject_id,
                        "ministry_subject_code": subject["ministry_subject_code"],
                        "ministry_subject_name": subject["ministry_subject_name"],
                        "ranking_source": source,
                        "ranking_subject_raw": latest.get("ranking_subject_raw", ""),
                        "release_year": latest.get("release_year", ""),
                        "ranking_year": latest.get("ranking_year", ""),
                        "rank_raw": latest.get("rank_raw", ""),
                        "rank_midpoint": latest.get("rank_midpoint", ""),
                        "total_score": latest.get("total_score", ""),
                        "source_file": latest.get("source_file", ""),
                        "source_sheet": latest.get("source_sheet", ""),
                        "source_row": latest.get("source_row", ""),
                    }
                )

            if (subject["ministry_subject_name"], source) in confirmed_no_mapping:
                status = "confirmed_no_mapping"
            elif not alias_norms:
                status = "source_not_applicable"
            elif tongji_facts.empty and facts.empty:
                status = "has_alias_no_ranking_records"
            elif tongji_facts.empty:
                status = "has_peer_records_no_tongji"
            else:
                status = "ok"

            area_mapping = False
            if source == "THE" and not aliases.empty:
                area_mapping = aliases["alias_type"].str.contains("the_area|manual_the_area_alias", regex=True, na=False).any()

            row = {
                "subject_id": subject_id,
                "ministry_subject_code": subject["ministry_subject_code"],
                "ministry_subject_name": subject["ministry_subject_name"],
                "tongji_college": subject.get("tongji_college", ""),
                "ranking_source": source,
                "status": status,
                "alias_count": len(alias_norms),
                "aliases": "；".join(alias_names),
                "is_area_mapping": area_mapping,
                "ranking_record_count": len(facts),
                "tongji_record_count": len(tongji_facts),
                "mainland_record_count": len(mainland_facts),
                "latest_release_year": "" if tongji_facts.empty else str(latest_rows[-1]["release_year"]),
                "latest_rank_raw": "" if tongji_facts.empty else str(latest_rows[-1]["rank_raw"]),
            }
            rows.append(row)

            if status not in {"ok", "confirmed_no_mapping", "source_not_applicable"}:
                issue_rows.append(
                    {
                        **row,
                        "issue_type": status,
                        "suggested_action": suggested_action(status, source),
                    }
                )

    resolution = pd.DataFrame(rows)
    issues = pd.DataFrame(issue_rows)
    latest = pd.DataFrame(latest_rows)

    resolution.to_csv(QA_DIR / "subject_resolution_matrix.csv", index=False, encoding="utf-8-sig")
    issues.to_csv(QA_DIR / "subject_resolution_issues.csv", index=False, encoding="utf-8-sig")
    latest.to_csv(QA_DIR / "subject_latest_tongji_rankings.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "tongji_subject_count": int(len(subjects)),
        "resolution_rows": int(len(resolution)),
        "status_counts": resolution["status"].value_counts().to_dict() if not resolution.empty else {},
        "issue_rows": int(len(issues)),
        "confirmed_no_mapping_rows": int((resolution["status"] == "confirmed_no_mapping").sum()) if not resolution.empty else 0,
        "latest_tongji_ranking_rows": int(len(latest)),
        "outputs": {
            "subject_resolution_matrix": str(QA_DIR / "subject_resolution_matrix.csv"),
            "subject_resolution_issues": str(QA_DIR / "subject_resolution_issues.csv"),
            "subject_latest_tongji_rankings": str(QA_DIR / "subject_latest_tongji_rankings.csv"),
        },
    }
    (QA_DIR / "subject_resolution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown_summary(summary, resolution, issues, latest)
    return summary


def suggested_action(status: str, source: str) -> str:
    if status == "missing_alias":
        return f"补充{source}学科别名或确认该一级学科不参与该榜单。"
    if status == "source_not_applicable":
        return f"{source}当前无该学科可用榜单口径，报告中跳过该来源。"
    if status == "has_alias_no_ranking_records":
        return f"检查{source}别名是否与排名表字段一致，或确认该榜单无此学科。"
    if status == "has_peer_records_no_tongji":
        return f"排名表有该学科其他高校记录，但没有同济记录；报告中应标为未上榜或待确认。"
    return "无"


def write_markdown_summary(
    summary: dict[str, Any],
    resolution: pd.DataFrame,
    issues: pd.DataFrame,
    latest: pd.DataFrame,
) -> None:
    lines = [
        "# 同济学科解析核验报告",
        "",
        "## 目标",
        "",
        "验证后续 agent 输入任一同济一级学科后，是否能通过 `dim_subject` 与 `dim_subject_alias` 解析到四大榜单，并查询到同济在榜单中的记录。",
        "",
        "## 核验摘要",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 同济相关一级学科数：{summary['tongji_subject_count']}",
        f"- 学科-榜单解析行数：{summary['resolution_rows']}",
        f"- 问题行数：{summary['issue_rows']}",
        f"- 已确认无映射行数：{summary['confirmed_no_mapping_rows']}",
        f"- 最新同济排名记录数：{summary['latest_tongji_ranking_rows']}",
        "",
        "## 状态统计",
        "",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"- `{status}`：{count}")

    lines.extend(["", "## 按榜单问题统计", ""])
    if issues.empty:
        lines.append("- 无。")
    else:
        source_issue = issues.groupby(["ranking_source", "issue_type"]).size().reset_index(name="count")
        for _, row in source_issue.iterrows():
            lines.append(f"- {row['ranking_source']} / {row['issue_type']}：{row['count']}")

    lines.extend(["", "## THE领域口径提示", ""])
    the_area = resolution[(resolution["ranking_source"] == "THE") & (resolution["is_area_mapping"] == True)]
    lines.append(f"- THE领域映射行数：{len(the_area)}")
    lines.append("- THE不是严格一级学科排名，生成报告时需要保留领域口径说明。")

    lines.extend(["", "## 可直接用于首批闭环的样例", ""])
    if latest.empty:
        lines.append("- 无。")
    else:
        sample = latest.sort_values(["ministry_subject_name", "ranking_source"]).head(20)
        for _, row in sample.iterrows():
            lines.append(
                f"- {row['ministry_subject_name']} / {row['ranking_source']}："
                f"{row['ranking_subject_raw']}，{row['release_year']}发布，排名 {row['rank_raw']}"
            )

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            "- `subject_resolution_matrix.csv`：同济学科 x 四大榜单的解析矩阵。",
            "- `subject_resolution_issues.csv`：需要补 alias、确认未上榜或确认无数据的问题清单。",
            "- `subject_latest_tongji_rankings.csv`：每个同济学科在各榜单中最新可查记录。",
        ]
    )

    (QA_DIR / "subject_resolution_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def append_run_log(summary: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# 学科解析过程留档\n", encoding="utf-8", newline="\n")
    lines = [
        "",
        f"## {summary['generated_at']} subject resolution",
        "",
        "### 目标",
        "",
        "核验同济相关一级学科能否通过 `dim_subject_alias` 解析到四大榜单，并查询同济排名记录。",
        "",
        "### 输出",
        "",
        f"- `{QA_DIR / 'subject_resolution_summary.md'}`",
        f"- `{QA_DIR / 'subject_resolution_matrix.csv'}`",
        f"- `{QA_DIR / 'subject_resolution_issues.csv'}`",
        f"- `{QA_DIR / 'subject_latest_tongji_rankings.csv'}`",
        "",
        "### 核验摘要",
        "",
        f"- 同济相关一级学科数：{summary['tongji_subject_count']}",
        f"- 学科-榜单解析行数：{summary['resolution_rows']}",
        f"- 问题行数：{summary['issue_rows']}",
        f"- 已确认无映射行数：{summary['confirmed_no_mapping_rows']}",
        f"- 最新同济排名记录数：{summary['latest_tongji_ranking_rows']}",
        "",
    ]
    with RUN_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    dim_subject, dim_alias, fact_ranking = load_data()
    summary = build_reports(dim_subject, dim_alias, fact_ranking)
    append_run_log(summary)
    print((QA_DIR / "subject_resolution_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
