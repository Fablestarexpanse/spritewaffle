import numpy as np

from spritewaffle.pixel import chroma, grid, palette, quantize, cleanup
from spritewaffle.pixel.color import srgb_to_oklab
from spritewaffle.pixel.pipeline import PixelParams, pixelize
from synth import PALETTE, draw_sprite, render


def _same_partition(a: np.ndarray, b: np.ndarray) -> bool:
    """True if label images match up to a relabeling (and -1 maps to -1)."""
    if a.shape != b.shape or not np.array_equal(a < 0, b < 0):
        return False
    m = a >= 0
    pairs = set(zip(a[m].tolist(), b[m].tolist()))
    return len(pairs) == len({p[0] for p in pairs}) == len({p[1] for p in pairs})


# --- chroma -------------------------------------------------------------------------------

def test_chroma_keeps_enclosed_green_and_despills_edges():
    img = np.zeros((40, 40, 3), np.uint8); img[:] = (0, 255, 0)
    img[10:30, 10:30] = (90, 60, 40)          # brown body
    img[18:22, 18:22] = (60, 170, 60)         # green leaf inside: must survive
    img[10:30, 9] = (100, 210, 90)            # spill fringe on left edge
    rgba = chroma.key(img)
    a = rgba[..., 3]
    assert a[0, 0] == 0 and a[20, 20] == 255 and a[15, 15] == 255
    assert tuple(rgba[20, 20, :3]) == (60, 170, 60)   # interior green not despilled/deleted
    fr = rgba[20, 9]
    assert fr[3] == 255 and fr[1] <= max(fr[0], fr[2])  # fringe kept, G clamped


def test_chroma_keys_compressed_offgreen_and_specks():
    img = np.zeros((40, 40, 3), np.uint8); img[:] = (12, 236, 18)
    img[10:30, 10:30] = (200, 50, 50)
    img[2, 2] = (200, 50, 50)                 # 1px speck
    rgba = chroma.remove_specks(chroma.key(img), min_px=4)
    assert rgba[0, 0, 3] == 0 and rgba[2, 2, 3] == 0 and rgba[20, 20, 3] == 255


# --- grid ---------------------------------------------------------------------------------

def test_grid_detects_size_and_phase():
    rgba = chroma.key(render(draw_sprite(), scale=8, offset=(3, 5)))
    g = grid.detect([rgba])
    assert g.size == 8 and g.ox == 3 and g.oy == 5 and g.confident


def test_grid_detects_other_scale():
    rgba = chroma.key(render(draw_sprite(), scale=5, offset=(7, 2), blur=0.8))
    g = grid.detect([rgba])
    assert g.size == 5 and g.ox % 5 == 2 and g.oy % 5 == 2


def test_downscale_votes_dominant_not_average():
    big = np.zeros((8, 8, 4), np.uint8)
    big[..., 3] = 255
    big[:, :] = (255, 0, 0, 255)
    big[0:3, 0:3] = (0, 0, 255, 255)          # minority color must not tint the result
    small = grid.downscale(big, 8, 0, 0)
    assert small.shape == (1, 1, 4) and tuple(small[0, 0]) == (255, 0, 0, 255)


# --- palette / saliency / hysteresis ------------------------------------------------------

def test_saliency_weights_small_contrasting_detail():
    lab = np.zeros((10, 10, 3)); lab[...] = srgb_to_oklab(np.array([44, 92, 196]))
    lab[5, 5] = srgb_to_oklab(np.array([220, 30, 40]))
    w = palette.saliency_weights(lab[None], np.ones((1, 10, 10), bool))
    assert w[0, 5, 5] > 5 * w[0, 0, 0]


def test_hysteresis_stops_flicker():
    pal = srgb_to_oklab(np.array([[0, 0, 0], [100, 100, 100]], float))
    mid = (pal[0] + pal[1]) / 2
    frames = np.stack([np.tile(mid + d * (pal[1] - pal[0]), (1, 1, 1)) for d in (-0.01, 0.01, -0.01, 0.01)])
    alpha = np.ones(frames.shape[:3], bool)
    jittery = quantize.assign(frames, alpha, pal, threshold=0.0)
    stable = quantize.assign(frames, alpha, pal, threshold=0.05)
    assert len(set(jittery[:, 0, 0].tolist())) == 2
    assert len(set(stable[:, 0, 0].tolist())) == 1


