"""Common configuration and atomic state for the local report demonstrator."""
from __future__ import annotations

import json
import ctypes
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import agent_runtime

PROJECT_DIR = Path(__file__).resolve().parent.parent


def shared_bytes(path: Path) -> bytes:
    if os.name != "nt":
        return path.read_bytes()
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    handle = kernel.CreateFileW(str(path.resolve()), 0x80000000, 0x7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


def read_json(path: Path, default=None):
    if not path.is_file():
        return {} if default is None else default
    for attempt in range(8):
        try:
            return json.loads(shared_bytes(path).decode("utf-8-sig"))
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(min(0.005 * (2 ** attempt), 0.1))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Windows readers can briefly hold a file without FILE_SHARE_DELETE.
    # Keep replacement atomic; retry only sharing/permission contention.
    for attempt in range(12):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if os.name != "nt" or attempt == 11:
                raise
            time.sleep(min(0.005 * (2 ** attempt), 0.15))


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def configuration() -> dict:
    runtime = agent_runtime.load_runtime_profile()
    web = runtime["web_demo"]
    return dict(read_json(PROJECT_DIR / web["config_path"]), host=web["host"], port=int(web["port"]),
                python=runtime["recommended_python"], university=read_json(PROJECT_DIR / runtime["active_subject_request_path"])["request"]["target_university"])


def job_root() -> Path:
    return PROJECT_DIR / configuration()["runs_dir"]
