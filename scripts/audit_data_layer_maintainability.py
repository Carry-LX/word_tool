from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
PROCESSED_DIR = PROJECT_DIR / "processed"
CONFIG_DIR = PROJECT_DIR / "configs"
EXTERNAL_PROCESSED_DIR = PROJECT_DIR / "external_data" / "processed"
SCRIPT_DIR = PROJECT_DIR / "scripts"
OUTPUT_DIR = CONFIG_DIR / "data_governance"

CORE_TABLES = [
    "dim_subject.csv",
    "dim_subject_alias.csv",
    "dim_indicator.csv",
    "dim_university_province.csv",
    "fact_ranking.csv",
    "fact_ranking_indicator.csv",
    "fact_indicator_weight.csv",
    "ranking.sqlite",
]

EXPECTED_BUT_NOT_FIRST_CLASS = [
    "dim_university.csv",
    "fact_domestic_evaluation.csv",
    "fact_domestic_status.csv",
    "fact_paper_metric.csv",
    "fact_external_indicator_history.csv",
    "artifact_data_contract.csv",
]

RISK_PATTERNS = {
    "hardcoded_request_variable": r"TARGET_SUBJECT|TARGET_SUBJECT_CODE|TARGET_UNIVERSITY",
    "math_specific_branch": r"is_math_subject|math-only|数学专用|数学样例|0701",
    "candidate_or_proxy_policy": r"candidate|候选|proxy|代理|CWTS|candidate_only",
    "external_file_direct_read": r"EXTERNAL_PROCESSED_DIR|external_data|read_external_csv",
    "manual_alias_rule": r"manual_subject_aliases|subject_alias_rules|mapping_class",
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame()


def table_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in CORE_TABLES:
        path = PROCESSED_DIR / name
        row = {
            "layer": "core_processed",
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "row_count": "",
            "column_count": "",
            "columns": "",
            "maintainability_note": "",
        }
        if path.exists() and path.suffix == ".csv":
            df = read_csv_if_exists(path)
            row["row_count"] = len(df)
            row["column_count"] = len(df.columns)
            row["columns"] = "；".join(df.columns.tolist()[:30])
        if name == "dim_university_province.csv":
            row["maintainability_note"] = "当前只是学校-省份映射，不是完整 dim_university。"
        rows.append(row)

    for name in EXPECTED_BUT_NOT_FIRST_CLASS:
        path = PROCESSED_DIR / name
        exists = path.exists()
        rows.append(
            {
                "layer": "first_class_table_added" if exists else "missing_first_class_table",
                "name": name,
                "path": str(path),
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else 0,
                "row_count": "",
                "column_count": "",
                "columns": "",
                "maintainability_note": "已由 data_layer_v2 沉淀为一等规范表。" if exists else "数据或逻辑已经部分存在，但没有沉淀为一等规范表。",
            }
        )
    return rows


def external_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not EXTERNAL_PROCESSED_DIR.exists():
        return rows
    for path in sorted(EXTERNAL_PROCESSED_DIR.glob("*.csv")):
        role = "external_supplement"
        note = ""
        name = path.name.lower()
        if "candidate" in name:
            role = "candidate_or_indirect"
            note = "候选/间接口径，进入报告前需要显式披露或用户确认。"
        elif "cwts" in name:
            role = "proxy_paper_metric"
            note = "CWTS 宽领域代理，不等于教育部一级学科 WOS/InCites 精确数据。"
        elif "arwu_gras_public" in name:
            role = "public_web_supplement"
            note = "网络补充的软科公开页数据，应统一进入规范外部分项历史表。"
        elif "usnews_tongji_subject_indicator_history" in name:
            role = "external_indicator_history"
            note = "US News 同济分项历史补充，应统一进入规范外部分项历史表。"
        rows.append(
            {
                "role": role,
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "note": note,
            }
        )
    return rows


def runtime_config_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    runtime_dir = CONFIG_DIR / "runtime"
    if not runtime_dir.exists():
        return rows
    for path in sorted(runtime_dir.glob("*")):
        if not path.is_file():
            continue
        note = ""
        if path.name == "manual_subject_aliases.json":
            note = "人工 alias 规则很大，是必要但高风险的映射层，需要 schema、审计和版本化。"
        elif "crosswalk" in path.name:
            note = "领域/指标口径 crosswalk，应并入统一 mapping registry。"
        elif path.name == "current_subject_request.json":
            note = "当前请求状态，不应被当作长期配置。"
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "note": note,
            }
        )
    return rows


