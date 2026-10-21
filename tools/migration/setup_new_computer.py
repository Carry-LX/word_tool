"""Initialize a cloned Windows checkout using explicit settings, without CLI flags."""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from common import ROOT, PROFILE, save_json

INSTALL_PYTHON_PACKAGES = True
RESTORE_RUNTIME_DATA = True


def choose_temporary_directory() -> Path:
    candidates = [ROOT / ".local/tmp", Path("E:/tools/word_tool_tmp"), Path("D:/tools/word_tool_tmp"),
                  Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "word_tool_tmp"]
    for directory in candidates:
        if not str(directory).isascii():
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory, prefix="write_probe_", suffix=".tmp") as probe:
                probe.write(b"ok")
            return directory
        except OSError:
            continue
    raise RuntimeError("Configure a writable ASCII temporary directory in local_runtime.json.")


def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError("Use 64-bit Python 3.12 on Windows for this runtime snapshot.")
    if INSTALL_PYTHON_PACKAGES:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", str(ROOT / "requirements.txt")], check=True)
    if RESTORE_RUNTIME_DATA:
        import restore_runtime
        restore_runtime.main()
    temporary = choose_temporary_directory()
    save_json(ROOT / PROFILE["local_runtime_path"], {"recommended_python": sys.executable,
                                                    "temporary_directory": str(temporary)})
    os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
    os.environ["PATH"] = os.pathsep.join([str(ROOT / ".local/bin"), str(ROOT / ".local/tools/poppler/bin"), os.environ.get("PATH", "")])
    subprocess.run([sys.executable, "-B", str(ROOT / "tools/migration/check_portability.py")], check=True)


if __name__ == "__main__":
    main()
