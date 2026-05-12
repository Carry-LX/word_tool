from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = PROJECT_DIR / "processed"
QA_DIR = PROCESSED_DIR / "qa" / "university_province"
OUTPUT_CSV = PROCESSED_DIR / "dim_university_province.csv"

SOURCE_FILES = [
    {
        "path": DATA_DIR / "全国双一流学科明细表2022&2017.v2.xlsx",
        "sheet": "双一流学科（第二轮-不含清北）明细",
        "university_column": "学校名称",
        "province_column": "省份",
    },
    {
        "path": DATA_DIR / "全国高校第四轮&第三轮学科评估结果.xlsx",
        "sheet": "数据",
        "university_column": "学校名称",
        "province_column": "省份",
    },
    {
        "path": DATA_DIR / "副本第五轮评估结果（不完全）20260508(分析).xlsx",
        "sheet": "数据",
        "university_column": "单位名称",
        "province_column": "省份",
    },
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def university_key(value: Any) -> str:
    name = clean_text(value)
    return re.sub(r"[（(].*?[）)]", "", name).strip()


def read_source_rows() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in SOURCE_FILES:
        path = source["path"]
        if not path.exists():
            continue
        frame = pd.read_excel(path, sheet_name=source["sheet"], dtype=str).fillna("")
        university_col = source["university_column"]
        province_col = source["province_column"]
        if university_col not in frame.columns or province_col not in frame.columns:
            continue
        for _, row in frame.iterrows():
            name = clean_text(row.get(university_col))
            province = clean_text(row.get(province_col))
            if not name or not province:
                continue
            rows.append(
                {
                    "university_name_cn": name,
                    "university_key": university_key(name),
                    "province": province,
                    "source_file": path.name,
                    "source_sheet": source["sheet"],
                }
            )
    return pd.DataFrame(rows)


def resolve_provinces(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["university_name_cn", "province", "source_count", "source_files", "province_candidates"])

    resolved_rows: list[dict[str, Any]] = []
    for key, group in raw.groupby("university_key", dropna=False):
        if not clean_text(key):
            continue
        province_counts = Counter(group["province"].tolist())
        province, count = province_counts.most_common(1)[0]
        names = sorted({clean_text(name) for name in group["university_name_cn"].tolist() if clean_text(name)})
        source_files = sorted({clean_text(name) for name in group["source_file"].tolist() if clean_text(name)})
        candidates = "；".join(f"{name}:{num}" for name, num in province_counts.most_common())
        resolved_rows.append(
            {
                "university_name_cn": names[0] if names else key,
                "university_key": key,
                "province": province,
                "source_count": int(count),
                "source_files": "；".join(source_files),
                "province_candidates": candidates,
            }
        )
    return pd.DataFrame(resolved_rows).sort_values(["province", "university_name_cn"]).reset_index(drop=True)


def write_qa(raw: pd.DataFrame, resolved: pd.DataFrame) -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_csv(QA_DIR / "university_province_raw_sources.csv", index=False, encoding="utf-8-sig")
    conflict_rows = []
    if not raw.empty:
        for key, group in raw.groupby("university_key", dropna=False):
            provinces = sorted({clean_text(value) for value in group["province"].tolist() if clean_text(value)})
            if len(provinces) > 1:
                conflict_rows.append(
                    {
                        "university_key": key,
                        "province_candidates": "；".join(provinces),
                        "source_rows": len(group),
                    }
                )
    conflict_df = pd.DataFrame(conflict_rows)
    conflict_df.to_csv(QA_DIR / "university_province_conflicts.csv", index=False, encoding="utf-8-sig")
    source_counts = defaultdict(int)
    for file_name in raw.get("source_file", pd.Series(dtype=str)).tolist():
        source_counts[file_name] += 1
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_rows": int(len(raw)),
        "resolved_universities": int(len(resolved)),
        "conflict_universities": int(len(conflict_df)),
        "source_rows": dict(sorted(source_counts.items())),
        "output_csv": str(OUTPUT_CSV),
    }
    (QA_DIR / "university_province_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# 学校-省份映射构建记录",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 原始来源行数：{summary['raw_rows']}",
        f"- 去重后学校数：{summary['resolved_universities']}",
        f"- 省份冲突学校数：{summary['conflict_universities']}",
        f"- 输出：`{OUTPUT_CSV}`",
        "",
        "## 来源",
    ]
    for name, count in summary["source_rows"].items():
        lines.append(f"- `{name}`：{count} 行")
    (QA_DIR / "university_province_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    raw = read_source_rows()
    resolved = resolve_provinces(raw)
    resolved.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    write_qa(raw, resolved)
    print(f"wrote {OUTPUT_CSV} rows={len(resolved)}")


if __name__ == "__main__":
    main()
