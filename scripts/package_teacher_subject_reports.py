from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
AUDIT_DIR = PROJECT_DIR / "outputs" / "final_subject_report_delivery_audit_20260928"
AUDIT_SUMMARY_JSON = AUDIT_DIR / "final_audit_summary.json"
SUBJECT_AUDIT_CSV = AUDIT_DIR / "subject_report_coverage_audit.csv"
DELIVERY_DIR = PROJECT_DIR / "outputs" / "teacher_delivery_20260928"
REPORT_DIR = DELIVERY_DIR / "学科报告"
ZIP_PATH = PROJECT_DIR / "outputs" / "同济大学46个学科国际排名发展分析报告_20260928.zip"
ZIP_ROOT = "同济大学46个学科国际排名发展分析报告"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def main() -> None:
    audit_summary = json.loads(AUDIT_SUMMARY_JSON.read_text(encoding="utf-8-sig"))
    if audit_summary.get("status") != "pass":
        raise RuntimeError("Final subject report audit has not passed.")

    subjects = pd.read_csv(SUBJECT_AUDIT_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    if len(subjects) != 46 or subjects["ministry_subject_code"].nunique() != 46:
        raise RuntimeError("Expected 46 unique subject reports before packaging.")
    if DELIVERY_DIR.exists() or ZIP_PATH.exists():
        raise FileExistsError("Teacher delivery output already exists; refusing to overwrite it.")

    REPORT_DIR.mkdir(parents=True, exist_ok=False)
    manifest: list[dict[str, Any]] = []
    for _, row in subjects.sort_values("ministry_subject_code").iterrows():
        source_path = Path(clean_text(row.get("deliverable_docx")))
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        target_path = REPORT_DIR / source_path.name
        shutil.copy2(source_path, target_path)
        source_hash = sha256(source_path)
        target_hash = sha256(target_path)
        if source_hash != target_hash:
            raise RuntimeError(f"Copied Word report hash mismatch: {source_path.name}")
        manifest.append(
            {
                "ministry_subject_code": clean_text(row.get("ministry_subject_code")),
                "subject_name": clean_text(row.get("subject_name")),
                "report_type": clean_text(row.get("report_type")),
                "page_count": int(float(clean_text(row.get("page_count")) or 0)),
                "file_name": target_path.name,
                "size_bytes": target_path.stat().st_size,
                "sha256": target_hash,
            }
        )

    coverage_rows = [row for row in manifest if row["report_type"] == "coverage_statement"]
    delivery_note = [
        "同济大学学科国际排名发展分析报告",
        "",
        "交付日期：2026年9月28日",
        f"报告总数：{len(manifest)} 份",
        f"完整分析报告：{sum(row['report_type'] == 'full_report' for row in manifest)} 份",
        f"数据覆盖说明：{len(coverage_rows)} 份",
        "",
        "数据覆盖说明对应学科：",
    ]
    for row in coverage_rows:
        delivery_note.append(f"- {row['ministry_subject_code']} {row['subject_name']}")
    delivery_note.extend(
        [
            "",
            "说明：以上 4 个学科在当前教育部基础映射、同济学科映射覆盖和已登记校正规则中，均没有四类国际学科排名的直接对应口径，因此保留为数据覆盖说明，不以相近学科排名替代。",
            "",
            "全部报告已完成文件完整性、页面渲染、学科映射和数据来源核查。",
        ]
    )
    (DELIVERY_DIR / "00_交付说明.txt").write_text(
        "\n".join(delivery_note),
        encoding="utf-8-sig",
        newline="\n",
    )

    report_list = ["同济大学学科国际排名发展分析报告清单", ""]
    for row in manifest:
        report_label = "完整报告" if row["report_type"] == "full_report" else "数据覆盖说明"
        report_list.append(
            f"{row['ministry_subject_code']}  {row['subject_name']}  {report_label}  {row['page_count']}页  {row['file_name']}"
        )
    (DELIVERY_DIR / "00_报告清单.txt").write_text(
        "\n".join(report_list),
        encoding="utf-8-sig",
        newline="\n",
    )

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(DELIVERY_DIR.rglob("*")):
            if path.is_file():
                relative = path.relative_to(DELIVERY_DIR).as_posix()
                archive.write(path, arcname=f"{ZIP_ROOT}/{relative}")

    with zipfile.ZipFile(ZIP_PATH) as archive:
        bad_zip_member = archive.testzip()
        archive_names = archive.namelist()
    if bad_zip_member is not None:
        raise RuntimeError(f"Corrupt ZIP member: {bad_zip_member}")
    if sum(name.lower().endswith(".docx") for name in archive_names) != 46:
        raise RuntimeError("Teacher ZIP does not contain exactly 46 Word reports.")

    package_summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "audit_status": audit_summary.get("status"),
        "delivery_dir": str(DELIVERY_DIR),
        "zip_path": str(ZIP_PATH),
        "zip_size_bytes": ZIP_PATH.stat().st_size,
        "zip_sha256": sha256(ZIP_PATH),
        "report_count": len(manifest),
        "full_report_count": sum(row["report_type"] == "full_report" for row in manifest),
        "coverage_statement_count": len(coverage_rows),
        "zip_entry_count": len(archive_names),
        "zip_docx_count": sum(name.lower().endswith(".docx") for name in archive_names),
        "zip_integrity_pass": bad_zip_member is None,
        "reports": manifest,
    }
    (DELIVERY_DIR / "delivery_package_summary.json").write_text(
        json.dumps(package_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({key: value for key, value in package_summary.items() if key != "reports"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
