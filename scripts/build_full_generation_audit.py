from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_DIR = Path(__file__).resolve().parent.parent
BATCH_DIRS = [
    PROJECT_DIR / "outputs" / "regenerate_all_ministry_subject_word_reports" / "batch_20260927_125119",
    PROJECT_DIR / "outputs" / "regenerate_all_ministry_subject_word_reports" / "batch_20260927_125121",
]
OUTPUT_DIR = (
    PROJECT_DIR
    / "outputs"
    / "regenerate_all_ministry_subject_word_reports"
    / "full_generation_audit_20260927"
)


def load_font(size: int) -> ImageFont.ImageFont:
    for path in [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def load_results() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for batch_dir in BATCH_DIRS:
        summary_path = batch_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in summary.get("results", []):
            row = dict(item)
            row["batch_dir"] = str(batch_dir)
            results.append(row)
    return sorted(results, key=lambda row: str(row.get("code", "")))


def build_report_contact_sheet(code: str, subject: str, page_paths: list[Path], output_path: Path) -> None:
    thumb_w, thumb_h = 180, 255
    label_h = 30
    cols = 5
    rows = max(1, (len(page_paths) + cols - 1) // cols)
    header_h = 58
    sheet = Image.new("RGB", (cols * thumb_w, header_h + rows * (thumb_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(22)
    label_font = load_font(15)
    draw.text((16, 14), f"{code} {subject} | {len(page_paths)} pages", font=title_font, fill=(20, 32, 48))
    for index, page_path in enumerate(page_paths):
        image = Image.open(page_path).convert("RGB")
        image.thumbnail((thumb_w - 10, thumb_h - 10))
        x = (index % cols) * thumb_w + (thumb_w - image.width) // 2
        y = header_h + (index // cols) * (thumb_h + label_h) + (thumb_h - image.height) // 2
        sheet.paste(image, (x, y))
        draw.rectangle((x, y, x + image.width, y + image.height), outline=(185, 193, 203), width=1)
        draw.text(
            ((index % cols) * thumb_w + 8, header_h + (index // cols) * (thumb_h + label_h) + thumb_h + 3),
            page_path.stem,
            font=label_font,
            fill=(55, 65, 81),
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def build_sparse_contact_sheet(rows: list[dict[str, Any]], output_path: Path) -> None:
    entries: list[tuple[str, Path]] = []
    for row in rows:
        for page in row["sparse_page_paths"]:
            entries.append((f"{row['code']} {row['subject']} | {page.name}", page))
    if not entries:
        return
    cell_w, cell_h = 360, 550
    cols = 4
    rows_count = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_count * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = load_font(17)
    for index, (label, page_path) in enumerate(entries):
        image = Image.open(page_path).convert("RGB")
        image.thumbnail((cell_w - 20, cell_h - 55))
        x = (index % cols) * cell_w + (cell_w - image.width) // 2
        y = (index // cols) * cell_h + 8
        sheet.paste(image, (x, y))
        draw.rectangle((x, y, x + image.width, y + image.height), outline=(185, 193, 203), width=1)
        draw.text(((index % cols) * cell_w + 10, (index // cols) * cell_h + cell_h - 35), label, font=font, fill=(20, 32, 48))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def build_audit() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    contact_dir = OUTPUT_DIR / "qa" / "report_contact_sheets"
    deliverable_dir = OUTPUT_DIR / "reports"
    deliverable_dir.mkdir(parents=True, exist_ok=True)
    source_results = load_results()
    rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for item in source_results:
        code = str(item["code"])
        if code in seen_codes:
            raise RuntimeError(f"Duplicate subject code: {code}")
        seen_codes.add(code)
        run_dir = Path(item["run_dir"])
        docx_path = Path(item["docx"])
        word_qa_path = docx_path.parent / "qa" / "word_qa_report.json"
        word_qa = json.loads(word_qa_path.read_text(encoding="utf-8"))
        render_dir = Path(word_qa["render"]["render_dir"])
        page_paths = sorted(
            render_dir.glob("page-*.png"),
            key=lambda path: int(path.stem.split("-")[-1]),
        )
        sparse_page_paths = [Path(path) for path in item.get("sparse_pages", [])]
        artifact_audit_path = run_dir / "audit" / "subject_artifact_audit.json"
        artifact_audit = (
            json.loads(artifact_audit_path.read_text(encoding="utf-8"))
            if artifact_audit_path.exists()
            else None
        )
        coverage_statement = int(item["page_count"]) == 1
        artifact_audit_expected = not coverage_statement
        artifact_audit_pass = (
            artifact_audit is not None
            and int(artifact_audit.get("fail_count", 0)) == 0
            and int(artifact_audit.get("artifact_count", 0)) > 0
        ) if artifact_audit_expected else artifact_audit is None
        contact_sheet_path = contact_dir / f"{code}_contact_sheet.png"
        build_report_contact_sheet(code, str(item["subject"]), page_paths, contact_sheet_path)
        deliverable_docx_path = deliverable_dir / f"{code}_{item['subject']}.docx"
        shutil.copy2(docx_path, deliverable_docx_path)
        rows.append(
            {
                "code": code,
                "subject": str(item["subject"]),
                "report_type": "coverage_statement" if coverage_statement else "full_report",
                "status": str(item["status"]),
                "word_qa_status": str(item["overall_status"]),
                "render_status": str(item["render_status"]),
                "page_count": int(item["page_count"]),
                "blank_page_count": len(item.get("blank_pages", [])),
                "sparse_page_count": len(sparse_page_paths),
                "artifact_count": int(artifact_audit.get("artifact_count", 0)) if artifact_audit else 0,
                "artifact_fail_count": int(artifact_audit.get("fail_count", 0)) if artifact_audit else 0,
                "artifact_audit_expected": artifact_audit_expected,
                "artifact_audit_pass": artifact_audit_pass,
                "runtime_rejected_sources": artifact_audit.get("runtime_rejected_sources", []) if artifact_audit else [],
                "docx": str(docx_path),
                "deliverable_docx": str(deliverable_docx_path),
                "run_dir": str(run_dir),
                "word_qa_path": str(word_qa_path),
                "artifact_audit_path": str(artifact_audit_path) if artifact_audit_path.exists() else "",
                "contact_sheet": str(contact_sheet_path),
                "sparse_page_paths": sparse_page_paths,
            }
        )

    build_sparse_contact_sheet(rows, OUTPUT_DIR / "qa" / "sparse_pages_contact_sheet.png")
    serializable_rows = []
    for row in rows:
        serializable = dict(row)
        serializable["sparse_page_paths"] = [str(path) for path in row["sparse_page_paths"]]
        serializable_rows.append(serializable)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "batch_dirs": [str(path) for path in BATCH_DIRS],
        "output_dir": str(OUTPUT_DIR),
        "summary": {
            "subject_count": len(rows),
            "unique_code_count": len(seen_codes),
            "full_report_count": sum(row["report_type"] == "full_report" for row in rows),
            "coverage_statement_count": sum(row["report_type"] == "coverage_statement" for row in rows),
            "total_page_count": sum(row["page_count"] for row in rows),
            "batch_failure_count": sum(row["status"] != "ok" for row in rows),
            "word_qa_failure_count": sum(row["word_qa_status"] not in {"pass", "pass_with_warnings"} for row in rows),
            "blank_page_report_count": sum(row["blank_page_count"] > 0 for row in rows),
            "sparse_page_report_count": sum(row["sparse_page_count"] > 0 for row in rows),
            "artifact_audit_failure_count": sum(not row["artifact_audit_pass"] for row in rows),
        },
        "reports": serializable_rows,
    }
    (OUTPUT_DIR / "full_generation_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )

    csv_fields = [
        "code", "subject", "report_type", "status", "word_qa_status", "render_status",
        "page_count", "blank_page_count", "sparse_page_count", "artifact_count",
        "artifact_fail_count", "artifact_audit_expected", "artifact_audit_pass",
        "runtime_rejected_sources", "docx", "run_dir", "word_qa_path",
        "deliverable_docx", "artifact_audit_path", "contact_sheet",
    ]
    with (OUTPUT_DIR / "full_generation_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            csv_row = {key: row[key] for key in csv_fields}
            csv_row["runtime_rejected_sources"] = ";".join(row["runtime_rejected_sources"])
            writer.writerow(csv_row)

    summary = report["summary"]
    lines = [
        "# 全部学科学科报告生成审计",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 学科数：{summary['subject_count']}",
        f"- 完整报告：{summary['full_report_count']}",
        f"- 覆盖说明：{summary['coverage_statement_count']}",
        f"- 总页数：{summary['total_page_count']}",
        f"- 集中交付目录：{deliverable_dir}",
        f"- 批次失败：{summary['batch_failure_count']}",
        f"- Word QA 失败：{summary['word_qa_failure_count']}",
        f"- 含空白页报告：{summary['blank_page_report_count']}",
        f"- 学科工件审计失败：{summary['artifact_audit_failure_count']}",
        "",
        "| 代码 | 学科 | 类型 | 页数 | Word QA | 空白页 | 稀疏页 | 工件审计 |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['code']} | {row['subject']} | {row['report_type']} | {row['page_count']} | "
            f"{row['word_qa_status']} | {row['blank_page_count']} | {row['sparse_page_count']} | "
            f"{'pass' if row['artifact_audit_pass'] else 'fail'} |"
        )
    (OUTPUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    build_audit()
