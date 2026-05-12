from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
STAGE1_DIR = PROJECT_DIR / "configs" / "stage1_inventory"
GOVERNANCE_DIR = PROJECT_DIR / "configs" / "data_governance"
OUTPUT_DIR = PROJECT_DIR / "configs" / "artifact_recipes"


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def src(
    source_id: str,
    file: str,
    sheet: str,
    fields: list[str],
    role: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "file": file,
        "sheet": sheet,
        "role": role,
        "required": required,
        "fields": fields,
    }


MAPPING_SOURCE = src(
    "map_ministry_rankings",
    "教育部学科与四大国际学科排名映射关系.xlsx",
    "学科映射关系",
    [
        "一级学科代码",
        "一级学科名称",
        "软科世界一流学科对应名称",
        "QS对应的学科名称",
        "U.S.NEWS学科排名对应名称",
        "THE对应领域",
    ],
    "subject_crosswalk",
)

TONGJI_MAPPING_SOURCE = src(
    "map_tongji_college_subject",
    "同济大学学院+学科映射关系20260509.xlsx",
    "Sheet1",
    [
        "学院",
        "学术学位点",
        "一级学科学科代码",
        "第五轮评估结果",
        "是否双一流学科",
        "上海市高峰高原",
        "软科世界一流学科对应名称",
        "QS对应的学科名称",
        "U.S.NEWS学科排名对应名称",
        "THE对应领域",
    ],
    "tongji_subject_crosswalk",
)

ARWU_2025 = src(
    "rank_arwu_2025",
    "2025年软科世界一流学科排名20251118.xlsx",
    "数据",
    [
        "学校名称",
        "所在地区",
        "发布年度",
        "学科领域",
        "学科名称",
        "国际排名",
        "总得分",
        "高水平研究成果/重要期刊论文数",
        "科研影响力/论文标准化影响力",
        "国际合作/国际合作论文比例",
        "世界一流成果",
        "世界一流教师",
        "辅助总得分",
    ],
    "ranking_detail",
)

QS_2026 = src(
    "rank_qs_2026",
    "2026年QS世界学科排名20260326.xlsx",
    "数据",
    [
        "中文名称",
        "英文名称",
        "所在地区",
        "学科英文",
        "学科中文",
        "发布年度",
        "国际排名",
        "总得分",
        "H指数",
        "篇均被引次数",
        "学术声誉",
        "雇主声誉",
        "国际网络研究",
    ],
    "ranking_detail",
)

USNEWS_2025_2026 = src(
    "rank_usnews_2025_2026",
    "2025-2026年度US News世界学科排名20251124.xlsx",
    "Sheet1",
    [
        "中文名称",
        "外文名称",
        "所在地区",
        "学科英文",
        "学科中文",
        "发布年度",
        "排名年度",
        "国际排名",
        "总得分",
        "全球学术声誉排名",
        "地区学术声誉排名",
        "出版物排名",
        "图书排名",
        "标准化论文引用影响指数排名",
        "总被引频次排名",
        "被引用最多的10%的出版物数量排名",
        "总被引率占总被引文献的10%排名",
        "具有国际合作出版物的比例排名",
        "国际合作排名",
        "排名前1%的高被引论文数量排名",
        "前1%的高被引论文占论文总数的百分比排名",
        "会议排名",
        "国内排名-lym",
    ],
    "ranking_detail",
)

THE_2026 = src(
    "rank_the_2026",
    "2026年THE世界学科排名20260123.xlsx",
    "数据",
    [
        "中文名称",
        "外文名称",
        "发布年度",
        "排名年度",
        "国际排名",
        "所在地区",
        "学科英文",
        "学科中文",
        "总得分",
        "篇均被引次数",
        "商业收入",
        "国际化视野",
        "研究",
        "教学",
        "科研环境",
        "科研质量",
    ],
    "ranking_detail",
)

THE_HISTORY = src(
    "rank_the_2022_2026_history",
    "世界大学学科排名THE（2022-2026年）20260123.xlsx",
    "数据",
    [
        "中文名称",
        "外文名称",
        "所在地区",
        "学科英文",
        "学科中文",
        "发布年度",
        "排名年度",
        "国际排名",
        "总得分",
        "教学",
        "教学排名",
        "科研环境",
        "科研环境排名",
        "科研质量",
        "科研质量排名",
        "商业收入",
        "商业收入排名",
        "国际化视野",
        "国际化视野排名",
        "篇均被引",
        "篇均被引排名",
    ],
    "ranking_detail_history",
)

WEIGHT_ARWU = src(
    "weights_four_rankings_2025",
    "四大世界学科2025指标权重.xlsx",
    "软科",
    [
        "学科领域",
        "学科名称",
        "世界一流教师",
        "世界一流成果",
        "高水平研究成果",
        "科研影响力",
        "国际合作",
        "权重",
    ],
    "indicator_weight",
)

WEIGHT_QS = src(
    "weights_four_rankings_2025",
    "四大世界学科2025指标权重.xlsx",
    "QS",
    [
        "大类",
        "英文学科/英文排名网站",
        "英文学科/指标解释中",
        "中文学科",
        "学术声誉",
        "雇主声誉",
        "篇均被引",
        "H指数",
        "IRN",
        "合计",
        "同济学科",
    ],
    "indicator_weight",
)

WEIGHT_USNEWS = src(
    "weights_four_rankings_2025",
    "四大世界学科2025指标权重.xlsx",
    "usnews",
    [
        "US News学科领域",
        "细分学科",
        "全球研究声誉",
        "区域研究声誉",
        "出版物",
        "图书",
        "会议",
        "标准化引用影响",
        "总引用次数",
        "被引用次数最多的 10% 的出版物数量",
        "被引用次数最多的 10% 的出版物占总出版物的百分比",
        "在各自领域中被引用次数最多的前 1% 的高被引论文数量",
        "被引用次数最多的前 1% 的论文占总出版物的百分比",
        "国际合作——相对于国家",
        "国际合作",
    ],
    "indicator_weight",
)

WEIGHT_THE = src(
    "weights_four_rankings_2025",
    "四大世界学科2025指标权重.xlsx",
    "the",
    [
        "一级指标名称",
        "二级指标名称",
        "大学排名",
        "艺术与人文",
        "医学与健康",
        "工程学",
        "计算机科学",
        "生命科学",
        "自然科学",
        "社会科学",
    ],
    "indicator_weight",
)

DOUBLE_FIRST_CLASS = src(
    "domestic_double_first_class",
    "全国双一流学科明细表2022&2017.v2.xlsx",
    "双一流学科（第二轮-不含清北）明细",
    ["学校名称", "一级学科", "批次", "备注", "省份", "年份"],
    "peer_scope",
)

