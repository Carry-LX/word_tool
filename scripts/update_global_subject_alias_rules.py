from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "runtime" / "manual_subject_aliases.json"
REPORT_PATH = PROJECT_DIR / "processed" / "qa" / "global_subject_alias_rule_update.md"


DETERMINISTIC_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "QS_BUSINESS_MANAGEMENT_TO_BUSINESS_ADMIN",
        "ranking_source": "QS",
        "subject_ids": ["subject_1202", "subject_1251"],
        "aliases": ["商业与管理研究", "商务与管理研究", "Business & Management Studies"],
        "mapping_class": "deterministic",
        "note": "QS Business & Management Studies 对应工商管理学/工商管理口径。",
    },
    {
        "rule_id": "QS_ACCOUNTING_FINANCE_TO_ECON_BUSINESS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0202", "subject_0251", "subject_1202", "subject_1253"],
        "aliases": ["会计与金融", "会计与金融学", "Accounting & Finance"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Accounting & Finance 跨应用经济学、金融、工商管理学与会计，不强行单学科化。",
    },
    {
        "rule_id": "QS_ENGLISH_LANGUAGE_LITERATURE_TO_LANGUAGE_SUBJECTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0501", "subject_0502"],
        "aliases": ["英语语言和文学", "英语语言与文学", "English Language and Literature"],
        "mapping_class": "broad_multi_subject",
        "note": "英语语言文学在中文/外国语言文学口径间存在交叉，保留多学科连接。",
    },
    {
        "rule_id": "QS_PHYSICS_ASTRONOMY_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0702", "subject_0704"],
        "aliases": ["物理学&天文学", "物理学天文学", "物理与天文学", "Physics & Astronomy"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Physics & Astronomy 覆盖物理学与天文学。",
    },
    {
        "rule_id": "QS_MEDIA_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0503", "subject_0552"],
        "aliases": ["传媒学", "传播学", "传播与媒体研究", "Communication and Media Studies"],
        "mapping_class": "deterministic",
        "note": "QS Communication and Media Studies 对应新闻传播学/新闻与传播。",
    },
    {
        "rule_id": "QS_EARTH_OCEAN_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0707", "subject_0708", "subject_0709"],
        "aliases": ["地球和海洋科学", "地球与海洋科学", "Earth and Marine Sciences"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Earth and Marine Sciences 横跨海洋、地球物理和地质方向。",
    },
    {
        "rule_id": "QS_ARCHITECTURE_BUILT_ENVIRONMENT_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0813", "subject_0833", "subject_0851", "subject_0853"],
        "aliases": ["建筑与建造环境", "建筑与建筑环境", "Architecture & Built Environment"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Architecture & Built Environment 覆盖建筑学和城乡规划相关口径。",
    },
    {
        "rule_id": "QS_ART_DESIGN_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_1357", "subject_1403"],
        "aliases": ["艺术&设计", "艺术设计", "艺术与设计", "Art & Design"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Art & Design 对应设计/设计学。",
    },
    {
        "rule_id": "QS_LIBRARY_INFORMATION_MANAGEMENT_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_1205", "subject_1255"],
        "aliases": ["图书馆及信息管理", "图书馆信息管理", "Library & Information Management"],
        "mapping_class": "deterministic",
        "note": "QS Library & Information Management 对应信息资源管理/图书情报。",
    },
    {
        "rule_id": "QS_MARKETING_TO_BUSINESS_ADMIN",
        "ranking_source": "QS",
        "subject_ids": ["subject_1202", "subject_1251"],
        "aliases": ["市场营销", "Marketing"],
        "mapping_class": "deterministic",
        "note": "市场营销归入工商管理学/工商管理。",
    },
    {
        "rule_id": "QS_DATA_SCIENCE_AI_VARIANTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0811", "subject_0812", "subject_1405"],
        "aliases": ["DataScience", "Data Science", "数据科学与人工智能"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Data Science / AI 横跨控制、计算机和智能科学。",
    },
    {
        "rule_id": "QS_ANATOMY_PHYSIOLOGY_TO_BASIC_MEDICINE",
        "ranking_source": "QS",
        "subject_ids": ["subject_1001"],
        "aliases": ["解剖和生理学", "解剖与生理学", "Anatomy & Physiology"],
        "mapping_class": "deterministic",
        "note": "解剖与生理学归入基础医学。",
    },
    {
        "rule_id": "QS_HISTORY_BROAD_TO_HISTORY_SUBJECTS",
        "ranking_source": "QS",
        "subject_ids": ["subject_0602", "subject_0603"],
        "aliases": ["历史学", "History"],
        "mapping_class": "broad_multi_subject",
        "note": "QS History 不是教育部单一一级学科，连接中国史与世界史。",
    },
    {
        "rule_id": "QS_CLASSICS_ANCIENT_HISTORY_TO_LITERATURE_HISTORY",
        "ranking_source": "QS",
        "subject_ids": ["subject_0501", "subject_0603"],
        "aliases": ["古典文学与古代史", "Classics & Ancient History"],
        "mapping_class": "broad_multi_subject",
        "note": "古典文学与古代史跨文学与世界史，保留多学科连接。",
    },
    {
        "rule_id": "QS_ANTHROPOLOGY_TO_SOCIOLOGY",
        "ranking_source": "QS",
        "subject_ids": ["subject_0303"],
        "aliases": ["人类学", "Anthropology"],
        "mapping_class": "approximate",
        "note": "教育部目录无独立人类学一级学科，暂挂社会学，报告中标记为近似映射。",
    },
    {
        "rule_id": "QS_THEOLOGY_RELIGION_TO_PHILOSOPHY",
        "ranking_source": "QS",
        "subject_ids": ["subject_0101"],
        "aliases": ["神学、神学与宗教研究", "神学神学与宗教研究", "Theology, Divinity & Religious Studies"],
        "mapping_class": "approximate",
        "note": "教育部目录无独立神学一级学科，宗教学方向暂归哲学近似口径。",
    },
    {
        "rule_id": "QS_MUSIC_TO_MUSIC",
        "ranking_source": "QS",
        "subject_ids": ["subject_1352"],
        "aliases": ["Music", "音乐"],
        "mapping_class": "deterministic",
        "note": "QS Music 对应音乐。",
    },
    {
        "rule_id": "QS_AGRI_FORESTRY_BROAD",
        "ranking_source": "QS",
        "subject_ids": [
            "subject_0901",
            "subject_0902",
            "subject_0903",
            "subject_0904",
            "subject_0905",
            "subject_0907",
            "subject_0908",
            "subject_0909",
            "subject_0951",
            "subject_0954",
        ],
        "aliases": ["农学与林学", "农业&林业", "农业林业", "Agriculture & Forestry"],
        "mapping_class": "broad_multi_subject",
        "note": "QS Agriculture & Forestry 是农学/林学大领域，作为多学科领域映射使用。",
    },
]


