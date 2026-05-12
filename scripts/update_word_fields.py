from __future__ import annotations

from pathlib import Path
from typing import Any


def update_word_fields(docx_path: Path) -> dict[str, Any]:
    """Update Word fields and TOC entries in-place when Microsoft Word is available."""
    result: dict[str, Any] = {
        "status": "skipped",
        "docx_path": str(docx_path),
        "reason": "",
        "fields_updated": 0,
        "tables_of_contents_updated": 0,
    }
    if not docx_path.exists():
        result["reason"] = "docx_not_found"
        return result

    try:
        import pythoncom
        import win32com.client
    except Exception as exc:  # pragma: no cover - depends on local Windows/Office setup.
        result["reason"] = f"pywin32_unavailable: {exc}"
        return result

    pythoncom.CoInitialize()
    word = None
    document = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(docx_path.resolve()), ReadOnly=False, AddToRecentFiles=False)

        fields_updated = int(document.Fields.Update())
        toc_updated = 0
        for toc in document.TablesOfContents:
            toc.Update()
            toc_updated += 1

        for section in document.Sections:
            for header in section.Headers:
                fields_updated += int(header.Range.Fields.Update())
            for footer in section.Footers:
                fields_updated += int(footer.Range.Fields.Update())

        document.Save()
        result.update(
            {
                "status": "ok",
                "reason": "",
                "fields_updated": fields_updated,
                "tables_of_contents_updated": toc_updated,
            }
        )
    except Exception as exc:  # pragma: no cover - depends on local Windows/Office setup.
        result["status"] = "failed"
        result["reason"] = str(exc)
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return result


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/update_word_fields.py <docx_path>")
    payload = update_word_fields(Path(sys.argv[1]))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
