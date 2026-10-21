from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
STAGE1_DIR = PROJECT_DIR / "configs" / "stage1_inventory"
OUTPUT_DIR = PROJECT_DIR / "configs" / "data_governance"


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def to_yaml(data: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(to_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return f"{prefix}[]"
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{prefix}{yaml_scalar(data)}"


def write_yaml(path: Path, data: Any) -> None:
    path.write_text(to_yaml(data) + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def read_catalog() -> dict[str, Any]:
    return json.loads((STAGE1_DIR / "data_catalog.json").read_text(encoding="utf-8"))


SOURCE_REGISTRY = [
    {
        "id": "map_ministry_rankings",
        "file": "教育部学科与四大国际学科排名映射关系.xlsx",
        "tier": "core",
        "role": "subject_crosswalk",
        "status": "use",
        "purpose": "教育部一级学科到软科、QS、US News、THE榜单学科的主映射表。",
        "canonical_tables": ["dim_subject"],
        "notes": "后续所有榜单数据进入统一模型前，优先通过该表做学科名称对齐。",
    },
    {
        "id": "map_tongji_college_subject",
        "file": "同济大学学院+学科映射关系20260509.xlsx",
        "tier": "core",
        "role": "tongji_subject_crosswalk",
        "status": "use",
        "purpose": "同济学院、学位点、一级学科、第五轮评估、双一流、高峰高原、四大榜单名称之间的映射。",
        "canonical_tables": ["dim_subject", "dim_tongji_unit"],
        "notes": "生成不同学院/学科报告时，这是定位目标学科和榜单名称的入口。",
    },
    {
        "id": "directory_postgraduate_subjects",
        "file": "1.研究生教育学科专业目录（2022年）.xlsx",
        "tier": "support",
        "role": "official_subject_directory",
        "status": "use_when_needed",
        "purpose": "官方学科门类、一级学科代码和名称校验。",
        "canonical_tables": ["dim_subject"],
        "notes": "用于补齐学科代码、门类和规范名称，不直接生成图表。",
    },
    {
        "id": "weights_four_rankings_2025",
        "file": "四大世界学科2025指标权重.xlsx",
        "tier": "core",
        "role": "indicator_weight",
        "status": "use",
        "purpose": "四大榜单指标体系和权重的主数据源。",
        "canonical_tables": ["dim_indicator", "fact_indicator_weight"],
        "notes": "优先使用该文件；另一个同名权重文件作为校验或历史副本。",
    },
    {
        "id": "weights_four_rankings_legacy",
        "file": "世界大学学科排名2025指标权重.xlsx",
        "tier": "support",
        "role": "indicator_weight",
        "status": "validate_or_fallback",
        "purpose": "指标权重备份/旧版来源。",
        "canonical_tables": ["fact_indicator_weight"],
        "notes": "如与主权重表冲突，先人工确认，不自动混用。",
    },
    {
        "id": "rank_arwu_2023",
        "file": "2023年软科世界一流学科排名-20231030.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "软科 2023 发布年度学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "字段含总得分和多项论文/合作指标。",
    },
    {
        "id": "rank_arwu_2024",
        "file": "2024年软科世界一流学科排名-20241111.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "软科 2024 发布年度学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "字段名称与 2025 软科较接近，适合历史趋势。",
    },
    {
        "id": "rank_arwu_2025",
        "file": "2025年软科世界一流学科排名20251118.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "软科 2025 发布年度学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "保留作 2025 单年校验；正式数据层优先使用 2021-2026 历史总库。",
    },
    {
        "id": "rank_arwu_2021_2026_history",
        "file": "2021-2026年软科世界一流学科排名（20260915已更新）.xlsx",
        "tier": "current",
        "role": "ranking_detail_history",
        "status": "use",
        "purpose": "软科 2021-2026 学科排名总库，作为当前排名、历史趋势和分项指标的主数据源。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "2021-2025 行与上一版总库逐值一致，新增 2026 年 19650 行；运行时由 configs/runtime/ranking_source_inputs.json 选择。",
    },
    {
        "id": "rank_qs_2023",
        "file": "2023年QS世界学科排名.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "QS 2023 学科排名明细。",
        "canonical_tables": ["fact_ranking"],
        "notes": "字段较少，主要用于排名和综合得分历史趋势。",
    },
    {
        "id": "rank_qs_2024",
        "file": "2024年QS世界学科排名-20240412.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "QS 2024 学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "含H指数、篇均引用、学术声誉等指标。",
    },
    {
        "id": "rank_qs_2025",
        "file": "2025年QS世界大学学科排名20250313.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "QS 2025 学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "含学术声誉、雇主声誉、H指数等指标。",
    },
    {
        "id": "rank_qs_2026",
        "file": "2026年QS世界学科排名20260326.xlsx",
        "tier": "current",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "QS 最新可用学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "优先用于2026报告中的QS当前表现分析。",
    },
    {
        "id": "rank_the_2022_2026_history",
        "file": "世界大学学科排名THE（2022-2026年）20260123.xlsx",
        "tier": "core",
        "role": "ranking_detail_history",
        "status": "use",
        "purpose": "THE 2022-2026 学科排名总库，含同济、同济历史、排名方法。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator", "fact_indicator_weight"],
        "notes": "THE 历史趋势优先用该文件，避免多文件拼接误差。",
    },
    {
        "id": "rank_the_2026",
        "file": "2026年THE世界学科排名20260123.xlsx",
        "tier": "current",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "THE 2026 学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "与THE历史总库互相校验，生成当前年度对标分析时优先用明细表。",
    },
    {
        "id": "rank_usnews_2021",
        "file": "2021US News世界学科排名2020年发布.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "US News 2021/2020发布口径历史数据。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "字段命名与后续年份差异较大，需单独映射。",
    },
    {
        "id": "rank_usnews_2022",
        "file": "2022US News世界学科排名20211026.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "US News 2022 学科排名历史数据。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "含较完整论文和声誉指标。",
    },
    {
        "id": "rank_usnews_2023",
        "file": "2023US News世界学科排名20221026.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "US News 2023 学科排名历史数据。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "含排名、总分和论文指标。",
    },
    {
        "id": "rank_usnews_2024_2025",
        "file": "2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx",
        "tier": "historical",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "US News 2024-2025 学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "文件名含2024-2025，需区分发布年份和排名年份。",
    },
    {
        "id": "rank_usnews_2025_2026",
        "file": "2025-2026年度US News世界学科排名20251124.xlsx",
        "tier": "current",
        "role": "ranking_detail",
        "status": "use",
        "purpose": "US News 最新可用学科排名明细。",
        "canonical_tables": ["fact_ranking", "fact_ranking_indicator"],
        "notes": "论文实力章节最重要的数据源之一。",
    },
    {
        "id": "domestic_double_first_class",
        "file": "全国双一流学科明细表2022&2017.v2.xlsx",
        "tier": "core",
        "role": "peer_scope",
        "status": "use",
        "purpose": "确定双一流高校和学科范围，用于对标高校筛选。",
        "canonical_tables": ["dim_peer_scope", "fact_domestic_status"],
        "notes": "对标高校范围如采用双一流口径，此表是入口。",
    },
    {
        "id": "domestic_eval_rounds_3_4",
        "file": "全国高校第四轮&第三轮学科评估结果.xlsx",
        "tier": "support",
        "role": "domestic_evaluation",
        "status": "use",
        "purpose": "第三轮、第四轮学科评估对比。",
        "canonical_tables": ["fact_domestic_evaluation"],
        "notes": "用于国内评估历史和对标背景。",
    },
    {
        "id": "domestic_eval_round5_incomplete",
        "file": "第五轮评估结果（不完全）20260508.xlsx",
        "tier": "core",
        "role": "domestic_evaluation",
        "status": "use_with_caveat",
        "purpose": "第五轮评估结果主表，但数据不完全。",
        "canonical_tables": ["fact_domestic_evaluation"],
        "notes": "报告必须注明数据不完全，避免过度结论。",
    },
    {
        "id": "domestic_eval_round5_analysis_copy",
        "file": "副本第五轮评估结果（不完全）20260508(分析).xlsx",
        "tier": "support",
        "role": "domestic_evaluation_enriched",
        "status": "validate_or_fallback",
        "purpose": "第五轮评估分析副本，含第四轮、第三轮、省份、层次等扩展字段。",
        "canonical_tables": ["fact_domestic_evaluation"],
        "notes": "可用于更丰富的国内评估图表，但需和主表校验。",
    },
    {
        "id": "tongji_domestic_status",
        "file": "同济大学第五轮学科评估结果+双一流+高峰高原.xlsx",
        "tier": "core",
        "role": "tongji_domestic_status",
        "status": "use",
        "purpose": "同济各学科第五轮评估、双一流、高峰高原状态。",
        "canonical_tables": ["dim_subject", "fact_domestic_status"],
        "notes": "总述和国内评估章节的重要来源。",
    },
    {
        "id": "tongji_15th_five_year_targets",
        "file": "同济大学学院十五五学科建设目标-指标X7学科国际排名.xlsx",
        "tier": "optional",
        "role": "planning_target",
        "status": "use_when_needed",
        "purpose": "学院十五五建设目标与指标名称。",
        "canonical_tables": ["fact_planning_target"],
        "notes": "用于建议和目标差距分析，不作为排名事实来源。",
    },
]


NON_EXCEL_ASSETS = [
    {
        "file": "【标黄】同济大学学科分析报告——理科（2026年）.docx",
        "tier": "core",
        "role": "target_template",
        "status": "use",
        "purpose": "后续最终报告的骨架模板。",
    },
    {
        "file": "同济大学XX学科的国际排名发展分析-2026年5月.docx",
        "tier": "core",
        "role": "reference_report",
        "status": "use",
        "purpose": "图表、表格和叙述样式的主要参考。",
    },
    {
        "file": "同济大学学科分析报告——理科（2026年给青塔的模板）.docx",
        "tier": "support",
        "role": "alternate_template",
        "status": "compare_when_needed",
        "purpose": "另一个理科模板版本，后续模板差异检查时使用。",
    },
    {
        "file": "1.研究生教育学科专业目录（2022年）.pdf",
        "tier": "support",
        "role": "official_reference_pdf",
        "status": "reference_only",
        "purpose": "官方目录 PDF 原件，必要时用于核对 Excel 目录。",
    },
    {
        "file": "1.教育部办公厅关于印发《有关学科专业调整对应关系表》等的通知.docx",
        "tier": "support",
        "role": "official_policy_reference",
        "status": "reference_only",
        "purpose": "学科专业调整政策背景材料，不直接入库。",
    },
    {
        "file": "THE世界大学排名指标体系3.0版new (数学).xmind",
        "tier": "optional",
        "role": "manual_indicator_mindmap",
        "status": "reference_only",
        "purpose": "THE 指标体系人工整理材料，当前不作为结构化数据源。",
    },
    {
        "file": "U.S. News世界大学排名 (数学).xmind",
        "tier": "optional",
        "role": "manual_indicator_mindmap",
        "status": "reference_only",
        "purpose": "US News 指标体系人工整理材料，当前不作为结构化数据源。",
    },
]


CANONICAL_MODEL = {
    "version": 1,
    "principles": [
        "原始 data 目录只读，不覆盖、不重命名、不清洗写回。",
        "所有派生结果进入 processed 或 outputs，且记录 source_file、source_sheet、source_row。",
        "先统一学科、学校、榜单、年份字段，再做联表分析。",
        "LLM 只负责选择分析意图和生成文字，数值计算由脚本或数据库完成。",
    ],
    "tables": {
        "dim_subject": {
            "grain": "一个教育部一级学科或报告分析学科一行。",
            "required_fields": [
                "subject_id",
                "ministry_category_code",
                "ministry_category_name",
                "ministry_subject_code",
                "ministry_subject_name",
                "tongji_college",
                "tongji_degree_program",
                "arwu_subject_name",
                "qs_subject_name",
                "usnews_subject_name",
                "the_subject_area",
            ],
            "primary_sources": [
                "教育部学科与四大国际学科排名映射关系.xlsx",
                "同济大学学院+学科映射关系20260509.xlsx",
                "1.研究生教育学科专业目录（2022年）.xlsx",
            ],
        },
        "dim_university": {
            "grain": "一所高校一行。",
            "required_fields": [
                "university_id",
                "university_name_cn",
                "university_name_en",
                "country_or_region",
                "province",
                "city",
                "is_tongji",
                "name_aliases",
            ],
            "primary_sources": ["各榜单排名明细", "全国双一流学科明细表2022&2017.v2.xlsx"],
        },
        "dim_ranking_source": {
            "grain": "一个排名机构/榜单一行。",
            "required_fields": ["ranking_source", "source_name_cn", "source_name_en", "ranking_family", "notes"],
            "primary_sources": ["配置手工维护"],
        },
        "dim_indicator": {
            "grain": "一个榜单指标一行。",
            "required_fields": [
                "indicator_id",
                "ranking_source",
                "indicator_name_raw",
                "indicator_name_cn",
                "indicator_group",
                "higher_is_better",
                "score_or_rank",
            ],
            "primary_sources": ["四大世界学科2025指标权重.xlsx", "各榜单排名明细字段"],
        },
        "fact_ranking": {
            "grain": "学校-学科-榜单-发布年度/排名年度一行。",
            "required_fields": [
                "ranking_source",
                "release_year",
                "ranking_year",
                "subject_id",
                "ranking_subject_raw",
                "university_id",
                "world_rank_raw",
                "world_rank_min",
                "world_rank_max",
                "world_rank_midpoint",
                "mainland_rank",
                "total_score",
                "source_file",
                "source_sheet",
                "source_row",
            ],
            "primary_sources": ["软科/QS/THE/US News 年度排名明细"],
        },
        "fact_ranking_indicator": {
            "grain": "学校-学科-榜单-年度-指标一行。",
            "required_fields": [
                "ranking_source",
                "release_year",
                "ranking_year",
                "subject_id",
                "university_id",
                "indicator_id",
                "indicator_value",
                "indicator_rank",
                "indicator_relative_rank",
                "source_file",
                "source_sheet",
                "source_row",
            ],
            "primary_sources": ["软科/QS/THE/US News 年度排名明细"],
        },
        "fact_indicator_weight": {
            "grain": "榜单-学科/领域-指标一行。",
            "required_fields": [
                "ranking_source",
                "ranking_subject_or_area",
                "indicator_id",
                "weight_percent",
                "source_file",
                "source_sheet",
            ],
            "primary_sources": ["四大世界学科2025指标权重.xlsx"],
        },
        "fact_domestic_evaluation": {
            "grain": "学校-一级学科-评估轮次一行。",
            "required_fields": [
                "university_id",
                "subject_id",
                "evaluation_round",
                "evaluation_result",
                "score",
                "province",
                "source_file",
                "source_sheet",
                "source_row",
            ],
            "primary_sources": ["第五轮评估结果", "全国高校第四轮&第三轮学科评估结果"],
        },
        "fact_domestic_status": {
            "grain": "学校-一级学科-国内建设标签一行。",
            "required_fields": [
                "university_id",
                "subject_id",
                "is_double_first_class",
                "double_first_class_batch",
                "shanghai_peak_plateau",
                "source_file",
            ],
            "primary_sources": ["全国双一流学科明细表2022&2017.v2.xlsx", "同济大学第五轮学科评估结果+双一流+高峰高原.xlsx"],
        },
    },
}


RELATIONSHIP_PLAN = [
    {
        "task": "确定目标学科",
        "join_path": [
            "用户输入：学院或一级学科",
            "同济大学学院+学科映射关系20260509.xlsx",
            "教育部学科与四大国际学科排名映射关系.xlsx",
            "得到四大榜单对应学科名称",
        ],
        "outputs": ["subject_id", "arwu_subject_name", "qs_subject_name", "usnews_subject_name", "the_subject_area"],
    },
    {
        "task": "四大排名历史趋势",
        "join_path": [
            "dim_subject",
            "按榜单对应学科名称筛选年度排名明细",
            "按 university_name_cn = 同济大学 筛选",
            "统一 release_year、ranking_year、rank_raw、rank_midpoint",
        ],
        "outputs": ["fact_ranking", "历史趋势图数据", "趋势描述"],
    },
    {
        "task": "对标高校整体分析",
        "join_path": [
            "dim_subject",
            "全国双一流学科明细表 或 第五轮评估结果确定 peer_scope",
            "peer_scope 学校名单连接 fact_ranking",
            "计算内地排名、分档数量、同济相对位置",
        ],
        "outputs": ["peer ranking table", "位次分布表", "对标结论"],
    },
    {
        "task": "分项指标分析",
        "join_path": [
            "fact_ranking_indicator",
            "fact_indicator_weight",
            "peer_scope",
            "同学科同年度内重算 indicator_relative_rank",
        ],
        "outputs": ["分项指标相对排名图", "优势/短板指标列表"],
    },
    {
        "task": "论文实力分析",
        "join_path": [
            "优先查找独立论文库",
            "若无独立论文库，使用 US News、软科、THE 中的论文/引用/高被引/国际合作代理指标",
            "记录每个指标口径和榜单来源",
        ],
        "outputs": ["论文代理指标表", "数据口径说明", "谨慎结论"],
    },
    {
        "task": "国内评估分析",
        "join_path": [
            "dim_subject",
            "第五轮评估结果（不完全）",
            "全国高校第四轮&第三轮学科评估结果",
            "全国双一流学科明细表",
        ],
        "outputs": ["评估结果对比表", "国内建设标签", "数据不完全说明"],
    },
]


def catalog_lookup(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {workbook["file"]: workbook for workbook in catalog["workbooks"]}


def enrich_registry(catalog: dict[str, Any]) -> dict[str, Any]:
    lookup = catalog_lookup(catalog)
    existing_files = {path.name for path in DATA_DIR.iterdir() if path.is_file()}
    registered_files = {entry["file"] for entry in SOURCE_REGISTRY}

    entries = []
    for entry in SOURCE_REGISTRY:
        workbook = lookup.get(entry["file"])
        enriched = dict(entry)
        enriched["exists"] = entry["file"] in existing_files
        enriched["sheet_count"] = len(workbook.get("sheets", [])) if workbook else 0
        enriched["sheets"] = [
            {
                "sheet": sheet["sheet"],
                "rows": sheet["max_row"],
                "columns": sheet["max_column"],
                "headers": sheet.get("headers", [])[:12],
            }
            for sheet in workbook.get("sheets", [])
        ] if workbook else []
        entries.append(enriched)

    non_excel_entries = []
    for entry in NON_EXCEL_ASSETS:
        enriched = dict(entry)
        enriched["exists"] = entry["file"] in existing_files
        non_excel_entries.append(enriched)

    unregistered_excel = [
        workbook["file"]
        for workbook in catalog["workbooks"]
        if workbook["file"] not in registered_files
    ]

    return {
        "version": 1,
        "data_dir": str(DATA_DIR),
        "policy": {
            "raw_files": "只读保留，不覆盖、不重命名。",
            "derived_files": "后续放入 processed 或 outputs，并保留来源追踪。",
            "status_meaning": {
                "use": "默认纳入数据层",
                "use_with_caveat": "可用但报告必须说明限制",
                "validate_or_fallback": "校验或兜底，不与主表自动混用",
                "use_when_needed": "按章节需要启用",
                "reference_only": "人工参考，不直接入结构化模型",
                "compare_when_needed": "版本比较时使用",
            },
        },
        "excel_sources": entries,
        "non_excel_assets": non_excel_entries,
        "unregistered_excel_files": unregistered_excel,
    }


def write_source_registry_csv(registry: dict[str, Any]) -> None:
    path = OUTPUT_DIR / "source_registry.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "file", "tier", "role", "status", "exists", "sheet_count", "purpose"],
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in registry["excel_sources"]:
            writer.writerow(
                {
                    "id": entry["id"],
                    "file": entry["file"],
                    "tier": entry["tier"],
                    "role": entry["role"],
                    "status": entry["status"],
                    "exists": entry["exists"],
                    "sheet_count": entry["sheet_count"],
                    "purpose": entry["purpose"],
                }
            )


def build_data_readiness_report(registry: dict[str, Any]) -> str:
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for entry in registry["excel_sources"]:
        by_tier.setdefault(entry["tier"], []).append(entry)

    missing = [entry for entry in registry["excel_sources"] if not entry["exists"]]
    caveats = [entry for entry in registry["excel_sources"] if entry["status"] in {"use_with_caveat", "validate_or_fallback"}]

    lines = [
        "# 数据层梳理报告",
        "",
        "## 目标",
        "",
        "在生成 Word 报告之前，先把杂乱表格整理成可追溯、可联表、可审查的数据层设计。",
        "",
        "## 结论先行",
        "",
        "- 四大国际排名、指标权重、学科映射、国内评估这四类核心数据都已具备。",
        "- 软科、QS、US News 是多年度多文件；THE 有一个 2022-2026 总库，可作为历史主源。",
        "- 后续不要直接让 agent 在 Excel 中随意检索，应先转成统一事实表和维表。",
        "- 论文实力和研究前沿两部分数据颗粒度不足，需要提前设定口径或补数据。",
        "",
        "## 数据源分级",
        "",
    ]

    for tier in ["core", "current", "historical", "support", "optional"]:
        entries = by_tier.get(tier, [])
        if not entries:
            continue
        lines.append(f"### {tier}")
        lines.append("")
        for entry in entries:
            lines.append(
                f"- `{entry['file']}`：{entry['role']}；状态 `{entry['status']}`；{entry['purpose']}"
            )
        lines.append("")

    lines.extend(["## 需要谨慎处理的数据", ""])
    for entry in caveats:
        lines.append(f"- `{entry['file']}`：{entry['notes']}")
    if not caveats:
        lines.append("- 暂无。")

    lines.extend(["", "## 未注册 Excel 文件", ""])
    if registry["unregistered_excel_files"]:
        for file_name in registry["unregistered_excel_files"]:
            lines.append(f"- `{file_name}`")
    else:
        lines.append("- 无。")

    lines.extend(["", "## 缺失文件检查", ""])
    if missing:
        for entry in missing:
            lines.append(f"- `{entry['file']}`")
    else:
        lines.append("- 注册表中的 Excel 文件均存在。")

    lines.extend(
        [
            "",
            "## 下一步数据处理建议",
            "",
            "1. 建立 `processed/ranking.duckdb` 或等价中间库。",
            "2. 先落 `dim_subject`，解决学科名称对齐。",
            "3. 再落 `fact_ranking`，统一四大榜单的排名、年份、学校字段。",
            "4. 再落 `fact_ranking_indicator` 和 `fact_indicator_weight`，支撑分项指标图。",
            "5. 最后落国内评估和对标高校范围表，支撑 peer 分析。",
        ]
    )

    return "\n".join(lines) + "\n"


def build_relationship_markdown() -> str:
    lines = [
        "# 数据联表关系说明",
        "",
        "## 总体思路",
        "",
        "所有分析都先从目标学科出发，再连接榜单学科名称、排名事实表、指标事实表和对标高校范围。不要让报告生成阶段重新猜表。",
        "",
    ]

    for item in RELATIONSHIP_PLAN:
        lines.append(f"## {item['task']}")
        lines.append("")
        lines.append("联表路径：")
        lines.append("")
        for step in item["join_path"]:
            lines.append(f"- {step}")
        lines.append("")
        lines.append("输出：")
        lines.append("")
        for output in item["outputs"]:
            lines.append(f"- {output}")
        lines.append("")

    return "\n".join(lines)


def build_cleaning_contract() -> str:
    return """# 数据清洗契约

## 原则

1. `data/` 目录只读，任何脚本不得覆盖原始 Word、Excel、PDF、xmind。
2. 清洗产物进入 `processed/`，报告产物进入 `outputs/`。
3. 每条事实数据必须保留 `source_file`、`source_sheet`、`source_row`。
4. 排名区间必须保留原始字符串，同时计算 `rank_min`、`rank_max`、`rank_midpoint`。
5. 发布年度和排名年度分开保存，不允许混成一个年份字段。
6. 学校、学科、榜单、指标名称先归一化，再联表。

## 排名字段处理

- `1`、`24` 等明确排名：`rank_min = rank_max = rank_midpoint = 原值`。
- `101-150` 等区间排名：保留 `rank_raw = "101-150"`，并计算中位数 `125.5`。
- `=35` 等并列排名：保留原文，数值字段取 35，并设置 `rank_note = "tied"`。
- 空值、未上榜、无数据：不填 999，不参与数值趋势计算。

## 指标字段处理

- 得分字段和排名字段必须区分。
- 如果原表没有指标排名，但有指标得分，可在同榜单、同学科、同年度内按得分重算相对排名。
- 方向不同的指标必须标记 `higher_is_better`，例如排名越小越好，得分越大越好。

## 对标高校范围

对标高校范围必须显式记录 `peer_scope`：

- `double_first_class_subject`：同一学科双一流高校。
- `round5_same_or_better`：第五轮评估同档或更高档高校。
- `mainland_top200_by_ranking`：某榜单该学科前200内地高校。
- `user_defined`：用户手工指定高校列表。

## 报告结论约束

- 每个数字结论必须能追溯到中间数据表。
- 使用“不完全”第五轮评估结果时，正文必须注明数据边界。
- 论文章节若只使用排名代理指标，正文必须说明并避免写成独立论文数据库结论。
- 研究前沿章节如果没有教师方向/论文主题数据，不应生成强结论。
"""


def build_processing_roadmap() -> str:
    return """# 后续数据处理路线

## 第一阶段：只读建模

目标：把源文件逻辑理顺，不生成报告。

- 已完成：`configs/stage1_inventory/`
- 已完成：`configs/data_governance/`

## 第二阶段：结构化入库

目标：把核心 Excel 转成统一中间库。

建议输出：

- `processed/ranking.duckdb`
- `processed/dim_subject.csv`
- `processed/dim_university.csv`
- `processed/fact_ranking.csv`
- `processed/fact_ranking_indicator.csv`
- `processed/fact_indicator_weight.csv`
- `processed/fact_domestic_evaluation.csv`

## 第三阶段：单 slot 数据闭环

目标：先选一个 slot 跑通数据、图、文字、插入 Word。

建议第一个 slot：

- `tongji_ranking_history`

原因：

- 数据源完整。
- 联表逻辑清楚。
- 参考报告里有对应表格和趋势图样式。
- 能检验学科映射、年度口径、排名区间处理。

## 第四阶段：扩展到整份报告

目标：按 `report_slots.yaml` 逐个生成章节。

顺序建议：

1. `tongji_ranking_history`
2. `ranking_indicator_system`
3. `double_first_class_peer_comparison`
4. `indicator_detail_comparison`
5. `domestic_evaluation_comparison`
6. `paper_strength_analysis`
7. `overview_competitive_summary`
8. `opportunities_challenges`
9. `research_frontier_interdiscipline`
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = read_catalog()
    registry = enrich_registry(catalog)

    write_yaml(OUTPUT_DIR / "source_registry.yaml", registry)
    write_json(OUTPUT_DIR / "source_registry.json", registry)
    write_source_registry_csv(registry)
    write_yaml(OUTPUT_DIR / "canonical_data_model.yaml", CANONICAL_MODEL)
    write_yaml(OUTPUT_DIR / "relationship_plan.yaml", {"version": 1, "relationships": RELATIONSHIP_PLAN})

    (OUTPUT_DIR / "data_readiness_report.md").write_text(
        build_data_readiness_report(registry),
        encoding="utf-8",
        newline="\n",
    )
    (OUTPUT_DIR / "data_relationships.md").write_text(
        build_relationship_markdown(),
        encoding="utf-8",
        newline="\n",
    )
    (OUTPUT_DIR / "data_cleaning_contract.md").write_text(
        build_cleaning_contract(),
        encoding="utf-8",
        newline="\n",
    )
    (OUTPUT_DIR / "processing_roadmap.md").write_text(
        build_processing_roadmap(),
        encoding="utf-8",
        newline="\n",
    )

    print("generated:", OUTPUT_DIR)
    print("excel sources:", len(registry["excel_sources"]))
    print("unregistered excel:", len(registry["unregistered_excel_files"]))
    print("non excel assets:", len(registry["non_excel_assets"]))


if __name__ == "__main__":
    main()
