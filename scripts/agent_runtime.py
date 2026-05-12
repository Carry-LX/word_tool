from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_PATH = PROJECT_DIR / "configs" / "runtime" / "agent_runtime_profile.json"
DEFAULT_REQUEST_PATH = PROJECT_DIR / "configs" / "runtime" / "current_subject_request.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def resolve_project_path(value: str | Path | None, default: Path | None = None) -> Path:
    if value is None or str(value).strip() == "":
        if default is None:
            raise ValueError("Path value is empty and no default was provided.")
        return default
    path = Path(str(value))
    return path if path.is_absolute() else PROJECT_DIR / path


def deep_get(payload: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    value: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def load_runtime_profile(path: str | Path | None = None) -> dict[str, Any]:
    profile_path = resolve_project_path(path, DEFAULT_PROFILE_PATH)
    if not profile_path.exists():
        raise FileNotFoundError(f"Runtime profile not found: {profile_path}")
    profile = read_json(profile_path)
    profile["_profile_path"] = str(profile_path)
    return profile


def load_subject_request(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = profile or load_runtime_profile()
    request_path = resolve_project_path(profile.get("active_subject_request_path"), DEFAULT_REQUEST_PATH)
    if not request_path.exists():
        raise FileNotFoundError(f"Subject request not found: {request_path}")
    payload = read_json(request_path)
    request = payload.get("request", payload)
    if not isinstance(request, dict):
        raise ValueError(f"Subject request has invalid shape: {request_path}")
    request = dict(request)
    request["_request_path"] = str(request_path)
    return request


def validate_subject_request(request: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not str(request.get("target_university", "")).strip():
        issues.append({"severity": "P0", "field": "target_university", "message": "Missing target university."})
    if not str(request.get("target_subject", "")).strip():
        issues.append({"severity": "P0", "field": "target_subject", "message": "Missing target subject."})
    code = str(request.get("target_subject_code", "")).strip()
    if code and not re.fullmatch(r"\d{4}", code):
        issues.append({"severity": "P1", "field": "target_subject_code", "message": "Expected a four-digit ministry subject code."})
    year = request.get("report_year", "")
    if year != "" and not isinstance(year, int):
        issues.append({"severity": "P1", "field": "report_year", "message": "Expected an integer report year."})
    sources = request.get("ranking_sources")
    if sources is not None and (not isinstance(sources, list) or not all(str(item).strip() for item in sources)):
        issues.append({"severity": "P1", "field": "ranking_sources", "message": "Expected a non-empty list of ranking source names."})
    proxy_policy = request.get("proxy_policy")
    if proxy_policy and proxy_policy not in {"allow_with_disclosure", "disallow"}:
        issues.append({"severity": "P1", "field": "proxy_policy", "message": "Unsupported proxy policy."})
    return issues


def profile_path(profile: dict[str, Any], dotted_key: str, default: str | Path) -> Path:
    return resolve_project_path(deep_get(profile, dotted_key), Path(default))


def profile_bool(profile: dict[str, Any], dotted_key: str, default: bool) -> bool:
    value = deep_get(profile, dotted_key, default)
    return bool(value)


def profile_int(profile: dict[str, Any], dotted_key: str, default: int) -> int:
    value = deep_get(profile, dotted_key, default)
    return int(value)


def profile_str(profile: dict[str, Any], dotted_key: str, default: str) -> str:
    value = deep_get(profile, dotted_key, default)
    return str(value)


def request_value(request: dict[str, Any], key: str, default: Any) -> Any:
    value = request.get(key, default)
    return default if value is None or value == "" else value
