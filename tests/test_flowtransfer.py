import numpy as np

from spritewaffle.frames import flowtransfer as ft
from synth import PALETTE, draw_sprite, render

RECOLOR = np.array([(10, 10, 60), (240, 200, 90), (30, 160, 70), (90, 40, 120), (250, 120, 0), (0, 0, 0)], np.uint8)


def art(labels, colors, canvas=(40, 40), at=(12, 8)):
    """Label image -> RGBA art pasted on a transparent canvas."""
    out = np.zeros((canvas[1], canvas[0], 4), np.uint8)
    h, w = labels.shape
    m = labels >= 0
    sub = np.zeros((h, w, 4), np.uint8)
    sub[m, :3] = colors[labels[m]]
    sub[m, 3] = 255
    out[at[1]:at[1] + h, at[0]:at[0] + w] = sub
    return out


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def test_nearest_opaque_lookup():
    alpha = np.zeros((7, 9), bool)
    alpha[1, 1] = alpha[5, 7] = True
    ny, nx = ft._nearest_opaque(alpha)
    assert (ny[0, 0], nx[0, 0]) == (1, 1) and (ny[6, 8], nx[6, 8]) == (5, 7)
    assert (ny[1, 1], nx[1, 1]) == (1, 1)


def test_alignment_scale_and_anchor():
    src = np.zeros((200, 200), bool); src[40:160, 80:120] = True     # 120 tall
    tgt = np.zeros((40, 40), bool); tgt[10:34, 12:28] = True         # 24 tall
    al = ft.align(src, tgt)
    assert al.k == 24 / 120 and al.src_anchor == (100, 160) and al.art_anchor == (20, 34)


def test_transfer_reproduces_motion_with_target_pixels_only():
    steps = [0, 1, 0, 3, 0, 1]
    clip = [render(draw_sprite(s), scale=8, offset=(80, 40), canvas=(320, 280), seed=i) for i, s in enumerate(steps)]
    target = art(draw_sprite(0), RECOLOR)
    out = ft.warp(target, clip)
    assert len(out) == len(clip) and out[0].shape == target.shape
    allowed = {tuple(c) for c in RECOLOR.tolist()}
    for i, f in enumerate(out):
        used = {tuple(c) for c in f[f[..., 3] > 0][:, :3].tolist()}
        assert used <= allowed, f"frame {i} invented colours {used - allowed}"
        expected = art(draw_sprite(steps[i]), RECOLOR)[..., 3] > 0
        assert iou(f[..., 3] > 0, expected) > 0.85, f"frame {i} silhouette off"
    # the legs actually move: frames 1 and 3 differ from frame 0 where the walk differs
    assert not np.array_equal(out[1][..., 3], out[0][..., 3])
    assert iou(out[0][..., 3] > 0, art(draw_sprite(0), RECOLOR)[..., 3] > 0) > 0.95


def test_holes_take_nearest_target_colour():
    clip = [render(draw_sprite(0), scale=8, offset=(80, 40), canvas=(320, 280), seed=0)] * 2
    target = art(draw_sprite(0), RECOLOR)
    target[20, 18, 3] = 0                                  # punch a hole in the target art
    out = ft.warp(target, clip)
    assert out[1][20, 18, 3] == 255                         # mask says opaque -> filled from a neighbour
    assert tuple(out[1][20, 18, :3]) in {tuple(c) for c in RECOLOR.tolist()}


def test_target_parts_outside_driver_silhouette_survive():
    """A club the driving figure doesn't have must not be clipped to the driver's outline."""
    clip = [render(draw_sprite(s), scale=8, offset=(80, 40), canvas=(320, 280), seed=i) for i, s in enumerate([0, 1, 0])]
    lab = draw_sprite(0)
    target = art(lab, RECOLOR)
    target[22:26, 6:12] = (*RECOLOR[4], 255)                 # club sticking out left of the body
    out = ft.warp(target, clip)
    for f in out:
        assert (f[22:26, 6:12, 3] > 0).mean() > 0.8
