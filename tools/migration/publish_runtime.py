"""Plan or publish runtime snapshots without making an uncompressed copy."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from common import ROOT, PROFILE, gh, save_json, upload_verified

# Explicit settings. Keep False until the local code commit has been reviewed.
PUBLISH = False
STAGING = ROOT / PROFILE["staging_directory"] / PROFILE["release_tag"]
EVIDENCE = ROOT / "outputs/github_migration"
TOOL_RENDER_SOURCE = Path.home() / ".codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/render_docx.py"


def tree_files(directory: Path):
    for base, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if not name.startswith("~$") and not name.endswith((".tmp", ".log", ".pyc")):
                path = Path(base) / name
                if path.is_symlink():
                    raise ValueError(f"Symlink not allowed in snapshot: {path}")
                yield path


def report_inputs() -> list[Path]:
    """Follow report manifests to their QA, DOCX and source artifact bundles."""
    profile = json.loads((ROOT / "configs/runtime/web_demo_profile.json").read_text(encoding="utf-8"))
    directories = {ROOT / "outputs/esi_subject_trends", (ROOT / profile["coverage_csv"]).parent}
    for name in profile["catalog_manifests"]:
        manifest_path = ROOT / name
        directories.add(manifest_path.parent)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        for report in manifest.get("reports", []):
            docx = Path(report.get("docx_path") or report.get("docx", ""))
            if not docx.is_file():
                raise FileNotFoundError(f"Report referenced by catalog is missing: {docx}")
            directories.add(docx.parent)
            summary_path = docx.parent / "subject_word_report_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8-sig")) if summary_path.is_file() else {}
            run = report.get("source_run_dir") or summary.get("run_dir")
            if run:
                run_path = Path(run)
                if not run_path.is_dir():
                    raise FileNotFoundError(f"Source run missing: {run_path}")
                directories.add(run_path)
    files = set()
    for directory in directories:
        for file in tree_files(directory):
            if not file.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError(f"Runtime source escapes project: {file}")
            files.add(file)
    return sorted(files)


def plan() -> dict[str, list[tuple[Path, str]]]:
    groups = {}
    for name in ["processed", "external_data"]:
        groups[name] = [(p, p.relative_to(ROOT).as_posix()) for p in tree_files(ROOT / name)]
    groups["demo_reports"] = [(p, p.relative_to(ROOT).as_posix()) for p in report_inputs()]
    if PROFILE["include_windows_tools"]:
        lo = Path(PROFILE["libreoffice_source"])
        if not (lo / "program/soffice.exe").is_file():
            raise FileNotFoundError(lo)
        tools = [(p, ".local/tools/LibreOffice/" + p.relative_to(lo).as_posix()) for p in tree_files(lo)]
        poppler_exe = shutil.which("pdftoppm")
        if not poppler_exe:
            raise FileNotFoundError("pdftoppm")
        poppler = Path(poppler_exe).parent
        tools.extend((p, ".local/tools/poppler/bin/" + p.relative_to(poppler).as_posix()) for p in tree_files(poppler))
        # Render helper and wrapper are small source-controlled files; only the executable is an asset.
        tools.append((STAGING / "generated/soffice.exe", ".local/bin/soffice.exe"))
        groups["windows_tools"] = tools
    return groups


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size=-1):
        block = self.stream.read(size)
        self.digest.update(block)
        return block


class UploadParts(io.RawIOBase):
    def __init__(self, group: str):
        self.group, self.index, self.size = group, 0, 0
        self.handle = None
        self.parts = []

    def writable(self):
        return True

    def write(self, block):
        original_size = len(block)
        view = memoryview(block)
        while view:
            if self.handle is None:
                self.index += 1
                self.path = STAGING / f"{self.group}.tar.gz.part{self.index:03d}"
                self.handle = self.path.open("xb")
                self.size = 0
            amount = min(len(view), PROFILE["part_bytes"] - self.size)
            self.handle.write(view[:amount])
            self.size += amount
            view = view[amount:]
            if self.size == PROFILE["part_bytes"]:
                self.finish_part()
        return original_size

    def finish_part(self):
        if self.handle:
            self.handle.close()
            self.handle = None
            self.parts.append(upload_verified(self.path))
            save_json(EVIDENCE / f"uploaded_{self.group}.json", self.parts)


def compile_wrapper() -> None:
    output = STAGING / "generated/soffice.exe"
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    subprocess.run([str(compiler), "/nologo", "/target:exe", f"/out:{output}",
                    str(ROOT / "tools/migration/soffice_wrapper.cs")], check=True)


def publish(groups: dict) -> None:
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT):
        raise RuntimeError("Review and commit code first; working tree is not clean.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    STAGING.mkdir(parents=True, exist_ok=True)
    if list(STAGING.glob("*.part*")):
        raise RuntimeError("A previous local part exists; inspect before retrying.")
    notes = ROOT / "docs/MIGRATION_RELEASE.md"
    gh("release", "create", PROFILE["release_tag"], "--repo", PROFILE["repository"], "--target", commit,
       "--draft", "--title", "Windows runtime data 2026-10-21", "--notes-file", str(notes))
    manifest = {"version": 1, "repository": PROFILE["repository"], "tag": PROFILE["release_tag"],
                "code_commit": commit, "source_project_root": str(ROOT), "groups": []}
    for group, entries in groups.items():
        print(f"Packing {group}: {len(entries)} files", flush=True)
        sink = UploadParts(group)
        files = []
        try:
            with gzip.GzipFile(filename="", mode="wb", fileobj=sink, compresslevel=PROFILE["compression_level"], mtime=0) as compressed:
                with tarfile.open(mode="w|", fileobj=compressed, format=tarfile.PAX_FORMAT) as archive:
                    for index, (path, name) in enumerate(entries):
                        before = path.stat()
                        info = archive.gettarinfo(str(path), arcname=name)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with path.open("rb") as source:
                            reader = HashingReader(source)
                            archive.addfile(info, reader)
                        after = path.stat()
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise RuntimeError(f"Input changed while packing: {path}")
                        files.append({"path": name, "size": before.st_size, "sha256": reader.digest.hexdigest()})
                        if index % 1000 == 0:
                            print(f"  {group}: {index + 1}/{len(entries)}", flush=True)
            sink.finish_part()
        except BaseException:
            if sink.handle:
                sink.handle.close()
            raise
        manifest["groups"].append({"name": group, "parts": sink.parts, "files": files})
        save_json(EVIDENCE / "runtime-manifest.json", manifest)
    temporary_manifest = STAGING / PROFILE["manifest_asset"]
    save_json(temporary_manifest, manifest)
    receipt = upload_verified(temporary_manifest)
    save_json(EVIDENCE / "manifest_receipt.json", receipt)
    print("All parts verified; release remains a draft until validation completes.", flush=True)


def main():
    compile_wrapper()
    groups = plan()
    listing = {group: {"files": len(entries), "bytes": sum(p.stat().st_size for p, _ in entries),
                       "entries": [name for _, name in entries]} for group, entries in groups.items()}
    save_json(EVIDENCE / "package_plan.json", listing)
    print(json.dumps({name: {k: v for k, v in row.items() if k != "entries"} for name, row in listing.items()}, indent=2), flush=True)
    if PUBLISH:
        publish(groups)


if __name__ == "__main__":
    main()
