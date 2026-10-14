"""Extract the ESI reference without changing its source file.

Run directly. All input and output variables come from the UTF-8 source config.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import shutil
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs/esi_trend/source_config.json"
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def inspect_reference() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source = Path(config["source_docx"])
    local_source = PROJECT_DIR / config["local_source_docx"]
    if not source.is_file() and local_source.is_file():
        source = local_source
    assert source.is_file() and "?" not in str(source)
    if not local_source.exists():
        local_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_source)
    out = PROJECT_DIR / config["source_snapshot_dir"]
    media_dir = out / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out / "source.docx"
    if not snapshot.exists():
        shutil.copy2(source, snapshot)
    elif hashlib.sha256(snapshot.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
        raise ValueError("Existing source snapshot differs; use a new output directory for the new source.")
    blocks = []
    media = []
    with zipfile.ZipFile(source) as archive:
        relationships = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
        targets = {row.get("Id"): posixpath.normpath("word/" + row.get("Target", "")) for row in relationships}
        root = etree.fromstring(archive.read("word/document.xml"))
        body = root.find("w:body", NS)
        for index, element in enumerate(body):
            tag = etree.QName(element).localname
            text = "".join(element.xpath(".//w:t/text()", namespaces=NS))
            yellow = []
            for run in element.xpath(".//w:r", namespaces=NS):
                colors = run.xpath("./w:rPr/w:highlight/@w:val | ./w:rPr/w:shd/@w:fill", namespaces=NS)
                if any(color.lower() in {"yellow", "ffff00"} for color in colors):
                    yellow.append("".join(run.xpath(".//w:t/text()", namespaces=NS)))
            ids = element.xpath(".//a:blip/@r:embed | .//v:imagedata/@r:id", namespaces=NS)
            row = {"block_index": index, "type": tag, "text": text,
                   "yellow_text": "".join(yellow), "media_targets": [targets.get(rid, rid) for rid in ids]}
            if tag == "tbl":
                row["table_rows"] = [["".join(cell.xpath(".//w:t/text()", namespaces=NS))
                                      for cell in tr.findall("w:tc", NS)] for tr in element.findall("w:tr", NS)]
            blocks.append(row)
        for name in archive.namelist():
            if not name.startswith("word/media/"):
                continue
            target = media_dir / Path(name).name
            target.write_bytes(archive.read(name))
            item = {"archive_path": name, "extracted_path": str(target), "bytes": target.stat().st_size}
            try:
                with Image.open(target) as img:
                    item.update({"width_px": img.width, "height_px": img.height, "format": img.format})
            except (OSError, ValueError):
                item["format"] = "vector_or_unsupported"
            media.append(item)
        counts = {"native_chart_count": sum(name.startswith("word/charts/") and name.endswith(".xml") for name in archive.namelist()),
                  "embedded_workbook_count": sum(name.startswith("word/embeddings/") for name in archive.namelist())}
    payload = {"source_file": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "snapshot_path": str(snapshot), "block_count": len(blocks),
               "table_count": sum(row["type"] == "tbl" for row in blocks),
               "media_count": len(media), **counts, "media": media, "blocks": blocks}
    write_json(out / "reference_inventory.json", payload)
    lines = []
    for row in blocks:
        lines.append(f"[{row['block_index']:03d}] {row['type']} {row['text']}")
        if row["yellow_text"]:
            lines.append("YELLOW: " + row["yellow_text"])
        if row["media_targets"]:
            lines.append("MEDIA: " + ", ".join(row["media_targets"]))
        if row.get("table_rows"):
            lines.extend(" | ".join(cells) for cells in row["table_rows"])
    (out / "reference_blocks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {key: value for key, value in payload.items() if key not in {"blocks", "media"}}


if __name__ == "__main__":
    print(json.dumps(inspect_reference(), ensure_ascii=True, indent=2))
