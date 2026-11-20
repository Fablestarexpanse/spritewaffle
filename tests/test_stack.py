import numpy as np
import cv2

from spritewaffle.stack import carve as st

W, D, H = 10, 6, 6
RED, BLUE, GREY, YEL, ROOF, BACK = (200, 30, 30), (30, 30, 200), (90, 90, 90), (230, 200, 40), (250, 250, 250), (20, 120, 20)


def car():
    """Body box (z 0-2) + narrower cabin (x 2-7, y 1-4, z 3-5). Colour per face direction."""
    occ = np.zeros((H, D, W), bool)
    occ[0:3, :, :] = True
    occ[3:6, 1:5, 2:8] = True
    return occ


def project(occ):
    """Reference projector: view images as SpriteWaffle expects them (see stack.carve docstring)."""
    Hh, Dd, Ww = occ.shape
    def img(shape):
        return np.zeros(shape + (4,), np.uint8)
    front, back, right, top = img((Hh, Ww)), img((Hh, Ww)), img((Hh, Dd)), img((Dd, Ww))
    for z in range(Hh):
        for x in range(Ww):
            if occ[z, :, x].any():
                front[Hh - 1 - z, x] = (*RED, 255)
                back[Hh - 1 - z, Ww - 1 - x] = (*BACK, 255)
        for y in range(Dd):
            if occ[z, y, :].any():
                right[Hh - 1 - z, y] = (*BLUE, 255)
    for y in range(Dd):
        for x in range(Ww):
            if occ[:, y, x].any():
                top[Dd - 1 - y, x] = (*ROOF, 255) if occ[3:, y, x].any() else (*YEL, 255)
    return st.Views(front=front, right=right, top=top, back=back)


def up(img, k=3):
    return cv2.resize(img, (img.shape[1] * k, img.shape[0] * k), interpolation=cv2.INTER_NEAREST)


def test_carve_recovers_shape_and_face_colours():
    model = car()
    v = project(model)
    v = st.Views(front=up(v.front), right=up(v.right), top=up(v.top), back=up(v.back))
    occ, col = st.carve(v)
    assert occ.shape == (18, 18, 30)
    small = occ[1::3, 1::3, 1::3]                       # sample the 3x-upscaled volume at cell centres
    np.testing.assert_array_equal(small, model)
    # surface voxels of the 3x volume (cell (z, y, x) spans 3z..3z+2 etc.)
    assert tuple(col[17, 7, 13]) == ROOF                # cabin roof: topmost layer, seen from above
    assert tuple(col[8, 1, 1]) == YEL                   # body top in front of the cabin (top wins)
    assert tuple(col[4, 0, 16]) == RED                  # body front face (y = 0)
    assert tuple(col[4, 17, 16]) == BACK                # body back face (y = max)
    assert tuple(col[4, 10, 29]) == BLUE                # body right face (x = max)
    assert tuple(col[4, 10, 0]) == BLUE                 # left face = mirrored right


def test_slices_and_render():
    occ, col = st.carve(project(car()))
    sl = st.slices(occ, col)
    assert sl.shape == (6, 6, 10, 4)
    assert (sl[5, ..., 3] > 0).sum() == 4 * 6          # top slice = cabin footprint
    assert tuple(sl[0, -1, 5, :3]) == RED               # front of the prop at the bottom row of a slice
    frames = st.turntable(sl, steps=8)
    assert len(frames) == 8 and all(f[..., 3].any() for f in frames)
    colours = {tuple(c) for f in frames for c in f[f[..., 3] > 0][:, :3].tolist()}
    assert colours <= {RED, BLUE, GREY, YEL, ROOF, BACK}  # nearest-neighbour: no new colours
    # stacking puts higher slices higher on screen
    r0 = st.render(sl, 0)
    rows = np.where(r0[..., 3].any(1))[0]
    assert rows.max() - rows.min() + 1 > 6               # taller than one slice: layers stack upward
