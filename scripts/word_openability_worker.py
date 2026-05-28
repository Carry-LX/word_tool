from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def inspect_one(docx_path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"docx": str(docx_path), "word_com_status": "unknown"}
    started = time.time()
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        row["word_com_status"] = "unavailable"
        row["error"] = repr(exc)
        return row

    pythoncom.CoInitialize()
    word = None
    doc = None
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
        doc = word.Documents.Open(
            FileName=str(docx_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Revert=False,
            Visible=False,
            OpenAndRepair=False,
            NoEncodingDialog=True,
        )
        row["word_com_status"] = "opened"
        row["paragraph_count"] = int(doc.Paragraphs.Count)
        row["table_count"] = int(doc.Tables.Count)
        row["inline_shape_count"] = int(doc.InlineShapes.Count)
        row["saved"] = bool(doc.Saved)
    except Exception as exc:
        row["word_com_status"] = "error"
        row["error"] = repr(exc)
    finally:
        row["elapsed_seconds"] = round(time.time() - started, 2)
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return row


def main() -> None:
    docx_value = os.environ.get("WORD_OPEN_DOCX_PATH", "").strip()
    if not docx_value:
        print(json.dumps({"word_com_status": "error", "error": "WORD_OPEN_DOCX_PATH is empty"}))
        sys.exit(2)
    payload = inspect_one(Path(docx_value).resolve())
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0 if payload.get("word_com_status") == "opened" else 1)


if __name__ == "__main__":
    main()
