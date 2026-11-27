"""Height and normal maps for seamless textures (texture.surface_maps): they must tile too."""
import numpy as np

from spritewaffle.core import texture


def _seamless(size=32, seed=0):
    """A wrapped random field (sum of whole-period sines), so the tile itself is seamless."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] / size * 2 * np.pi
    field = sum(np.sin(fx * x + fy * y + rng.random() * 6) for fx, fy in rng.integers(1, 5, (6, 2)))
    g = ((field - field.min()) / np.ptp(field) * 200 + 30).astype(np.uint8)
    return np.dstack([g, (g * 0.8).astype(np.uint8), (g * 0.5).astype(np.uint8)])


def test_surface_maps_tile_like_the_colour_map():
    tile = _seamless()
    height, normal = texture.surface_maps(tile)
    assert height.shape == (32, 32) and normal.shape == (32, 32, 3)
    assert height.min() == 0 and height.max() == 255
    # the same maps from a shifted copy are the shifted maps: no edge is treated differently
    shifted_h, shifted_n = texture.surface_maps(np.roll(tile, (11, 7), (0, 1)))
    assert np.array_equal(shifted_h, np.roll(height, (11, 7), (0, 1)))
    assert np.array_equal(shifted_n, np.roll(normal, (11, 7), (0, 1)))
    assert normal[..., 2].min() > 127                     # every normal faces out of the surface


def test_normal_points_up_the_slope_opengl_style():
    ramp = np.dstack([np.tile(np.linspace(40, 200, 16, dtype=np.uint8), (16, 1))] * 3)   # brighter to the right
    _, normal = texture.surface_maps(ramp)
    assert normal[8, 4, 0] < 128                          # surface rises to the right: normal leans left (-x)
    up = np.transpose(ramp, (1, 0, 2))                    # brighter downwards
    _, normal = texture.surface_maps(up)
    assert normal[4, 8, 1] > 128                          # falls toward the top: green (+y, up) is high
    flat = np.full((8, 8, 3), 90, np.uint8)
    h, n = texture.surface_maps(flat)
    assert not h.any() and (n == [128, 128, 255]).all()   # flat: no slope


def test_surface_settings_default_off_and_validated(tmp_path):
    import pytest
    from spritewaffle.core.job import Job
    job = Job.create("dirt", "t1", base=tmp_path, asset_type=texture.TYPE)
    s = texture.settings(job)
    assert s["surface_maps"] is False and s["surface_strength"] == 2.0
    s = texture.configure(job, surface_maps=True, surface_strength=4)
    assert s["surface_maps"] is True and s["surface_strength"] == 4.0
    with pytest.raises(ValueError):
        texture.configure(job, surface_strength=40)


def test_export_writes_seamless_lighting_maps_when_on(tmp_path):
    from test_texture import FakeComfy, _job
    from spritewaffle.core import generate as gen
    from PIL import Image
    j = _job(tmp_path)
    texture.generate(j, client=FakeComfy(), seed=3)
    gen.approve(j, "texture")
    out = j.root / "06_export" / "texture"
    assert "surface_maps" not in texture.export(j) and not (out / "cobble_0_normal.png").exists()   # off: as before
    texture.configure(j, surface_maps=True)
    info = texture.export(j)
    assert info["surface_maps"]["tiles"][0] == {"height": "cobble_0_height.png", "normal": "cobble_0_normal.png"}
    tile = np.array(Image.open(out / "cobble_0.png").convert("RGB"))
    height, normal = texture.surface_maps(tile)
    assert np.array_equal(np.array(Image.open(out / "cobble_0_normal.png")), normal)
    assert Image.open(out / "cobble_normal_sheet.png").size == (32 * 3, 32)
