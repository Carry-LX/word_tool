from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "word_openability_audit" / "normalization"
SOFFICE_EXE = PROJECT_DIR / ".local/bin/soffice.exe"
if not SOFFICE_EXE.is_file():
    SOFFICE_EXE = Path("E:/tools/codex-bin/soffice.exe")
WORD_OPENABILITY_WORKER = PROJECT_DIR / "scripts" / "word_openability_worker.py"
WORD_COM_PYTHON = Path(sys.executable)
WORD_OPEN_TIMEOUT_SECONDS = 60

# Explicit variables. Keep DOCX_PATH empty to normalize latest reports.
DOCX_PATH = ""
ONLY_CODES: list[str] = []
APPLY_TO_LATEST_REPORTS = True
REQUIRE_WORD_OPEN_VALIDATION = True


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
    wanted = {code.zfill(4) for code in ONLY_CODES}
    for path in REPORT_ROOT.glob("*"):
        if not path.is_dir():
            continue
        code = code_from_dir(path)
        if not code:
            continue
        if wanted and code not in wanted:
            continue
        if code not in latest or path.stat().st_mtime > latest[code].stat().st_mtime:
            latest[code] = path
    return latest


def latest_docx(report_dir: Path) -> Path | None:
    docs = [
        path
        for path in report_dir.glob("*.docx")
        if not path.name.startswith("~$")
        and not path.name.endswith(".tmp.docx")
        and not path.name.endswith(".pre_normalize.docx")
    ]
    docs = sorted(docs, key=lambda path: path.stat().st_mtime, reverse=True)
    return docs[0] if docs else None


def render_environment() -> dict[str, str]:
    env = os.environ.copy()
    path_key = next((key for key in env if key.lower() == "path"), "Path")
    parts = [
        item
        for item in env.get(path_key, "").split(";")
        if item and item.rstrip("\\").lower() != r"e:\tools\libreoffice\program"
    ]
    env[path_key] = str(SOFFICE_EXE.parent) + os.pathsep + os.pathsep.join(parts)
    env["Path"] = env[path_key]
    env["PATH"] = env[path_key]
    return env


def worker_python() -> str:
    return str(WORD_COM_PYTHON if WORD_COM_PYTHON.exists() else Path(sys.executable))


def parse_worker_stdout(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return {"word_com_status": "error", "error": "worker_stdout_invalid_json", "stdout": stdout[-2000:]}
    return {"word_com_status": "error", "error": "worker_stdout_missing_json", "stdout": stdout[-2000:]}


def verify_word_openability(docx_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["WORD_OPEN_DOCX_PATH"] = str(docx_path.resolve())
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
        return row
    except subprocess.TimeoutExpired as exc:
        return {
            "docx": str(docx_path),
            "word_com_status": "timeout",
            "timeout_seconds": WORD_OPEN_TIMEOUT_SECONDS,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }


def is_openability_verified(row: dict[str, Any]) -> bool:
    return row.get("word_com_status") == "opened"


def normalize_docx(docx_path: Path) -> dict[str, Any]:
    docx_path = docx_path.resolve()
    row: dict[str, Any] = {
        "docx": str(docx_path),
        "status": "pending",
        "original_size": docx_path.stat().st_size if docx_path.exists() else 0,
    }
    if not docx_path.exists():
        row["status"] = "missing_docx"
        return row
    soffice = SOFFICE_EXE if SOFFICE_EXE.exists() else Path("soffice")
    with tempfile.TemporaryDirectory(prefix="word_open_norm_") as temp_name:
        temp_root = Path(temp_name)
        source_dir = temp_root / "source"
        output_dir = temp_root / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        source_docx = source_dir / "input.docx"
        shutil.copy2(docx_path, source_docx)
        command = [
            str(soffice),
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(output_dir),
            str(source_docx),
        ]
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=300,
            env=render_environment(),
        )
        converted = output_dir / "input.docx"
        row.update(
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
                "converted_exists": converted.exists(),
                "converted_size": converted.stat().st_size if converted.exists() else 0,
            }
        )
        if completed.returncode != 0 or not converted.exists() or converted.stat().st_size == 0:
            row["status"] = "failed"
            return row
        openability = verify_word_openability(converted)
        row["converted_word_openability"] = openability
        if REQUIRE_WORD_OPEN_VALIDATION and not is_openability_verified(openability):
            row["status"] = "failed_word_openability"
            return row
        backup_path = docx_path.with_suffix(".pre_normalize.docx")
        try:
            if backup_path.exists():
                backup_path.unlink()
            shutil.copy2(docx_path, backup_path)
            shutil.copy2(converted, docx_path)
            backup_path.unlink(missing_ok=True)
            row["status"] = "ok"
            row["final_size"] = docx_path.stat().st_size
        except PermissionError as exc:
            row["status"] = "locked"
            row["error"] = repr(exc)
            if backup_path.exists():
                try:
                    backup_path.unlink()
                except PermissionError:
                    pass
            return row
    return row


def target_docx_paths() -> list[Path]:
    if str(DOCX_PATH).strip():
        path = Path(DOCX_PATH)
        return [PROJECT_DIR / path if not path.is_absolute() else path]
    if not APPLY_TO_LATEST_REPORTS:
        return []
    paths = []
    for _, report_dir in sorted(latest_report_dirs().items()):
        docx = latest_docx(report_dir)
        if docx is not None:
            paths.append(docx)
    return paths


def main() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = target_docx_paths()
    rows = [normalize_docx(path) for path in paths]
    payload = {
        "generated_at": now_text(),
        "target_count": len(paths),
        "ok_count": sum(1 for row in rows if row["status"] == "ok"),
        "failed_count": sum(1 for row in rows if row["status"] != "ok"),
        "rows": rows,
    }
    write_json(OUTPUT_DIR / "docx_normalization_summary.json", payload)
    print(json.dumps({key: payload[key] for key in ["target_count", "ok_count", "failed_count"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    env_docx = os.environ.get("NORMALIZE_DOCX_PATH", "").strip()
    if env_docx:
        result = normalize_docx(Path(env_docx))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("status") == "ok" else 1)
    main()
