from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
RUN_ROOT = PROJECT_DIR / "outputs" / "subject_agent_runs"
PROCESSED_QA_DIR = PROJECT_DIR / "processed" / "qa"
OUTPUT_DIR = PROJECT_DIR / "configs" / "pre_word_pipeline_qa"
README_PATH = PROJECT_DIR / "README.md"

# 不使用命令行参数；默认审计最新一次 subject agent run。
RUN_DIR = None


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def resolve_run_dir() -> Path:
    if RUN_DIR:
        return Path(RUN_DIR)
    candidates = [path for path in RUN_ROOT.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"未找到 subject agent run: {RUN_ROOT}")
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def issue(severity: str, area: str, item: str, finding: str, recommendation: str) -> dict[str, str]:
    return {
        "severity": severity,
        "area": area,
        "item": item,
        "finding": finding,
        "recommendation": recommendation,
    }


def count_rows(path: Path) -> int:
    if not path.exists():
        return -1
    return len(read_csv(path))


def audit_processed_layer() -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    notes: list[str] = []
    processed_summary = read_json(PROCESSED_QA_DIR / "processed_core_summary.json")
    indicator_summary = read_json(PROCESSED_QA_DIR / "ranking_indicators" / "ranking_indicator_summary.json")
    weight_summary = read_json(PROCESSED_QA_DIR / "indicator_weights" / "indicator_weight_summary.json")
    parse_exception_rows = count_rows(PROCESSED_QA_DIR / "ranking_parse_exceptions.csv")
    unmatched_rows = count_rows(PROCESSED_QA_DIR / "subject_mapping_unmatched.csv")
    weight_exception_rows = count_rows(PROCESSED_QA_DIR / "indicator_weights" / "indicator_weight_total_exceptions.csv")
    tongji_missing_indicator_rows = count_rows(PROCESSED_QA_DIR / "ranking_indicators" / "p1_tongji_missing_indicators.csv")

    notes.append(f"fact_ranking_rows={processed_summary.get('fact_ranking_rows')}")
    notes.append(f"fact_ranking_indicator_rows={indicator_summary.get('fact_ranking_indicator_rows')}")
    notes.append(f"fact_indicator_weight_rows={weight_summary.get('fact_indicator_weight_rows')}")
    notes.append(f"rank_parse_exception_rows={parse_exception_rows}")
    notes.append(f"indicator_weight_total_exception_rows={weight_exception_rows}")

    if parse_exception_rows != 0:
        issues.append(issue("P1", "processed", "ranking_parse", f"排名解析异常 {parse_exception_rows} 行。", "先修 rank_raw/rank_midpoint 解析，再进入图表生成。"))
    if weight_exception_rows != 0:
        issues.append(issue("P1", "processed", "indicator_weight", f"权重合计异常 {weight_exception_rows} 行。", "先修权重归一化或源表解析。"))
    if unmatched_rows > 0:
        issues.append(issue("P3", "processed", "subject_mapping", f"仍有 {unmatched_rows} 个榜单原始学科名未映射。", "不阻塞数学；换学科前由 subject agent 先判断目标学科是否落入未映射集合。"))
    if tongji_missing_indicator_rows > 0:
        missing_df = read_csv(PROCESSED_QA_DIR / "ranking_indicators" / "p1_tongji_missing_indicators.csv")
        missing_names = ";".join(missing_df.get("missing_for_tongji_indicator", pd.Series(dtype=str)).tolist())
        if missing_df["missing_for_tongji_indicator"].astype(str).str.contains("总得分", na=False).all():
            notes.append(f"tongji_missing_indicator_rows={tongji_missing_indicator_rows}; only_total_score_missing={missing_names}")
        else:
            issues.append(issue("P2", "processed", "tongji_indicator", f"同济 P1 分项指标缺失清单有 {tongji_missing_indicator_rows} 行。", "非总得分字段缺失时需修分项指标抽取或降级对应图表。"))
    return issues, notes