def test_locked_palette_is_used_verbatim():
    rgba = chroma.key(render(draw_sprite(), scale=8, offset=(3, 5)))
    locked = ["#%02x%02x%02x" % c for c in PALETTE]
    res = pixelize([rgba], PixelParams(palette=locked))
    assert [tuple(c) for c in res.palette] == PALETTE


# --- full recovery ------------------------------------------------------------------------

def test_pixelizer_recovers_grid_and_palette():
    frames = [chroma.key(render(draw_sprite(i), scale=8, offset=(3, 5), seed=i)) for i in range(4)]
    res = pixelize(frames, PixelParams(palette=len(PALETTE)))
    assert res.grid.size == 8
    for i, idx in enumerate(res.indices):
        crop = idx[res.grid.cell_y(5):, res.grid.cell_x(3):][:24, :16]
        assert _same_partition(crop, draw_sprite(i)), f"frame {i} grid/labels differ"
    # every original color recovered within a small tolerance, incl. the 1px eye and red hat
    for c in PALETTE:
        d = np.abs(res.palette.astype(int) - np.array(c)).max(1).min()
        assert d <= 8, f"color {c} lost (closest diff {d})"


def test_pixelizer_shared_palette_across_frames():
    frames = [chroma.key(render(draw_sprite(i), scale=8, offset=(3, 5), seed=i)) for i in range(4)]
    res = pixelize(frames, PixelParams(palette=len(PALETTE)))
    assert res.indices.max() < len(res.palette)
    assert len(res.indices) == 4 and res.palette.shape == (len(PALETTE), 3)


def test_cleanup_removes_orphans_and_outline_grows():
    idx = np.zeros((5, 5), int); idx[2, 2] = 1
    near = srgb_to_oklab(np.array([[100, 100, 100], [108, 104, 100]], float))
    far = srgb_to_oklab(np.array([[100, 100, 100], [250, 250, 250]], float))
    assert cleanup.remove_orphans(idx, near)[2, 2] == 0      # noise in flat area -> removed
    assert cleanup.remove_orphans(idx, far)[2, 2] == 1       # deliberate detail (eye) -> kept
    idx2 = np.full((5, 5), -1); idx2[2, 2] = 1
    pal = np.array([[10, 10, 10], [200, 200, 200]])
    o = cleanup.outline(idx2, pal, "dark_1px")
    assert o[1, 2] == 0 and o[2, 1] == 0 and o[0, 0] == -1


import pytest
import cv2


@pytest.mark.parametrize("s", [3, 4, 6, 7, 10, 16])
@pytest.mark.parametrize("off", [(0, 0), (5, 3)])
def test_grid_sweep_heavy_noise(s, off):
    r = chroma.key(render(draw_sprite(1), scale=s, offset=off, canvas=(400, 400), noise=6, blur=1.2))
    g = grid.detect([r])
    assert (g.size, g.ox, g.oy, g.confident) == (s, off[0] % s, off[1] % s, True)


def test_grid_not_confident_on_smooth_art():
    img = np.zeros((300, 300, 3), np.uint8); img[:] = (0, 255, 0)
    yy, xx = np.mgrid[:300, :300]
    m = (yy - 150) ** 2 + (xx - 150) ** 2 < 100 ** 2
    img[m] = np.stack([xx[m] * 0.8, yy[m] * 0.5, np.full(m.sum(), 120)], -1).astype(np.uint8)
    img[120:140, 100:200] = (200, 40, 40)
    img = cv2.GaussianBlur(img, (0, 0), 2)
    assert not grid.detect([chroma.key(img)]).confident


def test_fallback_grid_hits_target_height():
    img = np.zeros((300, 300, 3), np.uint8); img[:] = (0, 255, 0)
    img[50:250, 120:180] = (200, 40, 40)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    res = pixelize([img], PixelParams(palette=4, target_height=40))
    ys = np.where((res.indices[0] >= 0).any(1))[0]
    assert res.grid.source == "fallback" and abs((ys[-1] - ys[0] + 1) - 40) <= 1


def test_despill_all_clamps_interior_tint_but_edge_mode_keeps_it():
    img = np.zeros((40, 40, 3), np.uint8); img[:] = (0, 255, 0)
    img[8:32, 8:32] = (90, 60, 40)
    img[20, 20] = (8, 102, 45)                 # green-tinted outline pixel deep inside
    assert chroma.key(img)[20, 20, 1] == 102
    px = chroma.key(img, despill="all")[20, 20]
    assert px[3] == 255 and px[1] <= max(px[0], px[2])
