from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "runtime" / "ranking_source_inputs.json"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"version": 1, "sources": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def source_spec(source_key: str) -> dict[str, Any]:
    sources = load_config().get("sources", {})
    spec = sources.get(source_key, {}) if isinstance(sources, dict) else {}
    return spec if isinstance(spec, dict) else {}


def resolve_data_file_name(data_dir: Path, source_key: str, fallback: str) -> str:
    spec = source_spec(source_key)
    candidates = [spec.get("preferred_file", "")]
    candidates.extend(spec.get("fallback_files", []))
    candidates.append(fallback)
    for value in candidates:
        file_name = str(value or "").strip()
        if file_name and (data_dir / file_name).exists():
            return file_name
    preferred = str(spec.get("preferred_file") or fallback).strip()
    raise FileNotFoundError(f"No configured source file exists for {source_key}: {preferred}")


def resolve_sheet_name(path: Path, source_key: str, fallback: str) -> str:
    spec = source_spec(source_key)
    with pd.ExcelFile(path) as excel:
        sheet_names = list(excel.sheet_names)
    for value in spec.get("sheet_candidates", []):
        candidate = str(value or "").strip()
        if candidate in sheet_names:
            return candidate

    required = {str(value).strip() for value in spec.get("required_columns", []) if str(value).strip()}
    if required:
        for sheet_name in sheet_names:
            columns = {
                str(column).strip()
                for column in pd.read_excel(path, sheet_name=sheet_name, nrows=0).columns
            }
            if required.issubset(columns):
                return sheet_name

    if fallback in sheet_names:
        return fallback
    raise ValueError(f"No compatible sheet found for {source_key} in {path.name}: {sheet_names}")


def expected_latest_year(source_key: str) -> int | None:
    value = source_spec(source_key).get("expected_latest_year")
    return int(value) if value not in {None, ""} else None
