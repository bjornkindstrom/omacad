"""Measuring: what one or two picked sketch elements / body edges tell you (length, distance, angle ...).

Pure geometry, no Qt. Every function returns (lines_of_text, segments) where `segments` are the pairs of
points (2D or 3D, as given) to draw as the measuring line."""
import math
from typing import List, Tuple

import numpy as np


def _seg_closest(p0, p1, q0, q1):
    """Closest points between segments p0p1 and q0q1 (any dimension). Returns (a, b)."""
    p0, p1, q0, q1 = (np.asarray(v, dtype=float) for v in (p0, p1, q0, q1))
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    s = t = 0.0
    if a <= 1e-12 and e <= 1e-12:
        return p0, q0
    if a <= 1e-12:
        t = float(np.clip(f / e, 0, 1))
    else:
        c = d1 @ r
        if e <= 1e-12:
            s = float(np.clip(-c / a, 0, 1))
        else:
            b = d1 @ d2
            denom = a * e - b * b
            s = float(np.clip((b * f - c * e) / denom, 0, 1)) if denom > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, float(np.clip(-c / a, 0, 1))
            elif t > 1:
                t, s = 1.0, float(np.clip((b - c) / a, 0, 1))
    return p0 + d1 * s, q0 + d2 * t


def _line_line(p0, p1, q0, q1, label_len=True):
    p0, p1, q0, q1 = (np.asarray(v, dtype=float) for v in (p0, p1, q0, q1))
    d1, d2 = p1 - p0, q1 - q0
    n1, n2 = np.linalg.norm(d1), np.linalg.norm(d2)
    text: List[str] = []
    if n1 < 1e-9 or n2 < 1e-9:
        return ["Zero-length line"], []
    cosang = abs(float(d1 @ d2)) / (n1 * n2)
    ang = math.degrees(math.acos(min(1.0, cosang)))
    a, b = _seg_closest(p0, p1, q0, q1)
    dist = float(np.linalg.norm(a - b))
    if ang < 0.01:   # parallel: the perpendicular distance between them
        u = d1 / n1
        w = q0 - p0
        perp = w - (w @ u) * u
        text.append(f"Distance {np.linalg.norm(perp):.3f} mm (parallel)")
        mid = (q0 + q1) / 2.0
        foot = p0 + u * float((mid - p0) @ u)
        return text, [(foot, mid)]
    text.append(f"Angle {ang:.2f}°")
    text.append(f"Shortest distance {dist:.3f} mm" if dist > 1e-6 else "The lines cross")
    return text, ([(a, b)] if dist > 1e-6 else [])


def measure_2d(ents) -> Tuple[List[str], list]:
    """Sketch elements (SketchLine / SketchCircle / SketchArc), one or two."""
    kinds = [e.entity_type for e in ents]
    if len(ents) == 1:
        e = ents[0]
        if e.entity_type == "line":
            dx, dy = e.p2[0] - e.p1[0], e.p2[1] - e.p1[1]
            return [f"Length {math.hypot(dx, dy):.3f} mm", f"Direction {math.degrees(math.atan2(dy, dx)) % 180:.2f}°"], [(e.p1, e.p2)]
        if e.entity_type == "circle":
            r = e.radius
            return [f"Diameter {2 * r:.3f} mm", f"Radius {r:.3f} mm", f"Circumference {2 * math.pi * r:.3f} mm"], \
                   [((e.center[0] - r, e.center[1]), (e.center[0] + r, e.center[1]))]
        if e.entity_type == "arc":
            par = e.get_circle_params()
            if par:
                return [f"Radius {par[1]:.3f} mm"], []
        return ["Pick a line or a circle"], []
    a, b = ents[0], ents[1]
    if kinds == ["line", "line"]:
        return _line_line(a.p1, a.p2, b.p1, b.p2)
    circ = [e for e in ents if e.entity_type == "circle"]
    lines = [e for e in ents if e.entity_type == "line"]
    if len(circ) == 2:
        (c1, r1), (c2, r2) = (circ[0].center, circ[0].radius), (circ[1].center, circ[1].radius)
        d = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
        return [f"Centre to centre {d:.3f} mm", f"Between the edges {max(0.0, d - r1 - r2):.3f} mm" if d >= r1 + r2
                else "The circles overlap"], [(c1, c2)]
    if len(circ) == 1 and len(lines) == 1:
        c, r, ln = circ[0].center, circ[0].radius, lines[0]
        p0, p1 = np.array(ln.p1), np.array(ln.p2)
        d = p1 - p0
        t = float(np.clip((np.array(c) - p0) @ d / max(d @ d, 1e-12), 0, 1))
        foot = p0 + d * t
        dc = float(np.linalg.norm(foot - np.array(c)))
        return [f"Centre to the line {dc:.3f} mm", f"Edge of the circle to the line {max(0.0, dc - r):.3f} mm"], [(tuple(c), tuple(foot))]
    return ["Pick lines or circles to measure"], []


def measure_3d(edges) -> Tuple[List[str], list]:
    """Body edges (PlanarEdge / CircularEdge / LoopEdge), one or two."""
    if len(edges) == 1:
        e = edges[0]
        if e.kind == "line":
            return [f"Length {e.length:.3f} mm"], [(e.p0, e.p1)]
        if e.kind == "circle":
            return [f"Diameter {2 * e.radius:.3f} mm", f"Radius {e.radius:.3f} mm", f"Circumference {2 * math.pi * e.radius:.3f} mm"], []
        return [f"Outline length {e.perimeter:.3f} mm"], []
    a, b = edges
    if a.kind == "line" and b.kind == "line":
        return _line_line(a.p0, a.p1, b.p0, b.p1)
    ca = a.center if a.kind == "circle" else a.centroid
    cb = b.center if b.kind == "circle" else b.centroid
    d = float(np.linalg.norm(np.asarray(ca) - np.asarray(cb)))
    return [f"Centre to centre {d:.3f} mm"], [(np.asarray(ca), np.asarray(cb))]
