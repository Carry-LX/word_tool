"""Initialize a cloned Windows checkout using explicit settings, without CLI flags."""
from __future__ import annotations

import os
import subprocess
import sys

from common import ROOT, PROFILE, save_json

INSTALL_PYTHON_PACKAGES = True
RESTORE_RUNTIME_DATA = True


def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use 64-bit Python 3.12 on Windows for this runtime snapshot.")
    if INSTALL_PYTHON_PACKAGES:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", str(ROOT / "requirements.txt")], check=True)
    if RESTORE_RUNTIME_DATA:
        import restore_runtime
        restore_runtime.main()
    save_json(ROOT / PROFILE["local_runtime_path"], {"recommended_python": sys.executable})
    os.environ["PATH"] = os.pathsep.join([str(ROOT / ".local/bin"), str(ROOT / ".local/tools/poppler/bin"), os.environ.get("PATH", "")])
    subprocess.run([sys.executable, "-B", str(ROOT / "tools/migration/check_portability.py")], check=True)


if __name__ == "__main__":
    main()
