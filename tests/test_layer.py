"""Equipment layers: the variant's change alone, drawn back over the base."""
import numpy as np
from PIL import Image

from spritewaffle.core import layer


def _body(gold=False, noise=0):
    im = np.zeros((256, 256, 3), np.uint8)
    im[...] = (0, 255, 0)
    im[60:200, 100:156] = (60, 60, 200)                  # the body
    if gold:
        im[90:140, 95:161] = (230, 180, 40)               # the chest piece, a little wider than the body
    if noise:
        im[150:200, 100:156] = np.clip(im[150:200, 100:156].astype(int) + noise, 0, 255)   # redraw noise
    return im


def test_layer_is_the_change_and_recomposes_to_the_variant(tmp_path):
    lay, err = layer.extract(_body(), _body(gold=True, noise=20))
    a = lay[..., 3] > 0
    assert a[115, 128] and a[115, 96] and not a[170, 128] and not a[20, 20]   # chest + overhang, not legs
    assert err < 1
    moved = np.roll(_body(gold=True), 12, 1)
    moved[:, :12] = (0, 255, 0)
    assert layer.extract(_body(), moved)[1] > layer.MOVED_WARN


def test_facings_writes_one_layer_per_shared_facing(tmp_path):
    b, v = tmp_path / "b", tmp_path / "v"
    b.mkdir(); v.mkdir()
    for f in ("S", "N"):
        Image.fromarray(_body()).save(b / f"{f}.png")
        Image.fromarray(_body(gold=f == "S")).save(v / f"{f}.png")
    Image.fromarray(_body()).save(v / "E.png")             # no base E: skipped
    rep = layer.facings(b, v, v / "layers")
    assert set(rep["layers"]) == {"S", "N"} and (v / "layers" / "S.png").exists()
    assert rep["layers"]["S"] > 0 and rep["layers"]["N"] == 0
    assert any(w.startswith("N: no item layer") for w in rep["warnings"])


def test_facings_skips_other_files_and_size_mismatches(tmp_path):
    b, v = tmp_path / "b", tmp_path / "v"
    b.mkdir(); v.mkdir()
    Image.fromarray(_body()).save(b / "S.png")
    Image.fromarray(_body(gold=True)[:200]).save(v / "S.png")
    Image.fromarray(_body()).save(b / ".S.crop128.png")
    Image.fromarray(_body()[:10]).save(v / ".S.crop128.png")
    rep = layer.facings(b, v, v / "layers")
    assert rep["layers"] == {} and "no layer" in rep["warnings"][0]