USNEWS_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "USNEWS_ENGINEERING_BROAD",
        "ranking_source": "US News",
        "subject_ids": [
            "subject_0801",
            "subject_0802",
            "subject_0803",
            "subject_0804",
            "subject_0805",
            "subject_0806",
            "subject_0807",
            "subject_0808",
            "subject_0809",
            "subject_0810",
            "subject_0811",
            "subject_0812",
            "subject_0813",
            "subject_0814",
            "subject_0815",
            "subject_0816",
            "subject_0817",
            "subject_0818",
            "subject_0819",
            "subject_0820",
            "subject_0821",
            "subject_0822",
            "subject_0823",
            "subject_0824",
            "subject_0825",
            "subject_0828",
            "subject_0829",
            "subject_0830",
            "subject_0831",
            "subject_0832",
            "subject_0833",
            "subject_0835",
            "subject_0836",
            "subject_0837",
            "subject_0839",
            "subject_1401",
            "subject_1404",
            "subject_1405",
            "subject_1406",
        ],
        "aliases": ["engineering", "工程学", "Engineering"],
        "mapping_class": "broad_multi_subject",
        "note": "US News engineering 为大工程领域，不落到单一一级学科。",
    },
    {
        "rule_id": "USNEWS_ARTS_HUMANITIES_BROAD",
        "ranking_source": "US News",
        "subject_ids": ["subject_0101", "subject_0501", "subject_0502", "subject_0601", "subject_0602", "subject_0603", "subject_0813", "subject_0833", "subject_1301", "subject_1357", "subject_1403"],
        "aliases": ["arts and humanities", "艺术与人文"],
        "mapping_class": "broad_multi_subject",
        "note": "US News Arts and Humanities 为大领域口径。",
    },
    {
        "rule_id": "USNEWS_SOCIAL_PUBLIC_HEALTH_BROAD",
        "ranking_source": "US News",
        "subject_ids": ["subject_0302", "subject_0303", "subject_0401", "subject_0402", "subject_1004", "subject_1204"],
        "aliases": ["社会科学与公共卫生", "social sciences and public health"],
        "mapping_class": "broad_multi_subject",
        "note": "US News Social Sciences and Public Health 横跨社科与公共卫生。",
    },
    {
        "rule_id": "USNEWS_ENVIRONMENT_ECOLOGY",
        "ranking_source": "US News",
        "subject_ids": ["subject_0713", "subject_0830"],
        "aliases": ["环境与生态学", "environment/ecology", "environmentecology"],
        "mapping_class": "broad_multi_subject",
        "note": "US News Environment/Ecology 连接生态学与环境科学与工程。",
    },
    {
        "rule_id": "USNEWS_ELECTRICAL_ELECTRONIC_ENGINEERING",
        "ranking_source": "US News",
        "subject_ids": ["subject_0808", "subject_0809", "subject_0810"],
        "aliases": ["electrical and electronic engineering", "电气与电子工程"],
        "mapping_class": "broad_multi_subject",
        "note": "电气与电子工程覆盖电气、电子科学、信息通信。",
    },
    {
        "rule_id": "USNEWS_COMPUTER_SCIENCE",
        "ranking_source": "US News",
        "subject_ids": ["subject_0812", "subject_0835", "subject_0839"],
        "aliases": ["computer science", "Computer Science", "计算机科学"],
        "mapping_class": "broad_multi_subject",
        "note": "计算机科学连接计算机科学与技术、软件工程和网络空间安全。",
    },
    {
        "rule_id": "USNEWS_AI",
        "ranking_source": "US News",
        "subject_ids": ["subject_0811", "subject_0812", "subject_1405"],
        "aliases": ["artificial intelligence", "人工智能"],
        "mapping_class": "broad_multi_subject",
        "note": "人工智能横跨控制、计算机和智能科学。",
    },
    {
        "rule_id": "USNEWS_MATERIALS",
        "ranking_source": "US News",
        "subject_ids": ["subject_0805"],
        "aliases": ["materials science", "polymer science", "材料科学", "高分子科学"],
        "mapping_class": "deterministic",
        "note": "材料科学/高分子科学归入材料科学与工程。",
    },
    {
        "rule_id": "USNEWS_PHYSICS",
        "ranking_source": "US News",
        "subject_ids": ["subject_0702"],
        "aliases": ["condensed matter physics", "凝聚态物理学"],
        "mapping_class": "deterministic",
        "note": "凝聚态物理学归入物理学。",
    },
    {
        "rule_id": "USNEWS_BIOLOGY",
        "ranking_source": "US News",
        "subject_ids": ["subject_0710"],
        "aliases": [
            "biology and biochemistry",
            "plant and animal science",
            "molecular biology and genetics",
            "cell biology",
            "microbiology",
            "biotechnology and applied microbiology",
            "生物学与生物化学",
            "植物与动物科学",
            "分子生物与遗传",
            "细胞生物学",
            "微生物学",
            "生物技术应用微生物学",
        ],
        "mapping_class": "deterministic",
        "note": "US News 生物相关细分学科归入生物学主口径。",
    },
    {
        "rule_id": "USNEWS_MEDICAL_CLINICAL",
        "ranking_source": "US News",
        "subject_ids": ["subject_1002"],
        "aliases": [
            "oncology",
            "endocrinology and metabolism",
            "cardiac and cardiovascular systems",
            "surgery",
            "radiology, nuclear medicine and medical imaging",
            "radiology nuclear medicine and medical imaging",
            "gastroenterology and hepatology",
            "肿瘤学",
            "内分泌代谢",
            "心脏及心血管系统",
            "外科学",
            "放射核医学医学影像学",
            "肠胃病学肝病学",
        ],
        "mapping_class": "deterministic",
        "note": "US News 临床医学相关细分项归入临床医学。",
    },
    {
        "rule_id": "USNEWS_PUBLIC_HEALTH",
        "ranking_source": "US News",
        "subject_ids": ["subject_1004"],
        "aliases": [
            "public, environmental and occupational health",
            "public environmental and occupational health",
            "公共、环境和职业健康",
            "infectious diseases",
            "传染性疾病",
        ],
        "mapping_class": "deterministic",
        "note": "公共、环境和职业健康及传染性疾病归入公共卫生与预防医学。",
    },
    {
        "rule_id": "USNEWS_BASIC_MEDICINE",
        "ranking_source": "US News",
        "subject_ids": ["subject_1001"],
        "aliases": ["immunology", "免疫学"],
        "mapping_class": "deterministic",
        "note": "免疫学归入基础医学。",
    },
    {
        "rule_id": "USNEWS_NEUROSCIENCE",
        "ranking_source": "US News",
        "subject_ids": ["subject_0710", "subject_1001"],
        "aliases": ["neuroscience and behavior", "神经科学与行为"],
        "mapping_class": "broad_multi_subject",
        "note": "神经科学与行为跨生物学与基础医学。",
    },
    {
        "rule_id": "USNEWS_PSYCHIATRY_PSYCHOLOGY",
        "ranking_source": "US News",
        "subject_ids": ["subject_0402"],
        "aliases": ["psychiatry/psychology", "psychiatrypsychology", "精神病学与心理学"],
        "mapping_class": "deterministic",
        "note": "精神病学与心理学归入心理学分析口径。",
    },
    {
        "rule_id": "USNEWS_CHEMISTRY_CHEMICAL_ENGINEERING",
        "ranking_source": "US News",
        "subject_ids": ["subject_0703", "subject_0817"],
        "aliases": ["physical chemistry", "chemical engineering", "物理化学", "化学工程"],
        "mapping_class": "broad_multi_subject",
        "note": "物理化学归化学，化学工程归化学工程；保留双连接以覆盖榜单混合项。",
    },
    {
        "rule_id": "USNEWS_BUSINESS_ECONOMICS",
        "ranking_source": "US News",
        "subject_ids": ["subject_0201", "subject_0202", "subject_1202"],
        "aliases": ["economics and business", "商业与经济"],
        "mapping_class": "broad_multi_subject",
        "note": "商业与经济横跨理论经济学、应用经济学与工商管理。",
    },
    {
        "rule_id": "USNEWS_ENERGY_FUELS",
        "ranking_source": "US News",
        "subject_ids": ["subject_0807", "subject_0858"],
        "aliases": ["energy and fuels", "能源和燃料"],
        "mapping_class": "broad_multi_subject",
        "note": "能源与燃料连接动力工程及工程热物理/能源动力。",
    },
    {
        "rule_id": "USNEWS_NANO",
        "ranking_source": "US News",
        "subject_ids": ["subject_1406"],
        "aliases": ["nanoscience and nanotechnology", "纳米科学与纳米技术"],
        "mapping_class": "deterministic",
        "note": "纳米科学与纳米技术归入纳米科学与工程。",
    },
    {
        "rule_id": "USNEWS_EARTH_ATMOS_WATER",
        "ranking_source": "US News",
        "subject_ids": ["subject_0706", "subject_0708", "subject_0709", "subject_0815"],
        "aliases": ["geosciences", "meteorology and atmospheric sciences", "water resources", "地球科学", "气象学和大气科学", "水资源"],
        "mapping_class": "broad_multi_subject",
        "note": "地球/大气/水资源为跨一级学科口径。",
    },
    {
        "rule_id": "USNEWS_SPACE",
        "ranking_source": "US News",
        "subject_ids": ["subject_0704", "subject_0825"],
        "aliases": ["space science", "空间科学"],
        "mapping_class": "broad_multi_subject",
        "note": "空间科学连接天文学和航空宇航。",
    },
    {
        "rule_id": "USNEWS_OPTICS",
        "ranking_source": "US News",
        "subject_ids": ["subject_0803"],
        "aliases": ["optics", "光学"],
        "mapping_class": "deterministic",
        "note": "光学归入光学工程。",
    },
    {
        "rule_id": "USNEWS_FOOD_SCIENCE",
        "ranking_source": "US News",
        "subject_ids": ["subject_0832", "subject_0955"],
        "aliases": ["food science and technology", "食品科学与技术"],
        "mapping_class": "broad_multi_subject",
        "note": "食品科学与技术连接食品科学与工程/食品与营养。",
    },
    {
        "rule_id": "USNEWS_PHARMACOLOGY",
        "ranking_source": "US News",
        "subject_ids": ["subject_1007"],
        "aliases": ["pharmacology and toxicology", "药理学与毒理学"],
        "mapping_class": "deterministic",
        "note": "药理学与毒理学归入药学。",
    },
    {
        "rule_id": "USNEWS_GREEN_SUSTAINABLE_TECH",
        "ranking_source": "US News",
        "subject_ids": ["subject_0830"],
        "aliases": ["绿色可持续科技", "绿色与可持续的科学技术"],
        "mapping_class": "deterministic",
        "note": "绿色/可持续科学技术暂归环境科学与工程。",
    },
    {
        "rule_id": "USNEWS_AGRICULTURAL_SCIENCES",
        "ranking_source": "US News",
        "subject_ids": ["subject_0901", "subject_0902", "subject_0903", "subject_0904", "subject_0905", "subject_0908", "subject_0909", "subject_0951"],
        "aliases": ["agricultural sciences", "农业科学"],
        "mapping_class": "broad_multi_subject",
        "note": "农业科学为农学大领域。",
    },
    {
        "rule_id": "USNEWS_EDUCATION",
        "ranking_source": "US News",
        "subject_ids": ["subject_0401", "subject_0451"],
        "aliases": ["education and educational research", "教育学和教育研究"],
        "mapping_class": "deterministic",
        "note": "教育学和教育研究归入教育学/教育。",
    },
]


