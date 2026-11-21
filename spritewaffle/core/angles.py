"""View angles for directional sprites, any view count.

Convention (docs/MANIFEST.md): yaw_degrees = 0 when the character faces the camera, increasing
clockwise seen from above. With the camera in the south looking north: S = 0, SW = 45, W = 90,
NW = 135, N = 180, NE = 225, E = 270, SE = 315. "E" is the side view facing screen right.
Compass labels are for display only; data is keyed by yaw / view_index.
"""
from __future__ import annotations

LEGACY = {"S": 0.0, "SW": 45.0, "W": 90.0, "NW": 135.0, "N": 180.0, "NE": 225.0, "E": 270.0, "SE": 315.0}
_BY_YAW = {v: k for k, v in LEGACY.items()}


def norm(yaw: float) -> float:
    y = float(yaw) % 360.0
    return 0.0 if abs(y - 360.0) < 1e-9 else round(y, 6)


def views(n: int) -> list[float]:
    """Yaw of each view_index for a set of n evenly spaced views (view 0 faces the camera)."""
    if int(n) < 1:
        raise ValueError("view count must be at least 1")
    return [norm(i * 360.0 / int(n)) for i in range(int(n))]


def view_index(yaw: float, n: int) -> int:
    return int(round(norm(yaw) / (360.0 / int(n)))) % int(n)


def yaw_of(label: str) -> float:
    if label not in LEGACY:
        raise ValueError(f"unknown facing label {label!r}; known: {sorted(LEGACY)}")
    return LEGACY[label]


def label(yaw: float) -> str:
    """Compass label for display: the legacy name when exact, else the degrees."""
    y = norm(yaw)
    return _BY_YAW.get(y, f"{y:g}°")


def mirror_of(yaw: float) -> float:
    """The yaw a flipped image of `yaw` shows (W <-> E, SW <-> SE; S and N map to themselves)."""
    return norm(360.0 - norm(yaw))


def rendered_half(yaw: float) -> bool:
    """mirror_left_from_right: views that are rendered (S, N and the right-facing half, yaw in
    (180, 360)); the left-facing half (0, 180) is flipped from its mirror."""
    y = norm(yaw)
    return y in (0.0, 180.0) or y > 180.0


POLICIES = ("legacy", "none", "mirror_left_from_right", "custom")


def mirror_source(yaw: float, policy: str, mirror_map: dict | None = None, n: int | None = None) -> float | None:
    """Yaw to flip for this view under the policy, or None when it is rendered. legacy: decided
    per run as before (None here; the manifest records what actually happened)."""
    if policy not in POLICIES:
        raise ValueError(f"mirror_policy must be one of {POLICIES}")
    if policy in ("legacy", "none"):
        return None
    if policy == "mirror_left_from_right":
        return None if rendered_half(yaw) else mirror_of(yaw)
    src = (mirror_map or {}).get(str(view_index(yaw, n)) if n else label(yaw))
    if src is None:
        return None
    return views(n)[int(src)] if n and str(src).isdigit() else yaw_of(str(src))
