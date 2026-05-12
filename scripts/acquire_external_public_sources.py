from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"E:\projects\water\word_tool")
EXTERNAL_DATA_ROOT = PROJECT_ROOT / "external_data"
RAW_ROOT = EXTERNAL_DATA_ROOT / "raw"
REPORT_ROOT = EXTERNAL_DATA_ROOT / "reports"

DOWNLOADS = [
    {
        "source_id": "cwts_leiden_traditional_2025_pdf",
        "title": "CWTS Leiden Ranking Traditional Edition 2025 PDF",
        "url": "https://zenodo.org/api/records/17473109/files/CWTS%20Leiden%20Ranking%20Traditional%20Edition%202025.pdf/content",
        "output_path": RAW_ROOT / "cwts_leiden_traditional_2025" / "CWTS Leiden Ranking Traditional Edition 2025.pdf",
        "expected_bytes": 342439,
        "expected_md5": "b214d74a0997867720d3223ac35de056",
        "license": "CC-BY-4.0",
        "doi": "10.5281/zenodo.17473109",
        "use_case": "论文计量公开来源方法说明；WoS/Clarivate 传统口径。",
    },
    {
        "source_id": "cwts_leiden_traditional_2025_xlsx",
        "title": "CWTS Leiden Ranking Traditional Edition 2025 XLSX",
        "url": "https://zenodo.org/api/records/17473109/files/CWTS%20Leiden%20Ranking%20Traditional%20Edition%202025.xlsx/content",
        "output_path": RAW_ROOT / "cwts_leiden_traditional_2025" / "CWTS Leiden Ranking Traditional Edition 2025.xlsx",
        "expected_bytes": 204808583,
        "expected_md5": "e5f8441f97094f99cd780cd988e19303",
        "license": "CC-BY-4.0",
        "doi": "10.5281/zenodo.17473109",
        "use_case": "论文量、高被引、国际合作等公开论文计量指标补充源；可支撑论文实力章节的公开替代口径。",
    },
    {
        "source_id": "cwts_leiden_open_2025_main_fields",
        "title": "CWTS Leiden Ranking Open Edition 2025 Main fields",
        "url": "https://zenodo.org/api/records/17473224/files/CWTS%20Leiden%20Ranking%20Open%20Edition%202025%20-%20Main%20fields.xlsx/content",
        "output_path": RAW_ROOT / "cwts_leiden_open_2025" / "CWTS Leiden Ranking Open Edition 2025 - Main fields.xlsx",
        "expected_bytes": 15483,
        "expected_md5": "40bdbffafe85898e2f13a5334b88e849",
        "license": "CC0",
        "doi": "10.5281/zenodo.17473224",
        "use_case": "OpenAlex 版领域维表；用于未来学科迁移时建立公开领域映射。",
    },
    {
        "source_id": "cwts_leiden_open_2025_universities",
        "title": "CWTS Leiden Ranking Open Edition 2025 Universities",
        "url": "https://zenodo.org/api/records/17473224/files/CWTS%20Leiden%20Ranking%20Open%20Edition%202025%20-%20Universities.xlsx/content",
        "output_path": RAW_ROOT / "cwts_leiden_open_2025" / "CWTS Leiden Ranking Open Edition 2025 - Universities.xlsx",
        "expected_bytes": 117456,
        "expected_md5": "5bc3ff9fd5f4870d59e2eb29979db572",
        "license": "CC0",
        "doi": "10.5281/zenodo.17473224",
        "use_case": "OpenAlex 版高校维表；用于未来按高校 ID 做公开论文计量接入。",
    },
]


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ok(path: Path, expected_bytes: int, expected_md5: str) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        return False, f"size_mismatch:{actual_bytes}!={expected_bytes}"
    actual_md5 = md5_file(path)
    if actual_md5.lower() != expected_md5.lower():
        return False, f"md5_mismatch:{actual_md5}!={expected_md5}"
    return True, "ok"


def download_file(item: dict) -> dict:
    path = Path(item["output_path"])
    path.parent.mkdir(parents=True, exist_ok=True)

    ok, status = file_ok(path, item["expected_bytes"], item["expected_md5"])
    if ok:
        return {
            **item,
            "status": "already_complete",
            "bytes": path.stat().st_size,
            "md5": md5_file(path),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    part_path = path.with_suffix(path.suffix + ".part")
    if part_path.exists():
        part_path.unlink()

    if path.exists() and status.startswith("size_mismatch"):
        backup_path = path.with_suffix(path.suffix + f".incomplete_{int(time.time())}")
        shutil.move(str(path), str(backup_path))

    request = urllib.request.Request(
        item["url"],
        headers={"User-Agent": "Mozilla/5.0 data-acquisition audit"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, part_path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    os.replace(part_path, path)
    ok, final_status = file_ok(path, item["expected_bytes"], item["expected_md5"])
    return {
        **item,
        "status": "downloaded_complete" if ok else f"downloaded_but_{final_status}",
        "bytes": path.stat().st_size,
        "md5": md5_file(path),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in DOWNLOADS:
        print(f"checking {item['source_id']}")
        row = download_file(item)
        row["output_path"] = str(row["output_path"])
        rows.append(row)
        print(f"  {row['status']} bytes={row['bytes']}")

    registry_path = REPORT_ROOT / "external_source_download_registry.json"
    registry_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    csv_path = REPORT_ROOT / "external_source_download_registry.csv"
    headers = [
        "source_id",
        "title",
        "doi",
        "license",
        "status",
        "bytes",
        "md5",
        "output_path",
        "url",
        "use_case",
        "checked_at",
    ]
    lines = [",".join(headers)]
    for row in rows:
        values = []
        for header in headers:
            value = str(row.get(header, "")).replace('"', '""')
            values.append(f'"{value}"')
        lines.append(",".join(values))
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
