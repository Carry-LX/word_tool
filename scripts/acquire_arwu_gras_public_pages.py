from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(r"E:\projects\water\word_tool")
NODE_EXE = Path(r"C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
RAW_ROOT = PROJECT_ROOT / "external_data" / "raw" / "shanghairanking_gras_public"
PROCESSED_ROOT = PROJECT_ROOT / "external_data" / "processed"
REPORT_ROOT = PROJECT_ROOT / "external_data" / "reports"

YEARS_TO_FETCH = [2023, 2024, 2025]
REQUEST_SLEEP_SECONDS = 0.25
USER_AGENT = "Mozilla/5.0 common-data-gap-supplement"
BASE_URL = "https://www.shanghairanking.com"
TARGET_UNIVERSITY_KEYWORDS = ["Tongji University", "同济大学"]


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def request_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8", errors="replace") == text:
        return
    path.write_text(text, encoding="utf-8", newline="\n")


def extract_static_base(index_html: str) -> str:
    match = re.search(r'href="(/_nuxt/static/\d+)/rankings/gras/\d{4}(?:/[A-Z]{2}\d{4})?/payload\.js"', index_html)
    if not match:
        raise ValueError("Cannot find Nuxt static base in ShanghaiRanking index HTML.")
    return match.group(1)


def extract_subject_catalog(year: int, index_html: str) -> pd.DataFrame:
    pattern = re.compile(
        rf'href="/rankings/gras/{year}/([A-Z]{{2}}\d{{4}})"[^>]*>\s*<span[^>]*>\s*([^<]+)\s*</span>',
        re.S,
    )
    rows = []
    for code, subject_name in pattern.findall(index_html):
        rows.append(
            {
                "year": year,
                "arwu_subject_code": code,
                "arwu_subject_name_en": clean_text(subject_name),
                "source_url": f"{BASE_URL}/rankings/gras/{year}/{code}",
            }
        )
    return pd.DataFrame(rows).drop_duplicates()


def download_year_index(year: int) -> tuple[pd.DataFrame, str]:
    index_url = f"{BASE_URL}/rankings/gras/{year}"
    index_path = RAW_ROOT / str(year) / "index.html"
    if index_path.exists():
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
    else:
        index_html = request_text(index_url)
        write_text_if_changed(index_path, index_html)
        time.sleep(REQUEST_SLEEP_SECONDS)
    catalog = extract_subject_catalog(year, index_html)
    static_base = extract_static_base(index_html)
    return catalog, static_base


def download_payload(year: int, subject_code: str, static_base: str) -> tuple[Path | None, str]:
    payload_path = RAW_ROOT / str(year) / f"{subject_code}_payload.js"
    if payload_path.exists() and payload_path.stat().st_size > 1000:
        return payload_path, "cached"
    payload_url = f"{BASE_URL}{static_base}/rankings/gras/{year}/{subject_code}/payload.js"
    try:
        payload_text = request_text(payload_url)
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except Exception as exc:
        return None, f"error_{type(exc).__name__}"
    write_text_if_changed(payload_path, payload_text)
    time.sleep(REQUEST_SLEEP_SECONDS)
    return payload_path, "downloaded"


def payload_to_json(payload_path: Path) -> dict[str, Any]:
    node_code = r"""
const fs = require("fs");
const vm = require("vm");
const payloadPath = process.argv[1];
const source = fs.readFileSync(payloadPath, "utf8");
let captured = null;
global.__NUXT_JSONP__ = (routePath, payload) => {
  captured = { routePath, payload };
};
vm.runInThisContext(source, { timeout: 10000 });
if (!captured || !captured.payload || !captured.payload.data || !captured.payload.data[0]) {
  throw new Error("ShanghaiRanking payload did not expose data[0].");
}
process.stdout.write(JSON.stringify(captured.payload.data[0]));
"""
    completed = subprocess.run(
        [str(NODE_EXE), "-e", node_code, str(payload_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def parse_payload_rows(year: int, subject_code: str, subject_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    indicator_name_by_code = {
        str(item.get("code")): clean_text(item.get("nameEn"))
        for item in payload.get("indList", [])
        if clean_text(item.get("code"))
    }
    rows = []
    for item in payload.get("univList", []):
        base = {
            "ranking_source": "ARWU GRAS public web",
            "ranking_year": year,
            "arwu_subject_code": subject_code,
            "arwu_subject_name_en": subject_name,
            "world_rank": clean_text(item.get("ranking")),
            "university_name_en": clean_text(item.get("univNameEn")),
            "university_slug": clean_text(item.get("univUp")),
            "university_code": clean_text(item.get("univCode")),
            "region": clean_text(item.get("region")),
            "region_rank": clean_text(item.get("regionRanking")),
            "total_score": item.get("score"),
            "source_url": f"{BASE_URL}/rankings/gras/{year}/{subject_code}",
        }
        ind_data = item.get("indData") if isinstance(item.get("indData"), dict) else {}
        for indicator_code, indicator_name in indicator_name_by_code.items():
            value = item.get(indicator_code, ind_data.get(indicator_code))
            base[f"indicator_{indicator_code}"] = value
            base[f"indicator_{indicator_code}_name"] = indicator_name
        rows.append(base)
    return rows


def build_long_indicator_rows(wide: pd.DataFrame) -> pd.DataFrame:
    if wide.empty:
        return pd.DataFrame()
    indicator_codes = sorted(
        {
            col.replace("indicator_", "")
            for col in wide.columns
            if re.fullmatch(r"indicator_\d+", col)
        },
        key=int,
    )
    rows = []
    id_cols = [
        "ranking_source",
        "ranking_year",
        "arwu_subject_code",
        "arwu_subject_name_en",
        "world_rank",
        "university_name_en",
        "university_slug",
        "university_code",
        "region",
        "region_rank",
        "total_score",
        "source_url",
    ]
    for _, row in wide.iterrows():
        for code in indicator_codes:
            rows.append(
                {
                    **{col: row.get(col) for col in id_cols},
                    "indicator_code": code,
                    "indicator_name": row.get(f"indicator_{code}_name"),
                    "indicator_value": row.get(f"indicator_{code}"),
                }
            )
    return pd.DataFrame(rows)


def is_tongji(value: Any) -> bool:
    text = clean_text(value).lower()
    return any(keyword.lower() in text for keyword in TARGET_UNIVERSITY_KEYWORDS)


def main() -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    catalog_frames = []
    ranking_rows: list[dict[str, Any]] = []
    registry_rows = []

    for year in YEARS_TO_FETCH:
        catalog, static_base = download_year_index(year)
        catalog_frames.append(catalog)
        for _, subject in catalog.iterrows():
            subject_code = clean_text(subject["arwu_subject_code"])
            subject_name = clean_text(subject["arwu_subject_name_en"])
            payload_path, status = download_payload(year, subject_code, static_base)
            registry_rows.append(
                {
                    "year": year,
                    "arwu_subject_code": subject_code,
                    "arwu_subject_name_en": subject_name,
                    "status": status,
                    "payload_path": str(payload_path.relative_to(PROJECT_ROOT)) if payload_path else "",
                    "source_url": subject["source_url"],
                    "checked_at": now_text(),
                }
            )
            if payload_path is None:
                continue
            try:
                payload = payload_to_json(payload_path)
                ranking_rows.extend(parse_payload_rows(year, subject_code, subject_name, payload))
            except Exception as exc:
                registry_rows[-1]["status"] = f"parse_error_{type(exc).__name__}"
                registry_rows[-1]["parse_error"] = str(exc)[:300]

    catalog_df = pd.concat(catalog_frames, ignore_index=True) if catalog_frames else pd.DataFrame()
    wide_df = pd.DataFrame(ranking_rows)
    long_df = build_long_indicator_rows(wide_df)
    registry_df = pd.DataFrame(registry_rows)

    catalog_df.to_csv(PROCESSED_ROOT / "arwu_gras_public_subject_catalog.csv", index=False, encoding="utf-8-sig")
    wide_df.to_csv(PROCESSED_ROOT / "arwu_gras_public_rankings_2023_2025_wide.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(PROCESSED_ROOT / "arwu_gras_public_rankings_2023_2025_long.csv", index=False, encoding="utf-8-sig")
    registry_df.to_csv(REPORT_ROOT / "arwu_gras_public_acquisition_registry.csv", index=False, encoding="utf-8-sig")

    tongji_wide = wide_df[wide_df["university_name_en"].apply(is_tongji)].copy() if not wide_df.empty else pd.DataFrame()
    tongji_long = long_df[long_df["university_name_en"].apply(is_tongji)].copy() if not long_df.empty else pd.DataFrame()
    tongji_wide.to_csv(PROCESSED_ROOT / "arwu_gras_public_tongji_history_2023_2025_wide.csv", index=False, encoding="utf-8-sig")
    tongji_long.to_csv(PROCESSED_ROOT / "arwu_gras_public_tongji_history_2023_2025_long.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": now_text(),
        "years_to_fetch": YEARS_TO_FETCH,
        "subject_catalog_rows": int(len(catalog_df)),
        "ranking_rows": int(len(wide_df)),
        "indicator_long_rows": int(len(long_df)),
        "tongji_subject_year_rows": int(len(tongji_wide)),
        "status_counts": registry_df["status"].value_counts().to_dict() if not registry_df.empty else {},
        "source_pages": [
            "https://www.shanghairanking.com/rankings/gras/2025",
            "https://www.shanghairanking.com/methodology/gras/2025",
        ],
        "notes": [
            "This script caches ShanghaiRanking Nuxt payloads and parses the public web table data.",
            "The public page normally exposes the ranked universities contained in the payload for each subject/year.",
            "Use source_url and payload_path for audit before merging into report artifacts.",
        ],
    }
    (REPORT_ROOT / "arwu_gras_public_acquisition_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# ARWU GRAS Public Web Acquisition",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- years_to_fetch: {', '.join(str(year) for year in YEARS_TO_FETCH)}",
        f"- subject_catalog_rows: {summary['subject_catalog_rows']}",
        f"- ranking_rows: {summary['ranking_rows']}",
        f"- tongji_subject_year_rows: {summary['tongji_subject_year_rows']}",
        "",
        "## Outputs",
        "",
        "- `external_data/processed/arwu_gras_public_subject_catalog.csv`",
        "- `external_data/processed/arwu_gras_public_rankings_2023_2025_wide.csv`",
        "- `external_data/processed/arwu_gras_public_rankings_2023_2025_long.csv`",
        "- `external_data/processed/arwu_gras_public_tongji_history_2023_2025_wide.csv`",
        "- `external_data/processed/arwu_gras_public_tongji_history_2023_2025_long.csv`",
        "- `external_data/reports/arwu_gras_public_acquisition_registry.csv`",
        "",
        "## Use",
        "",
        "This closes part of the common ARWU multi-year indicator-history gap. It is not tied to mathematics, computer science, or civil engineering.",
    ]
    (REPORT_ROOT / "arwu_gras_public_acquisition_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
