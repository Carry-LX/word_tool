from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import subject_bridge_utils


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
QA_DIR = PROCESSED_DIR / "qa" / "ranking_indicators"
LOG_DIR = PROJECT_DIR / "logs"

SQLITE_PATH = PROCESSED_DIR / "ranking.sqlite"
FACT_RANKING_INDICATOR_CSV = PROCESSED_DIR / "fact_ranking_indicator.csv"
DIM_SUBJECT_ALIAS_CSV = PROCESSED_DIR / "dim_subject_alias.csv"
FACT_RANKING_INDICATOR_SUBJECT_BRIDGE_CSV = PROCESSED_DIR / "fact_ranking_indicator_subject_bridge.csv"
RUN_LOG = LOG_DIR / "ranking_indicator_run_log.md"

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


def as_number(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"-", "NA", "N/A", "不适用"}:
        return None
    text = text.replace(",", "").replace("%", "")
    try:
        return float(text)
    except Exception:
        return None


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


def parse_rank_midpoint(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("–", "-").replace("—", "-").replace("~", "-").replace("至", "-").replace("#", "")
    numbers = [int(match) for match in re.findall(r"\d+", text)]
    if not numbers:
        return None
    if len(numbers) >= 2 and "-" in text:
        return (min(numbers[0], numbers[1]) + max(numbers[0], numbers[1])) / 2
    return float(numbers[0])


def read_sheet(file_name: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(DATA_DIR / file_name, sheet_name=sheet_name, dtype=object)
    df.columns = [clean_text(column) for column in df.columns]
    df = df.dropna(how="all").copy()
    return df


def indicator_group_for(indicator_name: str) -> str:
    text = normalize_key(indicator_name)
    if any(key in text for key in ["声誉", "reputation", "雇主"]):
        return "声誉"
    if any(key in text for key in ["国际", "合作", "网络", "international", "irn"]):
        return "国际化/合作"
    if any(key in text for key in ["教学", "teaching", "科研环境", "研究环境"]):
        return "教学/环境"
    if any(key in text for key in ["商业", "产业", "收入", "转化"]):
        return "产业/转化"
    if any(key in text for key in ["论文", "引用", "被引", "出版", "高被引", "h指数", "h-index", "科研", "研究", "成果", "期刊", "图书", "会议"]):
        return "科研/论文"
    if any(key in text for key in ["教师", "奖"]):
        return "人才/奖项"
    return "其他"


def record(
    ranking_source: str,
    release_year: int | None,
    ranking_year: int | None,
    ranking_subject_raw: str,
    university_name_cn: str,
    university_name_en: str,
    country_or_region: str,
    world_rank_raw: Any,
    indicator_name: str,
    metric_type: str,
    metric_value: Any,
    source_file: str,
    source_sheet: str,
    source_row: int,
) -> dict[str, Any]:
    number = as_number(metric_value)
    rank_midpoint = parse_rank_midpoint(metric_value) if metric_type == "rank" else None
    return {
        "ranking_source": ranking_source,
        "release_year": release_year,
        "ranking_year": ranking_year,
        "ranking_subject_raw": ranking_subject_raw,
        "ranking_subject_norm": normalize_key(ranking_subject_raw),
        "university_name_cn": university_name_cn,
        "university_name_en": university_name_en,
        "country_or_region": country_or_region,
        "is_mainland_china": "中国内地" in country_or_region or country_or_region in {"中国", "中国大陆"},
        "is_tongji": university_name_cn == TARGET_UNIVERSITY or university_name_en == "Tongji University",
        "world_rank_raw": clean_text(world_rank_raw),
        "world_rank_midpoint": parse_rank_midpoint(world_rank_raw),
        "indicator_name": indicator_name,
        "indicator_norm": normalize_key(indicator_name),
        "indicator_group": indicator_group_for(indicator_name),
        "metric_type": metric_type,
        "metric_raw": clean_text(metric_value),
        "metric_value": number,
        "metric_rank_midpoint": rank_midpoint,
        "relative_rank_in_subject": None,
        "relative_rank_scope_size": None,
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
    }


def append_records_from_config(records: list[dict[str, Any]], config: dict[str, Any]) -> None:
    df = read_sheet(config["file"], config["sheet"])
    for idx, row in df.iterrows():
        subject_raw = clean_text(row.get(config["subject_col"]))
        university_cn = clean_text(row.get(config["university_cn_col"]))
        university_en = clean_text(row.get(config.get("university_en_col", ""))) if config.get("university_en_col") else ""
        region = clean_text(row.get(config.get("region_col", ""))) if config.get("region_col") else ""
        release_year = parse_year(row.get(config["release_year_col"])) if isinstance(config["release_year_col"], str) else config["release_year_col"]
        ranking_year = parse_year(row.get(config["ranking_year_col"])) if isinstance(config["ranking_year_col"], str) else config["ranking_year_col"]
        world_rank = row.get(config["world_rank_col"])
        for item in config["indicators"]:
            column = item["column"]
            if column not in df.columns:
                continue
            value = row.get(column)
            if as_number(value) is None and not clean_text(value):
                continue
            records.append(
                record(
                    ranking_source=config["ranking_source"],
                    release_year=release_year,
                    ranking_year=ranking_year,
                    ranking_subject_raw=subject_raw,
                    university_name_cn=university_cn,
                    university_name_en=university_en,
                    country_or_region=region,
                    world_rank_raw=world_rank,
                    indicator_name=item.get("name", column),
                    metric_type=item["metric_type"],
                    metric_value=value,
                    source_file=config["file"],
                    source_sheet=config["sheet"],
                    source_row=int(idx) + 2,
                )
            )


def build_records() -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    configs = [
        {
            "ranking_source": "软科",
            "file": "2025年软科世界一流学科排名20251118.xlsx",
            "sheet": "数据",
            "release_year_col": "发布年度",
            "ranking_year_col": "发布年度",
            "subject_col": "学科名称",
            "university_cn_col": "学校名称",
            "region_col": "所在地区",
            "world_rank_col": "国际排名",
            "indicators": [
                {"column": "总得分", "name": "总得分", "metric_type": "score"},
                {"column": "高水平研究成果/重要期刊论文数", "name": "高水平研究成果/重要期刊论文数", "metric_type": "score"},
                {"column": "科研影响力/论文标准化影响力", "name": "科研影响力/论文标准化影响力", "metric_type": "score"},
                {"column": "国际合作/国际合作论文比例", "name": "国际合作/国际合作论文比例", "metric_type": "score"},
                {"column": "世界一流成果", "name": "世界一流成果", "metric_type": "score"},
                {"column": "世界一流教师", "name": "世界一流教师", "metric_type": "score"},
                {"column": "辅助总得分", "name": "辅助总得分", "metric_type": "score"},
            ],
        },
        {
            "ranking_source": "QS",
            "file": "2024年QS世界学科排名-20240412.xlsx",
            "sheet": "数据",
            "release_year_col": "发布年度",
            "ranking_year_col": "发布年度",
            "subject_col": "学科中文",
            "university_cn_col": "中文名称",
            "university_en_col": "英文名称",
            "region_col": "所在地区",
            "world_rank_col": "国际排名",
            "indicators": [
                {"column": "总得分", "name": "总得分", "metric_type": "score"},
                {"column": "H指数", "name": "H指数", "metric_type": "score"},
                {"column": "篇均被引次数", "name": "篇均被引次数", "metric_type": "score"},
                {"column": "学术声誉", "name": "学术声誉", "metric_type": "score"},
                {"column": "雇主声誉", "name": "雇主声誉", "metric_type": "score"},
                {"column": "国际网络研究", "name": "国际网络研究", "metric_type": "score"},
            ],
        },
        {
            "ranking_source": "QS",
            "file": "2025年QS世界大学学科排名20250313.xlsx",
            "sheet": "明细数",
            "release_year_col": "年份",
            "ranking_year_col": "年份",
            "subject_col": "学科中文",
            "university_cn_col": "大学",
            "region_col": "地区",
            "world_rank_col": "排名",
            "indicators": [
                {"column": "综合得分", "name": "总得分", "metric_type": "score"},
                {"column": "H指数排名", "name": "H指数", "metric_type": "score"},
                {"column": "论文篇均引用率", "name": "篇均被引次数", "metric_type": "score"},
                {"column": "学术声誉", "name": "学术声誉", "metric_type": "score"},
                {"column": "雇主声誉", "name": "雇主声誉", "metric_type": "score"},
                {"column": "国际研究网络", "name": "国际网络研究", "metric_type": "score"},
            ],
        },
        {
            "ranking_source": "QS",
            "file": "2026年QS世界学科排名20260326.xlsx",
            "sheet": "数据",
            "release_year_col": "发布年度",
            "ranking_year_col": "发布年度",
            "subject_col": "学科中文",
            "university_cn_col": "中文名称",
            "university_en_col": "英文名称",
            "region_col": "所在地区",
            "world_rank_col": "国际排名",
            "indicators": [
                {"column": "总得分", "name": "总得分", "metric_type": "score"},
                {"column": "H指数", "name": "H指数", "metric_type": "score"},
                {"column": "篇均被引次数", "name": "篇均被引次数", "metric_type": "score"},
                {"column": "学术声誉", "name": "学术声誉", "metric_type": "score"},
                {"column": "雇主声誉", "name": "雇主声誉", "metric_type": "score"},
                {"column": "国际网络研究", "name": "国际网络研究", "metric_type": "score"},
            ],
        },
        {
            "ranking_source": "US News",
            "file": "2025-2026年度US News世界学科排名20251124.xlsx",
            "sheet": "Sheet1",
            "release_year_col": "发布年度",
            "ranking_year_col": "排名年度",
            "subject_col": "学科中文",
            "university_cn_col": "中文名称",
            "university_en_col": "外文名称",
            "region_col": "所在地区",
            "world_rank_col": "国际排名",
            "indicators": [
                {"column": "总得分", "name": "总得分", "metric_type": "score"},
                {"column": "全球学术声誉排名", "name": "全球学术声誉排名", "metric_type": "rank"},
                {"column": "地区学术声誉排名", "name": "地区学术声誉排名", "metric_type": "rank"},
                {"column": "出版物排名", "name": "出版物排名", "metric_type": "rank"},
                {"column": "图书排名", "name": "图书排名", "metric_type": "rank"},
                {"column": "标准化论文引用影响指数排名", "name": "标准化论文引用影响指数排名", "metric_type": "rank"},
                {"column": "总被引频次排名", "name": "总被引频次排名", "metric_type": "rank"},
                {"column": "被引用最多的10%的出版物数量排名", "name": "被引用最多的10%的出版物数量排名", "metric_type": "rank"},
                {"column": "总被引率占总被引文献的10%排名", "name": "总被引率占总被引文献的10%排名", "metric_type": "rank"},
                {"column": "具有国际合作出版物的比例排名", "name": "具有国际合作出版物的比例排名", "metric_type": "rank"},
                {"column": "国际合作排名", "name": "国际合作排名", "metric_type": "rank"},
                {"column": "排名前1%的高被引论文数量排名", "name": "排名前1%的高被引论文数量排名", "metric_type": "rank"},
                {"column": "前1%的高被引论文占论文总数的百分比排名", "name": "前1%的高被引论文占论文总数的百分比排名", "metric_type": "rank"},
                {"column": "会议排名", "name": "会议排名", "metric_type": "rank"},
            ],
        },
        {
            "ranking_source": "THE",
            "file": "世界大学学科排名THE（2022-2026年）20260123.xlsx",
            "sheet": "数据",
            "release_year_col": "发布年度",
            "ranking_year_col": "排名年度",
            "subject_col": "学科中文",
            "university_cn_col": "中文名称",
            "university_en_col": "外文名称",
            "region_col": "所在地区",
            "world_rank_col": "国际排名",
            "indicators": [
                {"column": "总得分", "name": "总得分", "metric_type": "score"},
                {"column": "教学", "name": "教学", "metric_type": "score"},
                {"column": "教学排名", "name": "教学排名", "metric_type": "rank"},
                {"column": "科研环境", "name": "科研环境", "metric_type": "score"},
                {"column": "科研环境排名", "name": "科研环境排名", "metric_type": "rank"},
                {"column": "科研质量", "name": "科研质量", "metric_type": "score"},
                {"column": "科研质量排名", "name": "科研质量排名", "metric_type": "rank"},
                {"column": "商业收入", "name": "商业收入", "metric_type": "score"},
                {"column": "商业收入排名", "name": "商业收入排名", "metric_type": "rank"},
                {"column": "国际化视野", "name": "国际化视野", "metric_type": "score"},
                {"column": "国际化视野排名", "name": "国际化视野排名", "metric_type": "rank"},
                {"column": "篇均被引", "name": "篇均被引", "metric_type": "score"},
                {"column": "篇均被引排名", "name": "篇均被引排名", "metric_type": "rank"},
            ],
        },
    ]
    for config in configs:
        append_records_from_config(records, config)
    df = pd.DataFrame(records)
    df.insert(0, "ranking_indicator_id", [f"ri_{idx + 1:08d}" for idx in range(len(df))])
    return df


def compute_relative_ranks(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["metric_value_num"] = pd.to_numeric(df["metric_value"], errors="coerce")
    df["metric_rank_midpoint_num"] = pd.to_numeric(df["metric_rank_midpoint"], errors="coerce")
    group_cols = ["ranking_source", "release_year", "ranking_year", "ranking_subject_norm", "indicator_norm", "metric_type"]
    for _, idx in df.groupby(group_cols, dropna=False).groups.items():
        sub = df.loc[idx]
        if sub["metric_type"].iloc[0] == "score":
            ranks = sub["metric_value_num"].rank(method="min", ascending=False, na_option="bottom")
        else:
            ranks = sub["metric_rank_midpoint_num"].rank(method="min", ascending=True, na_option="bottom")
        df.loc[idx, "relative_rank_in_subject"] = ranks.astype("Int64").astype(str).replace("<NA>", "")
        df.loc[idx, "relative_rank_scope_size"] = int(len(sub))
    df = df.drop(columns=["metric_value_num", "metric_rank_midpoint_num"])
    return df


def write_sqlite(df: pd.DataFrame) -> None:
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS fact_ranking_indicator")
        df.to_sql("fact_ranking_indicator", conn, index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_source_subject ON fact_ranking_indicator(ranking_source, ranking_subject_norm)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_indicator ON fact_ranking_indicator(ranking_source, indicator_norm)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_university ON fact_ranking_indicator(university_name_cn, university_name_en)")


def build_indicator_subject_bridge(df: pd.DataFrame) -> pd.DataFrame:
    aliases = subject_bridge_utils.read_alias_table(DIM_SUBJECT_ALIAS_CSV)
    return subject_bridge_utils.build_subject_bridge(
        df,
        aliases,
        fact_id_col="ranking_indicator_id",
        subject_id_col="",
        bridge_id_prefix="ranking_indicator_subject_bridge",
    )


def write_bridge_sqlite(bridge: pd.DataFrame) -> None:
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS fact_ranking_indicator_subject_bridge")
        bridge.to_sql("fact_ranking_indicator_subject_bridge", conn, index=False)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ri_bridge_subject ON fact_ranking_indicator_subject_bridge(subject_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ri_bridge_fact ON fact_ranking_indicator_subject_bridge(ranking_indicator_id)"
        )


def qa_reports(df: pd.DataFrame, indicator_subject_bridge: pd.DataFrame) -> dict[str, Any]:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    by_source = df.groupby("ranking_source").size().to_dict()
    by_source_metric = df.groupby(["ranking_source", "metric_type"]).size().reset_index(name="row_count")
    by_source_metric.to_csv(QA_DIR / "ranking_indicator_by_source_metric_type.csv", index=False, encoding="utf-8-sig")

    indicator_coverage = (
        df.groupby(["ranking_source", "indicator_name", "metric_type"], dropna=False)
        .agg(row_count=("ranking_indicator_id", "count"), subject_count=("ranking_subject_norm", "nunique"))
        .reset_index()
        .sort_values(["ranking_source", "indicator_name"])
    )
    indicator_coverage.to_csv(QA_DIR / "ranking_indicator_coverage.csv", index=False, encoding="utf-8-sig")

    bridge_summary = (
        indicator_subject_bridge.groupby(["ranking_source", "match_policy"], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["ranking_source", "match_policy"])
    )
    bridge_summary.to_csv(QA_DIR / "ranking_indicator_subject_bridge_summary.csv", index=False, encoding="utf-8-sig")

    tongji = df[df["is_tongji"] == True].copy()
    tongji.to_csv(QA_DIR / "tongji_ranking_indicators.csv", index=False, encoding="utf-8-sig")

    # Smoke-test data for the P1 peer indicator charts.
    p1_subjects = [
        ("软科", "数学"),
        ("QS", "数学"),
        ("US News", "数学"),
        ("THE", "理学"),
    ]
    smoke_rows = []
    for source, subject in p1_subjects:
        sub = df[
            (df["ranking_source"] == source)
            & (df["ranking_subject_norm"] == normalize_key(subject))
            & (df["is_mainland_china"] == True)
        ].copy()
        if not sub.empty:
            sub = sub[sub["world_rank_midpoint"].fillna(999999) <= 500]
        smoke_rows.append(
            {
                "ranking_source": source,
                "subject": subject,
                "mainland_rows": int(len(sub)),
                "mainland_university_count": int(sub["university_name_cn"].nunique()) if not sub.empty else 0,
                "indicator_count": int(sub["indicator_name"].nunique()) if not sub.empty else 0,
                "tongji_indicator_rows": int(len(sub[sub["is_tongji"] == True])) if not sub.empty else 0,
            }
        )
    smoke = pd.DataFrame(smoke_rows)
    smoke.to_csv(QA_DIR / "p1_peer_indicator_smoke_test.csv", index=False, encoding="utf-8-sig")

    missing_smoke_rows = []
    for source, subject in p1_subjects:
        sub = df[
            (df["ranking_source"] == source)
            & (df["ranking_subject_norm"] == normalize_key(subject))
            & (df["is_mainland_china"] == True)
        ].copy()
        if sub.empty:
            continue
        all_indicators = sorted(set(sub["indicator_name"]))
        tongji_indicators = sorted(set(sub[sub["is_tongji"] == True]["indicator_name"]))
        for indicator in sorted(set(all_indicators) - set(tongji_indicators)):
            missing_smoke_rows.append(
                {
                    "ranking_source": source,
                    "subject": subject,
                    "missing_for_tongji_indicator": indicator,
                    "note": "该指标在同学科其他高校中存在，但同济记录为空或未入表。",
                }
            )
    missing_smoke = pd.DataFrame(missing_smoke_rows)
    missing_smoke.to_csv(QA_DIR / "p1_tongji_missing_indicators.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "fact_ranking_indicator_rows": int(len(df)),
        "ranking_indicator_subject_bridge_rows": int(len(indicator_subject_bridge)),
        "ranking_indicator_subject_bridge_multi_alias_rows": int(
            (indicator_subject_bridge.get("match_policy", pd.Series(dtype=str)) == "multi_alias_bridge").sum()
        ),
        "rows_by_source": by_source,
        "metric_type_counts": df["metric_type"].value_counts().to_dict(),
        "tongji_indicator_rows": int(len(tongji)),
        "p1_smoke": smoke_rows,
        "outputs": {
            "fact_ranking_indicator": str(FACT_RANKING_INDICATOR_CSV),
            "fact_ranking_indicator_subject_bridge": str(FACT_RANKING_INDICATOR_SUBJECT_BRIDGE_CSV),
            "by_source_metric_type": str(QA_DIR / "ranking_indicator_by_source_metric_type.csv"),
            "indicator_coverage": str(QA_DIR / "ranking_indicator_coverage.csv"),
            "tongji_ranking_indicators": str(QA_DIR / "tongji_ranking_indicators.csv"),
            "p1_peer_indicator_smoke_test": str(QA_DIR / "p1_peer_indicator_smoke_test.csv"),
            "p1_tongji_missing_indicators": str(QA_DIR / "p1_tongji_missing_indicators.csv"),
        },
    }
    (QA_DIR / "ranking_indicator_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# 分项指标结构化 QA",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- fact_ranking_indicator 行数：{summary['fact_ranking_indicator_rows']}",
        f"- fact_ranking_indicator_subject_bridge 行数：{summary['ranking_indicator_subject_bridge_rows']}",
        f"- bridge 一对多候选行数：{summary['ranking_indicator_subject_bridge_multi_alias_rows']}",
        f"- 同济分项指标记录数：{summary['tongji_indicator_rows']}",
        "",
        "## rows by source",
        "",
    ]
    for source, count in by_source.items():
        lines.append(f"- {source}: {count}")
    lines.extend(["", "## metric type counts", ""])
    for metric_type, count in summary["metric_type_counts"].items():
        lines.append(f"- {metric_type}: {count}")
    lines.extend(["", "## P1 smoke test", ""])
    for row in smoke_rows:
        lines.append(
            f"- {row['ranking_source']} / {row['subject']}: 内地记录 {row['mainland_rows']}，"
            f"高校 {row['mainland_university_count']}，指标 {row['indicator_count']}，同济指标行 {row['tongji_indicator_rows']}"
        )
    lines.extend(["", "## P1 tongji missing indicators", ""])
    if missing_smoke.empty:
        lines.append("- 无。")
    else:
        for _, row in missing_smoke.iterrows():
            lines.append(f"- {row['ranking_source']} / {row['subject']}：{row['missing_for_tongji_indicator']}")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 软科、QS、THE得分字段按同榜单/同学科/同年度/同指标重算 `relative_rank_in_subject`。",
            "- US News多数分项为排名字段，保留原排名，同时也写入相对排名字段用于统一绘图。",
            "- P1 smoke test 只是验证数据可用性，不代表最终对标范围。正式图表仍需按 recipe 过滤前200或用户指定范围。",
        ]
    )
    (QA_DIR / "ranking_indicator_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def append_run_log(summary: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# 分项指标过程留档\n", encoding="utf-8", newline="\n")
    lines = [
        "",
        f"## {summary['generated_at']} ranking indicators",
        "",
        "### 目标",
        "",
        "结构化四大榜单分项指标，生成 `fact_ranking_indicator`，支撑分项指标相对排名图。",
        "",
        "### 输出",
        "",
        f"- `{FACT_RANKING_INDICATOR_CSV}`",
        f"- `{FACT_RANKING_INDICATOR_SUBJECT_BRIDGE_CSV}`",
        f"- `{QA_DIR / 'ranking_indicator_summary.md'}`",
        "",
        "### 核验摘要",
        "",
        f"- fact_ranking_indicator 行数：{summary['fact_ranking_indicator_rows']}",
        f"- fact_ranking_indicator_subject_bridge 行数：{summary['ranking_indicator_subject_bridge_rows']}",
        f"- bridge 一对多候选行数：{summary['ranking_indicator_subject_bridge_multi_alias_rows']}",
        f"- 同济分项指标记录数：{summary['tongji_indicator_rows']}",
        "",
    ]
    with RUN_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    df = build_records()
    df = compute_relative_ranks(df)
    indicator_subject_bridge = build_indicator_subject_bridge(df)
    df.to_csv(FACT_RANKING_INDICATOR_CSV, index=False, encoding="utf-8-sig")
    indicator_subject_bridge.to_csv(FACT_RANKING_INDICATOR_SUBJECT_BRIDGE_CSV, index=False, encoding="utf-8-sig")
    write_sqlite(df)
    write_bridge_sqlite(indicator_subject_bridge)
    summary = qa_reports(df, indicator_subject_bridge)
    append_run_log(summary)
    print((QA_DIR / "ranking_indicator_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
