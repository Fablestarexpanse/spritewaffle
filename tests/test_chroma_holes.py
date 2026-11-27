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


def test_black_fill_merged_into_the_outline_is_keyed_inside_its_green_loop():
    """Measured S facing of a fitted body: the black fill touches the sprite outline, so it is one
    dark region with the whole outline; the thin green line around it still closes a loop."""
    img = _figure()
    img[60:140, 100:140] = (0, 0, 0)                     # black fill that merges with ...
    img[60:140, 140:143] = (0, 0, 0)                     # ... a dark band reaching the outline
    img[60:140, 140:157] = (0, 0, 0)
    img[60, 100:140] = img[139, 100:140] = (0, 255, 0)   # thin green loop around the fill
    img[60:140, 100] = img[60:140, 139] = (0, 255, 0)
    new = chroma.key(img)[..., 3] > 0
    assert not new[70:130, 105:135].any()                # the fill inside the loop is gone
    assert new[100, 150] and new[31, 100] and new[100, 70]   # the band, outline and body stay


def _green_gap(width):
    """Video-model gap mush: dark green with black specks, `width` px wide, inside the body."""
    rng = np.random.default_rng(1)
    img = _figure()
    gap = img[60:140, 70:70 + width]
    gap[:] = (10, 90, 15)
    gap[rng.random(gap.shape[:2]) < 0.3] = (5, 5, 5)
    return img


def test_green_gap_mush_is_keyed_only_when_asked():
    img = _green_gap(12)
    assert (chroma.key(img)[..., 3] > 0)[100, 76]        # off by default: green is not removed for being green
    new = chroma.key(img, green_gaps=True)[..., 3] > 0
    assert new[60:140, 70:82].mean() < 0.05
    assert new[100, 100] and new[31, 100]


def test_thin_green_tint_is_kept_by_green_gaps():
    """Video models tint dark outlines green 1-2 px deep; that is outline, not a gap."""
    img = _green_gap(2)
    assert (chroma.key(img, green_gaps=True)[..., 3] > 0)[60:140, 70:72].mean() > 0.9


def test_has_green():
    sprite = chroma.key(_figure())
    assert not chroma.has_green(sprite)
    img = _figure(); img[60:100, 60:100] = (40, 160, 50)  # a green tunic patch
    assert chroma.has_green(chroma.key(img))
