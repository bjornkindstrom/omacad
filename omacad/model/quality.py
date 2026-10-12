"""How finely round shapes are cut into flat pieces (the 'Curve smoothness' setting). The model has no
Qt, so the settings manager pushes the value in here."""
import math

DEFAULT_SEGMENTS = 96
_segments = DEFAULT_SEGMENTS


def set_circle_segments(n: int) -> None:
    global _segments
    _segments = max(16, min(720, int(n)))


def circle_segments() -> int:
    """Flat pieces around a full circle."""
    return _segments


def arc_segments(sweep: float) -> int:
    """Pieces for an arc of `sweep` radians: the same fineness as a circle, never fewer than 32."""
    return max(32, round(_segments * abs(sweep) / (2.0 * math.pi)))


def sphere_segments() -> int:
    return max(36, _segments * 3 // 4)