ARWU_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "ARWU_AGRICULTURE_BROAD",
        "ranking_source": "软科",
        "subject_ids": ["subject_0901", "subject_0902", "subject_0903", "subject_0904", "subject_0905", "subject_0908", "subject_0909", "subject_0951"],
        "aliases": ["农学", "Agricultural Sciences"],
        "mapping_class": "broad_multi_subject",
        "note": "软科农学为农学大领域，不强行单学科化。",
    },
    {
        "rule_id": "ARWU_MEDICAL_TECHNOLOGY",
        "ranking_source": "软科",
        "subject_ids": ["subject_1058"],
        "aliases": ["医学技术", "Medical Technology"],
        "mapping_class": "deterministic",
        "note": "软科医学技术对应医学技术。",
    },
    {
        "rule_id": "ARWU_AI",
        "ranking_source": "软科",
        "subject_ids": ["subject_0811", "subject_0812", "subject_1405"],
        "aliases": ["人工智能", "Artificial Intelligence"],
        "mapping_class": "broad_multi_subject",
        "note": "软科人工智能横跨控制、计算机与智能科学。",
    },
    {
        "rule_id": "ARWU_ROBOTICS",
        "ranking_source": "软科",
        "subject_ids": ["subject_0802", "subject_0811", "subject_1405"],
        "aliases": ["机器人科学与工程", "Robotics"],
        "mapping_class": "broad_multi_subject",
        "note": "机器人科学与工程连接机械、控制与智能科学。",
    },
]


