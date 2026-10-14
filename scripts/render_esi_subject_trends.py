"""Render the ESI sample with the standard Documents renderer and Windows wrapper."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageOps

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs/esi_trend/source_config.json"
TARGET_SIZE = (620, 880)


def render_and_audit() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    output = PROJECT_DIR / config["output_dir"]
    summary_path = output / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    render_dir = output / "qa/rendered"
    render_dir.mkdir(parents=True, exist_ok=True)
    for old_page in render_dir.glob("page-*.png"):
        old_page.unlink()
    environment = dict(os.environ)
    paths = [entry for entry in environment.get("PATH", "").split(os.pathsep)
             if entry and Path(entry).as_posix().lower() != "e:/tools/libreoffice/program"]
    environment["PATH"] = config["soffice_wrapper_dir"] + os.pathsep + os.pathsep.join(paths)
    rendered = subprocess.run([sys.executable, config["render_script"], summary["docx_path"],
                               "--output_dir", str(render_dir), "--emit_pdf"],
                              env=environment, capture_output=True, timeout=240)
    log = rendered.stdout.decode("utf-8", errors="replace") + rendered.stderr.decode("utf-8", errors="replace")
    (output / "qa/render_log.txt").write_text(log, encoding="utf-8", newline="\n")
    if rendered.returncode:
        raise RuntimeError(f"Standard render failed; inspect {output / 'qa/render_log.txt'}")
    pdf_path = render_dir / (Path(summary["docx_path"]).stem + ".pdf")
    pages = []
    document = fitz.open(pdf_path)
    for index, page in enumerate(document):
        text = page.get_text()
        captions = [line for line in text.splitlines() if line.strip().startswith("图")]
        image_count = len(page.get_image_info())
        paragraphs = []
        text_lines = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            text_lines.extend({"text": "".join(span["text"] for span in line["spans"]), "bbox": line["bbox"]}
                              for line in block["lines"])
        text_lines.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        image_tops = sorted(image["bbox"][1] for image in page.get_image_info())
        for line in text_lines:
            if not line["text"].strip().startswith("（"):
                continue
            start = line["bbox"][1]
            stop = next((top for top in image_tops if top > start), page.rect.height)
            paragraph_lines = [item for item in text_lines if start <= item["bbox"][1] < stop]
            paragraphs.append({"first_line": line["text"], "line_count": len(paragraph_lines)})
        pages.append({"page_number": index + 1, "image_count": image_count, "captions": captions,
                      "narrative_paragraphs": paragraphs,
                      "blank": image_count == 0 and len(text.strip()) < 50})
    document.close()
    issues = []
    if len(pages) != 4:
        issues.append(f"Expected 4 pages, got {len(pages)}")
    for page in pages:
        if page["image_count"] != 2 or len(page["captions"]) != 2:
            issues.append(f"Page {page['page_number']} does not contain two complete figure blocks")
        if page["blank"]:
            issues.append(f"Blank page: {page['page_number']}")
        for paragraph in page["narrative_paragraphs"]:
            if paragraph["line_count"] not in {2, 3}:
                issues.append(f"Narrative on page {page['page_number']} is not 2-3 lines")
    files = sorted(render_dir.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    sheet = Image.new("RGB", (TARGET_SIZE[0] * 2, TARGET_SIZE[1] * ((len(files) + 1) // 2)), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(files):
        with Image.open(path) as image:
            thumb = ImageOps.contain(image.convert("RGB"), (TARGET_SIZE[0] - 20, TARGET_SIZE[1] - 30))
        origin = ((index % 2) * TARGET_SIZE[0], (index // 2) * TARGET_SIZE[1])
        sheet.paste(thumb, (origin[0] + 10, origin[1] + 22))
        draw.text((origin[0] + 10, origin[1] + 5), f"Page {index + 1}", fill="black")
    sheet.save(output / "qa/contact_sheet.jpg", quality=94)
    result = {"status": "pass" if not issues else "fail", "page_count": len(pages),
              "issues": issues, "pages": pages, "pdf_path": str(pdf_path), "visual_review": "pending"}
    (output / "qa/render_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8", newline="\n")
    summary["render_visual_qa"] = result
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    print(json.dumps(render_and_audit(), ensure_ascii=True, indent=2))