ROUND5 = src(
    "domestic_eval_round5_incomplete",
    "第五轮评估结果（不完全）20260508.xlsx",
    "数据",
    ["单位名称", "学科门类", "一级学科", "评估结果"],
    "domestic_evaluation",
)

ROUND5_ENRICHED = src(
    "domestic_eval_round5_analysis_copy",
    "副本第五轮评估结果（不完全）20260508(分析).xlsx",
    "数据",
    [
        "单位名称",
        "学科门类",
        "学科代码",
        "一级学科",
        "第五轮评估结果",
        "第四轮学科评估结果",
        "第三轮学科得分",
        "第三轮等级",
        "省份",
        "城市",
        "双一流",
    ],
    "domestic_evaluation_enriched",
)

ROUND34 = src(
    "domestic_eval_rounds_3_4",
    "全国高校第四轮&第三轮学科评估结果.xlsx",
    "数据",
    [
        "一级学科名称",
        "一级学科代码",
        "第四轮评估结果",
        "学校名称",
        "第三轮得分",
        "第三轮等级",
        "省份",
        "城市",
        "双一流",
    ],
    "domestic_evaluation",
)

USNEWS_HISTORY_SOURCES = [
    src(
        "rank_usnews_2021",
        "2021US News世界学科排名2020年发布.xlsx",
        "Sheet1",
        ["subjectrank", "subject", "university", "university_zh", "location", "pubyear", "globalscore", "subjectscore"],
        "ranking_detail",
    ),
    src(
        "rank_usnews_2022",
        "2022US News世界学科排名20211026.xlsx",
        "Sheet2",
        [
            "subject",
            "subjectrank",
            "university",
            "university_zh",
            "pubyear",
            "overallscore",
            "globalresearchreputation",
            "regionalresearchreputation",
            "publications",
            "normalizedcitationimpact",
        ],
        "ranking_detail",
    ),
    src(
        "rank_usnews_2023",
        "2023US News世界学科排名20221026.xlsx",
        "sheet",
        [
            "Rank",
            "Name",
            "Country",
            "发布时间",
            "Time",
            "Subject",
            "OVERALL_SCORE",
            "Global_Research_Reputatio",
            "Regional_Research_Reputation",
            "Publications",
        ],
        "ranking_detail",
    ),
    src(
        "rank_usnews_2024_2025",
        "2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx",
        "全球排名",
        ["学科", "学科中文", "名称", "中文名称", "国家", "总得分", "发布年份", "排名年份", "世界排名"],
        "ranking_detail",
    ),
    USNEWS_2025_2026,
]

QS_HISTORY_SOURCES = [
    src(
        "rank_qs_2023",
        "2023年QS世界学科排名.xlsx",
        "2023",
        ["学科", "地区", "高校名称", "国际排名", "综合得分"],
        "ranking_detail",
    ),
    src(
        "rank_qs_2024",
        "2024年QS世界学科排名-20240412.xlsx",
        "数据",
        ["中文名称", "英文名称", "发布年度", "国际排名", "所在地区", "学科英文", "学科中文", "总得分", "H指数", "学术声誉"],
        "ranking_detail",
    ),
    src(
        "rank_qs_2025",
        "2025年QS世界大学学科排名20250313.xlsx",
        "明细数",
        ["年份", "学科中文", "学科领域", "地区", "排名", "大学", "综合得分", "学术声誉", "论文篇均引用率", "雇主声誉", "H指数排名"],
        "ranking_detail",
    ),
    QS_2026,
]

ARWU_HISTORY_SOURCES = [
    src(
        "rank_arwu_2023",
        "2023年软科世界一流学科排名-20231030.xlsx",
        "名单",
        ["学校名称", "中文名称", "发布年度", "国际排名", "所在地区", "学科领域", "总得分", "重要期刊论文数", "论文标准化影响力", "国际合作论文比例"],
        "ranking_detail",
    ),
    src(
        "rank_arwu_2024",
        "2024年软科世界一流学科排名-20241111.xlsx",
        "所有高校",
        ["中文校名", "英文校名", "国家", "学科领域", "排名", "总分", "年份", "世界一流教师", "世界一流成果", "高水平研究成果", "科研影响力", "国际合作"],
        "ranking_detail",
    ),
    ARWU_2025,
]


def build_reference_artifact_index(reference: dict[str, Any]) -> dict[str, Any]:
    captions = []
    image_counter = 0
    table_caption_counter = 0
    for paragraph in reference["paragraphs"]:
        kind = paragraph["kind"]
        if kind not in {"figure_caption", "table_caption"}:
            continue
        if kind == "figure_caption":
            image_counter += 1
            artifact_id = f"figure_{image_counter:02d}"
        else:
            table_caption_counter += 1
            artifact_id = f"table_caption_{table_caption_counter:02d}"
        captions.append(
            {
                "artifact_id": artifact_id,
                "paragraph_index": paragraph["paragraph_index"],
                "artifact_type": "chart" if kind == "figure_caption" else "table",
                "caption": paragraph["text"],
                "notes": "参考报告存在图号/表号重复和待更新字样，artifact_id 按出现顺序编号。",
            }
        )

    physical_tables = [
        {
            "physical_table_id": f"physical_table_{table['table_index']:02d}",
            "table_index": table["table_index"],
            "rows": table["rows"],
            "columns": table["columns"],
            "sample_header": table["sample_rows"][0] if table["sample_rows"] else [],
        }
        for table in reference["tables"]
    ]

    physical_images = [
        {
            "physical_image_id": f"physical_image_{image['image_index']:02d}",
            "image_index": image["image_index"],
            "width_cm": image["width_cm"],
            "height_cm": image["height_cm"],
        }
        for image in reference["images"]
    ]

    return {
        "version": 1,
        "source_reference_report": reference["file"],
        "caption_count": len(captions),
        "physical_table_count": len(physical_tables),
        "physical_image_count": len(physical_images),
        "caption_artifacts": captions,
        "physical_tables": physical_tables,
        "physical_images": physical_images,
    }


def recipe(
    artifact_id: str,
    artifact_type: str,
    section: str,
    reference_caption: str,
    readiness: str,
    purpose: str,
    data_sources: list[dict[str, Any]],
    join_keys: list[str],
    filters: list[str],
    transforms: list[str],
    output_data: list[str],
    visual_or_table_spec: dict[str, Any],
    validation_checks: list[str],
    risks: list[str],
    priority: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "section": section,
        "reference_caption": reference_caption,
        "readiness": readiness,
        "priority": priority,
        "purpose": purpose,
        "data_sources": data_sources,
        "join_keys": join_keys,
        "filters": filters,
        "transforms": transforms,
        "output_data": output_data,
        "visual_or_table_spec": visual_or_table_spec,
        "validation_checks": validation_checks,
        "risks": risks,
    }


