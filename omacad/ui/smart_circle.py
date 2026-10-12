"""Smart Circle: place a circle with numbers and Enter.

Step 1 type the diameter, step 2 type the distance from the centre to the nearest vertical line, step 3 the
distance to the nearest horizontal line. The mouse picks the line and the side; with nothing typed a step
just takes the mouse position. Pure logic, no Qt (the viewport draws it and creates the circle)."""
import math
from typing import List, Optional, Tuple

from omacad.model import expr

UV = Tuple[float, float]
# a guide line: (p1, p2, ref) where ref is a sketch line id or ("edge", p1, p2) for a face edge, so it can be dimensioned
Segment = Tuple[UV, UV, object]

SIZE, ACROSS, DOWN = 0, 1, 2
LABELS = {SIZE: "Diameter", ACROSS: "To vertical line", DOWN: "To horizontal line"}


def _seg_distance(p: UV, a: UV, b: UV) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def nearest_axis_line(segments: List[Segment], p: UV, vertical: bool) -> Optional[Segment]:
    """The vertical (or horizontal) straight line closest to p, or None."""
    best, best_d = None, 1e18
    for seg in segments:
        a, b, _ = seg
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-6:
            continue
        along, across = (abs(b[1] - a[1]), abs(b[0] - a[0])) if vertical else (abs(b[0] - a[0]), abs(b[1] - a[1]))
        if across > 1e-3 * length + 1e-9 or along < 0.99 * length:
            continue
        d = _seg_distance(p, a, b)
        if d < best_d:
            best, best_d = seg, d
    return best


class SmartCircle:
    def __init__(self):
        self.segments: List[Segment] = []
        self.reset()

    def reset(self):
        self.stage = SIZE
        self.text = ""
        self.mouse: Optional[UV] = None
        self.diameter: Optional[float] = None
        self.dimension = {}          # stage -> (segment, typed distance), kept for the dimensions of the circle
        self.fixed = {}              # stage -> coordinate locked by Enter / click

    # ---- typing -------------------------------------------------------------------
    def typed(self) -> Optional[float]:
        try:
            return expr.evaluate(self.text)
        except ValueError:
            return None

    def invalid(self) -> bool:
        return bool(self.text.strip()) and self.typed() is None

    # ---- geometry -----------------------------------------------------------------
    def guide(self) -> Optional[Segment]:
        if self.stage == SIZE or self.mouse is None:
            return None
        return nearest_axis_line(self.segments, self.mouse, vertical=(self.stage == ACROSS))

    def _resolve(self, stage: int) -> Optional[float]:
        """Centre coordinate for the vertical-line step (u) or the horizontal-line step (v) as it looks now."""
        if self.mouse is None:
            return None
        k = 0 if stage == ACROSS else 1
        d, g = self.typed(), self.guide() if stage == self.stage else None
        if d is None or g is None:
            return self.mouse[k]
        line_at = g[0][k]
        side = 1.0 if self.mouse[k] >= line_at else -1.0
        return line_at + side * d

    def centre(self) -> Optional[UV]:
        if self.mouse is None:
            return None
        u = self.fixed.get(ACROSS)
        v = self.fixed.get(DOWN)
        if u is None:
            u = self._resolve(ACROSS) if self.stage == ACROSS else self.mouse[0]
        if v is None:
            v = self._resolve(DOWN) if self.stage == DOWN else self.mouse[1]
        return (u, v)

    # ---- Enter / click ------------------------------------------------------------
    def accept(self) -> str:
        """Takes the current step. Returns "invalid", "need_size", "next" or "done"."""
        if self.invalid():
            return "invalid"
        if self.stage == SIZE:
            d = self.typed()
            if d is None or abs(d) < 1e-6:
                return "need_size"
            self.diameter = abs(d)
            self.stage, self.text = ACROSS, ""
            return "next"
        d, g = self.typed(), self.guide()
        if d is not None and g is None:
            return "no_line"
        coord = self._resolve(self.stage)
        if coord is None:
            return "invalid"
        self.fixed[self.stage] = coord
        if d is not None:
            self.dimension[self.stage] = (g, abs(d))
        if self.stage == ACROSS:
            self.stage, self.text = DOWN, ""
            return "next"
        return "done"

    def back(self) -> bool:
        """Backspace on an empty field: return to the previous step."""
        if self.text or self.stage == SIZE:
            return False
        self.stage -= 1
        self.fixed.pop(self.stage, None)
        self.dimension.pop(self.stage, None)
        if self.stage == SIZE:
            self.diameter = None
        return True
