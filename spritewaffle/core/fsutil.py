"""Atomic JSON-file writes/reads that survive Windows sharing violations.

On Windows, os.replace() onto a file that another thread or process has open fails with
PermissionError (and a read can fail the same way mid-replace). The queue polls task files while
workers update them, so both sides retry briefly instead of failing the task.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

RETRIES = 50
DELAY = 0.02


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text)
    for i in range(RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == RETRIES - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(DELAY)


def read_text(path: Path) -> str:
    for i in range(RETRIES):
        try:
            return Path(path).read_text()
        except PermissionError:
            if i == RETRIES - 1:
                raise
            time.sleep(DELAY)
    raise AssertionError("unreachable")