def script_risk_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(SCRIPT_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = {name: len(re.findall(pattern, text, flags=re.IGNORECASE)) for name, pattern in RISK_PATTERNS.items()}
        total = sum(counts.values())
        if total == 0:
            continue
        risk_level = "low"
        if counts["hardcoded_request_variable"] or counts["math_specific_branch"]:
            risk_level = "high"
        elif counts["external_file_direct_read"] or counts["candidate_or_proxy_policy"]:
            risk_level = "medium"
        rows.append(
            {
                "script": path.name,
                "risk_level": risk_level,
                "total_hits": total,
                **counts,
            }
        )
    return sorted(rows, key=lambda row: ({"high": 0, "medium": 1, "low": 2}[row["risk_level"]], -int(row["total_hits"])))


def subject_coverage_summary() -> dict[str, Any]:
    readiness = read_csv_if_exists(PROCESSED_DIR / "qa" / "global_subject_data_readiness.csv")
    smoke = read_csv_if_exists(CONFIG_DIR / "pre_word_pipeline_qa" / "subject_migration_smoke_test.csv")
    result: dict[str, Any] = {
        "global_readiness_available": not readiness.empty,
        "smoke_test_available": not smoke.empty,
        "global_status_counts": {},
        "smoke_subject_count": 0,
        "smoke_ok_count": 0,
        "important_note": "当前 readiness 更多说明数据可查询，不等价于所有 Word 图表均达到模板级视觉和语义质量。",
    }
    if not readiness.empty and "readiness_status" in readiness.columns:
        result["global_status_counts"] = Counter(readiness["readiness_status"].tolist())
    if not smoke.empty:
        result["smoke_subject_count"] = int(len(smoke))
        result["smoke_ok_count"] = int((smoke.get("status", pd.Series(dtype=str)) == "ok").sum())
        result["smoke_subjects"] = smoke[["subject_code", "subject_name", "status", "weight_missing"]].to_dict("records")
    return result


def issue_rows(
    tables: list[dict[str, Any]],
    external_files: list[dict[str, Any]],
    runtime_configs: list[dict[str, Any]],
    script_risks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows = [
        {
            "severity": "P0",
            "area": "execution_contract",
            "issue": "run_subject_agent.py 仍通过脚本顶部变量切换学科。",
            "impact": "适合当前开发，不适合作为真正 agent 的稳定接口。",
            "recommended_fix": "保留显式变量风格，但改为 subject_request.json/profile 驱动，脚本只读配置，不散落状态。",
        },
        {
            "severity": "P1",
            "area": "mapping",
            "issue": "manual_subject_aliases.json 体量大，且 mapping_class 混合 deterministic、broad、approximate。",
            "impact": "查询时如果不区分映射可信度，会把宽领域口径当成精确一级学科。",
            "recommended_fix": "拆成 subject_crosswalk_registry.csv，字段包含 confidence、scope_type、requires_disclosure。",
        },
        {
            "severity": "P1",
            "area": "external_data",
            "issue": "external_data/processed 中包含候选权重、CWTS 代理、公开网页补源等不同证据等级。",
            "impact": "后续 agent 可能误把候选/代理数据写成正式结论。",
            "recommended_fix": "统一沉淀 external_source_registry 和 evidence_level，在 artifact spec 中强制披露。",
        },
        {
            "severity": "P1",
            "area": "artifact_layer",
            "issue": "subject_artifact_builders.py 已承担查询、修补、绘图、表格渲染多重职责。",
            "impact": "新图表继续叠加会越来越难维护。",
            "recommended_fix": "拆成 data_access、artifact_dataset_builders、renderers、validators 四层。",
        },
        {
            "severity": "P2",
            "area": "qa",
            "issue": "已有 audit 能检查生成是否失败，但对映射可信度、代理口径、图表模板相似度的约束还不够硬。",
            "impact": "可能出现 audit 通过但报告语义仍不够正式。",
            "recommended_fix": "新增 data_contract_audit 和 artifact_semantic_contract，每个 artifact 明确 allowed_evidence_level。",
        },
    ]
    missing_tables = [row["name"] for row in tables if row["layer"] == "missing_first_class_table" and row["name"] != "artifact_data_contract.csv"]
    if missing_tables:
        rows.insert(
            0,
            {
                "severity": "P0",
                "area": "data_model",
                "issue": f"仍有一等规范表未建立：{'；'.join(missing_tables)}。",
                "impact": "图表生成器会直接读补充 CSV 或临时映射，换学科时边界容易变乱。",
                "recommended_fix": "把这些数据提升为 processed 层规范表，并写入 ranking.sqlite。",
            },
        )
    else:
        rows.append(
            {
                "severity": "P2",
                "area": "data_model",
                "issue": "data_layer_v2 已补齐主要一等表，但 artifact 生成器尚未完全切换到新表。",
                "impact": "短期绘图逻辑不受影响；长期仍需要逐步迁移读取路径。",
                "recommended_fix": "下一阶段把 subject_artifact_builders 的数据访问改为消费 artifact_data_contract 和 v2 fact/dim 表。",
            }
        )
    if any(item["role"] == "candidate_or_indirect" for item in external_files):
        rows.append(
            {
                "severity": "P1",
                "area": "candidate_data",
                "issue": "仍存在 candidate_or_indirect 外部补充数据。",
                "impact": "不能无条件进入正式 Word。",
                "recommended_fix": "生成器必须把 candidate_only 标记传到最终 slot 状态。",
            }
        )
    if any(row["risk_level"] == "high" for row in script_risks):
        rows.append(
            {
                "severity": "P1",
                "area": "hardcoded_logic",
                "issue": "多个脚本存在硬编码请求变量、数学分支或旧样例逻辑。",
                "impact": "后续接手者难判断哪些脚本能跨学科运行。",
                "recommended_fix": "在 script registry 中标注 legacy/sample/production，并逐步迁移到统一入口。",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8", newline="\n")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    tables: list[dict[str, Any]],
    external_files: list[dict[str, Any]],
    runtime_configs: list[dict[str, Any]],
    script_risks: list[dict[str, Any]],
    coverage: dict[str, Any],
    issues: list[dict[str, str]],
) -> None:
    lines = [
        "# 数据层可维护性审计",
        "",
        f"- 生成时间：{now_text()}",
        "- 目的：把当前数据层从“能跑的补丁集合”整理成后续 agent 可维护的数据产品。",
        "",
        "## 结论",
        "",
        "当前系统已经能支撑计算机科学与技术等学科生成 24 个 Word 前 artifact，但数据层还不能算完全产品化。核心事实表、映射配置、外部补源和绘图修补逻辑边界不够硬，短期可继续使用，长期需要做一次数据层 v2 整理。",
        "",
        "## 全学科覆盖现状",
        "",
        f"- 全局 readiness 可用：{coverage.get('global_readiness_available')}",
        f"- smoke test 可用：{coverage.get('smoke_test_available')}",
        f"- smoke test 学科数：{coverage.get('smoke_subject_count')}，ok：{coverage.get('smoke_ok_count')}",
        "- 注意：readiness 表示数据可查询，不等价于所有 Word 图表都达到模板级质量。",
        "",
        "### readiness 分布",
        "",
    ]
    for key, value in dict(coverage.get("global_status_counts", {})).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 主要问题", ""])
    for item in issues:
        lines.append(f"- {item['severity']} / {item['area']}：{item['issue']} 影响：{item['impact']} 建议：{item['recommended_fix']}")
    lines.extend(
        [
            "",
            "## 分层建议",
            "",
            "1. `processed` 只放一等规范表：dim/fact 表必须有 grain、主键、source_trace、证据等级。",
            "2. `configs/runtime` 只放运行时请求和少量稳定 crosswalk，不放大体量人工知识库。",
            "3. `configs/mapping_registry` 应承接 subject alias、THE area、CWTS field、指标归并、学校别名等所有映射。",
            "4. `external_data/processed` 只做原始外部补源落盘，正式生成前必须进入规范 fact 表或以 candidate/proxy 状态显式披露。",
            "5. artifact 生成层只消费规范表和 artifact contract，不直接判断某个外部文件该不该用。",
            "",
            "## 下一步最小改造",
            "",
            "先不继续进 Word。下一步建议先做 `data_layer_v2`：建立 `dim_university`、`fact_external_indicator_history`、`fact_paper_metric_proxy`、`mapping_registry`，然后让 `run_subject_agent.py` 只读这些规范表。这样换学科才像 agent，而不是靠脚本补丁记忆。",
            "",
            "## 输出文件",
            "",
            "- `data_layer_table_inventory.csv`",
            "- `data_layer_external_inventory.csv`",
            "- `data_layer_runtime_config_inventory.csv`",
            "- `data_layer_script_risk_inventory.csv`",
            "- `data_layer_maintainability_issues.csv`",
            "- `data_layer_maintainability_audit.json`",
        ]
    )
    (OUTPUT_DIR / "data_layer_maintainability_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tables = table_inventory()
    external_files = external_inventory()
    runtime_configs = runtime_config_inventory()
    script_risks = script_risk_inventory()
    coverage = subject_coverage_summary()
    issues = issue_rows(tables, external_files, runtime_configs, script_risks)

    write_csv(OUTPUT_DIR / "data_layer_table_inventory.csv", tables)
    write_csv(OUTPUT_DIR / "data_layer_external_inventory.csv", external_files)
    write_csv(OUTPUT_DIR / "data_layer_runtime_config_inventory.csv", runtime_configs)
    write_csv(OUTPUT_DIR / "data_layer_script_risk_inventory.csv", script_risks)
    write_csv(OUTPUT_DIR / "data_layer_maintainability_issues.csv", issues)
    payload = {
        "generated_at": now_text(),
        "table_count": len(tables),
        "external_file_count": len(external_files),
        "runtime_config_count": len(runtime_configs),
        "script_risk_count": len(script_risks),
        "coverage": coverage,
        "issue_count": len(issues),
        "issues": issues,
    }
    (OUTPUT_DIR / "data_layer_maintainability_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(tables, external_files, runtime_configs, script_risks, coverage, issues)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
