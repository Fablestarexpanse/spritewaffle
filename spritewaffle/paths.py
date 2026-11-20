"""Where SpriteWaffle keeps its files, independent of the current directory.

Project root: $SPRITEWAFFLE_HOME if set, else the repository this package is installed from
(the folder that holds templates/), else the current directory. Read on every call so tests and
tools can point it elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("SPRITEWAFFLE_HOME")
    if env:
        return Path(env).resolve()
    repo = Path(__file__).resolve().parents[1]
    return repo if (repo / "templates").is_dir() else Path.cwd().resolve()


def jobs() -> Path:
    return Path(os.environ.get("SPRITEWAFFLE_JOBS") or root() / "jobs")


def templates() -> Path:
    return root() / "templates"


def profiles() -> Path:
    return root() / "profiles"
