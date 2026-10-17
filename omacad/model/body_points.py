"""Points on a body that Move/Rotate can start from or go to.

- "end": the end of a straight edge (a box corner, where a straight piece meets a rounding ...).
- "corner": the sharp corner a rounding hides, where the straight edges on both sides would meet. For a
  rounding that runs on tangentially, that is where the tangents at the two ends of the arc cross, so
  it is found from the arc alone (like the guide lines of a rounded rectangle in a sketch).
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

SHARP_TURN_DEG = 30.0   # a loop vertex turning more than this is a real corner, not a step of a tessellated arc


@dataclass
class BodyPoint:
    xyz: np.ndarray
    kind: str                                   # "end" or "corner"
    guides: Tuple[np.ndarray, ...] = field(default_factory=tuple)   # corner: the arc ends the guide lines start at


def _arc_ends(e):
    u, v = e._basis()
    ends, tangents = [], []
    for a in (e.a0, e.a0 + e.sweep):
        ends.append(e.center + e.radius * (np.cos(a) * u + np.sin(a) * v))
        tangents.append(-np.sin(a) * u + np.cos(a) * v)
    return ends, tangents


def tangent_corner(p0, t0, p1, t1) -> Optional[np.ndarray]:
    """Where the line through p0 along t0 meets the line through p1 along t1 (None if they miss or are parallel)."""
    a = np.column_stack([t0, -t1])
    st, *_ = np.linalg.lstsq(a, p1 - p0, rcond=None)
    q0, q1 = p0 + st[0] * t0, p1 + st[1] * t1
    if np.linalg.norm(q0 - q1) > 1e-6 * max(1.0, float(np.linalg.norm(p1 - p0))):
        return None
    return (q0 + q1) / 2.0


def body_points(body) -> List[BodyPoint]:
    """Every snap point of a body (ends of straight edges, arc ends, and the corners roundings hide)."""
    out: List[BodyPoint] = []
    for e in body.edges:
        kind = getattr(e, "kind", "")
        if kind == "line":
            out += [BodyPoint(np.asarray(e.p0, float), "end"), BodyPoint(np.asarray(e.p1, float), "end")]
        elif kind == "circle" and e.is_arc:
            (p0, p1), (t0, t1) = _arc_ends(e)
            out += [BodyPoint(p0, "end"), BodyPoint(p1, "end")]
            if 1e-3 < e.sweep < np.pi - 1e-3:   # a rounding of a corner (a half circle has no corner)
                corner = tangent_corner(p0, t0, p1, t1)
                if corner is not None:
                    out.append(BodyPoint(corner, "corner", (p0, p1)))
        elif kind == "loop":
            pts = np.asarray(e.pts, float)
            d_in = pts - np.roll(pts, 1, axis=0)
            d_out = np.roll(pts, -1, axis=0) - pts
            cos = np.einsum("ij,ij->i", d_in, d_out) / np.maximum(
                np.linalg.norm(d_in, axis=1) * np.linalg.norm(d_out, axis=1), 1e-18)
            for i in np.flatnonzero(cos < np.cos(np.radians(SHARP_TURN_DEG))):
                out.append(BodyPoint(pts[i], "end"))
    return _unique(out)


def _unique(points: List[BodyPoint], tol: float = 1e-6) -> List[BodyPoint]:
    kept: List[BodyPoint] = []
    for p in points:
        same = next((k for k in kept if np.linalg.norm(k.xyz - p.xyz) < tol), None)
        if same is None:
            kept.append(p)
        elif p.kind == "corner" and same.kind != "corner":   # a corner wins: it carries its guide lines
            kept[kept.index(same)] = p
    return kept


def nearest_point(body, xyz, kind: Optional[str] = None) -> Optional[BodyPoint]:
    """The body's snap point closest to `xyz` (of the given kind): finds a picked point again after a rebuild."""
    xyz = np.asarray(xyz, float)
    pts = [p for p in body_points(body) if kind is None or p.kind == kind]
    return min(pts, key=lambda p: float(np.linalg.norm(p.xyz - xyz)), default=None)
