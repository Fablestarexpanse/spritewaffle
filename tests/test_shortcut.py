"""Windows shortcuts to the app (spritewaffle/shortcut.py)."""
import sys

import pytest

from spritewaffle import cli, shortcut


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")
def test_shortcut_points_at_the_launcher_with_the_icon(tmp_path):
    made = shortcut.create([tmp_path])
    assert made == [str(tmp_path / "SpriteWaffle.lnk")]
    info = shortcut.describe(tmp_path / "SpriteWaffle.lnk")
    assert info["target"].lower() == str(shortcut.launcher()).lower()
    assert info["working_directory"].lower() == str(shortcut.launcher().parent).lower()
    assert info["icon"].lower().startswith(str(shortcut.icon()).lower())
    assert shortcut.icon().is_file()
    assert cli.main(["shortcut", "--remove", "--dir", str(tmp_path)]) in (0, None)
    assert not (tmp_path / "SpriteWaffle.lnk").exists()