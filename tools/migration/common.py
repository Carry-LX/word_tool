"""Small, standard-library-only helpers shared by migration entry points."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PROFILE = json.loads((ROOT / "configs/runtime/migration_profile.json").read_text(encoding="utf-8"))


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, encoding="utf-8")
    return result.stdout


def release_metadata() -> dict:
    return json.loads(gh("api", f"repos/{PROFILE['repository']}/releases/tags/{PROFILE['release_tag']}"))


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_target(name: str, root: Path = ROOT) -> Path:
    portable = PurePosixPath(name)
    if portable.is_absolute() or ".." in portable.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe archive member: {name}")
    target = (root / name).resolve()
    if target == root.resolve() or not target.is_relative_to(root.resolve()):
        raise ValueError(f"Archive member escapes project: {name}")
    return target


def download_asset(asset: dict, output: Path | None = None) -> str:
    """Stream a private asset using gh authentication, optionally to disk."""
    proc = subprocess.Popen(
        ["gh", "api", f"repos/{PROFILE['repository']}/releases/assets/{asset['id']}",
         "-H", "Accept: application/octet-stream"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    digest = hashlib.sha256()
    size = 0
    handle = output.open("wb") if output else None
    try:
        while block := proc.stdout.read(1024 * 1024):
            digest.update(block)
            size += len(block)
            if handle:
                handle.write(block)
        error = proc.stderr.read().decode("utf-8", errors="replace")
        if proc.wait() != 0 or size != asset["size"]:
            raise RuntimeError(f"Asset download failed: {asset['name']}: {error}")
        return digest.hexdigest()
    finally:
        if handle:
            handle.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def upload_verified(path: Path) -> dict:
    """Delete a local part only after GitHub confirms its exact bytes."""
    local_hash, local_size = digest_file(path), path.stat().st_size
    gh("release", "upload", PROFILE["release_tag"], str(path), "--repo", PROFILE["repository"])
    asset = next(a for a in release_metadata()["assets"] if a["name"] == path.name)
    remote_digest = asset.get("digest", "") or ""
    remote_hash = remote_digest.removeprefix("sha256:") if remote_digest.startswith("sha256:") else download_asset(asset)
    if asset["size"] != local_size or remote_hash != local_hash:
        raise RuntimeError(f"Remote verification failed; keeping local file: {path}")
    record = {"name": path.name, "size": local_size, "sha256": local_hash, "asset_id": asset["id"]}
    path.unlink()
    print(f"Uploaded, verified, deleted local part: {record['name']} ({local_size:,} bytes)", flush=True)
    return record
