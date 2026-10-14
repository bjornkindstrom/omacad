"""
Omacad - 2D Sketch System
Represents sketch planes, 2D geometry primitives, and closed profile detection.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import math
import numpy as np
from omacad.model import quality
import shapely
from shapely.geometry import LineString, Polygon, Point, MultiPoint
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union, snap


def _dist_point_segment(pt, p1, p2) -> float:
    px, py = pt
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


@dataclass
class SketchPlane:
    """Represents a 2D plane in 3D space (XY, XZ, YZ or arbitrary)."""
    name: str = "XY"
    origin: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0], dtype=np.float32))
    u_axis: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v_axis: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0], dtype=np.float32))
    normal: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0], dtype=np.float32))

    @classmethod
    def create_named(cls, name: str) -> "SketchPlane":
        if name.upper() == "XY":
            return cls(
                name="XY",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
                normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            )
        elif name.upper() == "XZ":
            return cls(
                name="XZ",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
                normal=np.array([0.0, -1.0, 0.0], dtype=np.float32),
            )
        elif name.upper() == "YZ":
            return cls(
                name="YZ",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
                normal=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            )
        else:
            return cls()

    @classmethod
    def from_face(cls, normal: np.ndarray, point: np.ndarray, name: str = "FACE") -> "SketchPlane":
        """Plane on an arbitrary face. Origin = world origin projected onto the plane,
        u = world X (or Y when the normal is parallel to X) projected into the plane."""
        n = np.asarray(normal, dtype=np.float64)
        n = n / np.linalg.norm(n)
        hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = hint - np.dot(hint, n) * n
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        origin = n * float(np.dot(np.asarray(point, dtype=np.float64), n))
        f32 = lambda a: np.asarray(a, dtype=np.float32)
        return cls(name=name, origin=f32(origin), u_axis=f32(u), v_axis=f32(v), normal=f32(n))

    def centered_on(self, tris: np.ndarray) -> "SketchPlane":
        """Same plane with the origin moved to the middle of the given world triangles (a face), so
        (0, 0) is the face centre and the grid and the origin snap work from there."""
        pts = np.asarray(tris, dtype=np.float64).reshape(-1, 3) - np.asarray(self.origin, dtype=np.float64)
        u, v = pts @ np.asarray(self.u_axis, dtype=np.float64), pts @ np.asarray(self.v_axis, dtype=np.float64)
        c = self.uv_to_world((u.min() + u.max()) / 2, (v.min() + v.max()) / 2)
        return SketchPlane(name=self.name, origin=np.asarray(c, dtype=np.float32), u_axis=self.u_axis,
                           v_axis=self.v_axis, normal=self.normal)

    def uv_to_world(self, u: float, v: float) -> np.ndarray:
        """Convert local 2D (u, v) coordinates on the plane to 3D world (x, y, z)."""
        return self.origin + float(u) * self.u_axis + float(v) * self.v_axis

    def world_to_uv(self, world_pt: np.ndarray) -> Tuple[float, float]:
        """Project a 3D world point onto local (u, v) plane coordinates."""
        rel = world_pt - self.origin
        u = float(np.dot(rel, self.u_axis))
        v = float(np.dot(rel, self.v_axis))
        return u, v

    def get_transform_matrix_3x4(self) -> np.ndarray:
        """Returns 3x4 transform matrix [u | v | normal | origin] for Manifold3D."""
        return np.column_stack([self.u_axis, self.v_axis, self.normal, self.origin]).astype(float)


class SketchEntity:
    """Base class for 2D sketch elements."""
    def __init__(self, entity_id: str, entity_type: str, is_construction: bool = False):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.is_construction = is_construction
        self.group: Optional[str] = None   # elements built together (a polygon's sides and its centre circle)

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """Returns line segments as ((u1, v1), (u2, v2))."""
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchEntity":
        raise NotImplementedError


class SketchLine(SketchEntity):
    def __init__(self, entity_id: str, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="line", is_construction=is_construction)
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        return [(self.p1, self.p2)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "line",
            "p1": list(self.p1),
            "p2": list(self.p2),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchLine":
        return cls(
            entity_id=data["entity_id"],
            p1=tuple(data["p1"]),
            p2=tuple(data["p2"]),
            is_construction=data.get("is_construction", False),
        )


class SketchRect(SketchEntity):
    """2-point rectangle from corner1 to corner2."""

    def __init__(self, entity_id: str, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="rect", is_construction=is_construction)
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        x1, y1 = self.p1
        x2, y2 = self.p2
        c1 = (min(x1, x2), min(y1, y2))
        c2 = (max(x1, x2), min(y1, y2))
        c3 = (max(x1, x2), max(y1, y2))
        c4 = (min(x1, x2), max(y1, y2))
        return [(c1, c2), (c2, c3), (c3, c4), (c4, c1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "rect",
            "p1": list(self.p1),
            "p2": list(self.p2),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchRect":
        return cls(
            entity_id=data["entity_id"],
            p1=tuple(data["p1"]),
            p2=tuple(data["p2"]),
            is_construction=data.get("is_construction", False),
        )


class SketchCenterRect(SketchEntity):
    """Center rectangle defined by center point and one corner."""

    def __init__(self, entity_id: str, center: Tuple[float, float], corner: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="center_rect", is_construction=is_construction)
        self.center = (float(center[0]), float(center[1]))
        self.corner = (float(corner[0]), float(corner[1]))

    def get_corners(self) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
        cx, cy = self.center
        dx = abs(self.corner[0] - cx)
        dy = abs(self.corner[1] - cy)
        c1 = (cx - dx, cy - dy)
        c2 = (cx + dx, cy - dy)
        c3 = (cx + dx, cy + dy)
        c4 = (cx - dx, cy + dy)
        return c1, c2, c3, c4

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        c1, c2, c3, c4 = self.get_corners()
        return [(c1, c2), (c2, c3), (c3, c4), (c4, c1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "center_rect",
            "center": list(self.center),
            "corner": list(self.corner),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchCenterRect":
        return cls(
            entity_id=data["entity_id"],
            center=tuple(data["center"]),
            corner=tuple(data["corner"]),
            is_construction=data.get("is_construction", False),
        )


class SketchCircle(SketchEntity):
    def __init__(self, entity_id: str, center: Tuple[float, float], radius: float, is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="circle", is_construction=is_construction)
        self.center = (float(center[0]), float(center[1]))
        self.radius = float(radius)

    def to_lines(self, segments: Optional[int] = None) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_polygon_points(segments)
        lines = []
        for i in range(len(pts)):
            lines.append((pts[i], pts[(i + 1) % len(pts)]))
        return lines

    def get_polygon_points(self, segments: Optional[int] = None) -> List[Tuple[float, float]]:
        segments = segments or quality.circle_segments()
        cx, cy = self.center
        r = self.radius
        pts = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "circle",
            "center": list(self.center),
            "radius": self.radius,
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchCircle":
        return cls(
            entity_id=data["entity_id"],
            center=tuple(data["center"]),
            radius=data["radius"],
            is_construction=data.get("is_construction", False),
        )


class SketchArc(SketchEntity):
    """3-point circular arc: p_start, p_mid, p_end."""

    def __init__(
        self,
        entity_id: str,
        p_start: Tuple[float, float],
        p_mid: Tuple[float, float],
        p_end: Tuple[float, float],
        is_construction: bool = False
    ):
        super().__init__(entity_id=entity_id, entity_type="arc", is_construction=is_construction)
        self.p_start = (float(p_start[0]), float(p_start[1]))
        self.p_mid = (float(p_mid[0]), float(p_mid[1]))
        self.p_end = (float(p_end[0]), float(p_end[1]))

    def get_circle_params(self) -> Optional[Tuple[Tuple[float, float], float, float, float, bool]]:
        """Returns (center, radius, start_angle, end_angle, ccw) or None if collinear."""
        p1 = np.array(self.p_start)
        p2 = np.array(self.p_mid)
        p3 = np.array(self.p_end)

        d = 2 * (p1[0] * (p2[1] - p3[1]) + p2[0] * (p3[1] - p1[1]) + p3[0] * (p1[1] - p2[1]))
        if abs(d) < 1e-7:
            return None

        p1_sq = np.sum(p1**2)
        p2_sq = np.sum(p2**2)
        p3_sq = np.sum(p3**2)

        cx = (p1_sq * (p2[1] - p3[1]) + p2_sq * (p3[1] - p1[1]) + p3_sq * (p1[1] - p2[1])) / d
        cy = (p1_sq * (p3[0] - p2[0]) + p2_sq * (p1[0] - p3[0]) + p3_sq * (p2[0] - p1[0])) / d
        center = (float(cx), float(cy))
        r = float(math.hypot(p1[0] - cx, p1[1] - cy))

        a1 = math.atan2(p1[1] - cy, p1[0] - cx) % (2 * math.pi)
        a2 = math.atan2(p2[1] - cy, p2[0] - cx) % (2 * math.pi)
        a3 = math.atan2(p3[1] - cy, p3[0] - cx) % (2 * math.pi)

        sweep_12 = (a2 - a1) % (2 * math.pi)
        sweep_13 = (a3 - a1) % (2 * math.pi)

        ccw = (sweep_12 < sweep_13)
        return center, r, a1, a3, ccw

    def get_points(self, segments: Optional[int] = None) -> List[Tuple[float, float]]:
        params = self.get_circle_params()
        if not params:
            return [self.p_start, self.p_mid, self.p_end]

        center, r, a1, a3, ccw = params
        cx, cy = center
        if segments is None:
            segments = quality.arc_segments((a3 - a1) % (2 * math.pi) if ccw else (a1 - a3) % (2 * math.pi))

        if ccw:
            total_sweep = (a3 - a1) % (2 * math.pi)
            step = total_sweep / segments
        else:
            total_sweep = (a1 - a3) % (2 * math.pi)
            step = -total_sweep / segments

        pts = []
        for i in range(segments + 1):
            ang = a1 + i * step
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        if pts:
            pts[0] = self.p_start
            pts[-1] = self.p_end
        return pts

    def to_lines(self, segments: Optional[int] = None) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_points(segments)
        lines = []
        for i in range(len(pts) - 1):
            lines.append((pts[i], pts[i + 1]))
        return lines

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "entity_id": self.entity_id,
            "entity_type": "arc",
            "p_start": list(self.p_start),
            "p_mid": list(self.p_mid),
            "p_end": list(self.p_end),
            "is_construction": self.is_construction,
        }
        if hasattr(self, "fillet_info") and self.fillet_info:
            d["fillet_info"] = self.fillet_info
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchArc":
        arc = cls(
            entity_id=data["entity_id"],
            p_start=tuple(data["p_start"]),
            p_mid=tuple(data["p_mid"]),
            p_end=tuple(data["p_end"]),
            is_construction=data.get("is_construction", False),
        )
        if "fillet_info" in data:
            arc.fillet_info = data["fillet_info"]
        return arc


class SketchSlot(SketchEntity):
    """Center-to-center elongated slot / pill."""

    def __init__(
        self,
        entity_id: str,
        center1: Tuple[float, float],
        center2: Tuple[float, float],
        radius: float,
        is_construction: bool = False
    ):
        super().__init__(entity_id=entity_id, entity_type="slot", is_construction=is_construction)
        self.center1 = (float(center1[0]), float(center1[1]))
        self.center2 = (float(center2[0]), float(center2[1]))
        self.radius = float(radius)

    def get_polygon_points(self, arc_segments: int = 16) -> List[Tuple[float, float]]:
        c1x, c1y = self.center1
        c2x, c2y = self.center2
        dx = c2x - c1x
        dy = c2y - c1y
        length = math.hypot(dx, dy)
        r = self.radius

        if length < 1e-4:
            pts = []
            for i in range(arc_segments * 2):
                a = 2.0 * math.pi * i / (arc_segments * 2)
                pts.append((c1x + r * math.cos(a), c1y + r * math.sin(a)))
            return pts

        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux

        base_angle = math.atan2(uy, ux)

        pts = []
        pts.append((c1x + r * nx, c1y + r * ny))
        pts.append((c2x + r * nx, c2y + r * ny))

        for i in range(1, arc_segments):
            ang = base_angle + math.pi * 0.5 - math.pi * (i / arc_segments)
            pts.append((c2x + r * math.cos(ang), c2y + r * math.sin(ang)))

        pts.append((c2x - r * nx, c2y - r * ny))
        pts.append((c1x - r * nx, c1y - r * ny))

        for i in range(1, arc_segments):
            ang = base_angle - math.pi * 0.5 - math.pi * (i / arc_segments)
            pts.append((c1x + r * math.cos(ang), c1y + r * math.sin(ang)))

        return pts

    def to_lines(self, arc_segments: int = 16) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_polygon_points(arc_segments)
        lines = []
        for i in range(len(pts)):
            lines.append((pts[i], pts[(i + 1) % len(pts)]))
        return lines

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "slot",
            "center1": list(self.center1),
            "center2": list(self.center2),
            "radius": self.radius,
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchSlot":
        return cls(
            entity_id=data["entity_id"],
            center1=tuple(data["center1"]),
            center2=tuple(data["center2"]),
            radius=data["radius"],
            is_construction=data.get("is_construction", False),
        )


# PT_LINE_DIST point names meaning "the near/far edge of this circle" instead of a point
EDGE_PTS = ("edge_near", "edge_far")
SOLVER_DIM_TYPES = ("ANGLE", "DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST")


REF_PREFIX = "ref:"


def ref_id(seg) -> str:
    """Dimension reference to a fixed face edge, stored by its coordinates so it survives edge reordering."""
    (x1, y1), (x2, y2) = seg
    return f"{REF_PREFIX}{x1:.6f},{y1:.6f},{x2:.6f},{y2:.6f}"


def ref_segment(ref: str):
    """Inverse of ref_id: ((x1, y1), (x2, y2)) or None if `ref` is not an edge reference."""
    if not ref.startswith(REF_PREFIX):
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in ref[len(REF_PREFIX):].split(","))
    except ValueError:
        return None
    return (x1, y1), (x2, y2)


def point_of(ent, name: str):
    """A named point of an entity: line ends (p1, p2) or a circle centre."""
    if isinstance(ent, SketchLine):
        return ent.p1 if name == "p1" else ent.p2
    if isinstance(ent, SketchCircle) and name == "center":
        return ent.center
    return None


def arm_vector(line: "SketchLine", vertex_end: str):
    """Direction of a line pointing away from the end that sits at the angle's vertex."""
    a, b = (line.p1, line.p2) if vertex_end == "p1" else (line.p2, line.p1)
    return (b[0] - a[0], b[1] - a[1])


