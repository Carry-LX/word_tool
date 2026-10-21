"""Restore private release assets; keep at most one compressed part on disk."""
from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

from common import ROOT, PROFILE, digest_file, download_asset, release_metadata, safe_target, save_json

# Change these explicit variables when intentionally restoring a different snapshot.
RESTORE_WINDOWS_TOOLS = True
OVERWRITE_DIFFERENT_RUNTIME_FILES = False
DOWNLOADS = ROOT / PROFILE["download_directory"]


class DownloadedParts(io.RawIOBase):
    def __init__(self, parts: list[dict], assets: dict[str, dict]):
        self.parts, self.assets = iter(parts), assets
        self.handle = None
        self.path = None

    def readable(self):
        return True

    def clear_current(self):
        if self.handle:
            self.handle.close()
            self.handle = None
        if self.path:
            self.path.unlink(missing_ok=True)
            self.path = None

    def read(self, size=-1):
        if size < 0:
            raise ValueError("Use bounded reads for runtime parts.")
        if size == 0:
            return b""
        while True:
            if self.handle:
                block = self.handle.read(size)
                if block:
                    return block
                self.clear_current()
            part = next(self.parts, None)
            if part is None:
                return b""
            name = part["name"]
            if Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError(f"Invalid asset name: {name}")
            asset = self.assets[name]
            if asset["size"] != part["size"]:
                raise ValueError(f"Asset size mismatch: {name}")
            self.path = DOWNLOADS / name
            if not self.path.is_file() or digest_file(self.path) != part["sha256"]:
                self.path.unlink(missing_ok=True)
                print(f"Downloading {name} ({part['size']:,} bytes)", flush=True)
                if download_asset(asset, self.path) != part["sha256"]:
                    self.path.unlink(missing_ok=True)
                    raise ValueError(f"Downloaded asset checksum mismatch: {name}")
            self.handle = self.path.open("rb")

    def close(self):
        self.clear_current()
        super().close()


def validate_manifest(manifest: dict) -> None:
    if manifest.get("version") != 1 or manifest.get("repository") != PROFILE["repository"] or manifest.get("tag") != PROFILE["release_tag"]:
        raise ValueError("Unexpected runtime manifest identity.")
    prefixes = {"processed": "processed/", "external_data": "external_data/",
                "demo_reports": "outputs/", "windows_tools": ".local/"}
    all_paths = set()
    all_assets = set()
    for group in manifest["groups"]:
        prefix = prefixes[group["name"]]
        for entry in group["files"]:
            if not entry["path"].startswith(prefix) or entry["path"] in all_paths:
                raise ValueError(f"Unexpected/duplicate runtime path: {entry['path']}")
            safe_target(entry["path"])
            all_paths.add(entry["path"])
        for part in group["parts"]:
            if part["name"] in all_assets:
                raise ValueError("Duplicate part name.")
            all_assets.add(part["name"])


def restore_group(group: dict, assets: dict[str, dict]) -> None:
    expected = {row["path"]: row for row in group["files"]}
    if all((p := safe_target(row["path"])).is_file() and p.stat().st_size == row["size"]
           and digest_file(p) == row["sha256"] for row in expected.values()):
        print(f"Already restored and verified: {group['name']}", flush=True)
        return
    observed = set()
    with DownloadedParts(group["parts"], assets) as parts:
        with tarfile.open(fileobj=parts, mode="r|gz") as archive:
            for index, member in enumerate(archive):
                entry = expected.get(member.name)
                if not member.isfile() or entry is None or member.size != entry["size"] or member.name in observed:
                    raise ValueError(f"Unexpected tar member: {member.name}")
                observed.add(member.name)
                target = safe_target(member.name)
                unchanged = target.is_file() and target.stat().st_size == entry["size"] and digest_file(target) == entry["sha256"]
                if target.exists() and not unchanged and not OVERWRITE_DIFFERENT_RUNTIME_FILES:
                    raise FileExistsError(f"Preserving a different existing file: {target}")
                temporary = target.with_name(target.name + ".restore.tmp")
                handle = None
                digest = hashlib.sha256()
                try:
                    if not unchanged:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        handle = temporary.open("wb")
                    with archive.extractfile(member) as source:
                        while block := source.read(1024 * 1024):
                            digest.update(block)
                            if handle:
                                handle.write(block)
                    if digest.hexdigest() != entry["sha256"]:
                        raise ValueError(f"Restored file checksum mismatch: {member.name}")
                    if handle:
                        handle.close()
                        handle = None
                        os.replace(temporary, target)
                finally:
                    if handle:
                        handle.close()
                    temporary.unlink(missing_ok=True)
                if index % 1000 == 0:
                    print(f"  {group['name']}: {index + 1}/{len(expected)} files", flush=True)
        # Consume trailing gzip/tar bytes and verify every declared part, including the final one.
        while parts.read(1024 * 1024):
            pass
    if observed != set(expected):
        raise ValueError(f"Runtime archive omitted {len(set(expected) - observed)} files")
    save_json(ROOT / f".local/restored_groups/{group['name']}.json",
              {"tag": PROFILE["release_tag"], "files": len(observed), "status": "verified"})
    print(f"Restored and verified {group['name']}; compressed downloads removed.", flush=True)


def main():
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    metadata = release_metadata()
    assets = {row["name"]: row for row in metadata["assets"]}
    manifest_path = ROOT / ".local/runtime-manifest.json"
    asset = assets[PROFILE["manifest_asset"]]
    actual = download_asset(asset, manifest_path)
    remote_digest = asset.get("digest")
    if remote_digest and remote_digest != "sha256:" + actual:
        raise ValueError("Manifest asset checksum mismatch.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    for group in manifest["groups"]:
        if group["name"] == "windows_tools" and not RESTORE_WINDOWS_TOOLS:
            continue
        restore_group(group, assets)
    save_json(ROOT / ".local/runtime_restore_receipt.json",
              {"tag": manifest["tag"], "code_commit": manifest["code_commit"], "status": "verified",
               "windows_tools": RESTORE_WINDOWS_TOOLS})


if __name__ == "__main__":
    main()
