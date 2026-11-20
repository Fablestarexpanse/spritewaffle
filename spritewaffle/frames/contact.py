"""Contact sheet: numbered thumbnail grid of a frame folder."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def contact_sheet(frames: list[np.ndarray], labels: list[str] | None = None, cols: int = 8,
                  cell: int = 128, bg=(40, 40, 40)) -> Image.Image:
    """Fit each frame into a cell x cell box (aspect kept), label its number top-left."""
    labels = labels or [str(i) for i in range(len(frames))]
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), bg)
    draw = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        im = Image.fromarray(f)
        if im.mode == "RGBA":
            checker = Image.new("RGBA", im.size, (90, 90, 90, 255))
            im = Image.alpha_composite(checker, im)
        im = im.convert("RGB")
        k = min(cell / im.width, cell / im.height)
        resample = Image.NEAREST if k >= 1 else Image.BILINEAR
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), resample)
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        draw.rectangle([x, y, x + 8 * len(labels[i]) + 4, y + 14], fill=(0, 0, 0))
        draw.text((x + 2, y + 1), labels[i], fill=(255, 255, 0))
    return sheet


def write(frames: list[np.ndarray], out: str | Path, **kw) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet(frames, **kw).save(out)
    return out
