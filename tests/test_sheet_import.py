"""Character-sheet import with a stub SAM 3 (mask comes from the synthetic drawing itself)."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import sheet_import
from spritewaffle.core.job import Job


def _sheet(tmp_path):
    """Three figures (different heights) on a parchment-coloured background + their true mask."""
    img = np.full((300, 600, 3), (222, 200, 160), np.uint8)
    mask = np.zeros((300, 600), bool)
    for i, (x, h, col) in enumerate([(60, 200, (200, 40, 40)), (260, 180, (40, 160, 40)), (460, 200, (40, 40, 200))]):
        img[250 - h:250, x:x + 60] = col
        mask[250 - h:250, x:x + 60] = True
    Image.fromarray(img).save(tmp_path / "sheet.png")
    Image.fromarray((mask * 255).astype(np.uint8)).save(tmp_path / "mask.png")
    return tmp_path / "sheet.png", tmp_path / "mask.png"


class StubSam:
    def __init__(self, mask):
        self.mask, self.calls = mask, []

    def run_template(self, slot, values, out_dir):
        self.calls.append((slot, values))
        return {"files": [str(self.mask)]}


def test_import_maps_views_keeps_scale_and_mirrors(tmp_path):
    sheet, mask = _sheet(tmp_path)
    job = Job.create("hero", "j", base=tmp_path)
    sam = StubSam(mask)
    out = sheet_import.import_sheet(job, sheet, ["S", "SE", "N"], subject="block man", client=sam)
    assert sam.calls[0][0] == "sam3_mask" and sam.calls[0][1]["prompt"] == "block man:3"
    assert out["mirrored"] == ["SW"] and set(out["missing"]) == {"E", "W", "NE", "NW"}
    f = job.root / "02_facings"
    s, se, sw = (np.array(Image.open(f / f"{n}.png")) for n in ("S", "SE", "SW"))
    assert tuple(s[0, 0]) == (0, 255, 0)                                  # exact green background
    hs = [np.where(((im != (0, 255, 0)).any(-1)).any(1))[0] for im in (s, se)]
    assert abs((hs[0][-1] - hs[0][0]) / (hs[1][-1] - hs[1][0]) - 200 / 180) < 0.03   # relative size kept
    assert hs[0][-1] == hs[1][-1]                                         # common foot line
    np.testing.assert_array_equal(sw, se[:, ::-1])
    assert (job.root / "01_anchor/anchor.png").exists()
    meta = job.read_meta()["stages"]
    assert meta["anchor"]["status"] == "review" and meta["facings"]["status"] == "review"


def test_import_refuses_bad_views(tmp_path):
    sheet, mask = _sheet(tmp_path)
    job = Job.create("hero", "k", base=tmp_path)
    for views in (["SE", "E", "N"], ["S", "S", "N"], ["S", "UP", "N"]):
        with pytest.raises(ValueError):
            sheet_import.import_sheet(job, sheet, views, client=StubSam(mask))
    with pytest.raises(ValueError, match="found 3 figures"):
        sheet_import.import_sheet(job, sheet, ["S", "SE", "E", "N"], client=StubSam(mask))