def build_recipes() -> dict[str, Any]:
    recipes = [
        recipe(
            "figure_01_tongji_subject_ranking_overview",
            "chart",
            "一、概述",
            "图1、同济大学xx学科国际排名",
            "ready_after_fact_ranking",
            "用四大榜单最新年份展示同济目标学科的国际排名概览。",
            [MAPPING_SOURCE, TONGJI_MAPPING_SOURCE, ARWU_2025, QS_2026, USNEWS_2025_2026, THE_2026],
            ["目标一级学科 -> 四大榜单学科名称", "学校名称/中文名称 = 同济大学", "发布年度/排名年度"],
            ["目标学科对应的四大榜单学科", "同济大学", "每个榜单取最新可用年份"],
            [
                "解析国际排名区间，保留rank_raw并计算rank_midpoint",
                "生成四大榜单一行一条记录",
                "若某榜单没有该学科数据，则保留缺失并在正文说明",
            ],
            ["ranking_source", "release_year", "ranking_year", "rank_raw", "rank_midpoint", "total_score"],
            {
                "recommended_chart": "横向条形图或点图",
                "x_axis": "rank_midpoint",
                "y_axis": "ranking_source",
                "direction_note": "排名数值越小越好，图中应反转轴或明确标注。",
            },
            ["四大榜单最多各一条同济记录", "rank_raw与rank_midpoint同时存在", "缺失榜单需列入notes"],
            ["不同榜单发布年度和排名年度不一致，图标题必须说明口径。"],
            "P1",
        ),
        recipe(
            "figure_02_indicator_commonality",
            "chart",
            "二、xx学科国际排名指标介绍",
            "图2、XX学科在世界学科排名中指标共性",
            "partial_needs_indicator_grouping",
            "把四大榜单指标归并为科研、声誉、国际化、教学/环境、产业/转化等共性类别，比较权重结构。",
            [WEIGHT_ARWU, WEIGHT_QS, WEIGHT_USNEWS, WEIGHT_THE, MAPPING_SOURCE],
            ["目标学科 -> QS/软科/US News细分学科/THE领域", "indicator_name -> common_indicator_group"],
            ["目标学科或THE对应领域", "四大榜单"],
            [
                "清洗各权重表的多级表头",
                "把原始指标映射到common_indicator_group",
                "按榜单聚合每个common_indicator_group的权重",
                "输出四大榜单权重矩阵",
            ],
            ["ranking_source", "common_indicator_group", "weight_percent", "raw_indicator_names"],
            {
                "recommended_chart": "堆叠条形图或雷达图",
                "category_order": ["科研", "声誉", "国际化", "教学/环境", "产业/转化", "其他"],
            },
            ["每个榜单权重合计接近100%或记录原表特殊口径", "保留原始指标到共性类别的映射表"],
            ["共性类别映射带有人工判断，必须可审查。"],
            "P1",
        ),
        recipe(
            "figure_03_arwu_indicator_weight",
            "chart",
            "二、xx学科国际排名指标介绍/软科",
            "图3、软科世界一流学科数学指标权重",
            "ready_after_weight_cleaning",
            "展示软科目标学科各指标权重。",
            [WEIGHT_ARWU, MAPPING_SOURCE],
            ["一级学科名称 -> 软科世界一流学科对应名称", "学科名称"],
            ["目标软科学科名称"],
            ["处理软科权重表两行表头", "抽取权重数值列", "转成长表：indicator, weight"],
            ["indicator_name", "weight", "indicator_group"],
            {"recommended_chart": "环形图或水平条形图", "sort": "按权重降序"},
            ["目标学科权重合计与原表合计一致", "空指标不进入图表"],
            ["软科权重表有多级表头，不能只读取第一行。"],
            "P1",
        ),
        recipe(
            "figure_04_qs_indicator_weight",
            "chart",
            "二、xx学科国际排名指标介绍/QS",
            "图4、软科世界一流学科数学指标权重（参考报告疑似标题误写，实际应为QS指标权重）",
            "ready_after_weight_cleaning",
            "展示QS目标学科各指标权重。",
            [WEIGHT_QS, MAPPING_SOURCE],
            ["一级学科名称 -> QS对应的学科名称", "中文学科/英文学科"],
            ["目标QS学科名称"],
            ["处理QS权重表第二行真实表头", "抽取学术声誉、雇主声誉、篇均被引、H指数、IRN等权重"],
            ["indicator_name", "weight"],
            {"recommended_chart": "环形图或水平条形图", "sort": "按权重降序"},
            ["权重合计应为1或100%", "标题需修正为QS而非软科"],
            ["参考报告标题疑似复制错误，后续生成报告时应纠正。"],
            "P1",
        ),
        recipe(
            "figure_05_usnews_indicator_weight",
            "chart",
            "二、xx学科国际排名指标介绍/US News",
            "图3、U.S.News学科排名数学学科指标权重",
            "ready_after_weight_cleaning",
            "展示US News目标学科各指标权重。",
            [WEIGHT_USNEWS, MAPPING_SOURCE],
            ["一级学科名称 -> U.S.NEWS学科排名对应名称", "细分学科"],
            ["目标US News学科名称"],
            ["抽取目标细分学科权重行", "过滤不适用指标", "转成长表"],
            ["indicator_name", "weight", "is_applicable"],
            {"recommended_chart": "水平条形图", "sort": "按权重降序"},
            ["权重合计接近100%", "不适用字段要被排除或标注"],
            ["参考报告图号重复，后续应重新编号。"],
            "P1",
        ),
        recipe(
            "figure_06_the_indicator_weight",
            "chart",
            "二、xx学科国际排名指标介绍/THE",
            "图4、THE世界学科排名自然科学领域指标权重",
            "ready_after_weight_cleaning",
            "展示THE目标领域各一级指标权重。",
            [WEIGHT_THE, MAPPING_SOURCE],
            ["一级学科名称 -> THE对应领域", "THE领域列名"],
            ["目标THE领域，例如自然科学"],
            ["在THE权重表中选取目标领域列", "按一级指标或二级指标聚合权重"],
            ["indicator_group", "indicator_name", "weight"],
            {"recommended_chart": "水平条形图或环形图", "sort": "按报告常用指标顺序"},
            ["目标领域权重合计接近100%", "一级指标和二级指标不要重复计数"],
            ["THE表同时有大学排名和各领域列，需要选对领域列。"],
            "P1",
        ),
        recipe(
            "figure_07_all_rankings_history",
            "chart",
            "三、xx学科排名历史发展分析",
            "图5、同济xx学科在世界学科排名中的历史（排名区间的取值中间位次）",
            "ready_after_fact_ranking",
            "展示同济目标学科在四大榜单中的历史排名趋势。",
            [MAPPING_SOURCE, TONGJI_MAPPING_SOURCE, *ARWU_HISTORY_SOURCES, *QS_HISTORY_SOURCES, *USNEWS_HISTORY_SOURCES, THE_HISTORY],
            ["目标学科 -> 各榜单学科名称", "学校名称/中文名称/中文校名 = 同济大学", "发布年度/排名年度"],
            ["同济大学", "目标学科", "每个榜单可用年份"],
            [
                "统一不同文件的学校、学科、年份、排名字段",
                "解析排名区间为rank_midpoint",
                "按ranking_source和release_year排序",
                "保留每条记录source_file和source_sheet",
            ],
            ["ranking_source", "release_year", "ranking_year", "rank_raw", "rank_midpoint", "total_score", "source_file"],
            {"recommended_chart": "多折线趋势图", "y_axis": "rank_midpoint", "invert_y_axis": True},
            ["同济每榜单每年份最多一条", "排名区间解析成功率100%或列出异常", "趋势图使用rank_midpoint但表格保留rank_raw"],
            ["QS/US News历年字段名差异大，必须先入fact_ranking再画图。"],
            "P1",
        ),
        recipe(
            "table_01_arwu_history_detail",
            "table",
            "三、xx学科排名历史发展分析/软科",
            "表3、xx学科在软科排名中的细分指标排名历史（待更新）",
            "ready_after_fact_ranking_indicator",
            "展示同济目标学科在软科历年排名和分项指标表现。",
            [MAPPING_SOURCE, *ARWU_HISTORY_SOURCES],
            ["目标学科 -> 软科学科名称", "学校名称/中文校名 = 同济大学", "发布年度"],
            ["同济大学", "目标软科学科名称"],
            [
                "统一2023/2024/2025软科字段",
                "保留世界排名、地区排名、总得分和分项指标",
                "如需要相对排名，在同学科同年度全量高校中重算",
            ],
            ["release_year", "world_rank_raw", "mainland_rank", "total_score", "indicator_scores", "indicator_relative_ranks"],
            {"recommended_table": "年份为列、指标为行的历史表", "keep_header_repeat": True},
            ["年份列完整", "同济行可追溯", "指标字段跨年份名称对齐"],
            ["2023/2024/2025软科指标字段名称不完全一致，需要字段别名映射。"],
            "P2",
        ),
        recipe(
            "table_02_usnews_history_detail",
            "table",
            "三、xx学科排名历史发展分析/US News",
            "表2、xx学科在U.S.News学科排名中的细分指标排名历史（待更新）",
            "ready_after_fact_ranking_indicator",
            "展示同济目标学科在US News历年排名和分项指标表现。",
            [MAPPING_SOURCE, *USNEWS_HISTORY_SOURCES],
            ["目标学科 -> US News学科名称", "同济大学名称别名", "发布年度/排名年度"],
            ["同济大学", "目标US News学科名称"],
            [
                "按年份统一US News不同字段命名",
                "保留总排名、总得分、声誉、论文、引用、高被引、国际合作等指标排名",
                "对缺失年份或缺失指标标注NA",
            ],
            ["release_year", "ranking_year", "world_rank_raw", "total_score", "indicator_ranks"],
            {"recommended_table": "年份为列、指标为行的历史表"},
            ["每个指标的方向和口径一致", "缺失值不填0"],
            ["US News各年份字段差异最大，需要单独清洗器。"],
            "P2",
        ),
        recipe(
            "figure_08_usnews_history_trend",
            "chart",
            "三、xx学科排名历史发展分析/US News",
            "图6、xx学科在U.S.News学科排名中的历史（趋势图分析）",
            "ready_after_fact_ranking",
            "展示US News目标学科历史排名趋势，可与表2共用数据。",
            [MAPPING_SOURCE, *USNEWS_HISTORY_SOURCES],
            ["目标US News学科名称", "同济大学", "发布年度/排名年度"],
            ["同济大学", "目标US News学科名称"],
            ["从fact_ranking筛选US News", "解析rank_midpoint", "按年份绘制趋势"],
            ["release_year", "ranking_year", "rank_raw", "rank_midpoint", "total_score"],
            {"recommended_chart": "折线图", "invert_y_axis": True},
            ["与table_02_usnews_history_detail使用同一底层数据"],
            ["如果年份不连续，图中要保持真实年份间隔。"],
            "P2",
        ),
        recipe(
            "table_03_the_history_detail",
            "table",
            "三、xx学科排名历史发展分析/THE",
            "表4、xx学科在THE排名中的细分指标排名历史（待更新）",
            "ready_after_fact_ranking_indicator",
            "展示同济目标领域在THE历年排名和分项指标表现。",
            [MAPPING_SOURCE, THE_HISTORY],
            ["目标学科 -> THE对应领域", "中文名称 = 同济大学", "发布年度/排名年度"],
            ["同济大学", "目标THE领域"],
            ["优先使用THE总库数据sheet", "抽取总排名、总分、教学/科研环境/科研质量/商业收入/国际化等分项"],
            ["release_year", "ranking_year", "world_rank_raw", "total_score", "indicator_scores", "indicator_ranks"],
            {"recommended_table": "年份为列、指标为行的历史表"},
            ["THE当前表与历史总库当前年份能互相校验"],
            ["THE在2023后指标体系变化，跨年比较需要在正文说明。"],
            "P2",
        ),
        recipe(
            "table_04_mainland_rank_band_distribution",
            "table",
            "四、对标高校整体分析",
            "表5、2025年发布的四大国际排名中内地高校位次分布",
            "ready_after_fact_ranking",
            "统计最新年份四大榜单中，中国内地高校在前50、51-100、101-200等区间的数量。",
            [ARWU_2025, QS_2026, USNEWS_2025_2026, THE_2026, MAPPING_SOURCE],
            ["目标学科 -> 四大榜单学科", "所在地区 = 中国内地", "国际排名"],
            ["中国内地高校", "目标学科", "前200或报告指定范围"],
            [
                "解析排名区间为rank_midpoint",
                "按榜单统计排名分档数量",
                "注意QS 2026与其他榜单发布年度口径不同，表题需按数据实际年份改写",
            ],
            ["ranking_source", "rank_band", "mainland_university_count"],
            {"recommended_table": "榜单为列、位次分档为行"},
            ["各榜单计数之和等于对应筛选结果总数", "前200过滤口径一致"],
            ["参考表题写2025年发布，但当前数据含2026 QS/THE，需生成时改成最新可用年份口径。"],
            "P1",
        ),
        recipe(
            "table_05_arwu_mainland_peer_ranking",
            "table",
            "四、对标高校整体分析/软科",
            "表7、软科排名中内地高校位于前列的比较",
            "ready_after_fact_ranking",
            "列出软科目标学科中国内地高校前列排名，并展示多年度变化。",
            [MAPPING_SOURCE, *ARWU_HISTORY_SOURCES],
            ["目标软科学科名称", "所在地区/国家 = 中国内地", "学校名称"],
            ["中国内地高校", "目标软科学科", "前200或前N"],
            ["统一软科2023-2025排名字段", "按最新年份排序", "保留历年排名列"],
            ["university_name", "province_or_region", "rank_by_year", "latest_rank_midpoint"],
            {"recommended_table": "学校为行、年份为列"},
            ["同济大学必须出现在表中或说明未进入筛选范围", "排名区间保留原文"],
            ["需要省份字段时软科只有所在地区，可能要用双一流/评估表补省份。"],
            "P2",
        ),
        recipe(
            "table_06_usnews_mainland_peer_ranking",
            "table",
            "四、对标高校整体分析/US News",
            "表6、U.S.News排名中内地高校位于前列的比较",
            "ready_after_fact_ranking",
            "列出US News目标学科中国内地高校前列排名，并展示多年度变化。",
            [MAPPING_SOURCE, *USNEWS_HISTORY_SOURCES],
            ["目标US News学科名称", "所在地区/国家 = 中国内地", "学校名称"],
            ["中国内地高校", "目标US News学科", "前200或前N"],
            ["统一US News多年度排名字段", "按最新年份排序", "保留历年排名列"],
            ["university_name", "province_or_region", "rank_by_year", "latest_rank_midpoint"],
            {"recommended_table": "学校为行、年份为列"},
            ["多年度字段成功对齐", "同济大学位置可定位"],
            ["US News 2021-2023国家/地区字段和学校中文名字段不完全一致。"],
            "P2",
        ),
        recipe(
            "table_07_qs_mainland_peer_ranking",
            "table",
            "四、对标高校整体分析/QS",
            "表：QS排名中内地高校位于前列的比较（参考报告表7样式）",
            "ready_after_fact_ranking",
            "列出QS目标学科中国内地高校前列排名，并展示多年度变化。",
            [MAPPING_SOURCE, *QS_HISTORY_SOURCES],
            ["目标QS学科名称", "所在地区/地区 = 中国内地", "学校名称"],
            ["中国内地高校", "目标QS学科", "前200或前N"],
            ["统一QS 2023-2026字段", "按最新年份排序", "保留历年排名列"],
            ["university_name", "province_or_region", "rank_by_year", "latest_rank_midpoint"],
            {"recommended_table": "学校为行、年份为列"},
            ["QS不同年份学科字段成功对齐"],
            ["参考报告中QS段落和表号较混乱，需要生成时统一编号。"],
            "P2",
        ),
        recipe(
            "table_08_the_mainland_peer_ranking",
            "table",
            "四、对标高校整体分析/THE",
            "表8、THE排名中内地高校位于前列的比较",
            "ready_after_fact_ranking",
            "列出THE目标领域中国内地高校前列排名，并展示多年度变化。",
            [MAPPING_SOURCE, THE_HISTORY],
            ["目标THE领域", "所在地区 = 中国内地", "中文名称"],
            ["中国内地高校", "目标THE领域", "前200或前N"],
            ["用THE总库统一历史年份", "按最新年份排序", "保留历年排名列"],
            ["university_name", "province_or_region", "rank_by_year", "latest_rank_midpoint"],
            {"recommended_table": "学校为行、年份为列"},
            ["THE当前明细与历史总库最新年份一致"],
            ["THE按领域而非细分一级学科，需在标题说明。"],
            "P2",
        ),
        recipe(
            "table_09_combined_peer_ranking_matrix",
            "table",
            "四、对标高校整体分析",
            "参考报告物理表8：四大榜单合并对标矩阵",
            "ready_after_fact_ranking",
            "把同一批对标高校在四大榜单多年度排名合并为一个宽表。",
            [MAPPING_SOURCE, *ARWU_HISTORY_SOURCES, *QS_HISTORY_SOURCES, *USNEWS_HISTORY_SOURCES, THE_HISTORY, DOUBLE_FIRST_CLASS, ROUND5_ENRICHED],
            ["peer_scope学校名单", "目标学科", "四大榜单学科名称", "学校名称"],
            ["对标高校范围由用户或配置确定", "目标学科"],
            [
                "先确定peer_scope",
                "分别连接四大榜单fact_ranking",
                "生成宽表，多级表头：学校、地区、各榜单年度排名",
            ],
            ["university_name", "province", "peer_scope_reason", "rank_matrix_by_source_year"],
            {"recommended_table": "宽表，必要时横向页面或拆分为多个表"},
            ["所有列都有榜单和年份说明", "缺失排名用空值而不是0"],
            ["宽表列很多，插入Word时可能超宽；也可以拆成四张表。"],
            "P3",
        ),
        recipe(
            "figure_09_arwu_peer_indicator_relative_rank",
            "chart",
            "五、对标高校分指标分析/软科",
            "图8、软科排名前200位内地高校分项指标相对排名",
            "ready_after_fact_ranking_indicator",
            "比较软科前200内地高校在分项指标上的相对排名，突出同济优势和短板。",
            [MAPPING_SOURCE, ARWU_2025, WEIGHT_ARWU],
            ["目标软科学科名称", "所在地区 = 中国内地", "国际排名 <= 200或rank_midpoint <= 200"],
            ["中国内地高校", "目标软科学科", "前200"],
            [
                "筛选前200内地高校",
                "对每个分项指标按得分降序重算相对排名",
                "为同济大学高亮",
                "可按总排名排序学校",
            ],
            ["university_name", "world_rank_raw", "indicator_name", "indicator_score", "indicator_relative_rank", "is_tongji"],
            {"recommended_chart": "多指标点图/热力表", "highlight": "同济大学"},
            ["相对排名计算样本数等于前200内地高校数", "分项指标只使用数值字段"],
            ["软科当前表给的是得分，不是指标排名，需要重算相对排名。"],
            "P1",
        ),
        recipe(
            "figure_10_qs_peer_indicator_relative_rank",
            "chart",
            "五、对标高校分指标分析/QS",
            "QS排名前列内地高校分项指标相对排名（参考报告QS段落缺图题）",
            "ready_after_fact_ranking_indicator",
            "比较QS目标学科内地高校在学术声誉、雇主声誉、引用、H指数、IRN等指标上的表现。",
            [MAPPING_SOURCE, QS_2026, WEIGHT_QS],
            ["目标QS学科名称", "所在地区 = 中国内地", "国际排名或rank_midpoint <= 200"],
            ["中国内地高校", "目标QS学科", "前200"],
            ["筛选内地高校", "按各分项得分重算相对排名", "高亮同济"],
            ["university_name", "world_rank_raw", "indicator_name", "indicator_score", "indicator_relative_rank", "is_tongji"],
            {"recommended_chart": "多指标点图/热力表", "highlight": "同济大学"},
            ["QS指标字段存在且为数值", "总得分和分项得分不混用"],
            ["部分QS学科可能没有所有指标，需按非空字段绘制。"],
            "P2",
        ),
        recipe(
            "figure_11_usnews_peer_indicator_relative_rank",
            "chart",
            "五、对标高校分指标分析/US News",
            "图7、U.S.News排名前200位内地高校分项指标相对排名",
            "ready_after_fact_ranking_indicator",
            "比较US News前200内地高校在声誉、论文、引用、高被引、国际合作等指标排名上的表现。",
            [MAPPING_SOURCE, USNEWS_2025_2026, WEIGHT_USNEWS],
            ["目标US News学科名称", "所在地区 = 中国内地", "国际排名 <= 200或rank_midpoint <= 200"],
            ["中国内地高校", "目标US News学科", "前200"],
            [
                "筛选前200内地高校",
                "US News当前表分项多为排名字段，可直接使用indicator_rank",
                "把排名字段转成长表",
                "高亮同济大学",
            ],
            ["university_name", "world_rank_raw", "indicator_name", "indicator_rank", "is_tongji"],
            {"recommended_chart": "多指标点图，排名轴反转", "highlight": "同济大学"},
            ["所有indicator_rank为数值排名或缺失", "排名越小越好要在图中体现"],
            ["US News是排名字段，不是得分字段，不能按降序重算。"],
            "P1",
        ),
        recipe(
            "figure_12_the_peer_indicator_relative_rank",
            "chart",
            "五、对标高校分指标分析/THE",
            "图9、THE排名前200位内地高校分项指标相对排名",
            "ready_after_fact_ranking_indicator",
            "比较THE前200内地高校在教学、科研环境、科研质量、商业收入、国际化等指标上的表现。",
            [MAPPING_SOURCE, THE_HISTORY, THE_2026, WEIGHT_THE],
            ["目标THE领域", "所在地区 = 中国内地", "国际排名 <= 200或rank_midpoint <= 200"],
            ["中国内地高校", "目标THE领域", "前200"],
            [
                "优先用THE_HISTORY数据sheet，因为含分项排名",
                "如当前表只有分项得分，则在同领域同年度内重算相对排名",
                "高亮同济大学",
            ],
            ["university_name", "world_rank_raw", "indicator_name", "indicator_score", "indicator_rank_or_relative_rank", "is_tongji"],
            {"recommended_chart": "多指标点图，排名轴反转", "highlight": "同济大学"},
            ["当前年份THE_HISTORY和THE_2026筛选结果一致或差异有说明"],
            ["THE领域比一级学科更粗，需在图题说明。"],
            "P1",
        ),
        recipe(
            "figure_13_paper_quantity_citation_proxy",
            "chart",
            "六、对标高校论文指标分析/论文整体",
            "图10、37所内地高校论文及被引总量及相对排名",
            "partial_proxy_only",
            "用现有排名表中的论文数量、出版物、总被引等代理指标分析论文整体实力。",
            [USNEWS_2025_2026, ARWU_2025, THE_2026, MAPPING_SOURCE],
            ["目标学科", "中国内地高校", "论文/引用相关指标"],
            ["对标高校范围", "目标学科"],
            [
                "优先查找独立论文数据库；当前没有则使用US News出版物排名、总被引频次排名、软科高水平研究成果、THE篇均被引等代理指标",
                "记录proxy_source和proxy_metric",
                "避免把代理指标写成论文数据库统计",
            ],
            ["university_name", "proxy_metric", "proxy_value_or_rank", "proxy_source", "is_tongji"],
            {"recommended_chart": "散点图或双轴谨慎使用；优先分面点图"},
            ["所有代理指标都有source说明", "正文明确不是独立论文库口径"],
            ["缺少参考报告所需的论文总数和总被引原始值，当前只能做代理分析。"],
            "P3",
        ),
        recipe(
            "figure_14_paper_quality_proxy",
            "chart",
            "六、对标高校论文指标分析/论文质量",
            "图11、37所内地高校论文CNCI及篇均被引数及相对排名",
            "partial_proxy_only",
            "用标准化引用影响、篇均被引、高被引比例等代理指标分析论文质量。",
            [USNEWS_2025_2026, THE_2026, ARWU_2025, MAPPING_SOURCE],
            ["目标学科", "中国内地高校", "引用/篇均被引/标准化影响相关指标"],
            ["对标高校范围", "目标学科"],
            [
                "优先独立论文库；若没有，使用US News标准化论文引用影响指数排名、THE篇均被引、软科论文标准化影响力",
                "统一成proxy_quality_metric长表",
            ],
            ["university_name", "proxy_quality_metric", "proxy_value_or_rank", "proxy_source", "is_tongji"],
            {"recommended_chart": "分项点图或热力表"},
            ["代理指标方向明确", "不把排名和得分直接混画在同一数轴"],
            ["没有CNCI原始字段，只能用榜单代理指标。"],
            "P3",
        ),
        recipe(
            "figure_15_highly_cited_proxy",
            "chart",
            "六、对标高校论文指标分析/论文质量",
            "图12、37所内地高校高被引TOP论文量及相对排名",
            "partial_proxy_only",
            "用US News前10%/前1%高被引论文相关排名和软科相关指标代理高被引论文表现。",
            [USNEWS_2025_2026, ARWU_2025, MAPPING_SOURCE],
            ["目标学科", "中国内地高校", "高被引相关指标"],
            ["对标高校范围", "目标学科"],
            [
                "抽取US News前10%出版物数量/比例、前1%高被引论文数量/比例排名",
                "必要时结合软科高水平研究成果指标",
                "统一为长表并高亮同济",
            ],
            ["university_name", "highly_cited_metric", "metric_rank_or_score", "proxy_source", "is_tongji"],
            {"recommended_chart": "多指标点图"},
            ["所有高被引指标原始字段可追溯", "数量类和比例类分开说明"],
            ["缺少真实TOP论文量原始值时，只能做排名代理。"],
            "P3",
        ),
        recipe(
            "figure_16_international_collaboration_proxy",
            "chart",
            "六、对标高校论文指标分析/国际合著",
            "图13、37所内地高校国际合著论文占比及相对排名",
            "partial_proxy_only",
            "用国际合作相关指标代理国际合著论文表现。",
            [USNEWS_2025_2026, ARWU_2025, QS_2026, THE_2026, MAPPING_SOURCE],
            ["目标学科", "中国内地高校", "国际合作/国际网络/国际化相关指标"],
            ["对标高校范围", "目标学科"],
            [
                "抽取US News国际合作排名、软科国际合作论文比例、QS国际网络研究、THE国际化视野",
                "区分论文合作和广义国际化指标",
            ],
            ["university_name", "international_metric", "metric_value_or_rank", "proxy_source", "is_tongji"],
            {"recommended_chart": "点图或条形图"},
            ["国际合作论文口径和国际化视野口径分开标注"],
            ["THE/QS部分是广义国际化，不等同于国际合著论文占比。"],
            "P3",
        ),
        recipe(
            "table_10_domestic_evaluation_peer_comparison",
            "table",
            "三、国内评估",
            "双一流高校第五轮学科评估结果对比（目标模板新增）",
            "ready_with_caveat",
            "比较目标学科相关高校在第五轮、第四轮、第三轮评估及双一流状态中的位置。",
            [ROUND5, ROUND5_ENRICHED, ROUND34, DOUBLE_FIRST_CLASS, TONGJI_MAPPING_SOURCE],
            ["一级学科", "学校名称/单位名称", "双一流学科"],
            ["目标一级学科", "对标高校范围"],
            [
                "用第五轮主表定位最新结果",
                "用分析副本补第四轮、第三轮、省份、双一流字段",
                "用双一流表确认建设学科范围",
            ],
            ["university_name", "province", "round5_result", "round4_result", "round3_score", "round3_grade", "is_double_first_class"],
            {"recommended_table": "学校为行、评估轮次和建设标签为列"},
            ["第五轮不完全数据必须在表注说明", "同济大学记录必须包含"],
            ["第五轮数据不完全，不能做完整全国排名式断言。"],
            "P2",
        ),
        recipe(
            "text_or_table_11_research_frontier_gap",
            "table_or_text",
            "五、国内外高校研究前沿及学科交叉",
            "研究前沿及学科交叉（目标模板标黄）",
            "data_gap",
            "该章节需要教师方向、论文主题、研究前沿或交叉学科数据；当前Excel盘点未发现专门数据源。",
            [TONGJI_MAPPING_SOURCE, MAPPING_SOURCE],
            ["学科名称", "学院", "榜单学科"],
            ["目标学科"],
            [
                "当前只能列出同济学院/学科映射和四大榜单覆盖关系",
                "如需研究前沿，应补充教师研究方向、论文关键词、项目/平台、顶尖高校方向数据",
            ],
            ["available_context", "missing_data_need"],
            {"recommended_output": "缺口说明表，或补数据后再生成正式分析"},
            ["不能在无数据情况下生成强结论"],
            ["当前数据不足。"],
            "P4",
        ),
    ]

    return {
        "version": 1,
        "status": "draft_field_level",
        "scope": "参考报告中的主要图、表，以及目标模板新增国内评估/研究前沿位置。",
        "global_required_dimensions": ["dim_subject", "dim_university", "dim_indicator"],
        "recipes": recipes,
    }


