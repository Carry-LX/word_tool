"""Index real, QA-checked local reports for preview and random review."""
from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

from demo_runtime import PROJECT_DIR, configuration, read_json


def subjects() -> list[dict]:
    path = PROJECT_DIR / configuration()["coverage_csv"]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    unique = {}
    for row in rows:
        code = row.get("ministry_subject_code", "").zfill(4)
        unique.setdefault(code, {"code": code, "name": row["ministry_subject_name"], "college": row.get("college", "")})
    return sorted(unique.values(), key=lambda row: row["code"])


def report_record(docx: Path, qa: dict, code: str, name: str, run_dir: Path | None,
                  origin: str = "history", report_type: str = "full_subject_report") -> dict | None:
    if not docx.is_file() or qa.get("overall_status") not in {"pass", "pass_with_warnings"}:
        return None
    render = qa.get("render", qa)
    render_dir = Path(render.get("render_dir") or qa.get("render_dir") or docx.parent / "qa/rendered_pages")
    pages = sorted(render_dir.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    if not pages or render.get("blank_pages"):
        return None
    artifacts = run_dir / "artifacts" if run_dir else None
    overview = artifacts / "figure_01_tongji_subject_ranking_overview/chart_data.csv" if artifacts else None
    sources = []
    if overview and overview.is_file():
        with overview.open(encoding="utf-8-sig", newline="") as handle:
            sources = sorted({row["ranking_source"] for row in csv.DictReader(handle)})
    charts = []
    if artifacts and artifacts.is_dir():
        charts = sorted(artifacts.glob("*/chart.png"))
    esi_dir = docx.parent / "esi_source_bundle"
    if (esi_dir / "chart.png").is_file():
        charts.append(esi_dir / "chart.png")
    identifier = hashlib.sha256(str(docx.resolve()).encode("utf-8")).hexdigest()[:18]
    return {"id": identifier, "code": code, "name": name, "origin": origin, "report_type": report_type,
            "page_count": len(pages), "chart_count": len(charts), "sources": sources,
            "qa_status": qa["overall_status"], "has_esi": (esi_dir / "chart.png").is_file(),
            "docx": str(docx.resolve()), "pdf": str(next(render_dir.glob("*.pdf"), "")),
            "pages": [str(page.resolve()) for page in pages], "charts": [str(chart.resolve()) for chart in charts],
            "run_dir": str(run_dir) if run_dir else ""}


def catalog() -> list[dict]:
    selected = {}
    config = configuration()
    for manifest_name in config["catalog_manifests"]:
        manifest = read_json(PROJECT_DIR / manifest_name)
        for row in manifest.get("reports", []):
            docx = Path(row.get("docx_path") or row.get("docx", ""))
            if not docx.is_file():
                continue
            code = str(row.get("report_id") or row.get("code", ""))
            if code in config["excluded_report_ids"]:
                continue
            name = row.get("subject") or row.get("report_subject_name") or code
            qa = read_json(docx.parent / "qa/word_qa_report.json")
            if not qa:
                continue
            run = row.get("source_run_dir")
            if not run:
                summary = read_json(docx.parent / "subject_word_report_summary.json")
                run = summary.get("run_dir")
            record = report_record(docx, qa, code, name, Path(run) if run else None,
                                   report_type=row.get("report_type", "full_subject_report"))
            if record:
                if record["page_count"] <= 2 and not record["sources"]:
                    record["report_type"] = "esi_topic_report" if record["has_esi"] else "coverage_statement"
                selected[code] = record
    return list(selected.values())


def public_report(report: dict) -> dict:
    return {key: value for key, value in report.items() if key not in {"docx", "pdf", "pages", "charts", "run_dir"}}


def sample_reports(reports: list[dict], count: int, excluded: set[str] | None = None) -> tuple[list[dict], int]:
    config = configuration()
    unique = {}
    for report in reports:
        if (report["report_type"] == "full_subject_report"
                and len(report["sources"]) >= config["minimum_sample_source_count"] and report["page_count"] > 2):
            unique.setdefault(report["code"], report)
    candidates = list(unique.values())
    fresh = [report for report in candidates if report["id"] not in (excluded or set())]
    pool = fresh if len(fresh) >= min(count, len(candidates)) else candidates
    return random.SystemRandom().sample(pool, min(count, len(pool))), len(candidates)
