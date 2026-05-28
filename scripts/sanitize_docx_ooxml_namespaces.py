from __future__ import annotations

import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = PROJECT_DIR / "outputs" / "full_word_reports"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "word_openability_audit" / "namespace_sanitize"

# Explicit variables. Keep DOCX_PATH empty to sanitize latest reports.
DOCX_PATH = ""
ONLY_CODES: list[str] = []
APPLY_TO_LATEST_REPORTS = True

NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
}
IGNORABLE_PREFIX_ORDER = ["w14", "w15", "w16se", "w16cid", "w16", "w16cex", "w16sdtdh", "wp14", "a14"]
MC_IGNORABLE = f"{{{NAMESPACES['mc']}}}Ignorable"

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def namespace_uri(name: str) -> str:
    if name.startswith("{") and "}" in name:
        return name[1 : name.index("}")]
    return ""


def collect_used_namespace_uris(root: ET.Element) -> set[str]:
    used: set[str] = set()
    for element in root.iter():
        uri = namespace_uri(element.tag)
        if uri:
            used.add(uri)
        for attr_name in element.attrib:
            uri = namespace_uri(attr_name)
            if uri:
                used.add(uri)
    return used


def sanitize_xml_bytes(xml_bytes: bytes) -> tuple[bytes, bool, dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    if MC_IGNORABLE not in root.attrib:
        return xml_bytes, False, {"reason": "no_mc_ignorable"}
    old_value = root.attrib.get(MC_IGNORABLE, "")
    used_uris = collect_used_namespace_uris(root)
    new_tokens = [prefix for prefix in IGNORABLE_PREFIX_ORDER if NAMESPACES[prefix] in used_uris]
    if new_tokens:
        root.set(MC_IGNORABLE, " ".join(new_tokens))
    else:
        del root.attrib[MC_IGNORABLE]
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True, {"old_ignorable": old_value, "new_ignorable": " ".join(new_tokens)}


def sanitize_docx(docx_path: Path) -> dict[str, Any]:
    docx_path = docx_path.resolve()
    row: dict[str, Any] = {
        "docx": str(docx_path),
        "status": "pending",
        "changed_members": [],
        "original_size": docx_path.stat().st_size if docx_path.exists() else 0,
    }
    if not docx_path.exists():
        row["status"] = "missing_docx"
        return row

    with tempfile.TemporaryDirectory(prefix="docx_ns_sanitize_") as temp_name:
        temp_path = Path(temp_name) / "sanitized.docx"
        try:
            with ZipFile(docx_path, "r") as zin, ZipFile(temp_path, "w", ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.endswith(".xml"):
                        try:
                            new_data, changed, detail = sanitize_xml_bytes(data)
                        except ET.ParseError as exc:
                            row["status"] = "xml_parse_failed"
                            row["member"] = item.filename
                            row["error"] = repr(exc)
                            return row
                        if changed:
                            data = new_data
                            detail["member"] = item.filename
                            row["changed_members"].append(detail)
                    zout.writestr(item, data)
            if row["changed_members"]:
                shutil.copy2(temp_path, docx_path)
                row["status"] = "ok"
            else:
                row["status"] = "unchanged"
            row["final_size"] = docx_path.stat().st_size
        except PermissionError as exc:
            row["status"] = "locked"
            row["error"] = repr(exc)
    return row


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
    docs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return docs[0] if docs else None


def target_docx_paths() -> list[Path]:
    if str(DOCX_PATH).strip():
        path = Path(DOCX_PATH)
        return [(PROJECT_DIR / path if not path.is_absolute() else path).resolve()]
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
    rows = [sanitize_docx(path) for path in target_docx_paths()]
    payload = {
        "generated_at": now_text(),
        "target_count": len(rows),
        "changed_count": sum(1 for row in rows if row.get("status") == "ok"),
        "failed_count": sum(1 for row in rows if row.get("status") not in {"ok", "unchanged"}),
        "rows": rows,
    }
    write_json(OUTPUT_DIR / "namespace_sanitize_summary.json", payload)
    print(json.dumps({key: payload[key] for key in ["target_count", "changed_count", "failed_count"]}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