def expand_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for rule in rules:
        for subject_id in rule["subject_ids"]:
            expanded.append(
                {
                    "rule_id": rule["rule_id"],
                    "ranking_source": rule["ranking_source"],
                    "subject_id": subject_id,
                    "aliases": rule["aliases"],
                    "mapping_class": rule["mapping_class"],
                    "note": rule["note"],
                }
            )
    return expanded


def dedupe_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for rule in rules:
        key = (str(rule.get("rule_id", "")), str(rule.get("ranking_source", "")), str(rule.get("subject_id", "")))
        if key in seen:
            continue
        seen.add(key)
        output.append(rule)
    return output


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    old_rules = [
        rule
        for rule in config.get("subject_alias_rules", [])
        if not str(rule.get("rule_id", "")).startswith(("QS_", "USNEWS_", "ARWU_"))
    ]

    new_rules = expand_rules(DETERMINISTIC_RULES + USNEWS_RULES + ARWU_RULES)
    config["subject_alias_rules"] = dedupe_rules(old_rules + new_rules)

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# global subject alias rule update",
        "",
        f"- config: `{CONFIG_PATH}`",
        f"- total subject_alias_rules: {len(config['subject_alias_rules'])}",
        f"- generated rules this run: {len(new_rules)}",
        "",
        "## rule groups",
        "",
    ]
    for rule in DETERMINISTIC_RULES + USNEWS_RULES + ARWU_RULES:
        lines.append(
            f"- {rule['rule_id']}: {rule['ranking_source']} | {rule['mapping_class']} | "
            f"{len(rule['subject_ids'])} subject_ids | aliases={', '.join(rule['aliases'][:4])}"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