def audit_run_layer(run_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    notes: list[str] = []
    summary = read_json(run_dir / "agent_run_summary.json")
    subject_code = str(summary.get("request", {}).get("target_subject_code", ""))
    is_verified_math_run = subject_code == "0701"
    readiness = read_csv(run_dir / "artifact_readiness.csv")
    gaps = read_csv(run_dir / "data_gap_report.csv")
    ranking = read_csv(run_dir / "ranking_availability.csv")
    weights = read_csv(run_dir / "weight_availability.csv")
    indicators = read_csv(run_dir / "indicator_availability.csv")
    audit = read_json(run_dir / "audit" / "subject_artifact_audit.json")

    notes.append(f"run_dir={run_dir}")
    notes.append(f"ready_artifacts={summary.get('ready_artifact_count')}/{summary.get('artifact_count')}")
    notes.append(f"generated_artifacts={summary.get('parameterized_artifacts', {}).get('generated_count')}")
    notes.append(f"subject_artifact_audit={audit.get('pass_count')}/{audit.get('artifact_count')} pass")

    if int(audit.get("fail_count", 0)) != 0:
        issues.append(issue("P1", "artifact", "subject_artifact_audit", f"subject-run artifact 审计失败 {audit.get('fail_count')} 个。", "修复失败 artifact 后重跑 agent。"))
    if int(summary.get("ready_artifact_count", 0)) != int(summary.get("parameterized_artifacts", {}).get("generated_count", 0)):
        issues.append(
            issue(
                "P1",
                "agent",
                "ready_vs_generated",
                "ready artifact 数量与自动生成数量不一致。",
                "确认是否存在 ready 但尚未参数化的 artifact，不能进入 Word。",
            )
        )

    missing_weights = weights[weights["data_status"] != "available"]
    for _, row in missing_weights.iterrows():
        issues.append(
            issue(
                "KNOWN_BLOCKER",
                "data_gap",
                f"{row['ranking_source']} weight",
                f"{row['ranking_source']} 缺少 {row['expected_subject_or_area']} 权重。",
                "对应权重图必须 blocked，不能套用其他学科权重。",
            )
        )

    for _, row in indicators.iterrows():
        if row["ranking_source"] in {"软科", "US News"} and int(row["year_count"] or 0) < 2:
            issues.append(
                issue(
                    "KNOWN_BLOCKER",
                    "indicator_history",
                    row["ranking_source"],
                    f"{row['ranking_source']} 同济分项指标仅 {row['year_count']} 个年份。",
                    "多年历史表/趋势图继续保持 partial，或用户确认降级为最新年。",
                )
            )

    if len(gaps) > 0:
        notes.append(f"blocked_or_partial_items={len(gaps)}")
    if not is_verified_math_run:
        notes.append("math_verified_peer_scope_check_skipped=true; non-math subject peer counts vary by discipline.")
        return issues, notes
    ranking_expected = {"软科": 21, "QS": 16, "US News": 43, "THE": 18}
    for _, row in ranking.iterrows():
        source = row["ranking_source"]
        if source in ranking_expected and int(row["mainland_top200_rows"] or 0) != ranking_expected[source]:
            issues.append(
                issue(
                    "P1",
                    "peer_scope",
                    source,
                    f"{source} peer 数为 {row['mainland_top200_rows']}，与数学已核验口径 {ranking_expected[source]} 不一致。",
                    "检查 alias join 去重、国家/地区识别和 rank_midpoint 过滤。",
                )
            )
    return issues, notes


def audit_artifact_semantics(run_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    notes: list[str] = []
    artifact_root = run_dir / "artifacts"
    summary = read_json(run_dir / "agent_run_summary.json")
    subject_code = str(summary.get("request", {}).get("target_subject_code", ""))
    is_verified_math_run = subject_code == "0701"

    fig02 = read_csv(artifact_root / "figure_02_ranking_indicator_commonality" / "chart_data.csv")
    if "研究质量" in set(fig02.get("indicator_group", pd.Series(dtype=str)).tolist()):
        issues.append(issue("P2", "chart_semantics", "figure_02", "指标共性图仍出现未归并的“研究质量”分组。", "将 THE 研究质量归并到科研/论文的共性口径，source_trace 保留原始值。"))
    if "indicator_count_weight_missing" in set(fig02.get("basis", pd.Series(dtype=str)).tolist()):
        notes.append("figure_02 使用 US News 指标覆盖数量替代权重展示，这是明确降级口径。")

    fig09 = read_csv(artifact_root / "figure_09_arwu_peer_indicator_relative_rank" / "chart_data.csv")
    if fig09["indicator_name"].astype(str).str.contains("总得分").any():
        issues.append(issue("P1", "chart_semantics", "figure_09", "软科分项图混入总得分/辅助总得分。", "过滤总得分字段，只保留分项指标。"))
    if is_verified_math_run and len(fig09) != 5:
        issues.append(issue("P2", "chart_semantics", "figure_09", f"软科分项图当前 {len(fig09)} 个指标，预期数学有效分项为 5 个。", "检查 score/rank 指标过滤和总得分排除。"))

    peer_expectations = {
        "figure_09_arwu_peer_indicator_relative_rank": "table_05_arwu_mainland_peer_ranking",
        "figure_11_usnews_peer_indicator_relative_rank": "table_06_usnews_mainland_peer_ranking",
        "figure_12_the_peer_indicator_relative_rank": "table_08_the_mainland_peer_ranking",
    }
    for figure_id, table_id in peer_expectations.items():
        chart = read_csv(artifact_root / figure_id / "chart_data.csv")
        peers = read_csv(artifact_root / table_id / "latest_peer_records.csv")
        if "display_university" in peers.columns:
            unique_col = "display_university"
        elif "university_name_cn" in peers.columns:
            unique_col = "university_name_cn"
        else:
            unique_col = peers.columns[0]
        peer_rows = peers[unique_col].nunique()
        if "is_tongji" in peers.columns:
            tongji_in_peer = peers["is_tongji"].astype(str).str.lower().isin(["true", "1"]).any()
        else:
            tongji_in_peer = peers.astype(str).apply(lambda col: col.str.contains("同济大学|Tongji University", regex=True, na=False)).any(axis=1).any()
        expected_peer_scope = peer_rows - (1 if tongji_in_peer else 0)
        observed = {int(float(value)) for value in chart["peer_scope_size"].tolist() if clean_text(value)}
        if observed != {expected_peer_scope}:
            issues.append(
                issue(
                    "P1",
                    "peer_indicator",
                    figure_id,
                    f"{figure_id} peer_scope_size={sorted(observed)}，但 {table_id} 推导应为 {expected_peer_scope}。",
                    "检查 peer 表复用、同济是否在 peer scope 内、分项指标匹配。",
                )
            )

    table04 = read_csv(artifact_root / "table_04_mainland_rank_band_distribution" / "table_data.csv")
    if len(table04) != 16:
        issues.append(issue("P1", "table_semantics", "table_04", f"table_04 行数为 {len(table04)}，预期 4 榜单 x 4 分档 = 16。", "补齐 1-200 合计行。"))

    table09_rows = len(read_csv(artifact_root / "table_09_peer_full_ranking_history_appendix" / "table_data.csv"))
    if table09_rows < 200:
        issues.append(issue("P2", "table_semantics", "table_09", f"附表历史长表只有 {table09_rows} 行，可能只汇总最新年。", "应从 latest peer scope 回查历史排名，而不是只拼最新 peer 表。"))
    notes.append(f"table_09_history_rows={table09_rows}")
    return issues, notes


def write_reports(run_dir: Path, issues: list[dict[str, str]], notes: list[str]) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = now_text()
    severity_order = {"P1": 0, "P2": 1, "P3": 2, "KNOWN_BLOCKER": 3}
    issues = sorted(issues, key=lambda row: (severity_order.get(row["severity"], 9), row["area"], row["item"]))
    operational_issues = [row for row in issues if row["severity"] in {"P1", "P2", "P3"}]
    known_blockers = [row for row in issues if row["severity"] == "KNOWN_BLOCKER"]
    report = {
        "generated_at": generated_at,
        "run_dir": str(run_dir),
        "issue_count": len(operational_issues),
        "known_blocker_count": len(known_blockers),
        "p1_count": sum(1 for row in operational_issues if row["severity"] == "P1"),
        "p2_count": sum(1 for row in operational_issues if row["severity"] == "P2"),
        "p3_count": sum(1 for row in operational_issues if row["severity"] == "P3"),
        "issues": issues,
        "notes": notes,
    }
    (OUTPUT_DIR / "pre_word_pipeline_qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    pd.DataFrame(issues).to_csv(OUTPUT_DIR / "pre_word_pipeline_issues.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# Pre-Word Pipeline QA",
        "",
        f"- generated_at: {generated_at}",
        f"- run_dir: `{run_dir}`",
        f"- operational_issue_count: {len(operational_issues)}",
        f"- known_blocker_count: {len(known_blockers)}",
        f"- P1: {report['p1_count']}",
        f"- P2: {report['p2_count']}",
        f"- P3: {report['p3_count']}",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in notes)
    lines.extend(["", "## Issues", "", "| severity | area | item | finding | recommendation |", "| --- | --- | --- | --- | --- |"])
    for row in issues:
        lines.append(f"| {row['severity']} | {row['area']} | {row['item']} | {row['finding']} | {row['recommendation']} |")
    (OUTPUT_DIR / "pre_word_pipeline_qa.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return report


def update_readme(report: dict[str, Any]) -> None:
    section = "## Pre-Word Pipeline QA"
    block = [
        section,
        "",
        f"- generated_at: {report['generated_at']}",
        f"- latest_run: `{report['run_dir']}`",
        f"- operational_issue_count: {report['issue_count']}",
        f"- known_blocker_count: {report['known_blocker_count']}",
        f"- P1: {report['p1_count']}",
        f"- P2: {report['p2_count']}",
        f"- P3: {report['p3_count']}",
        "- QA report: `configs/pre_word_pipeline_qa/pre_word_pipeline_qa.md`",
        "",
    ]
    text = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else "# word_tool\n"
    if section in text:
        text = text.split(section)[0].rstrip() + "\n\n" + "\n".join(block)
    else:
        text = text.rstrip() + "\n\n" + "\n".join(block)
    README_PATH.write_text(text, encoding="utf-8", newline="\n")


def audit_run_layer_v2(run_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    notes: list[str] = []
    summary = read_json(run_dir / "agent_run_summary.json")
    subject_code = str(summary.get("request", {}).get("target_subject_code", ""))
    is_verified_math_run = subject_code == "0701"
    gaps = read_csv(run_dir / "data_gap_report.csv")
    ranking = read_csv(run_dir / "ranking_availability.csv")
    weights = read_csv(run_dir / "weight_availability.csv")
    indicators = read_csv(run_dir / "indicator_availability.csv")
    audit = read_json(run_dir / "audit" / "subject_artifact_audit.json")
    generated_results = [row for row in summary.get("parameterized_artifacts", {}).get("results", []) if row.get("status") == "generated"]
    generated_ids = {row.get("artifact_id") for row in generated_results}

    ready_count = int(summary.get("ready_artifact_count", 0))
    generated_count = int(summary.get("parameterized_artifacts", {}).get("generated_count", 0))
    notes.append(f"run_dir={run_dir}")
    notes.append(f"ready_artifacts={ready_count}/{summary.get('artifact_count')}")
    notes.append(f"generated_artifacts={generated_count}")
    notes.append(f"subject_artifact_audit={audit.get('pass_count')}/{audit.get('artifact_count')} pass")

    if int(audit.get("fail_count", 0)) != 0:
        issues.append(issue("P1", "artifact", "subject_artifact_audit", f"subject artifact audit failed: {audit.get('fail_count')}", "Fix failed artifacts and rerun the subject agent."))
    if generated_count < ready_count:
        issues.append(issue("P1", "agent", "ready_vs_generated", "Some ready artifacts were not generated.", "Do not enter Word writing until every ready artifact is generated."))
    elif generated_count > ready_count:
        notes.append(f"generated_artifacts_exceed_ready_by={generated_count - ready_count}; extra outputs are external-data/candidate artifacts.")

    for _, row in weights[weights["data_status"] != "available"].iterrows():
        if row["ranking_source"] == "US News" and "figure_05_usnews_indicator_weight" in generated_ids:
            notes.append("US News 数学权重缺官方专表；已生成 candidate_only 权重图，进入 Word 前需要确认是否接受 soft sciences 候选口径。")
            continue
        issues.append(issue("KNOWN_BLOCKER", "data_gap", f"{row['ranking_source']} weight", f"{row['ranking_source']} 缺少 {row['expected_subject_or_area']} 权重。", "对应权重图必须 blocked，不能套用其他学科权重。"))

    for _, row in indicators.iterrows():
        source = row["ranking_source"]
        if source in {"杞", "软科", "US News"} and int(row["year_count"] or 0) < 2:
            if is_verified_math_run and source == "US News" and {"table_02_usnews_tongji_indicator_history", "figure_10_usnews_indicator_history_trend"}.issubset(generated_ids):
                notes.append("US News 同济数学分项历史已由 external_data/local_usnews_tongji_math_indicator_history.csv 补齐并生成。")
                continue
            if source in {"杞", "软科"} and "table_01_arwu_tongji_indicator_history" in generated_ids:
                notes.append("软科同济数学分项历史已由 external_data/local_arwu_tongji_math_indicator_history.csv 恢复 2023/2025；2024 缺测。")
                continue
            issues.append(issue("KNOWN_BLOCKER", "indicator_history", source, f"{source} 同济分项指标只有 {row['year_count']} 个年份。", "多年历史表/趋势图继续保持 partial，或确认降级为最新年。"))

    if len(gaps) > 0:
        notes.append(f"blocked_or_partial_items={len(gaps)}")
    if not is_verified_math_run:
        notes.append("math_verified_peer_scope_check_skipped=true; non-math subject peer counts vary by discipline.")
        return issues, notes
    ranking_expected = {"杞": 21, "软科": 21, "QS": 16, "US News": 43, "THE": 18}
    for _, row in ranking.iterrows():
        source = row["ranking_source"]
        if source in ranking_expected and int(row["mainland_top200_rows"] or 0) != ranking_expected[source]:
            issues.append(issue("P1", "peer_scope", source, f"{source} peer count is {row['mainland_top200_rows']}, expected {ranking_expected[source]} for the verified math scope.", "Check alias join, deduplication, mainland recognition, and rank_midpoint filtering."))
    return issues, notes


def main() -> None:
    run_dir = resolve_run_dir()
    issues: list[dict[str, str]] = []
    notes: list[str] = []
    for audit_fn in [audit_processed_layer, lambda: audit_run_layer_v2(run_dir), lambda: audit_artifact_semantics(run_dir)]:
        new_issues, new_notes = audit_fn()
        issues.extend(new_issues)
        notes.extend(new_notes)
    report = write_reports(run_dir, issues, notes)
    update_readme(report)
    print(json.dumps({"run_dir": str(run_dir), "issue_count": report["issue_count"], "p1_count": report["p1_count"], "p2_count": report["p2_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
