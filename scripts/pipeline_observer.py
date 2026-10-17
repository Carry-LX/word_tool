"""Optional progress observer shared by CLI and the local demonstration UI."""
from __future__ import annotations

from typing import Callable

_observer: Callable | None = None


def set_observer(observer: Callable | None) -> None:
    global _observer
    _observer = observer


def report_progress(stage: str, status: str, message: str, **metrics) -> None:
    if _observer is not None:
        _observer(stage, status, message, metrics)
