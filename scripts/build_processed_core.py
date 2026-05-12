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
QA_DIR = PROCESSED_DIR / "qa"
LOG_DIR = PROJECT_DIR / "logs"
MANUAL_ALIASES_PATH = PROJECT_DIR / "configs" / "runtime" / "manual_subject_aliases.json"
TONGJI_SUBJECT_PROXY_SUPPLEMENT_CSV = PROJECT_DIR / "configs" / "runtime" / "tongji_subject_proxy_supplement.csv"

DIM_SUBJECT_CSV = PROCESSED_DIR / "dim_subject.csv"
DIM_SUBJECT_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_RANKING_CSV = PROCESSED_DIR / "fact_ranking.csv"
SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"

RUN_LOG = LOG_DIR / "processed_core_run_log.md"


TARGET_UNIVERSITY = "同济大学"
REFERENCE_SUBJECT = "数学"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text


def split_alias_text(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []

    candidates: list[str] = [text]
    for part in re.split(r"[；;,/、，|]+", text):
        item = clean_text(part)
        if not item:
            continue
        if re.search(r"[\u4e00-\u9fff]", item) and re.search(r"\s+", item):
            candidates.extend(clean_text(piece) for piece in re.split(r"\s+", item) if clean_text(piece))
        else:
            candidates.append(item)

    unique_items: list[str] = []
    for item in candidates:
        if item and item not in unique_items:
            unique_items.append(item)
    return unique_items


def read_sheet(file_name: str, sheet_name: str, header: int = 0) -> pd.DataFrame:
    path = DATA_DIR / file_name
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=object, header=header)
    df.columns = [clean_text(column) for column in df.columns]
    df = df.dropna(how="all").copy()
    return df


def load_manual_alias_config() -> dict[str, Any]:
    if not MANUAL_ALIASES_PATH.exists():
        return {"invalid_alias_values": ["", "无", "暂无", "无对应", "-", "None", "nan"], "area_alias_rules": []}
    return json.loads(MANUAL_ALIASES_PATH.read_text(encoding="utf-8"))


def coalesce(row: pd.Series, columns: list[str]) -> Any:
    for column in columns:
        if column in row.index:
            value = row[column]
            if clean_text(value):
                return value
    return ""


