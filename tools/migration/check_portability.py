"""Read-only runtime preflight; no model calls or report generation."""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
from pathlib import Path

from common import ROOT, save_json

CHECK_WORD = True


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    failures = []
    for name in ["pandas", "numpy", "openpyxl", "docx", "PIL", "flask", "fitz", "pdf2image", "matplotlib", "pythoncom", "win32com.client"]:
        try:
            importlib.import_module(name)
        except ImportError as error:
            failures.append(f"{name}: {error}")
    import agent_runtime
    import demo_catalog
    import audit_word_report
    profile = agent_runtime.load_runtime_profile()
    subjects = demo_catalog.subjects()
    reports = demo_catalog.catalog()
    for name in ["processed/ranking.sqlite", "processed/fact_ranking_indicator.csv", "processed/fact_ranking_indicator_subject_bridge.csv",
                 "external_data/processed/cwts_subject_field_crosswalk.csv", "configs/esi_trend/verified_chart_data.json"]:
        if not (ROOT / name).is_file():
            failures.append(f"Missing runtime file: {name}")
    database = ROOT / "processed/ranking.sqlite"
    table_count = 0
    if database.is_file():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            table_count = connection.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
            tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
            required = {"dim_subject", "dim_subject_alias", "fact_ranking", "fact_ranking_indicator",
                        "fact_ranking_subject_bridge", "fact_ranking_indicator_subject_bridge"}
            if missing := required - tables:
                failures.append(f"SQLite is missing required tables: {sorted(missing)}")
    if not subjects or not reports:
        failures.append("Subject list or history report catalog is empty.")
    if not Path(profile["recommended_python"]).is_file():
        failures.append("Worker Python executable is missing.")
    if not audit_word_report.DOCUMENTS_RENDER_SCRIPT.is_file():
        failures.append("DOCX render helper is missing.")
    environment = audit_word_report.render_environment()
    import shutil
    for executable in ["soffice.exe", "pdfinfo.exe", "pdftoppm.exe"]:
        if not shutil.which(executable, path=environment["PATH"]):
            failures.append(f"Renderer executable missing: {executable}")
    if CHECK_WORD and os.name == "nt":
        try:
            # Check registration without opening Word or blocking on Office first-run dialogs.
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID") as key:
                winreg.QueryValue(key, None)
        except Exception as error:
            failures.append(f"Microsoft Word COM registration: {error}")
    result = {"status": "fail" if failures else "pass", "python": sys.executable,
              "subjects": len(subjects), "catalog_reports": len(reports), "sqlite_tables": table_count,
              "word_check": "COM registration and Python imports; document automation is checked on generation",
              "failures": failures}
    save_json(ROOT / "outputs/github_migration/portability_check.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