def arm_angle_deg(line_a: "SketchLine", end_a: str, line_b: "SketchLine", end_b: str) -> float:
    ax, ay = arm_vector(line_a, end_a)
    bx, by = arm_vector(line_b, end_b)
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    cosang = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
    return math.degrees(math.acos(cosang))


def nearest_ends_to_vertex(line_a: "SketchLine", line_b: "SketchLine"):
    """(end of A, end of B) that meet at, or are nearest to, the lines' common vertex."""
    best = None
    for ea in ("p1", "p2"):
        for eb in ("p1", "p2"):
            pa, pb = point_of(line_a, ea), point_of(line_b, eb)
            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if best is None or d < best[0]:
                best = (d, ea, eb)
    return best[1], best[2]


def _shift(pt, du, dv):
    return (pt[0] + du, pt[1] + dv)


def rotate_point(pt: Tuple[float, float], angle_deg: float, origin: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
    """Rotates a 2D point around an origin by angle_deg degrees."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    ox, oy = origin
    x, y = pt[0] - ox, pt[1] - oy
    return (ox + x * cos_a - y * sin_a, oy + x * sin_a + y * cos_a)


def move_entity(ent: "SketchEntity", du: float, dv: float) -> None:
    """Translates an entity in place."""
    if isinstance(ent, (SketchLine, SketchRect)):
        ent.p1, ent.p2 = _shift(ent.p1, du, dv), _shift(ent.p2, du, dv)
    elif isinstance(ent, SketchCenterRect):
        ent.center, ent.corner = _shift(ent.center, du, dv), _shift(ent.corner, du, dv)
    elif isinstance(ent, SketchCircle):
        ent.center = _shift(ent.center, du, dv)
    elif isinstance(ent, SketchArc):
        ent.p_start, ent.p_mid, ent.p_end = (_shift(ent.p_start, du, dv), _shift(ent.p_mid, du, dv),
                                             _shift(ent.p_end, du, dv))
    elif isinstance(ent, SketchSlot):
        ent.center1, ent.center2 = _shift(ent.center1, du, dv), _shift(ent.center2, du, dv)


def rotate_entity(ent: "SketchEntity", angle_deg: float, origin: Tuple[float, float]) -> None:
    """Rotates an entity in place around origin by angle_deg degrees."""
    if isinstance(ent, SketchLine):
        ent.p1 = rotate_point(ent.p1, angle_deg, origin)
        ent.p2 = rotate_point(ent.p2, angle_deg, origin)
    elif isinstance(ent, SketchRect):
        # Rotating an axis-aligned rect turns its corner coords; rotate both corners
        ent.p1 = rotate_point(ent.p1, angle_deg, origin)
        ent.p2 = rotate_point(ent.p2, angle_deg, origin)
    elif isinstance(ent, SketchCenterRect):
        ent.center = rotate_point(ent.center, angle_deg, origin)
        ent.corner = rotate_point(ent.corner, angle_deg, origin)
    elif isinstance(ent, SketchCircle):
        ent.center = rotate_point(ent.center, angle_deg, origin)
    elif isinstance(ent, SketchArc):
        ent.p_start = rotate_point(ent.p_start, angle_deg, origin)
        ent.p_mid = rotate_point(ent.p_mid, angle_deg, origin)
        ent.p_end = rotate_point(ent.p_end, angle_deg, origin)
    elif isinstance(ent, SketchSlot):
        ent.center1 = rotate_point(ent.center1, angle_deg, origin)
        ent.center2 = rotate_point(ent.center2, angle_deg, origin)


def entity_key_points(ent: "SketchEntity") -> List[Tuple[float, float]]:
    """Points on an entity that are worth snapping when it is dragged (ends, corners, centres)."""
    if isinstance(ent, SketchLine):
        return [ent.p1, ent.p2]
    if isinstance(ent, SketchRect):
        (x1, y1), (x2, y2) = ent.p1, ent.p2
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if isinstance(ent, SketchCenterRect):
        return list(ent.get_corners()) + [ent.center]
    if isinstance(ent, SketchCircle):
        return [ent.center]
    if isinstance(ent, SketchArc):
        return [ent.p_start, ent.p_end]
    if isinstance(ent, SketchSlot):
        return [ent.center1, ent.center2]
    return []


@dataclass
class SketchProfile:
    """A closed 2D profile bounded by sketch curves, ready for Extrude/Revolve."""
    profile_id: str
    exterior_pts: List[Tuple[float, float]]
    interior_holes: List[List[Tuple[float, float]]] = field(default_factory=list)
    area: float = 0.0

    def contains_point(self, u: float, v: float) -> bool:
        """Tests if a 2D point lies inside this profile."""
        try:
            poly = Polygon(self.exterior_pts, self.interior_holes)
            return poly.contains(Point(u, v))
        except Exception:
            return False


@dataclass
class SketchConstraint:
    """A geometric relation between sketch entities, enforced by the constraint solver.

    ctype: HORIZONTAL, VERTICAL, PARALLEL, PERPENDICULAR, EQUAL, TANGENT, CONCENTRIC,
           COINCIDENT (pts names the touching points), POINT_ON_CIRCLE (refs: circle, line; pts: the line's point), FIX
    """
    cid: str
    ctype: str
    refs: List[str]
    pts: List[str] = field(default_factory=list)  # point names for COINCIDENT ("p1", "p2", "center")

    def to_dict(self) -> Dict[str, Any]:
        return {"cid": self.cid, "ctype": self.ctype, "refs": list(self.refs), "pts": list(self.pts)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchConstraint":
        return cls(data["cid"], data["ctype"], list(data["refs"]), list(data.get("pts", [])))


@dataclass
class SketchDimension:
    """Represents a parametric dimensional constraint in 2D space."""
    dim_id: str
    name: str
    dim_type: str  # LENGTH, DIAMETER, RADIUS, ANGLE, DISTANCE, HORIZ_DIST, VERT_DIST, PT_LINE_DIST (+legacy RECT_*)
    target_entity_id: str
    value: float
    offset_distance: float = 12.0
    # Multi-entity dimensions: the other entity/entities and the point names involved.
    #   ANGLE:        target = line A, refs = [line B], pts = [end of A at the vertex, end of B at the vertex]
    #   *DIST:        target = entity A, refs = [entity B], pts = [point of A, point of B]
    #   PT_LINE_DIST: target = entity with the point, refs = [line], pts = [point name]
    refs: List[str] = field(default_factory=list)
    pts: List[str] = field(default_factory=list)
    # Formula the value comes from (e.g. "width/2"); None = a plain number. Re-evaluated whenever a
    # parameter changes.
    expr: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim_id": self.dim_id,
            "name": self.name,
            "dim_type": self.dim_type,
            "target_entity_id": self.target_entity_id,
            "value": float(self.value),
            "offset_distance": float(self.offset_distance),
            "refs": list(self.refs),
            "pts": list(self.pts),
            "expr": self.expr,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchDimension":
        return cls(
            dim_id=data["dim_id"],
            name=data.get("name", data["dim_id"]),
            dim_type=data["dim_type"],
            target_entity_id=data["target_entity_id"],
            value=float(data["value"]),
            offset_distance=float(data.get("offset_distance", 12.0)),
            refs=list(data.get("refs", [])),
            pts=list(data.get("pts", [])),
            expr=data.get("expr"),
        )


class Sketch:
    """A 2D parametric sketch container with entities, dimensions, and closed profile solver."""

    def __init__(self, sketch_id: str, name: str = "Sketch 1", plane: Optional[SketchPlane] = None):
        self.sketch_id = sketch_id
        self.name = name
        self.plane = plane or SketchPlane.create_named("XY")
        self.entities: List[SketchEntity] = []
        self.profiles: List[SketchProfile] = []
        self.dimensions: List[SketchDimension] = []
        self.constraints: List[SketchConstraint] = []
        self.dof: Optional[int] = None  # degrees of freedom from the last solve (None = unknown)
        # In-plane edges of existing bodies (face outlines). They close regions that the sketch
        # geometry alone leaves open, e.g. an arc whose ends sit on the edge of a face.
        self.reference_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self.visible: bool = True
        self.face_key = None  # set for sketches made from a body face, so the same face is not duplicated
        self.parent_body_id: Optional[str] = None  # body this sketch was drawn on, or None if independent

    def _new_entity_id(self, prefix: str) -> str:
        """Unique id even after entities were deleted."""
        used = {e.entity_id for e in self.entities}
        n = len(self.entities) + 1
        while f"{prefix}_{n}" in used:
            n += 1
        return f"{prefix}_{n}"

    def hit_test(self, u: float, v: float, tol: float) -> Optional[SketchEntity]:
        """Nearest entity whose outline passes within `tol` of (u, v)."""
        best, best_d = None, tol
        for ent in self.entities:
            for p1, p2 in ent.to_lines():
                d = _dist_point_segment((u, v), p1, p2)
                if d <= best_d:
                    best, best_d = ent, d
        return best

    def restore_from_dict(self, data: Dict[str, Any]) -> None:
        """Replaces entities/dimensions with a snapshot, keeping this object's identity
        (timeline features hold references to it)."""
        snap = Sketch.from_dict(data)
        self.entities = snap.entities
        self.dimensions = snap.dimensions
        self.constraints = snap.constraints
        self.solve_profiles()  # uses this sketch's own reference edges

    def connected_entities(self, entity_id: str, tol: float = 1e-6) -> set:
        """Entities joined to this one through coincident constraints or shared end points
        (e.g. all four lines of a rectangle)."""
        by_id = {e.entity_id: e for e in self.entities}
        links: Dict[str, set] = {eid: set() for eid in by_id}
        for c in self.constraints:
            if c.ctype == "COINCIDENT" and len(c.refs) == 2 and all(r in by_id for r in c.refs):
                links[c.refs[0]].add(c.refs[1])
                links[c.refs[1]].add(c.refs[0])
        ends = [(eid, pt) for eid, e in by_id.items() for pt in entity_key_points(e)]
        for i, (ea, pa) in enumerate(ends):
            for eb, pb in ends[i + 1:]:
                if ea != eb and abs(pa[0] - pb[0]) < tol and abs(pa[1] - pb[1]) < tol:
                    links[ea].add(eb)
                    links[eb].add(ea)
        seen, stack = {entity_id}, [entity_id]
        while stack:
            for nxt in links.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for eid in list(seen):   # a polygon's centre circle belongs with its sides
            seen |= {e.entity_id for e in self.group_entities(by_id[eid])}
        return seen

    def delete_entities(self, entity_ids) -> int:
        """Removes entities and the dimensions attached to them; re-solves profiles."""
        ids = set(entity_ids)
        before = len(self.entities)
        self.entities = [e for e in self.entities if e.entity_id not in ids]
        self.dimensions = [d for d in self.dimensions
                           if d.target_entity_id not in ids and not (set(d.refs) & ids)]
        self.constraints = [c for c in self.constraints if not (set(c.refs) & ids)]
        self.solve_profiles()
        return before - len(self.entities)

    def new_constraint_id(self) -> str:
        used = {c.cid for c in self.constraints}
        n = len(self.constraints) + 1
        while f"c{n}" in used:
            n += 1
        return f"c{n}"

    def get_entity(self, entity_id: str) -> Optional[SketchEntity]:
        for ent in self.entities:
            if ent.entity_id == entity_id:
                return ent
        return None

    def add_dimension(
        self,
        dim_type: str,
        target_entity_id: str,
        value: float,
        offset_distance: float = 12.0,
        name: str = "",
        refs: Optional[List[str]] = None,
        pts: Optional[List[str]] = None,
    ) -> SketchDimension:
        used = {d.dim_id for d in self.dimensions}
        d_idx = len(self.dimensions) + 1
        while f"d{d_idx}" in used:
            d_idx += 1
        dim_id = f"d{d_idx}"
        dim_name = name or f"Dim {d_idx}"
        dim = SketchDimension(
            dim_id=dim_id,
            name=dim_name,
            dim_type=dim_type,
            target_entity_id=target_entity_id,
            value=float(value),
            offset_distance=float(offset_distance),
            refs=list(refs or []),
            pts=list(pts or []),
        )
        self.dimensions.append(dim)
        return dim

    def set_dimension_value(self, dim_id: str, new_value: float) -> bool:
        """Parametrically updates a dimension and solves geometry and closed profiles."""
        target_dim = None
        for d in self.dimensions:
            if d.dim_id == dim_id:
                target_dim = d
                break

        if not target_dim or new_value <= 0.001:
            return False

        target_dim.value = float(new_value)
        ent = self.get_entity(target_dim.target_entity_id)
        if not ent:
            return False
        if target_dim.dim_type in SOLVER_DIM_TYPES:
            return True  # geometry follows from the constraint solver

        if target_dim.dim_type == "RECT_WIDTH":
            if isinstance(ent, SketchRect):
                sign = 1.0 if ent.p2[0] >= ent.p1[0] else -1.0
                ent.p2 = (ent.p1[0] + sign * target_dim.value, ent.p2[1])
            elif isinstance(ent, SketchCenterRect):
                sign = 1.0 if ent.corner[0] >= ent.center[0] else -1.0
                ent.corner = (ent.center[0] + sign * (target_dim.value * 0.5), ent.corner[1])
        elif target_dim.dim_type == "RECT_HEIGHT":
            if isinstance(ent, SketchRect):
                sign = 1.0 if ent.p2[1] >= ent.p1[1] else -1.0
                ent.p2 = (ent.p2[0], ent.p1[1] + sign * target_dim.value)
            elif isinstance(ent, SketchCenterRect):
                sign = 1.0 if ent.corner[1] >= ent.center[1] else -1.0
                ent.corner = (ent.corner[0], ent.center[1] + sign * (target_dim.value * 0.5))
        elif target_dim.dim_type == "LENGTH":
            if isinstance(ent, SketchLine):
                dx = ent.p2[0] - ent.p1[0]
                dy = ent.p2[1] - ent.p1[1]
                cur_len = math.hypot(dx, dy)
                if cur_len > 1e-6:
                    ux = dx / cur_len
                    uy = dy / cur_len
                    ent.p2 = (ent.p1[0] + ux * target_dim.value, ent.p1[1] + uy * target_dim.value)
            elif isinstance(ent, SketchSlot):
                dx = ent.center2[0] - ent.center1[0]
                dy = ent.center2[1] - ent.center1[1]
                cur_len = math.hypot(dx, dy)
                if cur_len > 1e-6:
                    ux = dx / cur_len
                    uy = dy / cur_len
                    ent.center2 = (ent.center1[0] + ux * target_dim.value, ent.center1[1] + uy * target_dim.value)
        elif target_dim.dim_type == "DIAMETER":
            if isinstance(ent, SketchCircle):
                ent.radius = target_dim.value / 2.0
            elif isinstance(ent, SketchSlot):
                ent.radius = target_dim.value / 2.0
        elif target_dim.dim_type == "RADIUS":
            if isinstance(ent, SketchCircle):
                ent.radius = target_dim.value
            elif isinstance(ent, SketchSlot):
                ent.radius = target_dim.value
            elif isinstance(ent, SketchArc):
                if getattr(ent, "fillet_info", None):
                    self._update_fillet_arc(ent, target_dim.value)
                else:
                    params = ent.get_circle_params()
                    if params and params[1] > 1e-5:
                        scale = target_dim.value / params[1]
                        cx, cy = params[0]
                        ent.p_start = (cx + (ent.p_start[0] - cx) * scale, cy + (ent.p_start[1] - cy) * scale)
                        ent.p_mid = (cx + (ent.p_mid[0] - cx) * scale, cy + (ent.p_mid[1] - cy) * scale)
                        ent.p_end = (cx + (ent.p_end[0] - cx) * scale, cy + (ent.p_end[1] - cy) * scale)

        self.solve_profiles()
        return True

    def add_line(self, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False) -> SketchLine:
        ent_id = self._new_entity_id("line")
        line = SketchLine(ent_id, p1, p2, is_construction=is_construction)
        self.entities.append(line)
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        self.add_dimension("LENGTH", ent_id, length, offset_distance=12.0, name="Length")
        self.solve_profiles()
        return line

    def offset_entities(self, ids, distance: float) -> list:
        """Parallel copies of the given elements, `distance` mm away: outward for closed shapes and circles
        (negative = inward), to the left of the drawing direction for open lines. Returns the new elements."""
        from shapely.geometry import LineString, Polygon
        from shapely.ops import linemerge
        ids = set(ids)
        new = []
        segs = []
        for ent in self.entities:
            if ent.entity_id not in ids or ent.is_construction:
                continue
            if isinstance(ent, SketchCircle):
                r = ent.radius + distance
                if r > 1e-6:
                    c = SketchCircle(self._new_entity_id("circle"), ent.center, r)
                    self.entities.append(c)
                    new.append(c)
            elif isinstance(ent, (SketchRect, SketchCenterRect, SketchSlot)):
                segs.extend(ent.to_lines())
        # lines and arcs: whole chains, radii follow along, joints are remade
        from omacad.model.sketch_offset import offset_entities_chains
        chain_in = [e for e in self.entities if e.entity_id in ids and not e.is_construction and isinstance(e, (SketchLine, SketchArc))]
        pieces, _ = offset_entities_chains(chain_in, distance)
        for seg in pieces:
            if seg.kind == "line":
                n = SketchLine(self._new_entity_id("line"), seg.p, seg.q)
            else:
                n = SketchArc(self._new_entity_id("arc"), seg.p, seg.mid(), seg.q)
            self.entities.append(n)
            new.append(n)
        if segs:
            merged = linemerge([LineString([a, b]) for a, b in segs])
            for geom in (merged.geoms if hasattr(merged, "geoms") else [merged]):
                coords = list(geom.coords)
                if geom.is_ring and len(coords) >= 4:
                    res = Polygon(coords).buffer(distance, join_style=2, mitre_limit=10.0)
                    outs = [res.exterior.coords] if not res.is_empty and res.geom_type == "Polygon" else []
                    if not res.is_empty and res.geom_type == "Polygon":
                        outs += [h.coords for h in res.interiors]
                    for ring in outs:
                        new.extend(self.add_loop(list(ring)[:-1], closed=True))
                else:
                    off = geom.offset_curve(distance, join_style=2, mitre_limit=10.0)
                    for part in (off.geoms if hasattr(off, "geoms") else [off]):
                        if not part.is_empty and len(part.coords) >= 2:
                            new.extend(self.add_loop(list(part.coords), closed=False))
        self.solve_profiles()
        return new

    def mirror_entities(self, ids, a, b) -> list:
        """Mirror copies of the given elements across the line through points a and b (the originals stay).
        Lines, circles, arcs and slots; the copies carry no dimensions or constraints."""
        ax, ay = a
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return []
        dx, dy = dx / L, dy / L

        def mp(q):
            wx, wy = q[0] - ax, q[1] - ay
            t = wx * dx + wy * dy
            fx, fy = ax + dx * t, ay + dy * t   # foot of the perpendicular
            return (2 * fx - q[0], 2 * fy - q[1])

        ids = set(ids)
        new = []
        for ent in list(self.entities):
            if ent.entity_id not in ids:
                continue
            c = ent.is_construction
            if isinstance(ent, SketchLine):
                n = SketchLine(self._new_entity_id("line"), mp(ent.p1), mp(ent.p2), is_construction=c)
            elif isinstance(ent, SketchCircle):
                n = SketchCircle(self._new_entity_id("circle"), mp(ent.center), ent.radius, is_construction=c)
            elif isinstance(ent, SketchArc):
                n = SketchArc(self._new_entity_id("arc"), mp(ent.p_start), mp(ent.p_mid), mp(ent.p_end), is_construction=c)
            elif isinstance(ent, SketchSlot):
                n = SketchSlot(self._new_entity_id("slot"), mp(ent.center1), mp(ent.center2), ent.radius, is_construction=c)
            else:
                continue
            self.entities.append(n)
            new.append(n)
        self.solve_profiles()
        return new

    def include_reference_edges(self, segments=None) -> list:
        """Fusion's Project / Include: the body edges lying in this sketch plane (the outline of the face the sketch is
        on) become real sketch elements - lines, full circles and arcs - that can be offset, trimmed, snapped to and
        drawn on like anything drawn here. They are marked `projected` (drawn in another colour, not draggable).
        Returns the new elements."""
        segs = [(tuple(a), tuple(b)) for a, b in (self.reference_segments if segments is None else segments)
                if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9]
        # ignore what is already here (included before, or drawn by hand on top of the edge)
        have = set()
        for e in self.entities:
            for a, b in e.to_lines():
                have.add((round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))
                have.add((round(b[0], 3), round(b[1], 3), round(a[0], 3), round(a[1], 3)))

        def key(p):
            return (round(p[0], 3), round(p[1], 3))

        adj: Dict[tuple, list] = {}
        for a, b in segs:
            adj.setdefault(key(a), []).append((b, a))
            adj.setdefault(key(b), []).append((a, b))
        pos = {key(p): p for ab in segs for p in ab}
        used = set()
        chains = []

        def walk(start, first):
            chain = [start]
            prev, cur = start, first
            while True:
                chain.append(cur)
                ks = (key(prev), key(cur))
                used.add(ks); used.add(ks[::-1])
                nxt = [q for q, _ in adj[key(cur)] if key(q) != key(prev) and (key(cur), key(q)) not in used]
                if len(adj[key(cur)]) != 2 or not nxt or key(cur) == key(start):
                    break
                prev, cur = cur, nxt[0]
            return chain

        for k0, nbrs in adj.items():          # chains start at junctions and free ends first, then closed loops
            if len(nbrs) != 2:
                for q, _ in nbrs:
                    if (k0, key(q)) not in used:
                        chains.append(walk(pos[k0], q))
        for k0, nbrs in adj.items():
            for q, _ in nbrs:
                if (k0, key(q)) not in used:
                    chains.append(walk(pos[k0], q))

        new = []

        def add(ent):
            ent.projected = True
            self.entities.append(ent)
            new.append(ent)

        for chain in chains:
            pts = np.array(chain, dtype=float)
            closed = key(chain[0]) == key(chain[-1])
            if len(pts) >= 6:                   # a curve? (many short pieces round one centre)
                body = pts[:-1] if closed else pts
                A = np.c_[2 * body[:, 0], 2 * body[:, 1], np.ones(len(body))]
                sol, *_ = np.linalg.lstsq(A, (body ** 2).sum(axis=1), rcond=None)
                c = sol[:2]
                r = float(np.sqrt(max(sol[2] + c @ c, 0.0)))
                res = np.abs(np.linalg.norm(body - c, axis=1) - r)
                if r > 1e-6 and float(res.max()) < max(2e-3 * r, 2e-3):
                    if closed:
                        if (round(c[0], 3), round(c[1], 3), round(r, 3)) not in {(round(e.center[0], 3), round(e.center[1], 3), round(e.radius, 3)) for e in self.entities if e.entity_type == "circle"}:
                            add(SketchCircle(self._new_entity_id("circle"), (float(c[0]), float(c[1])), r))
                    else:
                        mid = pts[len(pts) // 2]
                        add(SketchArc(self._new_entity_id("arc"), tuple(pts[0]), tuple(mid), tuple(pts[-1])))
                    continue
            # straight pieces: merge consecutive collinear segments
            run_start = pts[0]
            for i in range(1, len(pts)):
                last = i == len(pts) - 1
                if not last:
                    d1, d2 = pts[i] - pts[i - 1], pts[i + 1] - pts[i]
                    n1, n2 = np.linalg.norm(d1), np.linalg.norm(d2)
                    if n1 > 1e-12 and n2 > 1e-12 and abs(float(d1 @ d2) / (n1 * n2) - 1.0) < 1e-6:
                        continue
                a, b = tuple(run_start), tuple(pts[i])
                if (round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)) not in have and math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                    add(SketchLine(self._new_entity_id("line"), a, b))
                run_start = pts[i]
        self.solve_profiles()
        return new

    @staticmethod
    def polygon_points(center, vertex, sides: int):
        """Corners of a regular polygon: one corner at `vertex`, the others evenly round `center`."""
        cx, cy = center
        r = math.hypot(vertex[0] - cx, vertex[1] - cy)
        a0 = math.atan2(vertex[1] - cy, vertex[0] - cx)
        return [(cx + r * math.cos(a0 + 2 * math.pi * k / sides), cy + r * math.sin(a0 + 2 * math.pi * k / sides))
                for k in range(sides)]

    def add_polygon(self, center, vertex, sides: int, is_construction: bool = False) -> list:
        """A regular polygon (triangle, hexagon ...). It is built so it stays regular when dimensioned: its
        corners lie on a construction circle around the centre (so the centre can be measured from, as with a
        circle), the sides are equal and joined end to end."""
        n = max(3, int(sides))
        pts = self.polygon_points(center, vertex, n)
        gid = self._new_group_id()
        circle = SketchCircle(self._new_entity_id("circle"), center, math.hypot(vertex[0] - center[0], vertex[1] - center[1]),
                              is_construction=True)
        circle.group = gid
        self.entities.append(circle)
        lines = []
        for i, a in enumerate(pts):
            b = pts[(i + 1) % n]
            line = SketchLine(self._new_entity_id("line"), a, b, is_construction=is_construction)
            line.group = gid
            self.entities.append(line)
            lines.append(line)
        for i, ln in enumerate(lines):
            nxt = lines[(i + 1) % n]
            self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [ln.entity_id, nxt.entity_id], ["p2", "p1"]))
            self.constraints.append(SketchConstraint(self.new_constraint_id(), "POINT_ON_CIRCLE", [circle.entity_id, ln.entity_id], ["p1"]))
            if i:
                self.constraints.append(SketchConstraint(self.new_constraint_id(), "EQUAL", [lines[0].entity_id, ln.entity_id]))
        side = math.hypot(lines[0].p2[0] - lines[0].p1[0], lines[0].p2[1] - lines[0].p1[1])
        self.add_dimension("LENGTH", lines[0].entity_id, side, offset_distance=12.0, name="Side")
        self.solve_profiles()
        return lines

    def _new_group_id(self) -> str:
        used = {getattr(e, "group", None) for e in self.entities}
        n = 1
        while f"poly_{n}" in used:
            n += 1
        return f"poly_{n}"

    def group_entities(self, entity) -> list:
        """The other elements built together with this one (a polygon's sides and its centre circle)."""
        g = getattr(entity, "group", None)
        return [e for e in self.entities if g and getattr(e, "group", None) == g]

    def add_loop(self, points, closed: bool = True) -> List[SketchLine]:
        """A polyline as plain lines (no dimensions or constraints); used to turn a face outline into a sketch."""
        pts = [tuple(map(float, p)) for p in points]
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue
            line = SketchLine(self._new_entity_id("line"), a, b)
            self.entities.append(line)
            out.append(line)
        self.solve_profiles()
        return out

    def _add_rect_lines(self, c0, c1, c2, c3, is_construction: bool, width: float, height: float,
                        offset: float = 10.0) -> List[SketchLine]:
        """A rectangle is four lines held by Horizontal/Vertical/Coincident constraints plus
        a width and a height dimension - exactly what Fusion 360 creates."""
        corners = [c0, c1, c2, c3]
        lines = []
        for i in range(4):
            line = SketchLine(self._new_entity_id("line"), corners[i], corners[(i + 1) % 4],
                              is_construction=is_construction)
            self.entities.append(line)
            lines.append(line)
        ids = [ln.entity_id for ln in lines]
        for i, kind in enumerate(("HORIZONTAL", "VERTICAL", "HORIZONTAL", "VERTICAL")):
            self.constraints.append(SketchConstraint(self.new_constraint_id(), kind, [ids[i]]))
        for i in range(4):  # start of the next line meets the end of this one
            self.constraints.append(SketchConstraint(
                self.new_constraint_id(), "COINCIDENT", [ids[(i + 1) % 4], ids[i]], ["p1", "p2"]))
        self.add_dimension("LENGTH", ids[0], width, offset_distance=offset, name="Width")
        self.add_dimension("LENGTH", ids[1], height, offset_distance=offset, name="Height")
        self.solve_profiles()
        return lines

    def add_rect(self, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False) -> List[SketchLine]:
        (x1, y1), (x2, y2) = p1, p2
        return self._add_rect_lines((x1, y1), (x2, y1), (x2, y2), (x1, y2), is_construction,
                                    abs(x2 - x1), abs(y2 - y1))

    @staticmethod
    def corner_radius_limit(p1, p2, radius: float) -> float:
        """The radius a rounded rectangle can really have: just under half the shorter side."""
        return min(radius, 0.495 * min(abs(p2[0] - p1[0]), abs(p2[1] - p1[1])))

    @staticmethod
    def rounded_rect_outline(p1, p2, radius: float, steps: int = 8) -> List[Tuple[float, float]]:
        """Closed outline of a rounded rectangle as points (for the live preview)."""
        x0, x1 = sorted((p1[0], p2[0]))
        y0, y1 = sorted((p1[1], p2[1]))
        r = Sketch.corner_radius_limit(p1, p2, radius)
        if r <= 0.001:
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for k in range(steps + 1):
                a = math.radians(a0 + 90.0 * k / steps)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    def add_rounded_rect(self, p1: Tuple[float, float], p2: Tuple[float, float], radius: float,
                         is_construction: bool = False) -> List[SketchLine]:
        """A rectangle with all four corners filleted in one step. The radius is capped just under
        half the shorter side, so the straight pieces never vanish."""
        lines = self.add_rect(p1, p2, is_construction)
        r = self.corner_radius_limit(p1, p2, radius)
        if r > 0.001:
            for pt, la, lb, _ea, _eb in self.find_corners(lines):
                self.fillet_corner(la, lb, r, pt)
            self._outer_size_dimensions(lines)
        return lines

    def _outer_size_dimensions(self, lines) -> None:
        """After the corners are rounded the width/height dimensions of the straight pieces would measure the flats,
        not the part. Replace them by the overall width (left wall to right wall) and height (bottom to top wall),
        so the size can be changed with the corner radii and anything measured from the walls following along."""
        bottom, right, top, left = lines
        old = [d for d in self.dimensions if d.target_entity_id in (bottom.entity_id, right.entity_id) and d.dim_type == "LENGTH"]
        offsets = {d.target_entity_id: d.offset_distance for d in old}
        self.dimensions = [d for d in self.dimensions if not any(d is o for o in old)]
        self.add_dimension("HORIZ_DIST", left.entity_id, abs(right.p1[0] - left.p1[0]), offset_distance=offsets.get(bottom.entity_id, 10.0),
                           name="Width", refs=[right.entity_id], pts=["p1", "p1"])
        self.add_dimension("VERT_DIST", bottom.entity_id, abs(top.p1[1] - bottom.p1[1]), offset_distance=offsets.get(right.entity_id, 10.0),
                           name="Height", refs=[top.entity_id], pts=["p1", "p1"])

    def add_center_rect(self, center: Tuple[float, float], corner: Tuple[float, float], is_construction: bool = False) -> List[SketchLine]:
        cx, cy = center
        dx, dy = abs(corner[0] - cx), abs(corner[1] - cy)
        return self.add_rect((cx - dx, cy - dy), (cx + dx, cy + dy), is_construction)

    def add_center_rounded_rect(self, center: Tuple[float, float], corner: Tuple[float, float], radius: float,
                                is_construction: bool = False) -> List[SketchLine]:
        """A rounded rectangle drawn from its centre out to one corner."""
        cx, cy = center
        dx, dy = abs(corner[0] - cx), abs(corner[1] - cy)
        return self.add_rounded_rect((cx - dx, cy - dy), (cx + dx, cy + dy), radius, is_construction)

    def _migrate_legacy_rects(self) -> None:
        """Old files stored rectangles as one entity; turn them into lines + constraints."""
        legacy = [e for e in self.entities if isinstance(e, (SketchRect, SketchCenterRect))]
        for rect in legacy:
            if isinstance(rect, SketchRect):
                (x1, y1), (x2, y2) = rect.p1, rect.p2
                c0, c1, c2, c3 = (x1, y1), (x2, y1), (x2, y2), (x1, y2)
            else:
                c0, c1, c2, c3 = rect.get_corners()
            self.entities.remove(rect)
            self.dimensions = [d for d in self.dimensions if d.target_entity_id != rect.entity_id]
            width = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
            height = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
            self._add_rect_lines(c0, c1, c2, c3, rect.is_construction, width, height)

    def add_circle(self, center: Tuple[float, float], radius: float, is_construction: bool = False) -> SketchCircle:
        ent_id = self._new_entity_id("circle")
        circle = SketchCircle(ent_id, center, radius, is_construction=is_construction)
        self.entities.append(circle)
        self.add_dimension("DIAMETER", ent_id, radius * 2.0, offset_distance=12.0, name="Diameter")
        self.solve_profiles()
        return circle

    def add_arc(self, p_start: Tuple[float, float], p_mid: Tuple[float, float], p_end: Tuple[float, float], is_construction: bool = False) -> SketchArc:
        ent_id = self._new_entity_id("arc")
        arc = SketchArc(ent_id, p_start, p_mid, p_end, is_construction=is_construction)
        self.entities.append(arc)
        params = arc.get_circle_params()
        if params:
            self.add_dimension("RADIUS", ent_id, params[1], offset_distance=12.0, name="Radius")
        self.solve_profiles()
        return arc

    def add_slot(self, center1: Tuple[float, float], center2: Tuple[float, float], radius: float, is_construction: bool = False) -> SketchSlot:
        ent_id = self._new_entity_id("slot")
        slot = SketchSlot(ent_id, center1, center2, radius, is_construction=is_construction)
        self.entities.append(slot)
        length = math.hypot(center2[0] - center1[0], center2[1] - center1[1])
        self.add_dimension("LENGTH", ent_id, length, offset_distance=12.0, name="Length")
        self.add_dimension("DIAMETER", ent_id, radius * 2.0, offset_distance=10.0, name="Width")
        self.solve_profiles()
        return slot

    def _update_fillet_arc(self, arc: SketchArc, new_radius: float) -> bool:
        """Parametrically updates a fillet arc and its connected lines when the fillet dimension changes."""
        info = getattr(arc, "fillet_info", None)
        if not info or new_radius <= 0.001:
            return False
        line_a = self.get_entity(info.get("line_a"))
        line_b = self.get_entity(info.get("line_b"))
        V = info.get("corner")
        end_a = info.get("end_a")
        end_b = info.get("end_b")
        if not (isinstance(line_a, SketchLine) and isinstance(line_b, SketchLine) and V and end_a and end_b):
            return False

        Pa = line_a.p2 if end_a == "p1" else line_a.p1
        Pb = line_b.p2 if end_b == "p1" else line_b.p1

        va = np.array([Pa[0] - V[0], Pa[1] - V[1]], dtype=float)
        vb = np.array([Pb[0] - V[0], Pb[1] - V[1]], dtype=float)
        la, lb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if la < 1e-5 or lb < 1e-5:
            return False

        ua, ub = va / la, vb / lb
        cos_th = float(np.dot(ua, ub))
        if abs(cos_th) > 0.9999:
            return False

        half_ang = math.acos(max(-1.0, min(1.0, cos_th))) * 0.5
        tan_half = math.tan(half_ang)
        sin_half = math.sin(half_ang)

        d = new_radius / tan_half
        max_d = min(la, lb) * 0.995
        if d > max_d:
            return False

        Ta = tuple(np.array(V) + d * ua)
        Tb = tuple(np.array(V) + d * ub)

        bsum = ua + ub
        b = bsum / np.linalg.norm(bsum)
        C = np.array(V) + (new_radius / sin_half) * b
        M = tuple(C - new_radius * b)

        setattr(line_a, end_a, Ta)
        setattr(line_b, end_b, Tb)
        arc.p_start = Ta
        arc.p_mid = M
        arc.p_end = Tb

        # Update length dimensions on trimmed lines
        for line in (line_a, line_b):
            new_len = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
            for dim in self.dimensions:
                if dim.dim_type == "LENGTH" and dim.target_entity_id == line.entity_id:
                    dim.value = float(new_len)
        return True

    def refit_fillets(self) -> None:
        """Re-seats every fillet arc after the solver moved its lines (arcs are not solver entities):
        the corner becomes the intersection of the two lines, then the arc and the line ends are
        rebuilt there with the arc's own radius."""
        for arc in self.entities:
            info = getattr(arc, "fillet_info", None)
            params = arc.get_circle_params() if isinstance(arc, SketchArc) and info else None
            if not params:
                continue
            la, lb = self.get_entity(info.get("line_a")), self.get_entity(info.get("line_b"))
            if not (isinstance(la, SketchLine) and isinstance(lb, SketchLine)):
                continue
            da = (la.p2[0] - la.p1[0], la.p2[1] - la.p1[1])
            db = (lb.p2[0] - lb.p1[0], lb.p2[1] - lb.p1[1])
            den = da[0] * db[1] - da[1] * db[0]
            if abs(den) < 1e-9:
                continue
            t = ((lb.p1[0] - la.p1[0]) * db[1] - (lb.p1[1] - la.p1[1]) * db[0]) / den
            info["corner"] = (la.p1[0] + t * da[0], la.p1[1] + t * da[1])
            self._update_fillet_arc(arc, params[1])

    def find_corners(self, entities: Optional[List[SketchEntity]] = None) -> List[Tuple[Tuple[float, float], SketchLine, SketchLine, str, str]]:
        """Returns all corner vertices (point, line_a, line_b, end_a, end_b) where two non-collinear lines meet."""
        corners = []
        cands = [e for e in (entities or self.entities) if isinstance(e, SketchLine) and not e.is_construction]
        tol = 1e-3
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                la, lb = cands[i], cands[j]
                for ea, pa in (("p1", la.p1), ("p2", la.p2)):
                    for eb, pb in (("p1", lb.p1), ("p2", lb.p2)):
                        if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < tol:
                            other_a = la.p2 if ea == "p1" else la.p1
                            other_b = lb.p2 if eb == "p1" else lb.p1
                            va = (other_a[0] - pa[0], other_a[1] - pa[1])
                            vb = (other_b[0] - pb[0], other_b[1] - pb[1])
                            na, nb = math.hypot(*va), math.hypot(*vb)
                            if na > 1e-5 and nb > 1e-5:
                                cos_th = (va[0] * vb[0] + va[1] * vb[1]) / (na * nb)
                                if abs(cos_th) < 0.9999:
                                    corners.append((pa, la, lb, ea, eb))
                            break
        return corners

    def fillet_corner(self, line_a: SketchLine, line_b: SketchLine, radius: float,
                      corner_pt: Optional[Tuple[float, float]] = None) -> Tuple[Optional[SketchArc], str]:
        """Rounds the corner where line_a and line_b meet with a circular arc of given radius."""
        if radius <= 0.001:
            return None, "The radius must be larger than 0."

        tol = 1e-3
        end_a, end_b = None, None
        V = None

        if corner_pt is not None:
            best_d = 1e9
            for ea, pa in (("p1", line_a.p1), ("p2", line_a.p2)):
                for eb, pb in (("p1", line_b.p1), ("p2", line_b.p2)):
                    d_meeting = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if d_meeting < tol:
                        d_c = math.hypot(pa[0] - corner_pt[0], pa[1] - corner_pt[1])
                        if d_c < best_d:
                            best_d = d_c
                            end_a, end_b = ea, eb
                            V = pa
        if end_a is None:
            for ea, pa in (("p1", line_a.p1), ("p2", line_a.p2)):
                for eb, pb in (("p1", line_b.p1), ("p2", line_b.p2)):
                    if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < tol:
                        end_a, end_b = ea, eb
                        V = pa
                        break
                if end_a:
                    break

        if end_a is None or V is None:
            return None, "The lines do not meet in a common corner."

        Pa = line_a.p2 if end_a == "p1" else line_a.p1
        Pb = line_b.p2 if end_b == "p1" else line_b.p1

        va = np.array([Pa[0] - V[0], Pa[1] - V[1]], dtype=float)
        vb = np.array([Pb[0] - V[0], Pb[1] - V[1]], dtype=float)
        la, lb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if la < 1e-5 or lb < 1e-5:
            return None, "One of the lines is too short."

        ua, ub = va / la, vb / lb
        cos_th = float(np.dot(ua, ub))
        if abs(cos_th) > 0.9999:
            return None, "The lines are parallel or collinear."

        half_ang = math.acos(max(-1.0, min(1.0, cos_th))) * 0.5
        tan_half = math.tan(half_ang)
        sin_half = math.sin(half_ang)

        d = radius / tan_half
        max_d = min(la, lb) * 0.995
        if d > max_d:
            max_r = max_d * tan_half
            return None, f"The radius is too large for this corner (max {max_r:.1f} mm)."

        Ta = tuple(np.array(V) + d * ua)
        Tb = tuple(np.array(V) + d * ub)

        bsum = ua + ub
        b = bsum / np.linalg.norm(bsum)
        C = np.array(V) + (radius / sin_half) * b
        M = tuple(C - radius * b)

        # Trim lines
        setattr(line_a, end_a, Ta)
        setattr(line_b, end_b, Tb)

        # Remove coincident constraint between line_a and line_b at this corner
        self.constraints = [
            c for c in self.constraints
            if not (c.ctype == "COINCIDENT" and set(c.refs) == {line_a.entity_id, line_b.entity_id})
        ]

        # Update length dimensions on trimmed lines
        for line in (line_a, line_b):
            new_len = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
            for dim in self.dimensions:
                if dim.dim_type == "LENGTH" and dim.target_entity_id == line.entity_id:
                    dim.value = float(new_len)

        # Create fillet arc
        arc_id = self._new_entity_id("arc")
        arc = SketchArc(arc_id, Ta, M, Tb, is_construction=line_a.is_construction and line_b.is_construction)
        arc.fillet_info = {
            "line_a": line_a.entity_id,
            "line_b": line_b.entity_id,
            "corner": (float(V[0]), float(V[1])),
            "end_a": end_a,
            "end_b": end_b,
        }
        self.entities.append(arc)

        # Add coincident constraints to connect lines with arc endpoints
        self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [line_a.entity_id, arc.entity_id], [end_a, "p_start"]))
        self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [line_b.entity_id, arc.entity_id], [end_b, "p_end"]))

        # Add dimension for fillet radius
        self.add_dimension("RADIUS", arc_id, radius, offset_distance=12.0, name="Fillet")

        self.solve_profiles()
        return arc, "OK"

    def solve_profiles(self) -> List[SketchProfile]:
        """Finds all closed 2D loops and builds SketchProfile objects."""
        all_lines = []
        for ent in self.entities:
            if ent.is_construction:
                continue
            all_lines.extend(ent.to_lines())

        if not all_lines:
            self.profiles = []
            return self.profiles

        shapely_lines = []
        for p1, p2 in all_lines:
            # Avoid zero length lines
            if abs(p1[0] - p2[0]) > 1e-6 or abs(p1[1] - p2[1]) > 1e-6:
                shapely_lines.append(LineString([p1, p2]))

        if not shapely_lines:
            self.profiles = []
            return self.profiles

        try:
            sketch_union = unary_union(shapely.set_precision(shapely_lines, 1e-4))
            if self.reference_segments:
                ref_union = unary_union([LineString([a, b]) for a, b in self.reference_segments
                                         if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9])
                # Sketch end points that sit on a face edge are inserted into that edge (a tiny float
                # gap would otherwise leave the loop open), so the regions close.
                sketch_points = MultiPoint([c for g in getattr(sketch_union, "geoms", [sketch_union])
                                            for c in g.coords])
                merged = unary_union([sketch_union, snap(ref_union, sketch_points, 1e-3)])
                polys = []
                guard = sketch_union.buffer(2e-3)
                for poly in polygonize(merged):
                    # keep regions whose outline uses sketch geometry; the bare face itself is not a profile
                    if poly.exterior.intersection(guard).length > 5e-3:
                        polys.append(poly)
            else:
                polys = list(polygonize(sketch_union))

            # Also handle standalone circles and slots if not polygonized
            for ent in self.entities:
                if ent.is_construction:
                    continue
                if isinstance(ent, SketchCircle) and ent.radius > 1e-4:
                    circle_pts = ent.get_polygon_points()
                    circle_poly = Polygon(circle_pts)
                    if not any(p.contains(Point(ent.center)) for p in polys):
                        polys.append(circle_poly)
                elif isinstance(ent, SketchSlot) and ent.radius > 1e-4:
                    slot_pts = ent.get_polygon_points(16)
                    slot_poly = Polygon(slot_pts)
                    if not any(p.contains(Point(ent.center1)) for p in polys):
                        polys.append(slot_poly)

            profiles = []
            for idx, p in enumerate(polys):
                if p.is_valid and p.area > 1e-5:
                    p_ccw = orient(p, sign=1.0)
                    ext = list(p_ccw.exterior.coords)[:-1]
                    holes = [list(h.coords)[:-1] for h in p_ccw.interiors]
                    prof = SketchProfile(
                        profile_id=f"{self.sketch_id}_prof_{idx + 1}",
                        exterior_pts=ext,
                        interior_holes=holes,
                        area=p_ccw.area
                    )
                    profiles.append(prof)

            self.profiles = profiles
        except Exception:
            self.profiles = []

        return self.profiles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sketch_id": self.sketch_id,
            "name": self.name,
            "plane": {
                "name": self.plane.name,
                "origin": self.plane.origin.tolist(),
                "u_axis": self.plane.u_axis.tolist(),
                "v_axis": self.plane.v_axis.tolist(),
                "normal": self.plane.normal.tolist(),
            },
            "entities": [dict(e.to_dict(), **({"group": e.group} if getattr(e, "group", None) else {}),
                          **({"projected": True} if getattr(e, "projected", False) else {})) for e in self.entities],
            "dimensions": [d.to_dict() for d in self.dimensions],
            "constraints": [c.to_dict() for c in self.constraints],
            "face_key": list(self.face_key) if self.face_key else None,
            "parent_body_id": self.parent_body_id,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sketch":
        plane_data = data.get("plane", {})
        plane = SketchPlane(
            name=plane_data.get("name", "XY"),
            origin=np.array(plane_data.get("origin", [0, 0, 0]), dtype=np.float32),
            u_axis=np.array(plane_data.get("u_axis", [1, 0, 0]), dtype=np.float32),
            v_axis=np.array(plane_data.get("v_axis", [0, 1, 0]), dtype=np.float32),
            normal=np.array(plane_data.get("normal", [0, 0, 1]), dtype=np.float32),
        )
        sketch = cls(data["sketch_id"], name=data.get("name", "Sketch"), plane=plane)
        sketch.visible = data.get("visible", True)
        sketch.face_key = tuple(data["face_key"]) if data.get("face_key") else None
        sketch.parent_body_id = data.get("parent_body_id", None)

        groups = {ed.get("entity_id"): ed["group"] for ed in data.get("entities", []) if ed.get("group")}
        for ent_data in data.get("entities", []):
            t = ent_data.get("entity_type")
            if t == "line":
                sketch.entities.append(SketchLine.from_dict(ent_data))
            elif t == "rect":
                sketch.entities.append(SketchRect.from_dict(ent_data))
            elif t == "center_rect":
                sketch.entities.append(SketchCenterRect.from_dict(ent_data))
            elif t == "circle":
                sketch.entities.append(SketchCircle.from_dict(ent_data))
            elif t == "arc":
                sketch.entities.append(SketchArc.from_dict(ent_data))
            elif t == "slot":
                sketch.entities.append(SketchSlot.from_dict(ent_data))

        for dim_data in data.get("dimensions", []):
            sketch.dimensions.append(SketchDimension.from_dict(dim_data))
        for c_data in data.get("constraints", []):
            sketch.constraints.append(SketchConstraint.from_dict(c_data))

        projected = {ed.get("entity_id") for ed in data.get("entities", []) if ed.get("projected")}
        for e in sketch.entities:
            if e.entity_id in groups:
                e.group = groups[e.entity_id]
            if e.entity_id in projected:
                e.projected = True
        sketch._migrate_legacy_rects()
        sketch.solve_profiles()
        return sketch
