"""Atomic JSON-file writes/reads that survive Windows sharing violations.

On Windows, os.replace() onto a file that another thread or process has open fails with
PermissionError (and a read can fail the same way mid-replace). The queue polls task files while
workers update them, so both sides retry briefly instead of failing the task.
"""
from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

RETRIES = 50
DELAY = 0.02


def _replace(path: Path, tmp: Path) -> None:
    for i in range(RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == RETRIES - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(DELAY)


def write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    _replace(path, tmp)


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    _replace(path, tmp)


def read_text(path: Path) -> str:
    for i in range(RETRIES):
        try:
            return Path(path).read_text(encoding="utf-8")
        except PermissionError:
            if i == RETRIES - 1:
                raise
            time.sleep(DELAY)
    raise AssertionError("unreachable")


@contextmanager
def locked(path: Path, busy_message: str):
    """Hold an OS lock until the file handle closes."""
    with path.open("a+b") as lock:
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            raise RuntimeError(busy_message) from error
        yield
