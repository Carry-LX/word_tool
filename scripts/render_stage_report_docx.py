from __future__ import annotations

import os
import runpy
import sys
import tempfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "outputs" / "stage_report"
RENDER_DIR = OUTPUT_DIR / "rendered_pages"
TEMP_DIR = PROJECT_DIR / "outputs" / "tmp_render"


def main() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(TEMP_DIR)
    os.environ["TMP"] = str(TEMP_DIR)
    os.environ["TMPDIR"] = str(TEMP_DIR)
    tempfile.tempdir = str(TEMP_DIR)

    docx_files = sorted(OUTPUT_DIR.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not docx_files:
        raise FileNotFoundError(f"No docx found under {OUTPUT_DIR}")

    candidates = []
    users_root = Path("C:/Users")
    if users_root.exists():
        candidates.extend(
            users_root.glob("*/.codex/plugins/cache/openai-primary-runtime/documents/*/skills/documents/render_docx.py")
        )
        candidates.extend(
            users_root.glob("*/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/documents/skills/documents/render_docx.py")
        )
    render_script = next((path for path in candidates if path.exists()), None)
    if render_script is None:
        raise FileNotFoundError("render_docx.py")

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    sys.argv = [
        str(render_script),
        str(docx_files[0]),
        "--output_dir",
        str(RENDER_DIR),
        "--emit_pdf",
    ]
    runpy.run_path(str(render_script), run_name="__main__")


if __name__ == "__main__":
    main()
