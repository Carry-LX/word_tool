"""Exercise split-stream restore, hashes, preservation, traversal and relocation."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import sys
import tarfile
import tempfile
from pathlib import Path

import common
import restore_runtime as restore
from common import ROOT


def check_roundtrip():
    payloads = {"processed/example.csv": "学科,数值\n环境科学与工程,123\n".encode("utf-8"),
                "processed/测试目录/学科数据.csv": "学科,年度\n化学,2026\n".encode("utf-8"),
                "processed/large.bin": bytes(range(256)) * 1000}
    output = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=output) as archive:
        for name, payload in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    raw = output.getvalue()
    parts = []
    blocks = {}
    for index, start in enumerate(range(0, len(raw), 257)):
        name = f"test.tar.gz.part{index + 1:03d}"
        block = raw[start:start + 257]
        blocks[name] = block
        parts.append({"name": name, "size": len(block), "sha256": hashlib.sha256(block).hexdigest()})
    group = {"name": "processed", "parts": parts,
             "files": [{"path": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
                       for name, payload in payloads.items()]}
    original_root, original_downloads, original_download = restore.ROOT, restore.DOWNLOADS, restore.download_asset
    original_safe = restore.safe_target
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs/github_migration", prefix="roundtrip_") as temporary:
            temporary = Path(temporary)
            restore.ROOT = temporary
            restore.DOWNLOADS = temporary / "downloads"
            restore.DOWNLOADS.mkdir()
            restore.safe_target = lambda name: common.safe_target(name, temporary)
            def local_download(asset, output=None):
                block = blocks[asset["name"]]
                output.write_bytes(block)
                return hashlib.sha256(block).hexdigest()
            restore.download_asset = local_download
            assets = {row["name"]: row for row in parts}
            restore.restore_group(group, assets)
            assert not list(restore.DOWNLOADS.iterdir())
            for name, payload in payloads.items():
                assert (temporary / name).read_bytes() == payload
            restore.restore_group(group, assets)
            changed = temporary / "processed/example.csv"
            changed.write_bytes(b"preserve-local-edit")
            try:
                restore.restore_group(group, assets)
            except FileExistsError:
                pass
            else:
                raise AssertionError("Conflicting local file was overwritten")
            assert changed.read_bytes() == b"preserve-local-edit"
            assert not list(restore.DOWNLOADS.iterdir())
            for malicious in ["../escape", "/absolute", "C:/escape", "processed/../../escape", "processed\\escape"]:
                try:
                    common.safe_target(malicious, temporary)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Unsafe path accepted: {malicious}")
            # A changed part must fail checksum before any member can be extracted.
            changed.write_bytes(payloads["processed/example.csv"])
            (temporary / "processed/large.bin").unlink()
            name = parts[0]["name"]
            blocks[name] = b"corrupted" + blocks[name]
            try:
                restore.restore_group(group, assets)
            except ValueError as error:
                assert "checksum" in str(error)
            else:
                raise AssertionError("Corrupted part was accepted")
    finally:
        restore.ROOT, restore.DOWNLOADS, restore.download_asset, restore.safe_target = original_root, original_downloads, original_download, original_safe


def check_paths():
    sys.path.insert(0, str(ROOT / "scripts"))
    import agent_runtime
    target = agent_runtime.resolve_project_path("Z:/missing/word_tool/processed/ranking.sqlite")
    assert target == ROOT / "processed/ranking.sqlite"
    # Reject traversal during project-root relocation.
    target = agent_runtime.resolve_project_path("Z:/missing/word_tool/../../outside")
    assert not target.is_relative_to(ROOT)
    import demo_catalog
    import demo_runtime
    assert len(demo_catalog.subjects()) >= 40
    assert len(demo_catalog.catalog()) >= 6
    assert Path(demo_runtime.configuration()["python"]).is_file()
    import run_demo_dashboard
    client = run_demo_dashboard.create_app().test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200


def main():
    (ROOT / "outputs/github_migration").mkdir(parents=True, exist_ok=True)
    check_roundtrip()
    check_paths()
    result = {"status": "pass", "checks": ["split_stream_utf8_roundtrip", "sha256_rejection", "temporary_part_cleanup",
              "preserve_existing_changes", "reject_path_traversal", "resolve_moved_paths", "dashboard_catalog"]}
    common.save_json(ROOT / "outputs/github_migration/transfer_check.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
