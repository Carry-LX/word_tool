from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile


PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "word_openability_audit" / "latest"
WORD_OPENABILITY_WORKER = PROJECT_DIR / "scripts" / "word_openability_worker.py"
WORD_COM_PYTHON = Path("E:/conda_envs/graph-rag/python.exe")
WORD_OPEN_TIMEOUT_SECONDS = 35


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def code_from_dir(path: Path) -> str:
    match = re.search(r"_(\d{4})_", path.name)
    return match.group(1) if match else ""


def latest_report_dirs() -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for path in REPORT_ROOT.glob("*"):
        if not path.is_dir():
            continue
        code = code_from_dir(path)
        if not code:
            continue
        if code not in latest or path.stat().st_mtime > latest[code].stat().st_mtime:
            latest[code] = path
    return latest


def latest_docx(report_dir: Path) -> Path | None:
    docs = sorted(
        [
            path
            for path in report_dir.glob("*.docx")
            if not path.name.startswith("~$")
            and not path.name.endswith(".tmp.docx")
            and not path.name.endswith(".pre_normalize.docx")
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return docs[0] if docs else None


def inspect_ooxml(docx_path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "docx": str(docx_path),
        "zip_ok": False,
        "external_relationship_count": 0,
        "target_mode_external_samples": [],
        "field_code_counts": {},
        "update_fields_present": False,
        "tracked_revisions_count": 0,
        "comment_reference_count": 0,
        "invalid_ignorable_count": 0,
        "invalid_ignorable_samples": [],
    }
    with ZipFile(docx_path) as package:
        row["zip_ok"] = True
        names = package.namelist()
        rel_names = [name for name in names if name.endswith(".rels")]
        external_samples = []
        for name in rel_names:
            text = package.read(name).decode("utf-8", errors="replace")
            for match in re.finditer(r'<Relationship\b[^>]*TargetMode="External"[^>]*/?>', text):
                external_samples.append({"part": name, "relationship": match.group(0)[:500]})
        row["external_relationship_count"] = len(external_samples)
        row["target_mode_external_samples"] = external_samples[:10]
        for name in names:
            if not name.endswith(".xml"):
                continue
            text = package.read(name).decode("utf-8", errors="replace")
            declared_prefixes = set(re.findall(r'\bxmlns:([A-Za-z_][\w.\-]*)="[^"]+"', text[:5000]))
            for attr_match in re.finditer(r'\b(?:[A-Za-z_][\w.\-]*:)?Ignorable="([^"]*)"', text):
                missing = [token for token in attr_match.group(1).split() if token not in declared_prefixes]
                if missing:
                    row["invalid_ignorable_count"] += len(missing)
                    if len(row["invalid_ignorable_samples"]) < 10:
                        row["invalid_ignorable_samples"].append({"part": name, "missing_prefixes": missing})
            if "w:updateFields" in text:
                row["update_fields_present"] = True
            row["tracked_revisions_count"] += sum(
                len(re.findall(pattern, text))
                for pattern in (r"<w:ins[\s>]", r"<w:del[\s>]", r"<w:moveFrom[\s>]", r"<w:moveTo[\s>]")
            )
            row["comment_reference_count"] += text.count("w:commentReference")
            if "w:fldChar" in text or "w:instrText" in text:
                for field in ("TOC", "HYPERLINK", "PAGEREF", "REF", "INCLUDEPICTURE", "LINK"):
                    row["field_code_counts"][field] = row["field_code_counts"].get(field, 0) + text.count(field)
    return row


def inspect_word_com(docx_paths: list[Path]) -> list[dict[str, Any]]:
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        return [{"word_com_status": "unavailable", "error": repr(exc)}]

    rows: list[dict[str, Any]] = []
    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            word.Options.UpdateLinksAtOpen = False
            word.Options.SaveNormalPrompt = False
            word.Options.ConfirmConversions = False
        except Exception:
            pass
        for path in docx_paths:
            started = time.time()
            row: dict[str, Any] = {"docx": str(path), "word_com_status": "unknown"}
            doc = None
            try:
                doc = word.Documents.Open(
                    FileName=str(path),
                    ConfirmConversions=False,
                    ReadOnly=True,
                    AddToRecentFiles=False,
                    PasswordDocument="",
                    PasswordTemplate="",
                    Revert=False,
                    WritePasswordDocument="",
                    WritePasswordTemplate="",
                    Format=0,
                    Encoding=65001,
                    Visible=False,
                    OpenAndRepair=False,
                    NoEncodingDialog=True,
                )
                row["word_com_status"] = "opened"
                row["elapsed_seconds"] = round(time.time() - started, 2)
                row["paragraph_count"] = int(doc.Paragraphs.Count)
                row["table_count"] = int(doc.Tables.Count)
                row["inline_shape_count"] = int(doc.InlineShapes.Count)
                row["saved"] = bool(doc.Saved)
            except Exception as exc:
                row["word_com_status"] = "error"
                row["error"] = repr(exc)
                row["elapsed_seconds"] = round(time.time() - started, 2)
            finally:
                if doc is not None:
                    try:
                        doc.Close(False)
                    except Exception:
                        pass
            rows.append(row)
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return rows


def worker_python() -> str:
    return str(WORD_COM_PYTHON if WORD_COM_PYTHON.exists() else Path(sys.executable))


def parse_worker_stdout(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    return {"word_com_status": "error", "error": "worker_stdout_missing_json", "stdout": stdout[-2000:]}


def inspect_word_com_isolated(docx_paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, path in enumerate(docx_paths, start=1):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["WORD_OPEN_DOCX_PATH"] = str(path.resolve())
        try:
            completed = subprocess.run(
                [worker_python(), str(WORD_OPENABILITY_WORKER)],
                cwd=str(PROJECT_DIR),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=WORD_OPEN_TIMEOUT_SECONDS,
                env=env,
            )
            row = parse_worker_stdout(completed.stdout)
            row["returncode"] = completed.returncode
            row["stderr"] = completed.stderr[-2000:]
        except subprocess.TimeoutExpired as exc:
            row = {
                "docx": str(path),
                "word_com_status": "timeout",
                "timeout_seconds": WORD_OPEN_TIMEOUT_SECONDS,
                "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            }
        row["audit_index"] = index
        rows.append(row)
    return rows


def main() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_dirs = latest_report_dirs()
    docx_paths = [doc for _, report_dir in sorted(report_dirs.items()) if (doc := latest_docx(report_dir))]
    ooxml_rows = []
    for path in docx_paths:
        try:
            ooxml_rows.append(inspect_ooxml(path))
        except Exception as exc:
            ooxml_rows.append({"docx": str(path), "zip_ok": False, "error": repr(exc)})
    word_rows = inspect_word_com_isolated(docx_paths)
    payload = {
        "generated_at": now_text(),
        "docx_count": len(docx_paths),
        "ooxml_issue_count": sum(
            1
            for row in ooxml_rows
            if row.get("external_relationship_count")
            or row.get("update_fields_present")
            or row.get("tracked_revisions_count")
            or row.get("comment_reference_count")
            or row.get("invalid_ignorable_count")
            or not row.get("zip_ok")
        ),
        "word_com_error_count": sum(1 for row in word_rows if row.get("word_com_status") in {"error", "timeout", "unavailable"}),
        "ooxml_rows": ooxml_rows,
        "word_com_rows": word_rows,
    }
    write_json(OUTPUT_DIR / "word_openability_audit.json", payload)
    summary_lines = [
        "# Word Openability Audit",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- docx_count: {payload['docx_count']}",
        f"- ooxml_issue_count: {payload['ooxml_issue_count']}",
        f"- word_com_error_count: {payload['word_com_error_count']}",
    ]
    (OUTPUT_DIR / "word_openability_audit.md").write_text("\n".join(summary_lines), encoding="utf-8", newline="\n")
    print(json.dumps({k: payload[k] for k in ["docx_count", "ooxml_issue_count", "word_com_error_count"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
