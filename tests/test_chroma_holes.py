"""Multi-pass cleanup of enclosed gaps the strict key misses (pixel/chroma._clean_holes)."""
import numpy as np

from spritewaffle.pixel import chroma


def _figure():
    """A figure on #00FF00: a black outline ring around a brown body with a gap through it."""
    img = np.zeros((200, 200, 3), np.uint8); img[:] = (0, 255, 0)
    img[30:170, 40:160] = (0, 0, 0)                      # outline
    img[33:167, 43:157] = (120, 70, 40)                  # body
    return img


def test_clean_figure_is_unchanged():
    img = _figure()
    assert (chroma.key(img)[..., 3] == chroma.key(img, clean_holes=False)[..., 3]).all()


def test_speckled_green_gap_and_black_gap_ringed_by_green_are_keyed():
    rng = np.random.default_rng(0)
    img = _figure()
    gap = img[60:140, 60:80]                             # speckled green: green with dark noise
    gap[:] = (20, 230, 30)                               # compressed green, as H3 returns it
    gap[rng.random(gap.shape[:2]) < 0.2] = (20, 20, 20)
    img[60:140, 110:130] = (0, 255, 0)                   # green rim ...
    img[62:138, 112:128] = (8, 8, 8)                     # ... around a black fill
    old = chroma.key(img, clean_holes=False)[..., 3] > 0
    new = chroma.key(img)[..., 3] > 0
    assert old[100, 70] and old[100, 120]                # the strict key left both gaps opaque
    assert new[60:140, 60:80].mean() < 0.01            # a few clumps of 3-4 specks may stay (20 % noise is harsh)
    assert not new[60:140, 110:130].any()               # the black fill and its green rim are gone
    assert new[100, 95] and new[31, 100]                 # body and outline stay