def validate_sources(recipes: dict[str, Any], registry: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    registry_files = {entry["file"]: entry for entry in registry["excel_sources"]}
    workbook_cache: dict[tuple[str, str], set[str]] = {}

    def sheet_tokens(file_name: str, sheet_name: str) -> set[str] | None:
        key = (file_name, sheet_name)
        if key in workbook_cache:
            return workbook_cache[key]
        path = PROJECT_DIR / "data" / file_name
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
            if sheet_name not in wb.sheetnames:
                wb.close()
                return None
            ws = wb[sheet_name]
            tokens: set[str] = set()
            for row in ws.iter_rows(min_row=1, max_row=min(8, ws.max_row), values_only=True):
                for value in row:
                    if value is None:
                        continue
                    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
                    if text:
                        tokens.add(text)
            wb.close()
            workbook_cache[key] = tokens
            return tokens
        except Exception:
            return None

    recipe_results = []
    readiness_counter = Counter()
    priority_counter = Counter()
    missing_files = []
    missing_sheets = []
    missing_fields = []

    for item in recipes["recipes"]:
        readiness_counter[item["readiness"]] += 1
        priority_counter[item["priority"]] += 1
        item_missing_files = []
        item_missing_sheets = []
        item_missing_fields = []
        for source in item["data_sources"]:
            file_name = source["file"]
            sheet_name = source["sheet"]
            if file_name not in registry_files:
                item_missing_files.append(file_name)
                missing_files.append({"artifact_id": item["artifact_id"], "file": file_name})
                continue
            tokens = sheet_tokens(file_name, sheet_name)
            if tokens is None:
                item_missing_sheets.append({"file": file_name, "sheet": sheet_name})
                missing_sheets.append({"artifact_id": item["artifact_id"], "file": file_name, "sheet": sheet_name})
                continue
            for field in source["fields"]:
                if field not in tokens:
                    item_missing_fields.append({"file": file_name, "sheet": sheet_name, "field": field})
                    missing_fields.append({"artifact_id": item["artifact_id"], "file": file_name, "sheet": sheet_name, "field": field})

        recipe_results.append(
            {
                "artifact_id": item["artifact_id"],
                "readiness": item["readiness"],
                "priority": item["priority"],
                "source_count": len(item["data_sources"]),
                "missing_files": item_missing_files,
                "missing_sheets": item_missing_sheets,
                "missing_fields": item_missing_fields,
            }
        )

    return {
        "version": 1,
        "recipe_count": len(recipes["recipes"]),
        "readiness_counts": dict(readiness_counter),
        "priority_counts": dict(priority_counter),
        "missing_file_count": len(missing_files),
        "missing_sheet_count": len(missing_sheets),
        "missing_field_count": len(missing_fields),
        "missing_files": missing_files,
        "missing_sheets": missing_sheets,
        "missing_fields": missing_fields[:200],
        "recipe_results": recipe_results,
        "notes": [
            "missing_field_count 包含多级表头或历史表字段别名导致的预期差异，需在清洗器中处理。",
            "如果字段在第二行才是真实表头，data_catalog第一行表头校验会提示缺失，这是权重表的正常风险。",
        ],
    }


def build_gaps_markdown(recipes: dict[str, Any], validation: dict[str, Any]) -> str:
    gap_recipes = [
        item
        for item in recipes["recipes"]
        if item["readiness"] in {"partial_proxy_only", "partial_needs_indicator_grouping", "data_gap", "ready_with_caveat"}
    ]
    lines = [
        "# 图表数据缺口与风险",
        "",
        "## 总体判断",
        "",
        "- 排名历史、对标高校整体、四大榜单分项指标这三类图表可以由现有数据支撑。",
        "- 指标权重图可以支撑，但权重表存在多级表头，需要专门清洗。",
        "- 论文实力图目前只能做代理分析，缺少独立论文库。",
        "- 研究前沿及学科交叉目前是明确数据缺口。",
        "",
        "## 需要重点处理的 artifact",
        "",
    ]
    for item in gap_recipes:
        lines.append(f"### {item['artifact_id']}")
        lines.append("")
        lines.append(f"- 参考标题：{item['reference_caption']}")
        lines.append(f"- 状态：`{item['readiness']}`")
        lines.append(f"- 目的：{item['purpose']}")
        lines.append("- 风险：")
        for risk in item["risks"]:
            lines.append(f"  - {risk}")
        lines.append("")

    lines.extend(
        [
            "## 字段校验提示",
            "",
            f"- 缺失文件数：{validation['missing_file_count']}",
            f"- 缺失 sheet 数：{validation['missing_sheet_count']}",
            f"- 字段校验提示数：{validation['missing_field_count']}",
            "",
            "字段提示并不一定代表不可做：权重表和部分历史表存在多级表头、字段别名、旧版英文字段，清洗器需要逐源处理。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_priority_markdown(recipes: dict[str, Any]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in recipes["recipes"]:
        groups.setdefault(item["priority"], []).append(item)

    lines = [
        "# 图表/表格实现优先级",
        "",
        "## P1：优先做，支撑主闭环",
        "",
    ]
    for item in groups.get("P1", []):
        lines.append(f"- `{item['artifact_id']}`：{item['reference_caption']}；状态 `{item['readiness']}`")

    lines.extend(["", "## P2：第二批，扩展历史表和国内评估", ""])
    for item in groups.get("P2", []):
        lines.append(f"- `{item['artifact_id']}`：{item['reference_caption']}；状态 `{item['readiness']}`")

    lines.extend(["", "## P3：第三批，注意版面或代理口径", ""])
    for item in groups.get("P3", []):
        lines.append(f"- `{item['artifact_id']}`：{item['reference_caption']}；状态 `{item['readiness']}`")

    lines.extend(["", "## P4：暂缓，除非补数据", ""])
    for item in groups.get("P4", []):
        lines.append(f"- `{item['artifact_id']}`：{item['reference_caption']}；状态 `{item['readiness']}`")

    lines.extend(
        [
            "",
            "## 推荐第一个闭环",
            "",
            "先做 `figure_07_all_rankings_history`，同时带上 `figure_01_tongji_subject_ranking_overview`。",
            "",
            "原因：这两个图共用 `fact_ranking`，能优先验证学科映射、学校别名、年份口径、排名区间解析和多榜单联表。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_summary_markdown(index: dict[str, Any], recipes: dict[str, Any], validation: dict[str, Any]) -> str:
    if validation["missing_field_count"]:
        field_note = "字段提示主要来自多级表头、旧版字段名和跨年字段别名，不等同于不可做。下一步应该进入结构化入库脚本，把这些字段别名和多级表头规则固化。"
    else:
        field_note = "recipe 中引用的文件、sheet 和字段都已在原始表前几行中找到。下一步应该进入结构化入库脚本，把字段别名、多级表头规则和排名区间解析固化。"
    return f"""# Artifact Recipe 阶段摘要

## 本阶段目标

把参考报告中的图、表，以及目标模板中新增的数据分析位置，拆到字段级数据依赖和处理步骤。

## 产物

- `reference_artifact_index.yaml`：参考报告图题、表题、物理表格和图片索引。
- `artifact_data_recipes.yaml`：每个图表/表格的数据源、字段、联表键、过滤、转换和验证规则。
- `artifact_gaps.md`：缺口、风险和谨慎口径。
- `artifact_priority.md`：实现优先级。
- `recipe_validation.json`：数据源、sheet、字段的自动核验结果。

## 覆盖情况

- 参考报告 caption artifact 数：{index['caption_count']}
- 参考报告物理表格数：{index['physical_table_count']}
- 参考报告物理图片数：{index['physical_image_count']}
- 当前 recipe 数：{validation['recipe_count']}

## 状态统计

{chr(10).join(f"- {key}: {value}" for key, value in validation['readiness_counts'].items())}

## 自动核验

- 缺失文件数：{validation['missing_file_count']}
- 缺失 sheet 数：{validation['missing_sheet_count']}
- 字段提示数：{validation['missing_field_count']}

{field_note}
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reference = load_json(STAGE1_DIR / "reference_report_outline.json")
    catalog = load_json(STAGE1_DIR / "data_catalog.json")
    registry = load_json(GOVERNANCE_DIR / "source_registry.json")

    index = build_reference_artifact_index(reference)
    recipes = build_recipes()
    validation = validate_sources(recipes, registry, catalog)

    write_yaml(OUTPUT_DIR / "reference_artifact_index.yaml", index)
    write_yaml(OUTPUT_DIR / "artifact_data_recipes.yaml", recipes)
    write_json(OUTPUT_DIR / "recipe_validation.json", validation)
    (OUTPUT_DIR / "artifact_gaps.md").write_text(
        build_gaps_markdown(recipes, validation),
        encoding="utf-8",
        newline="\n",
    )
    (OUTPUT_DIR / "artifact_priority.md").write_text(
        build_priority_markdown(recipes),
        encoding="utf-8",
        newline="\n",
    )
    (OUTPUT_DIR / "artifact_recipe_summary.md").write_text(
        build_summary_markdown(index, recipes, validation),
        encoding="utf-8",
        newline="\n",
    )

    print((OUTPUT_DIR / "artifact_recipe_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
