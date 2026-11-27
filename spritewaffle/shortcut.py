"""Windows shortcuts to the local app: Desktop and Start Menu entries that run the checkout's
Launch_SpriteWaffle.bat (starts `spritewaffle ui` and opens the browser) with the SpriteWaffle icon.

Uses Windows' own WScript.Shell through PowerShell, so there is no new dependency. Nothing is
installed; `remove` deletes exactly the shortcuts this wrote.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "SpriteWaffle.lnk"


def _repo() -> Path:
    return Path(__file__).resolve().parent.parent


def launcher() -> Path:
    path = _repo() / "Launch_SpriteWaffle.bat"
    if not path.is_file():
        raise FileNotFoundError(f"launcher not found: {path} (shortcuts need a source checkout)")
    return path


def icon() -> Path:
    return Path(__file__).resolve().parent / "ui" / "static" / "brand" / "SpriteWaffle.ico"


def default_folders() -> list[Path]:
    """The user's Desktop and Start Menu Programs folders (as Windows reports them)."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "[Environment]::GetFolderPath('Desktop'); [Environment]::GetFolderPath('Programs')"],
                         capture_output=True, text=True, check=True)
    return [Path(line.strip()) for line in out.stdout.splitlines() if line.strip()]


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create(folders: list[Path] | None = None) -> list[str]:
    if sys.platform != "win32":
        raise RuntimeError("shortcuts are made for Windows; on other systems run `spritewaffle ui`")
    target, ico = launcher(), icon()
    made = []
    for folder in folders or default_folders():
        folder.mkdir(parents=True, exist_ok=True)
        link = folder / NAME
        script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(link))}); "
                  f"$s.TargetPath = {_ps_quote(str(target))}; $s.WorkingDirectory = {_ps_quote(str(target.parent))}; "
                  f"$s.IconLocation = {_ps_quote(str(ico) + ',0')}; $s.Description = 'SpriteWaffle: AI images to game sprites'; "
                  "$s.WindowStyle = 7; $s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True, text=True)
        made.append(str(link))
    return made


def remove(folders: list[Path] | None = None) -> list[str]:
    gone = []
    for folder in folders or default_folders():
        link = folder / NAME
        if link.is_file():
            os.remove(link)
            gone.append(str(link))
    return gone


def describe(path: Path) -> dict:
    """Read a shortcut back (target, working folder, icon) as Windows sees it."""
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(path))}); "
              "\"$($s.TargetPath)|$($s.WorkingDirectory)|$($s.IconLocation)\"")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, check=True)
    target, cwd, ico = out.stdout.strip().split("|")
    return {"target": target, "working_directory": cwd, "icon": ico}