def parse_year(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(20\d{2})", text)
    if match:
        return int(match.group(1))
    try:
        number = int(float(text))
        if 1900 <= number <= 2100:
            return number
    except Exception:
        return None
    return None


def parse_rank(value: Any) -> dict[str, Any]:
    raw = clean_text(value)
    if not raw:
        return {"rank_raw": "", "rank_min": None, "rank_max": None, "rank_midpoint": None, "rank_note": "missing"}

    text = raw.replace("–", "-").replace("—", "-").replace("~", "-").replace("至", "-")
    text = text.replace(",", "").strip()
    note = ""

    if text.startswith("="):
        note = "tied"
        text = text[1:].strip()

    numbers = [int(match) for match in re.findall(r"\d+", text)]
    if not numbers:
        return {"rank_raw": raw, "rank_min": None, "rank_max": None, "rank_midpoint": None, "rank_note": "unparsed"}

    if len(numbers) >= 2 and "-" in text:
        rank_min = min(numbers[0], numbers[1])
        rank_max = max(numbers[0], numbers[1])
    else:
        rank_min = numbers[0]
        rank_max = numbers[0]

    return {
        "rank_raw": raw,
        "rank_min": rank_min,
        "rank_max": rank_max,
        "rank_midpoint": (rank_min + rank_max) / 2,
        "rank_note": note,
    }


def first_existing(row: pd.Series, columns: list[str]) -> str:
    return clean_text(coalesce(row, columns))


def aggregate_unique(values: pd.Series) -> str:
    items = []
    for value in values:
        text = clean_text(value)
        if text and text not in items:
            items.append(text)
    return "；".join(items)


def apply_tongji_subject_proxy_supplement(tongji: pd.DataFrame) -> pd.DataFrame:
    if not TONGJI_SUBJECT_PROXY_SUPPLEMENT_CSV.exists() or tongji.empty:
        return tongji
    supplements = pd.read_csv(TONGJI_SUBJECT_PROXY_SUPPLEMENT_CSV, dtype=str).fillna("")
    output = tongji.copy()
    if "学术学位点" not in output.columns or "一级学科学科代码" not in output.columns:
        return output

    for _, supplement in supplements.iterrows():
        source_subject_name = clean_text(supplement.get("source_subject_name"))
        proxy_code = clean_text(supplement.get("proxy_ministry_subject_code"))
        if not source_subject_name or not proxy_code:
            continue
        mask = output["学术学位点"].map(clean_text).eq(source_subject_name)
        if not mask.any():
            continue
        output.loc[mask, "一级学科学科代码"] = proxy_code
    return output


def build_dim_subject() -> pd.DataFrame:
    ministry = read_sheet("教育部学科与四大国际学科排名映射关系.xlsx", "学科映射关系")
    tongji = read_sheet("同济大学学院+学科映射关系20260509.xlsx", "Sheet1")
    official = read_sheet("1.研究生教育学科专业目录（2022年）.xlsx", "Sheet1")
    tongji = apply_tongji_subject_proxy_supplement(tongji)

    for column in ["编号", "学院"]:
        if column in tongji.columns:
            tongji[column] = tongji[column].ffill()

    tongji_grouped = (
        tongji.groupby("一级学科学科代码", dropna=True)
        .agg(
            tongji_college=("学院", aggregate_unique),
            tongji_academic_degree=("学术学位点", aggregate_unique),
            tongji_professional_degree=("专业学位点", aggregate_unique),
            tongji_undergraduate_major=("本科专业", aggregate_unique),
            tongji_level=("层次级别", aggregate_unique),
            tongji_round5_result=("第五轮评估结果", aggregate_unique),
            tongji_is_double_first_class=("是否双一流学科", aggregate_unique),
            tongji_shanghai_peak_plateau=("上海市高峰高原", aggregate_unique),
            tongji_arwu_subject=("软科世界一流学科对应名称", aggregate_unique),
            tongji_qs_subject=("QS对应的学科名称", aggregate_unique),
            tongji_usnews_subject=("U.S.NEWS学科排名对应名称", aggregate_unique),
            tongji_the_area=("THE对应领域", aggregate_unique),
        )
        .reset_index()
        .rename(columns={"一级学科学科代码": "ministry_subject_code"})
    )

    official_small = official[
        [
            column
            for column in ["门类代码", "学科门类", "一级学科代码", "一级学科名称", "年度", "学科简称"]
            if column in official.columns
        ]
    ].copy()
    official_small = official_small.drop_duplicates(subset=["一级学科代码"], keep="first")
    official_small = official_small.rename(
        columns={
            "门类代码": "official_category_code",
            "学科门类": "official_category_name",
            "一级学科代码": "ministry_subject_code",
            "一级学科名称": "official_subject_name",
            "年度": "official_catalog_year",
            "学科简称": "subject_short_name",
        }
    )

    dim = ministry.rename(
        columns={
            "门类代码": "ministry_category_code",
            "学科门类": "ministry_category_name",
            "一级学科代码": "ministry_subject_code",
            "一级学科名称": "ministry_subject_name",
            "目录年度": "catalog_year",
            "软科世界一流学科对应名称": "arwu_subject_name",
            "QS对应的学科名称": "qs_subject_name",
            "U.S.NEWS学科排名对应名称": "usnews_subject_name",
            "THE对应领域": "the_subject_area",
        }
    ).copy()

    dim["ministry_subject_code"] = dim["ministry_subject_code"].map(clean_text)
    dim = dim.merge(official_small, on="ministry_subject_code", how="left")
    dim = dim.merge(tongji_grouped, on="ministry_subject_code", how="left")

    dim["subject_id"] = dim["ministry_subject_code"].apply(lambda value: f"subject_{clean_text(value)}" if clean_text(value) else "")

    for target, fallback in [
        ("arwu_subject_name", "tongji_arwu_subject"),
        ("qs_subject_name", "tongji_qs_subject"),
        ("usnews_subject_name", "tongji_usnews_subject"),
        ("the_subject_area", "tongji_the_area"),
    ]:
        dim[target] = dim.apply(
            lambda row: clean_text(row[target]) or clean_text(row.get(fallback, "")),
            axis=1,
        )

    columns = [
        "subject_id",
        "ministry_category_code",
        "ministry_category_name",
        "ministry_subject_code",
        "ministry_subject_name",
        "catalog_year",
        "subject_short_name",
        "tongji_college",
        "tongji_academic_degree",
        "tongji_professional_degree",
        "tongji_undergraduate_major",
        "tongji_level",
        "tongji_round5_result",
        "tongji_is_double_first_class",
        "tongji_shanghai_peak_plateau",
        "arwu_subject_name",
        "qs_subject_name",
        "usnews_subject_name",
        "the_subject_area",
    ]
    for column in columns:
        if column not in dim.columns:
            dim[column] = ""
    dim = dim[columns].fillna("")
    return dim


def infer_ranking_source(value: Any) -> str:
    text = normalize_key(value)
    if "软科" in text or "arwu" in text:
        return "软科"
    if "qs" in text:
        return "QS"
    if "news" in text or "u.s" in text:
        return "US News"
    if "the" in text or "泰晤士" in text:
        return "THE"
    return ""


def build_dim_subject_alias(dim_subject: pd.DataFrame) -> pd.DataFrame:
    manual_config = load_manual_alias_config()
    invalid_alias_values = {normalize_key(value) for value in manual_config.get("invalid_alias_values", [])}
    ministry_name_to_id = {
        normalize_key(row["ministry_subject_name"]): clean_text(row["subject_id"])
        for _, row in dim_subject.iterrows()
        if clean_text(row["ministry_subject_name"]) and clean_text(row["subject_id"])
    }
    aliases: list[dict[str, Any]] = []

    def add_alias(subject_id: str, ranking_source: str, alias: Any, alias_type: str, source_note: str) -> None:
        text = clean_text(alias)
        if not subject_id or not ranking_source or not text:
            return
        for item in split_alias_text(text):
            if not item or normalize_key(item) in invalid_alias_values:
                continue
            aliases.append(
                {
                    "subject_id": subject_id,
                    "ranking_source": ranking_source,
                    "ranking_subject_alias": item,
                    "ranking_subject_norm": normalize_key(item),
                    "alias_type": alias_type,
                    "source_note": source_note,
                }
            )

    for _, row in dim_subject.iterrows():
        subject_id = clean_text(row["subject_id"])
        if not subject_id:
            continue
        for source, column in [
            ("软科", "arwu_subject_name"),
            ("QS", "qs_subject_name"),
            ("US News", "usnews_subject_name"),
            ("THE", "the_subject_area"),
            ("ministry", "ministry_subject_name"),
        ]:
            add_alias(subject_id, source, row[column], "dim_subject_column", column)

        the_area = clean_text(row["the_subject_area"])
        the_aliases = {
            "物理学": ["理学", "自然科学", "Physical Sciences"],
            "艺术与人文": ["艺术与人文学", "Arts and Humanities"],
            "临床健康": ["医学与健康", "临床与健康", "Medical and Health"],
            "商业与经济": ["商业与经济学", "商业和经济学", "Business and Economics"],
            "工程": ["工程学", "Engineering"],
            "计算机科学": ["Computer Science"],
            "生命科学": ["Life Sciences"],
            "社会科学": ["Social Sciences"],
            "教育学": ["Education"],
            "心理学": ["Psychology"],
            "法学": ["Law"],
        }.get(the_area, [])
        for alias in the_aliases:
            add_alias(subject_id, "THE", alias, "manual_the_area_alias", "THE领域中文/英文别名")

        for rule in manual_config.get("area_alias_rules", []):
            column = clean_text(rule.get("dim_subject_column"))
            value = clean_text(rule.get("dim_subject_value"))
            if column and value and clean_text(row.get(column, "")) == value:
                for alias in rule.get("aliases", []):
                    add_alias(
                        subject_id,
                        clean_text(rule.get("ranking_source")),
                        alias,
                        "manual_config_area_alias",
                        clean_text(rule.get("note")),
                    )

    known_subject_ids = set(dim_subject["subject_id"].map(clean_text))
    for rule in manual_config.get("subject_alias_rules", []):
        subject_id = clean_text(rule.get("subject_id"))
        if subject_id not in known_subject_ids:
            continue
        ranking_source = clean_text(rule.get("ranking_source"))
        for alias in rule.get("aliases", []):
            add_alias(
                subject_id,
                ranking_source,
                alias,
                "manual_config_subject_alias",
                clean_text(rule.get("note")),
            )

    sheet1 = read_sheet("教育部学科与四大国际学科排名映射关系.xlsx", "Sheet1")
    for _, row in sheet1.iterrows():
        source = infer_ranking_source(row.get("榜单名称"))
        subject_name = clean_text(row.get("对应一级学科"))
        subject_id = ministry_name_to_id.get(normalize_key(subject_name), "")
        add_alias(subject_id, source, row.get("榜单学科"), "mapping_sheet1", "教育部学科映射Sheet1")

    for file_name, sheet_name, source in [
        ("2025-2026年度US News世界学科排名20251124.xlsx", "Sheet1", "US News"),
        ("2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx", "全球排名", "US News"),
        ("2026年QS世界学科排名20260326.xlsx", "数据", "QS"),
        ("2025年QS世界大学学科排名20250313.xlsx", "明细数", "QS"),
        ("世界大学学科排名THE（2022-2026年）20260123.xlsx", "数据", "THE"),
    ]:
        df = read_sheet(file_name, sheet_name)
        for _, row in df.iterrows():
            subject_cn = first_existing(row, ["学科中文", "学科", "Subject"])
            subject_en = first_existing(row, ["学科英文", "Subject"])
            source_subject_id = ""
            for candidate_source in [source, "ministry"]:
                source_subject_id = source_subject_id or ministry_name_to_id.get(normalize_key(subject_cn), "")
            if not source_subject_id:
                continue
            add_alias(source_subject_id, source, subject_cn, "source_subject_cn", file_name)
            add_alias(source_subject_id, source, subject_en, "source_subject_en", file_name)

    alias_df = pd.DataFrame(aliases).drop_duplicates()
    alias_df = alias_df.sort_values(["ranking_source", "ranking_subject_norm", "subject_id", "alias_type"])
    return alias_df


def build_subject_lookup(dim_subject_alias: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    lookup: dict[tuple[str, str], list[str]] = {}
    for _, row in dim_subject_alias.iterrows():
        key = (clean_text(row["ranking_source"]), clean_text(row["ranking_subject_norm"]))
        subject_id = clean_text(row["subject_id"])
        if not key[0] or not key[1] or not subject_id:
            continue
        lookup.setdefault(key, [])
        if subject_id not in lookup[key]:
            lookup[key].append(subject_id)
    return lookup


def subject_ids_for(source: str, subject_raw: str, lookups: dict[tuple[str, str], list[str]]) -> list[str]:
    key = normalize_key(subject_raw)
    return lookups.get((source, key), [])


def direct_subject_id_for(source: str, subject_raw: str, lookups: dict[tuple[str, str], list[str]]) -> tuple[str, int]:
    subject_ids = subject_ids_for(source, subject_raw, lookups)
    if len(subject_ids) == 1:
        return subject_ids[0], 1
    return "", len(subject_ids)


def ranking_record(
    ranking_source: str,
    release_year: int | None,
    ranking_year: int | None,
    subject_raw: str,
    subject_id: str,
    subject_alias_match_count: int,
    university_name_cn: str,
    university_name_en: str,
    country_or_region: str,
    rank_value: Any,
    total_score: Any,
    source_file: str,
    source_sheet: str,
    source_row: int,
) -> dict[str, Any]:
    parsed_rank = parse_rank(rank_value)
    return {
        "ranking_source": ranking_source,
        "release_year": release_year,
        "ranking_year": ranking_year,
        "subject_id": subject_id,
        "ranking_subject_norm": normalize_key(subject_raw),
        "subject_alias_match_count": subject_alias_match_count,
        "ranking_subject_raw": subject_raw,
        "university_name_cn": university_name_cn,
        "university_name_en": university_name_en,
        "country_or_region": country_or_region,
        "is_mainland_china": "中国内地" in country_or_region or country_or_region in {"中国大陆", "中国"},
        "is_tongji": university_name_cn == TARGET_UNIVERSITY or university_name_en == "Tongji University",
        **parsed_rank,
        "total_score": clean_text(total_score),
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
    }


def append_arwu(records: list[dict[str, Any]], lookups: dict[tuple[str, str], list[str]]) -> None:
    configs = [
        {
            "file": "2023年软科世界一流学科排名-20231030.xlsx",
            "sheet": "名单",
            "release_year": "发布年度",
            "subject": "学科领域",
            "university_cn": "中文名称",
            "university_en": "学校名称",
            "region": "所在地区",
            "rank": "国际排名",
            "score": "总得分",
        },
        {
            "file": "2024年软科世界一流学科排名-20241111.xlsx",
            "sheet": "所有高校",
            "release_year": "年份",
            "subject": "学科领域",
            "university_cn": "中文校名",
            "university_en": "英文校名",
            "region": "国家",
            "rank": "排名",
            "score": "总分",
        },
        {
            "file": "2025年软科世界一流学科排名20251118.xlsx",
            "sheet": "数据",
            "release_year": "发布年度",
            "subject": "学科名称",
            "university_cn": "学校名称",
            "university_en": "",
            "region": "所在地区",
            "rank": "国际排名",
            "score": "总得分",
        },
    ]
    for config in configs:
        df = read_sheet(config["file"], config["sheet"])
        for index, row in df.iterrows():
            subject_raw = first_existing(row, [config["subject"]])
            subject_id, match_count = direct_subject_id_for("软科", subject_raw, lookups)
            records.append(
                ranking_record(
                    ranking_source="软科",
                    release_year=parse_year(row.get(config["release_year"])),
                    ranking_year=parse_year(row.get(config["release_year"])),
                    subject_raw=subject_raw,
                    subject_id=subject_id,
                    subject_alias_match_count=match_count,
                    university_name_cn=first_existing(row, [config["university_cn"]]),
                    university_name_en=first_existing(row, [config["university_en"]]) if config["university_en"] else "",
                    country_or_region=first_existing(row, [config["region"]]),
                    rank_value=row.get(config["rank"]),
                    total_score=row.get(config["score"]),
                    source_file=config["file"],
                    source_sheet=config["sheet"],
                    source_row=int(index) + 2,
                )
            )


def append_qs(records: list[dict[str, Any]], lookups: dict[tuple[str, str], list[str]]) -> None:
    configs = [
        {
            "file": "2023年QS世界学科排名.xlsx",
            "sheet": "2023",
            "release_year": 2023,
            "ranking_year": 2023,
            "subject": "学科",
            "university_cn": "高校名称",
            "university_en": "",
            "region": "地区",
            "rank": "国际排名",
            "score": "综合得分",
        },
        {
            "file": "2024年QS世界学科排名-20240412.xlsx",
            "sheet": "数据",
            "release_year": "发布年度",
            "ranking_year": "发布年度",
            "subject": "学科中文",
            "university_cn": "中文名称",
            "university_en": "英文名称",
            "region": "所在地区",
            "rank": "国际排名",
            "score": "总得分",
        },
        {
            "file": "2025年QS世界大学学科排名20250313.xlsx",
            "sheet": "明细数",
            "release_year": "年份",
            "ranking_year": "年份",
            "subject": "学科中文",
            "university_cn": "大学",
            "university_en": "",
            "region": "地区",
            "rank": "排名",
            "score": "综合得分",
        },
        {
            "file": "2026年QS世界学科排名20260326.xlsx",
            "sheet": "数据",
            "release_year": "发布年度",
            "ranking_year": "发布年度",
            "subject": "学科中文",
            "university_cn": "中文名称",
            "university_en": "英文名称",
            "region": "所在地区",
            "rank": "国际排名",
            "score": "总得分",
        },
    ]
    for config in configs:
        df = read_sheet(config["file"], config["sheet"])
        for index, row in df.iterrows():
            subject_raw = first_existing(row, [config["subject"]])
            subject_id, match_count = direct_subject_id_for("QS", subject_raw, lookups)
            release_year = config["release_year"] if isinstance(config["release_year"], int) else parse_year(row.get(config["release_year"]))
            ranking_year = config["ranking_year"] if isinstance(config["ranking_year"], int) else parse_year(row.get(config["ranking_year"]))
            records.append(
                ranking_record(
                    ranking_source="QS",
                    release_year=release_year,
                    ranking_year=ranking_year,
                    subject_raw=subject_raw,
                    subject_id=subject_id,
                    subject_alias_match_count=match_count,
                    university_name_cn=first_existing(row, [config["university_cn"]]),
                    university_name_en=first_existing(row, [config["university_en"]]) if config["university_en"] else "",
                    country_or_region=first_existing(row, [config["region"]]),
                    rank_value=row.get(config["rank"]),
                    total_score=row.get(config["score"]),
                    source_file=config["file"],
                    source_sheet=config["sheet"],
                    source_row=int(index) + 2,
                )
            )


def append_usnews(records: list[dict[str, Any]], lookups: dict[tuple[str, str], list[str]]) -> None:
    configs = [
        {
            "file": "2021US News世界学科排名2020年发布.xlsx",
            "sheet": "Sheet1",
            "fallback_release_year": 2020,
            "fallback_ranking_year": 2021,
            "release_year": "pubyear",
            "ranking_year": "",
            "subject": "subject",
            "university_cn": "university_zh",
            "university_en": "university",
            "region": "location",
            "rank": "subjectrank",
            "score": "globalscore",
        },
        {
            "file": "2022US News世界学科排名20211026.xlsx",
            "sheet": "Sheet2",
            "fallback_release_year": 2021,
            "fallback_ranking_year": 2022,
            "release_year": "pubyear",
            "ranking_year": "",
            "subject": "subject",
            "university_cn": "university_zh",
            "university_en": "university",
            "region": "",
            "rank": "subjectrank",
            "score": "overallscore",
        },
        {
            "file": "2023US News世界学科排名20221026.xlsx",
            "sheet": "sheet",
            "fallback_release_year": 2022,
            "fallback_ranking_year": 2023,
            "release_year": "发布时间",
            "ranking_year": "Time",
            "subject": "Subject",
            "university_cn": "Name",
            "university_en": "",
            "region": "Country",
            "rank": "Rank",
            "score": "OVERALL_SCORE",
        },
        {
            "file": "2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx",
            "sheet": "全球排名",
            "fallback_release_year": 2024,
            "fallback_ranking_year": 2025,
            "release_year": "发布年份",
            "ranking_year": "排名年份",
            "subject": "学科中文",
            "university_cn": "中文名称",
            "university_en": "名称",
            "region": "国家",
            "rank": "世界排名",
            "score": "总得分",
        },
        {
            "file": "2025-2026年度US News世界学科排名20251124.xlsx",
            "sheet": "Sheet1",
            "fallback_release_year": 2025,
            "fallback_ranking_year": 2026,
            "release_year": "发布年度",
            "ranking_year": "排名年度",
            "subject": "学科中文",
            "university_cn": "中文名称",
            "university_en": "外文名称",
            "region": "所在地区",
            "rank": "国际排名",
            "score": "总得分",
        },
    ]
    for config in configs:
        df = read_sheet(config["file"], config["sheet"])
        for index, row in df.iterrows():
            subject_raw = first_existing(row, [config["subject"]])
            subject_id, match_count = direct_subject_id_for("US News", subject_raw, lookups)
            release_year = parse_year(row.get(config["release_year"])) or config["fallback_release_year"]
            ranking_year = parse_year(row.get(config["ranking_year"])) if config["ranking_year"] else None
            ranking_year = ranking_year or config["fallback_ranking_year"]
            records.append(
                ranking_record(
                    ranking_source="US News",
                    release_year=release_year,
                    ranking_year=ranking_year,
                    subject_raw=subject_raw,
                    subject_id=subject_id,
                    subject_alias_match_count=match_count,
                    university_name_cn=first_existing(row, [config["university_cn"]]),
                    university_name_en=first_existing(row, [config["university_en"]]) if config["university_en"] else "",
                    country_or_region=first_existing(row, [config["region"]]) if config["region"] else "",
                    rank_value=row.get(config["rank"]),
                    total_score=row.get(config["score"]),
                    source_file=config["file"],
                    source_sheet=config["sheet"],
                    source_row=int(index) + 2,
                )
            )


def append_the(records: list[dict[str, Any]], lookups: dict[tuple[str, str], list[str]]) -> None:
    config = {
        "file": "世界大学学科排名THE（2022-2026年）20260123.xlsx",
        "sheet": "数据",
        "release_year": "发布年度",
        "ranking_year": "排名年度",
        "subject": "学科中文",
        "university_cn": "中文名称",
        "university_en": "外文名称",
        "region": "所在地区",
        "rank": "国际排名",
        "score": "总得分",
    }
    df = read_sheet(config["file"], config["sheet"])
    for index, row in df.iterrows():
        subject_raw = first_existing(row, [config["subject"]])
        subject_id, match_count = direct_subject_id_for("THE", subject_raw, lookups)
        records.append(
            ranking_record(
                ranking_source="THE",
                release_year=parse_year(row.get(config["release_year"])),
                ranking_year=parse_year(row.get(config["ranking_year"])),
                subject_raw=subject_raw,
                subject_id=subject_id,
                subject_alias_match_count=match_count,
                university_name_cn=first_existing(row, [config["university_cn"]]),
                university_name_en=first_existing(row, [config["university_en"]]),
                country_or_region=first_existing(row, [config["region"]]),
                rank_value=row.get(config["rank"]),
                total_score=row.get(config["score"]),
                source_file=config["file"],
                source_sheet=config["sheet"],
                source_row=int(index) + 2,
            )
        )


def build_fact_ranking(dim_subject_alias: pd.DataFrame) -> pd.DataFrame:
    lookups = build_subject_lookup(dim_subject_alias)
    records: list[dict[str, Any]] = []
    append_arwu(records, lookups)
    append_qs(records, lookups)
    append_usnews(records, lookups)
    append_the(records, lookups)
    fact = pd.DataFrame(records)

    fact["fact_id"] = [
        f"ranking_{index + 1:08d}"
        for index in range(len(fact))
    ]
    ordered_columns = [
        "fact_id",
        "ranking_source",
        "release_year",
        "ranking_year",
        "subject_id",
        "ranking_subject_norm",
        "subject_alias_match_count",
        "ranking_subject_raw",
        "university_name_cn",
        "university_name_en",
        "country_or_region",
        "is_mainland_china",
        "is_tongji",
        "rank_raw",
        "rank_min",
        "rank_max",
        "rank_midpoint",
        "rank_note",
        "total_score",
        "source_file",
        "source_sheet",
        "source_row",
    ]
    fact = fact[ordered_columns]
    return fact


def write_sqlite(dim_subject: pd.DataFrame, dim_subject_alias: pd.DataFrame, fact_ranking: pd.DataFrame) -> None:
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
    with sqlite3.connect(SQLITE_PATH) as conn:
        dim_subject.to_sql("dim_subject", conn, index=False)
        dim_subject_alias.to_sql("dim_subject_alias", conn, index=False)
        fact_ranking.to_sql("fact_ranking", conn, index=False)
        conn.execute("CREATE INDEX idx_fact_ranking_subject ON fact_ranking(subject_id)")
        conn.execute("CREATE INDEX idx_fact_ranking_subject_norm ON fact_ranking(ranking_source, ranking_subject_norm)")
        conn.execute("CREATE INDEX idx_dim_subject_alias_norm ON dim_subject_alias(ranking_source, ranking_subject_norm)")
        conn.execute("CREATE INDEX idx_fact_ranking_source_year ON fact_ranking(ranking_source, release_year, ranking_year)")
        conn.execute("CREATE INDEX idx_fact_ranking_university ON fact_ranking(university_name_cn, university_name_en)")


def qa_reports(dim_subject: pd.DataFrame, dim_subject_alias: pd.DataFrame, fact_ranking: pd.DataFrame) -> dict[str, Any]:
    QA_DIR.mkdir(parents=True, exist_ok=True)

    parse_exceptions = fact_ranking[fact_ranking["rank_note"].isin(["missing", "unparsed"])].copy()
    parse_exceptions.to_csv(QA_DIR / "ranking_parse_exceptions.csv", index=False, encoding="utf-8-sig")

    unmatched_subjects = fact_ranking[fact_ranking["subject_alias_match_count"].fillna(0).astype(int) == 0].copy()
    unmatched_subjects_summary = (
        unmatched_subjects.groupby(["ranking_source", "ranking_subject_raw"], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["ranking_source", "row_count"], ascending=[True, False])
    )
    unmatched_subjects_summary.to_csv(QA_DIR / "subject_mapping_unmatched.csv", index=False, encoding="utf-8-sig")

    source_trace = (
        fact_ranking.groupby(["ranking_source", "source_file", "source_sheet"], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["ranking_source", "source_file", "source_sheet"])
    )
    source_trace.to_csv(QA_DIR / "source_trace_summary.csv", index=False, encoding="utf-8-sig")

    tongji = fact_ranking[fact_ranking["is_tongji"] == True].copy()
    math_subject_ids = set(
        dim_subject[
            (dim_subject["ministry_subject_name"] == REFERENCE_SUBJECT)
            | (dim_subject["arwu_subject_name"] == REFERENCE_SUBJECT)
            | (dim_subject["qs_subject_name"] == REFERENCE_SUBJECT)
            | (dim_subject["usnews_subject_name"] == REFERENCE_SUBJECT)
        ]["subject_id"]
    )
    math_alias_keys = set(
        tuple(row)
        for row in dim_subject_alias[dim_subject_alias["subject_id"].isin(math_subject_ids)][
            ["ranking_source", "ranking_subject_norm"]
        ].drop_duplicates().itertuples(index=False, name=None)
    )
    tongji_math = tongji[
        tongji["subject_id"].isin(math_subject_ids)
        | tongji.apply(lambda row: (row["ranking_source"], row["ranking_subject_norm"]) in math_alias_keys, axis=1)
    ].copy()
    tongji_math_export = tongji_math.sort_values(["ranking_source", "release_year", "ranking_year"])
    tongji_math_export.to_csv(QA_DIR / "closed_loop_tongji_math_fact_ranking.csv", index=False, encoding="utf-8-sig")

    latest_rows = []
    for source, source_df in tongji_math_export.groupby("ranking_source"):
        latest = source_df.sort_values(["release_year", "ranking_year"], na_position="first").tail(1)
        latest_rows.append(latest)
    latest_overview = pd.concat(latest_rows, ignore_index=True) if latest_rows else pd.DataFrame()
    if not latest_overview.empty:
        latest_overview.to_csv(QA_DIR / "closed_loop_tongji_math_latest_overview.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "dim_subject_rows": int(len(dim_subject)),
        "fact_ranking_rows": int(len(fact_ranking)),
        "fact_ranking_by_source": fact_ranking.groupby("ranking_source").size().to_dict(),
        "subject_id_missing_rows": int((fact_ranking["subject_id"].map(clean_text) == "").sum()),
        "subject_alias_no_match_rows": int((fact_ranking["subject_alias_match_count"].fillna(0).astype(int) == 0).sum()),
        "subject_alias_ambiguous_rows": int((fact_ranking["subject_alias_match_count"].fillna(0).astype(int) > 1).sum()),
        "rank_parse_exception_rows": int(len(parse_exceptions)),
        "tongji_rows": int(len(tongji)),
        "tongji_math_rows": int(len(tongji_math)),
        "outputs": {
            "dim_subject_csv": str(DIM_SUBJECT_CSV),
            "dim_subject_alias_csv": str(DIM_SUBJECT_ALIAS_CSV),
            "fact_ranking_csv": str(FACT_RANKING_CSV),
            "sqlite": str(SQLITE_PATH),
            "ranking_parse_exceptions": str(QA_DIR / "ranking_parse_exceptions.csv"),
            "subject_mapping_unmatched": str(QA_DIR / "subject_mapping_unmatched.csv"),
            "source_trace_summary": str(QA_DIR / "source_trace_summary.csv"),
            "closed_loop_tongji_math_fact_ranking": str(QA_DIR / "closed_loop_tongji_math_fact_ranking.csv"),
        },
    }
    (QA_DIR / "processed_core_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# processed core QA",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- dim_subject 行数：{summary['dim_subject_rows']}",
        f"- fact_ranking 行数：{summary['fact_ranking_rows']}",
        f"- subject_id 缺失行数：{summary['subject_id_missing_rows']}",
        f"- 学科 alias 无匹配行数：{summary['subject_alias_no_match_rows']}",
        f"- 学科 alias 一对多行数：{summary['subject_alias_ambiguous_rows']}",
        f"- 排名解析异常行数：{summary['rank_parse_exception_rows']}",
        f"- 同济大学记录数：{summary['tongji_rows']}",
        f"- 同济数学记录数：{summary['tongji_math_rows']}",
        "",
        "## fact_ranking by source",
        "",
    ]
    for source, count in summary["fact_ranking_by_source"].items():
        lines.append(f"- {source}: {count}")
    lines.extend(
        [
            "",
            "## QA files",
            "",
            "- `ranking_parse_exceptions.csv`：排名缺失或无法解析的记录。",
            "- `subject_mapping_unmatched.csv`：无法映射到 dim_subject 的榜单学科。",
            "- `source_trace_summary.csv`：每个源文件/sheet 进入 fact_ranking 的行数。",
            "- `closed_loop_tongji_math_fact_ranking.csv`：首个闭环候选数据，同济数学四大榜单历史记录。",
            "- `closed_loop_tongji_math_latest_overview.csv`：首个闭环候选数据，同济数学四大榜单最新记录。",
        ]
    )
    (QA_DIR / "processed_core_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    closed_loop_lines = [
        "# 首个闭环数据核验",
        "",
        "## 目标",
        "",
        "验证 `figure_01_tongji_subject_ranking_overview` 和 `figure_07_all_rankings_history` 是否可以直接由 `dim_subject`、`dim_subject_alias`、`fact_ranking` 支撑。",
        "",
        "## 目标对象",
        "",
        f"- 学校：{TARGET_UNIVERSITY}",
        f"- 参考学科：{REFERENCE_SUBJECT}",
        f"- 关联 subject_id：{', '.join(sorted(math_subject_ids))}",
        "",
        "## 历史记录覆盖",
        "",
    ]
    if tongji_math_export.empty:
        closed_loop_lines.append("- 未找到记录。")
    else:
        counts = tongji_math_export.groupby("ranking_source").size().to_dict()
        for source, count in counts.items():
            closed_loop_lines.append(f"- {source}: {count} 条")
    closed_loop_lines.extend(["", "## 最新概览记录", ""])
    if latest_overview.empty:
        closed_loop_lines.append("- 未找到最新概览记录。")
    else:
        for _, row in latest_overview.sort_values("ranking_source").iterrows():
            closed_loop_lines.append(
                f"- {row['ranking_source']}：发布年度 {row['release_year']}，排名年度 {row['ranking_year']}，"
                f"学科 `{row['ranking_subject_raw']}`，排名 `{row['rank_raw']}`，中位数 `{row['rank_midpoint']}`，"
                f"来源 `{row['source_file']}`"
            )
    closed_loop_lines.extend(
        [
            "",
            "## 口径说明",
            "",
            "- THE 为领域排名，`理学` 通过 `dim_subject_alias` 一对多映射到数学、物理学、化学等理学一级学科；生成报告时图题和注释需要说明这是 THE 领域口径。",
            "- 趋势图建议使用 `rank_midpoint`，但表格和文字必须保留 `rank_raw`。",
            "- 发布年度和排名年度都已保留，后续图题按实际口径写。",
        ]
    )
    (QA_DIR / "closed_loop_support_check.md").write_text(
        "\n".join(closed_loop_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def append_run_log(summary: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        f"## {summary['generated_at']} processed core",
        "",
        "### 目标",
        "",
        "生成第一批结构化数据层：`dim_subject` 与 `fact_ranking`，支撑排名概览和四大排名历史趋势首个闭环。",
        "",
        "### 输入",
        "",
        "- 学科映射：教育部学科与四大国际学科排名映射关系、同济大学学院+学科映射关系、研究生教育学科专业目录。",
        "- 排名明细：软科2023-2025、QS2023-2026、US News2021-2026、THE 2022-2026总库。",
        "",
        "### 输出",
        "",
        f"- `{DIM_SUBJECT_CSV}`",
        f"- `{DIM_SUBJECT_ALIAS_CSV}`",
        f"- `{FACT_RANKING_CSV}`",
        f"- `{SQLITE_PATH}`",
        f"- `{QA_DIR / 'processed_core_summary.md'}`",
        "",
        "### 核验摘要",
        "",
        f"- dim_subject 行数：{summary['dim_subject_rows']}",
        f"- fact_ranking 行数：{summary['fact_ranking_rows']}",
        f"- subject_id 缺失行数：{summary['subject_id_missing_rows']}",
        f"- 学科 alias 无匹配行数：{summary['subject_alias_no_match_rows']}",
        f"- 学科 alias 一对多行数：{summary['subject_alias_ambiguous_rows']}",
        f"- 排名解析异常行数：{summary['rank_parse_exception_rows']}",
        f"- 同济数学记录数：{summary['tongji_math_rows']}",
        "",
    ]
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# 过程留档\n", encoding="utf-8", newline="\n")
    with RUN_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    dim_subject = build_dim_subject()
    dim_subject_alias = build_dim_subject_alias(dim_subject)
    fact_ranking = build_fact_ranking(dim_subject_alias)

    dim_subject.to_csv(DIM_SUBJECT_CSV, index=False, encoding="utf-8-sig")
    dim_subject_alias.to_csv(DIM_SUBJECT_ALIAS_CSV, index=False, encoding="utf-8-sig")
    fact_ranking.to_csv(FACT_RANKING_CSV, index=False, encoding="utf-8-sig")
    write_sqlite(dim_subject, dim_subject_alias, fact_ranking)

    summary = qa_reports(dim_subject, dim_subject_alias, fact_ranking)
    append_run_log(summary)

    print((QA_DIR / "processed_core_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
