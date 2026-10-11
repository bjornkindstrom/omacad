"""
Omacad - Parametric Timeline & Feature History
Tracks the sequential history of modeling operations and enables parametric recomputation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from omacad.model.kernel import CadKernel, RenderMesh
from omacad.model.faces import PlanarFace, compute_planar_faces, PlanarEdge, compute_planar_edges, match_edge, edge_from_ref
from omacad.model.sketch import Sketch, SketchPlane


@dataclass
class Body:
    """Represents a 3D solid body in the document."""
    body_id: str
    name: str
    manifold: m3d.Manifold
    render_mesh: Optional[RenderMesh] = None
    color: List[float] = field(default_factory=lambda: [0.72, 0.77, 0.82, 1.0])  # Fusion 360 steel/aluminum
    visible: bool = True
    selected: bool = False
    faces: List[PlanarFace] = field(default_factory=list)
    edges: List[PlanarEdge] = field(default_factory=list)

    def update_render_mesh(self):
        self.render_mesh = CadKernel.extract_render_mesh(self.manifold)
        try:
            self.faces = compute_planar_faces(self.manifold, self.body_id)
        except Exception:
            self.faces = []
        try:
            self.edges = compute_planar_edges(self.manifold)
        except Exception:
            self.edges = []


def profile_cross_section(profile: Any) -> m3d.CrossSection:
    """Builds a Manifold CrossSection (with holes) from a SketchProfile."""
    poly = orient(Polygon(profile.exterior_pts, profile.interior_holes), sign=1.0)
    cs = m3d.CrossSection([list(poly.exterior.coords)[:-1]])
    for h in poly.interiors:
        ring = list(h.coords)[:-1]
        if Polygon(ring).exterior.is_ccw is False:   # a hole is stored clockwise; as a solid it must run counter-clockwise
            ring.reverse()
        cs = cs - m3d.CrossSection([ring])
    return cs


class Feature:
    """Base class for parametric history features."""
    def __init__(self, feature_id: str, feature_type: str, name: str):
        self.feature_id = feature_id
        self.feature_type = feature_type
        self.name = name
        self.suppressed: bool = False
        # field name -> formula, e.g. {"distance": "depth-2"}; evaluated when parameters change
        self.exprs: Dict[str, str] = {}

    def execute(self, doc: Any) -> None:
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError


class BoxFeature(Feature):
    def __init__(self, feature_id: str, name: str, length: float, width: float, height: float, center: bool = False):
        super().__init__(feature_id, "box", name)
        self.length = float(length)
        self.width = float(width)
        self.height = float(height)
        self.center = center

    def execute(self, doc: Any) -> None:
        solid = CadKernel.create_box(self.length, self.width, self.height, self.center)
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "center": self.center,
        }


class CylinderFeature(Feature):
    def __init__(self, feature_id: str, name: str, radius: float, height: float, center: bool = False):
        super().__init__(feature_id, "cylinder", name)
        self.radius = float(radius)
        self.height = float(height)
        self.center = center

    def execute(self, doc: Any) -> None:
        solid = CadKernel.create_cylinder(self.radius, self.height, center=self.center)
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "radius": self.radius,
            "height": self.height,
            "center": self.center,
        }


class SphereFeature(Feature):
    def __init__(self, feature_id: str, name: str, radius: float):
        super().__init__(feature_id, "sphere", name)
        self.radius = float(radius)

    def execute(self, doc: Any) -> None:
        solid = CadKernel.create_sphere(self.radius)
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "radius": self.radius,
        }


class SketchFeature(Feature):
    def __init__(self, feature_id: str, name: str, sketch: Sketch):
        super().__init__(feature_id, "sketch", name)
        self.sketch = sketch

    def execute(self, doc: Any) -> None:
        # Register sketch in doc; face outlines of the bodies built so far close its profiles
        doc.refresh_sketch_references(self.sketch)
        doc.sketches[self.sketch.sketch_id] = self.sketch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch": self.sketch.to_dict(),
        }


class ExtrudeFeature(Feature):
    """Linear extrusion of a sketch profile.

    direction: "one_side" (distance may be negative to flip), "symmetric"
    (distance is the total length, centered on the sketch plane) or
    "two_sides" (distance along the normal, distance2 against it).
    """

    def __init__(
        self,
        feature_id: str,
        name: str,
        sketch_id: str,
        profile_idx: int,
        distance: float,
        operation: str = "new_body",  # new_body, join, cut, intersect
        direction: str = "one_side",
        distance2: float = 0.0,
        extra_profiles=None,
    ):
        super().__init__(feature_id, "extrude", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.extra_profiles = [int(i) for i in (extra_profiles or [])]   # more profiles of the same sketch, extruded together
        self.distance = float(distance)
        self.operation = operation
        self.direction = direction
        self.distance2 = float(distance2)

    def _z_range(self):
        """Returns (z_min, z_max) of the extrusion in sketch-local coordinates."""
        d = self.distance
        if self.direction == "symmetric":
            h = abs(d) / 2.0
            return -h, h
        if self.direction == "two_sides":
            return -abs(self.distance2), abs(d)
        return (0.0, d) if d >= 0 else (d, 0.0)

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if not sketch or self.profile_idx >= len(sketch.profiles):
            return None
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        cs = profile_cross_section(sketch.profiles[idxs[0]])
        for i in idxs[1:]:
            cs = cs + profile_cross_section(sketch.profiles[i])

        z0, z1 = self._z_range()
        height = z1 - z0
        if height < 1e-6:
            return None

        solid = m3d.Manifold.extrude(cs, height=float(height))
        if abs(z0) > 1e-9:
            solid = solid.translate((0.0, 0.0, float(z0)))
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        return solid if not solid.is_empty() else None

    def resolve_operation(self, doc: Any) -> str:
        """The 'Auto' choice. Into material -> cut; sitting on a body's face and going outward ->
        join; otherwise a new body."""
        tool = self.build_solid(doc)
        if tool is None:
            return "new_body"
        for body in doc.bodies.values():
            if not self._bbox_overlap(body.manifold, tool):
                continue
            inter = body.manifold ^ tool
            if not inter.is_empty() and inter.volume() > 1e-6:
                return "cut"
        sketch = doc.sketches.get(self.sketch_id)
        if sketch is not None and self.profile_idx < len(sketch.profiles):
            from shapely.ops import unary_union
            plane = sketch.plane
            n0 = np.asarray(plane.normal, dtype=float)
            o0 = np.asarray(plane.origin, dtype=float)
            ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
            region = unary_union([Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes)
                                  for i in [self.profile_idx] + [j for j in self.extra_profiles if j < len(sketch.profiles)]])
            for body in doc.bodies.values():
                for face in body.faces:
                    if abs(float(np.dot(face.normal, n0))) < 0.999 or abs(float(np.dot(face.origin - o0, n0))) > 1e-3:
                        continue  # not a face in the sketch plane
                    tris = [Polygon([(float(v @ ua), float(v @ va)) for v in tri]) for tri in face.tris]
                    if region.intersection(unary_union([t for t in tris if t.is_valid and t.area > 0])).area > 1e-6:
                        return "join"
        return "new_body"

    @staticmethod
    def _bbox_overlap(a: m3d.Manifold, b: m3d.Manifold, tol: float = 1e-6) -> bool:
        a0, a1 = np.array(a.bounding_box()[:3]), np.array(a.bounding_box()[3:])
        b0, b1 = np.array(b.bounding_box()[:3]), np.array(b.bounding_box()[3:])
        return bool(np.all(a0 <= b1 + tol) and np.all(b0 <= a1 + tol))

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        if self.operation == "auto":
            self.operation = self.resolve_operation(doc)  # decided once, then stored like any other choice

        def new_body():
            body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=tool)
            body.update_render_mesh()
            doc.bodies[body.body_id] = body

        if self.operation == "new_body":
            new_body()
            return

        # Combine operations act on every body the extrusion actually touches
        targets = [
            b for b in doc.bodies.values()
            if self._bbox_overlap(b.manifold, tool)
            and (self.operation == "join" or not (b.manifold ^ tool).is_empty())
        ]

        if self.operation == "join":
            if not targets:
                new_body()
                return
            merged = targets[0].manifold
            for other in targets[1:]:
                merged = merged + other.manifold
                doc.bodies.pop(other.body_id, None)
            targets[0].manifold = merged + tool
            targets[0].update_render_mesh()
            return

        for body in targets:
            if self.operation == "cut":
                result = body.manifold - tool
            elif self.operation == "intersect":
                result = body.manifold ^ tool
            else:
                continue
            if result.is_empty():
                doc.bodies.pop(body.body_id, None)
            else:
                body.manifold = result
                body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch_id": self.sketch_id,
            "profile_idx": self.profile_idx,
            "extra_profiles": list(self.extra_profiles),
            "distance": self.distance,
            "operation": self.operation,
            "direction": self.direction,
            "distance2": self.distance2,
        }


class FilletFeature(Feature):
    """Rounds (fillet) or bevels (chamfer) straight edges. Works on outside and inside corners.

    Edges are remembered by their end points and found again on rebuild, so the step survives
    changes elsewhere as long as the edge is still there."""

    def __init__(self, feature_id: str, name: str, edges, size: float, kind: str = "fillet"):
        super().__init__(feature_id, "fillet", name)
        # each entry: ((x,y,z),(x,y,z)) for a straight edge, or ("circle", centre, axis, radius)
        self.edges = [self._norm_ref(e) for e in edges]
        self.size = float(size)
        self.kind = kind  # "fillet" or "chamfer"
        self.skipped = 0  # edges that could not be found/applied in the last rebuild

    @staticmethod
    def _norm_ref(e):
        if e and e[0] == "circle":
            return ("circle", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]))
        if e and e[0] == "loop":
            return ("loop", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]))
        return (tuple(map(float, e[0])), tuple(map(float, e[1])))

    def execute(self, doc: Any) -> None:
        """All edges are matched against the body as it is *before* this step and the tools are applied
        together; rounding them one after another would hide the neighbouring edges (the first
        rounding turns the faces next to it into curved ones)."""
        self.skipped = 0
        if self.size <= 1e-6:
            return
        cut, add = {}, {}
        seen = []
        for ref in self.edges:
            hit = None
            for body in doc.bodies.values():
                edge = edge_from_ref(ref, body.edges)
                if edge is not None:
                    hit = (body, edge)
                    break
            if hit is None:
                self.skipped += 1
                continue
            body, edge = hit
            if any(body is b and edge.same_as(e) for b, e in seen):
                continue  # the same edge selected twice
            seen.append((body, edge))
            tool = CadKernel.round_tool(edge, self.size, self.kind, extend=1e-3 if edge.convex else 0.0)
            (cut if edge.convex else add).setdefault(body.body_id, []).append(tool)

        for body_id in set(cut) | set(add):
            body = doc.bodies.get(body_id)
            if body is None:
                continue
            try:
                result = body.manifold
                if cut.get(body_id):
                    combined = cut[body_id][0]
                    for t in cut[body_id][1:]:
                        combined = combined + t
                    result = result - combined
                for t in add.get(body_id, []):
                    result = result + t
            except Exception:
                self.skipped += len(cut.get(body_id, [])) + len(add.get(body_id, []))
                continue
            if not result.is_empty():
                body.manifold = CadKernel.drop_slivers(result)
                body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "edges": [list(e) if isinstance(e[0], str) else [list(e[0]), list(e[1])] for e in self.edges],
            "size": self.size,
            "kind": self.kind,
        }


class PatternFeature(Feature):
    """Copies what some earlier steps did to a body (a hole and its chamfers, a boss ...) to other places:
    evenly spaced (linear), mirrored around the body (e.g. one corner hole -> all four corners) or around
    an axis (circular). The copies are the difference between the body before and after those steps, so
    anything they changed is copied, chamfers and fillets included."""

    AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

    def __init__(self, feature_id: str, name: str, source_ids, kind: str = "linear", **params):
        super().__init__(feature_id, "pattern", name)
        self.source_ids = list(source_ids)
        self.kind = kind                    # "linear", "mirror", "circular", "fill" (gap = spacing1, margin = spacing2, layout in mirror_mode)
        self.axis1, self.count1, self.spacing1 = params.get("axis1", "x"), float(params.get("count1", 2)), float(params.get("spacing1", 20.0))
        self.axis2, self.count2, self.spacing2 = params.get("axis2", "y"), float(params.get("count2", 1)), float(params.get("spacing2", 20.0))
        self.mirror_mode = params.get("mirror_mode", "auto")   # auto, x, y, xy
        self.about = params.get("about", "body")                # body (its centre) or origin
        self.angle = float(params.get("angle", 360.0))
        self.copies = 0

    # ---- the copies ----------------------------------------------------------------------
    def _transforms(self, centre, feature_centre, size):
        """Functions turning the changed region into each copy."""
        c = np.array(centre, dtype=float)
        out = []

        def mirror(vec):
            return lambda m: m.translate(tuple(-c)).mirror(vec).translate(tuple(c))

        if self.kind == "linear":
            d1, d2 = self.AXES.get(self.axis1, self.AXES["x"]), self.AXES.get(self.axis2, self.AXES["y"])
            for i in range(max(1, int(round(self.count1)))):
                for j in range(max(1, int(round(self.count2)))):
                    if i == 0 and j == 0:
                        continue
                    off = tuple(i * self.spacing1 * np.array(d1) + j * self.spacing2 * np.array(d2))
                    out.append(lambda m, off=off: m.translate(off))
        elif self.kind == "mirror" and self.mirror_mode.startswith("plane:"):
            pl = getattr(self, "_mirror_plane", None)   # (point, unit normal), resolved in compute()
            if pl is not None:
                p0, nrm = np.array(pl[0], dtype=float), tuple(pl[1])
                out.append(lambda m: m.translate(tuple(-p0)).mirror(nrm).translate(tuple(p0)))
        elif self.kind == "mirror":
            mode = self.mirror_mode
            if mode == "auto" and getattr(self, "_round_body", False):
                mode = "diameter"   # a round body has no corners: the copy goes to the other end of the diameter
            if mode == "diameter":   # evenly spaced around the round body; 2 = the other end of the diameter
                n = max(2, int(round(self.count1)))
                for k in range(1, n):
                    deg = 360.0 * k / n
                    out.append(lambda m, deg=deg: m.translate(tuple(-c)).rotate((0.0, 0.0, deg)).translate(tuple(c)))
            elif mode == "auto":  # mirror across each mid-plane the feature is off-centre in
                ax = abs(feature_centre[0] - c[0]) > 0.02 * size[0] + 1e-6
                ay = abs(feature_centre[1] - c[1]) > 0.02 * size[1] + 1e-6
                mode = "xy" if ax and ay else "x" if ax else "y" if ay else ""
            mx, my = mirror((1.0, 0.0, 0.0)), mirror((0.0, 1.0, 0.0))
            if "x" in mode:
                out.append(mx)
            if "y" in mode:
                out.append(my)
            if mode == "xy":
                out.append(lambda m: my(mx(m)))
        elif self.kind == "circular":
            n = max(2, int(round(self.count1)))
            step = self.angle / n if abs(self.angle - 360.0) < 1e-6 else self.angle / (n - 1)
            for k in range(1, n):
                deg = k * step
                out.append(lambda m, deg=deg: m.translate(tuple(-c)).rotate((0.0, 0.0, deg)).translate(tuple(c)))
        return out

    def _source_plane(self, doc):
        for f in doc.timeline.features:
            if f.feature_id in self.source_ids:
                sk = getattr(f, "sketch", None) or doc.sketches.get(getattr(f, "sketch_id", None))
                if sk is not None:
                    return sk.plane
        return None

    @staticmethod
    def _room_prism(clip, before):
        """The allowed region of the face as a tall prism (through the whole body) in world space."""
        room, o, ua, va, n = clip
        from shapely.geometry import Polygon
        from shapely.geometry.polygon import orient
        bb = before.bounding_box()
        h = 2.0 * float(np.max(np.array(bb[3:]) - np.array(bb[:3]))) + 10.0
        cs = None
        for poly in (room.geoms if hasattr(room, "geoms") else [room]):
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            poly = orient(poly, sign=1.0)
            part = m3d.CrossSection([list(poly.exterior.coords)[:-1]])
            for hole in poly.interiors:
                ring = list(hole.coords)[:-1]
                if Polygon(ring).exterior.is_ccw is False:
                    ring.reverse()
                part = part - m3d.CrossSection([ring])
            cs = part if cs is None else cs + part
        if cs is None:
            return None
        mat = np.column_stack([ua, va, n, o]).astype(float)
        return m3d.Manifold.extrude(cs, height=h).translate((0, 0, -h / 2.0)).transform(mat)

    def _fill_funcs(self, doc, before, removed, added, now=None, other_bodies=None):
        """Fill the flat face the source sketch is on: copies on a lattice that keeps exactly `gap` mm between
        neighbours (measured edge to edge, so hexagons, circles and triangles all pack right), staying
        `margin` mm inside the face. Avoids anything standing on or connected to the surface (bosses,
        walls, cylinders, separate bodies) across all regions of the face."""
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        from shapely import affinity
        from omacad.model.faces import compute_planar_faces
        plane = self._source_plane(doc)
        if plane is None:
            return []
        gap, margin = max(self.spacing1, 0.0), max(self.spacing2, 0.0)
        o = np.asarray(plane.origin, dtype=float)
        n = np.asarray(plane.normal, dtype=float)
        ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
        inv = np.linalg.inv(np.vstack([plane.get_transform_matrix_3x4(), [0, 0, 0, 1]]))[:3]
        # the footprint of what the steps changed, seen along the plane's normal
        shapes = []
        for m in (removed, added):
            if not m.is_empty():
                for ring in m.transform(inv).project().to_polygons():
                    if len(ring) >= 3:
                        shapes.append(Polygon(ring).buffer(0))
        shapes = [sh for sh in shapes if not sh.is_empty]
        if not shapes:
            return []
        foot = unary_union(shapes)
        c0 = foot.representative_point()

        # 1. Obstacles: any protrusion, boss, rib, cylinder, sphere or separate body connected to or
        # standing on the face (material above z = 0.05 in plane space).
        now_bodies = ([now] if now is not None and not now.is_empty() else []) + [b for b in (other_bodies or []) if not b.is_empty()]
        obs_polys = []
        for b in now_bodies:
            m_plane = b.transform(inv)
            above = m_plane.trim_by_plane([0.0, 0.0, 1.0], 0.05)
            if not above.is_empty():
                for ring in above.project().to_polygons():
                    if len(ring) >= 3:
                        p = Polygon(ring).buffer(0)
                        if p.is_valid and p.area > 1e-6:
                            obs_polys.append(p)
        # Exclude the original feature's own spot so it isn't treated as an obstacle to itself
        all_obs = unary_union(obs_polys).difference(foot.buffer(0.02)) if obs_polys else Polygon()

        # 2. The flat face in that plane (coplanar triangles at z = 0)
        regions = []
        for face in compute_planar_faces(now if now is not None else before):
            if abs(abs(float(face.normal @ n)) - 1.0) > 1e-3 or abs(float((face.origin - o) @ n)) > 1e-3:
                continue
            for tri in face.tris:
                pg = Polygon([(float(v @ ua), float(v @ va)) for v in tri])
                if pg.is_valid and pg.area > 1e-9:
                    regions.append(pg)
        if not regions:
            return []
        raw_face = unary_union(regions + [foot.buffer(1e-4)])
        if all_obs and not all_obs.is_empty:
            raw_face = raw_face.difference(all_obs)
        parts = [p for p in (raw_face.geoms if hasattr(raw_face, "geoms") else [raw_face]) if p.area > 1e-6]
        if not parts:
            return []
        face_poly = unary_union(parts)
        room = face_poly.buffer(-margin) if margin > 0 else face_poly
        if room.is_empty:
            return []
        minx, miny, maxx, maxy = foot.bounds
        bw, bh = maxx - minx, maxy - miny

        # Check if shape is an equilateral triangle for triangular alternating tiling
        tri_info = None
        if self.mirror_mode in ("stagger", "triangular"):
            coords = list(foot.exterior.coords)[:-1] if hasattr(foot, "exterior") else []
            if len(coords) == 3:
                p0, p1, p2 = np.array(coords[0]), np.array(coords[1]), np.array(coords[2])
                d01, d12, d20 = np.linalg.norm(p1 - p0), np.linalg.norm(p2 - p1), np.linalg.norm(p0 - p2)
                s_tri = float((d01 + d12 + d20) / 3.0)
                if s_tri > 1e-4 and max(abs(d01 - s_tri), abs(d12 - s_tri), abs(d20 - s_tri)) < 0.08 * s_tri:
                    c_tri = (p0 + p1 + p2) / 3.0
                    v0 = p0 - c_tri
                    if np.linalg.norm(v0) > 1e-5:
                        a0 = float(np.arctan2(v0[1], v0[0]))
                        tri_info = (s_tri, c_tri, a0)

        funcs = []
        min_frac = max(0.0, min(100.0, float(self.count1))) / 100.0
        self._fill_clip = (room, o, ua, va, n) if min_frac > 0 else None
        foot_area = max(foot.area, 1e-9)
        from shapely.prepared import prep
        prepared = prep(room)

        if tri_info is not None:
            s_tri, c_tri, a0 = tri_info
            u_edge = np.array([-np.sin(a0), np.cos(a0)])
            v_edge = np.array([np.cos(a0), np.sin(a0)])
            dx = s_tri + np.sqrt(3) * gap
            dy = dx * np.sqrt(3) / 2.0
            v1 = dx * u_edge
            v2 = (dx / 2.0) * u_edge + dy * v_edge
            v_inv = (dx / 2.0) * u_edge + (dx / (2.0 * np.sqrt(3))) * v_edge

            M = np.eye(4)
            M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = ua, va, n, o
            M_inv = np.linalg.inv(M)

            foot_inv = affinity.rotate(foot, 180, origin=tuple(c_tri))
            rx0, ry0, rx1, ry1 = room.bounds
            reach_x = max(abs(rx1 - c0.x), abs(rx0 - c0.x)) + bw
            reach_y = max(abs(ry1 - c0.y), abs(ry0 - c0.y)) + bh
            step_sz = max(min(dx, dy), 1e-3)
            imax = int(reach_x / step_sz) + 2
            jmax = int(reach_y / step_sz) + 2

            for j in range(-jmax, jmax + 1):
                for i in range(-imax, imax + 1):
                    # 1. Upright candidate
                    p_up = i * v1 + j * v2
                    if not (i == 0 and j == 0):
                        m_up = affinity.translate(foot, *p_up)
                        if min_frac > 0:
                            if prepared.intersects(m_up) and m_up.intersection(room).area >= min_frac * foot_area:
                                vec = tuple(ua * p_up[0] + va * p_up[1])
                                funcs.append(lambda m, vec=vec: m.translate(vec))
                        elif prepared.contains(m_up):
                            vec = tuple(ua * p_up[0] + va * p_up[1])
                            funcs.append(lambda m, vec=vec: m.translate(vec))

                    # 2. Inverted candidate
                    p_inv = i * v1 + j * v2 + v_inv
                    m_inv = affinity.translate(foot_inv, *p_inv)
                    if min_frac > 0:
                        if prepared.intersects(m_inv) and m_inv.intersection(room).area >= min_frac * foot_area:
                            T_plane = np.eye(4)
                            T_plane[0, 0] = -1.0; T_plane[1, 1] = -1.0
                            T_plane[0, 3] = 2.0 * c_tri[0] + p_inv[0]
                            T_plane[1, 3] = 2.0 * c_tri[1] + p_inv[1]
                            T_world = (M @ T_plane @ M_inv)[:3]
                            funcs.append(lambda m, mat=T_world: m.transform(mat))
                    elif prepared.contains(m_inv):
                        T_plane = np.eye(4)
                        T_plane[0, 0] = -1.0; T_plane[1, 1] = -1.0
                        T_plane[0, 3] = 2.0 * c_tri[0] + p_inv[0]
                        T_plane[1, 3] = 2.0 * c_tri[1] + p_inv[1]
                        T_world = (M @ T_plane @ M_inv)[:3]
                        funcs.append(lambda m, mat=T_world: m.transform(mat))

                    if len(funcs) >= 1500:
                        return funcs
            return funcs

        def clear_dx(ax, ay, hi):   # smallest shift along (ax, ay) that leaves `gap` between two footprints
            lo_, hi_ = 0.0, hi
            for _ in range(40):
                mid = (lo_ + hi_) / 2.0
                if foot.distance(affinity.translate(foot, ax * mid, ay * mid)) >= gap - 1e-9:
                    hi_ = mid
                else:
                    lo_ = mid
            return hi_

        stagger = self.mirror_mode in ("stagger", "triangular")
        dx = clear_dx(1.0, 0.0, bw + gap + 1e-6)
        dy_grid = clear_dx(0.0, 1.0, bh + gap + 1e-6)
        if stagger:
            sx = dx / 2.0
            lo_, hi_ = 0.0, bh + gap + 1e-6
            for _ in range(40):
                mid = (lo_ + hi_) / 2.0
                if foot.distance(affinity.translate(foot, sx, mid)) >= gap - 1e-9:
                    hi_ = mid
                else:
                    lo_ = mid
            dy = max(hi_, dy_grid / 2.0)
        else:
            sx, dy = 0.0, dy_grid
        if dx < 1e-6 or dy < 1e-6:
            return []
        rx0, ry0, rx1, ry1 = room.bounds
        reach_x = max(abs(rx1 - c0.x), abs(rx0 - c0.x)) + bw
        reach_y = max(abs(ry1 - c0.y), abs(ry0 - c0.y)) + bh
        imax, jmax = int(reach_x / dx) + 2, int(reach_y / dy) + 2
        for j in range(-jmax, jmax + 1):
            off = sx if (j % 2) else 0.0
            for i in range(-imax, imax + 1):
                a, b = i * dx + off, j * dy
                if i == 0 and j == 0:
                    continue
                moved = affinity.translate(foot, a, b)
                if min_frac > 0:
                    if not prepared.intersects(moved) or moved.intersection(room).area < min_frac * foot_area:
                        continue
                elif not prepared.contains(moved):
                    continue
                vec = tuple(ua * a + va * b)
                funcs.append(lambda m, vec=vec: m.translate(vec))
                if len(funcs) >= 1500:
                    return funcs
        return funcs

    @staticmethod
    def _is_round(body) -> bool:
        """True when the body's outline (seen from above) is a circle."""
        try:
            bb = body.bounding_box()
            z = (bb[2] + bb[5]) / 2.0
            polys = body.slice(z).to_polygons()
            if not polys:
                return False
            pts = max(polys, key=len)
            c = (np.array(bb[:2]) + np.array(bb[3:5])) / 2.0
            r = np.linalg.norm(pts - c, axis=1)
            return len(pts) >= 16 and float(r.std()) < 0.01 * float(r.mean()) and abs((bb[3] - bb[0]) - (bb[4] - bb[1])) < 0.02 * (bb[3] - bb[0])
        except Exception:
            return False

    @staticmethod
    def _reach_out(removed, before):
        """Where a cut leaves the body (a hole breaking through a curved top), let its copies reach a hair
        further out: a copy of a tessellated surface never lines up exactly with the body's own and would
        leave paper-thin slivers behind."""
        if removed.is_empty():
            return removed
        bb = removed.bounding_box()
        ext = np.array(bb[3:]) - np.array(bb[:3])
        axis = int(np.argmax(ext))
        eps = 0.03
        out = removed
        v0 = max(removed.volume(), 1e-9)
        for sgn in (1.0, -1.0):
            d = [0.0, 0.0, 0.0]
            d[axis] = sgn * eps
            shifted = removed.translate(tuple(d))
            piece = shifted - removed
            if piece.is_empty():
                continue
            if (piece - before).volume() > 0.25 * piece.volume():   # that end sticks out of the body
                out = out + shifted
        return out

    def _resolve_plane(self, doc):
        """(point, unit normal) of the plane named in mirror_mode "plane:<id>" (origin or offset plane)."""
        pid = self.mirror_mode.split(":", 1)[1]
        if pid in doc.construction_planes:
            c = doc.construction_planes[pid]
            o, n = c["origin"], c["normal"]
        elif pid in doc.origin_planes:
            o, n = doc.origin_planes[pid].origin, doc.origin_planes[pid].normal
        else:
            return None
        n = np.asarray(n, dtype=float)
        ln = float(np.linalg.norm(n))
        return (np.asarray(o, dtype=float), n / ln) if ln > 1e-9 else None

    def compute(self, doc, body_id: str):
        """(removed copies, added copies) for one body, or None if there is nothing to copy."""
        idx = doc.timeline.features.index(self) if self in doc.timeline.features else len(doc.timeline.features)
        pos = [i for i, f in enumerate(doc.timeline.features) if f.feature_id in self.source_ids and i < idx]
        if not pos:
            return None
        before = doc.step_states.get(min(pos), {}).get(body_id)
        after = doc.step_states.get(max(pos) + 1, {}).get(body_id)
        if before is None or after is None:
            return None
        removed, added = before - after, after - before
        removed, added = CadKernel.drop_slivers(removed), CadKernel.drop_slivers(added)
        removed = self._reach_out(removed, before)
        regions = [m for m in (removed, added) if not m.is_empty()]
        if not regions:
            return None
        lo = np.min([np.array(r.bounding_box()[:3]) for r in regions], axis=0)
        hi = np.max([np.array(r.bounding_box()[3:]) for r in regions], axis=0)
        bb = before.bounding_box()
        bmin, bmax = np.array(bb[:3]), np.array(bb[3:])
        centre = (bmin + bmax) / 2.0 if self.about == "body" else np.zeros(3)
        self._round_body = self._is_round(before)
        self._mirror_plane = self._resolve_plane(doc) if self.mirror_mode.startswith("plane:") else None
        if self.kind == "fill":
            step_bodies = doc.step_states.get(idx, {})
            now = step_bodies.get(body_id, before)   # the body as it is when this step runs
            other_bodies = [m for bid, m in step_bodies.items() if bid != body_id and not m.is_empty()]
            funcs = self._fill_funcs(doc, before, removed, added, now, other_bodies=other_bodies)
        else:
            funcs = self._transforms(centre, (lo + hi) / 2.0, bmax - bmin)
        if not funcs:
            self.copies = 0
            return None
        rem = add = None
        if not removed.is_empty():
            parts = [f(removed) for f in funcs]
            rem = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]
        if not added.is_empty():
            parts = [f(added) for f in funcs]
            add = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]
        clip = getattr(self, "_fill_clip", None) if self.kind == "fill" else None
        if clip is not None:   # partial copies at the frame are cut off at the inset outline
            prism = self._room_prism(clip, before)   # also keeps the cut out of anything standing on the face
            if prism is not None:
                rem = (rem ^ prism) if rem is not None else None
                add = (add ^ prism) if add is not None else None
        self.copies = len(funcs)
        return rem, add

    def execute(self, doc: Any) -> None:
        self.copies = 0
        for bid, body in list(doc.bodies.items()):
            res = self.compute(doc, bid)
            if res is None:
                continue
            rem, add = res
            result = body.manifold
            if rem is not None:
                result = result - rem
            if add is not None:
                result = result + add
            if not result.is_empty():
                body.manifold = CadKernel.drop_slivers(result)
                body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
            "suppressed": self.suppressed, "source_ids": list(self.source_ids), "kind": self.kind,
            "axis1": self.axis1, "count1": self.count1, "spacing1": self.spacing1,
            "axis2": self.axis2, "count2": self.count2, "spacing2": self.spacing2,
            "mirror_mode": self.mirror_mode, "about": self.about, "angle": self.angle,
        }


class RevolveFeature(Feature):
    def __init__(
        self,
        feature_id: str,
        name: str,
        sketch_id: str,
        profile_idx: int,
        segments: int = 48,
        operation: str = "new_body"
    ):
        super().__init__(feature_id, "revolve", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.segments = segments
        self.operation = operation

    def execute(self, doc: Any) -> None:
        sketch = doc.sketches.get(self.sketch_id)
        if not sketch or not sketch.profiles:
            return

        if self.profile_idx >= len(sketch.profiles):
            return

        profile = sketch.profiles[self.profile_idx]
        mat_3x4 = sketch.plane.get_transform_matrix_3x4()

        coords = [[float(p[0]), float(p[1])] for p in profile.exterior_pts]
        cs = m3d.CrossSection([coords])
        solid = m3d.Manifold.revolve(cs, circular_segments=self.segments)
        solid = solid.transform(mat_3x4)

        if self.operation == "new_body" or len(doc.bodies) == 0:
            body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
            body.update_render_mesh()
            doc.bodies[body.body_id] = body
        else:
            target_id = list(doc.bodies.keys())[-1]
            target = doc.bodies[target_id]
            if self.operation == "join":
                target.manifold = CadKernel.boolean_union(target.manifold, solid)
            elif self.operation == "cut":
                target.manifold = CadKernel.boolean_difference(target.manifold, solid)
            target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch_id": self.sketch_id,
            "profile_idx": self.profile_idx,
            "segments": self.segments,
            "operation": self.operation,
        }


class CombineFeature(Feature):
    def __init__(self, feature_id: str, name: str, target_body_id: str, tool_body_id: str, operation: str = "join"):
        super().__init__(feature_id, "combine", name)
        self.target_body_id = target_body_id
        self.tool_body_id = tool_body_id
        self.operation = operation  # join, cut, intersect

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        tool = doc.bodies.get(self.tool_body_id)
        if not target or not tool:
            return

        if self.operation == "join":
            target.manifold = CadKernel.boolean_union(target.manifold, tool.manifold)
        elif self.operation == "cut":
            target.manifold = CadKernel.boolean_difference(target.manifold, tool.manifold)
        elif self.operation == "intersect":
            target.manifold = CadKernel.boolean_intersection(target.manifold, tool.manifold)

        target.update_render_mesh()
        # Remove tool body after combine
        doc.bodies.pop(self.tool_body_id, None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "tool_body_id": self.tool_body_id,
            "operation": self.operation,
        }


class SplitBodyFeature(Feature):
    """Splits an existing solid body using a plane (construction plane or origin plane) into two separate bodies."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        plane_id: str,
        plane_origin: Optional[List[float]] = None,
        plane_normal: Optional[List[float]] = None,
        new_body_name: Optional[str] = None,
    ):
        super().__init__(feature_id, "split_body", name)
        self.target_body_id = target_body_id
        self.plane_id = plane_id
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.new_body_name = new_body_name

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return

        origin, normal = None, None
        if hasattr(doc, "construction_planes") and self.plane_id in doc.construction_planes:
            cp = doc.construction_planes[self.plane_id]
            origin = np.array(cp["origin"], dtype=float)
            normal = np.array(cp["normal"], dtype=float)
        elif hasattr(doc, "origin_planes") and self.plane_id in doc.origin_planes:
            op = doc.origin_planes[self.plane_id]
            origin = np.array(op.origin, dtype=float)
            normal = np.array(op.normal, dtype=float)
        elif self.plane_origin is not None and self.plane_normal is not None:
            origin = np.array(self.plane_origin, dtype=float)
            normal = np.array(self.plane_normal, dtype=float)

        if origin is None or normal is None:
            return

        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            return
        normal = normal / norm
        d = float(np.dot(normal, origin))

        # Split manifold into two watertight solid bodies
        part1 = target.manifold.trim_by_plane(normal, d)
        part2 = target.manifold.trim_by_plane(-normal, -d)

        if part1.is_empty() or part2.is_empty() or part1.volume() < 1e-6 or part2.volume() < 1e-6:
            return

        target.manifold = part1
        target.update_render_mesh()

        new_body_id = f"body_{self.feature_id}"
        name = self.new_body_name or f"{target.name} (Split)"
        new_body = Body(
            body_id=new_body_id,
            name=name,
            manifold=part2,
            color=list(target.color),
        )
        new_body.update_render_mesh()
        doc.bodies[new_body_id] = new_body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "plane_id": self.plane_id,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "new_body_name": self.new_body_name,
        }


class ShellFeature(Feature):
    """Hollows out a 3D solid body with a specified wall thickness, optionally opening selected faces."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        thickness: float = 2.0,
        open_faces: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(feature_id, "shell", name)
        self.target_body_id = target_body_id
        self.thickness = float(thickness)
        self.open_faces = list(open_faces or [])

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target or self.thickness <= 0.001:
            return

        # 1. Create inner eroded solid via spherical Minkowski difference
        sph = m3d.Manifold.sphere(self.thickness, 16)
        try:
            inner = target.manifold.minkowski_difference(sph)
        except Exception as e:
            print(f"ShellFeature Minkowski difference error: {e}")
            return

        if inner.is_empty() or inner.volume() < 1e-6:
            print(f"ShellFeature: wall thickness {self.thickness} mm is too thick for body {target.name}.")
            return

        # 2. If open faces are specified, extend the inner cavity through those faces
        cavity = inner
        if self.open_faces:
            for f in self.open_faces:
                norm = np.array(f.get("normal", [0, 0, 1]), dtype=float)
                norm_len = float(np.linalg.norm(norm))
                if norm_len > 1e-6:
                    norm = norm / norm_len
                    # Translate inner solid out through the face boundary
                    shift = norm * (self.thickness * 2.5 + 1.0)
                    cavity = cavity + inner.translate(list(shift))

        # 3. Subtract cavity from original solid body
        try:
            shelled = target.manifold - cavity
            if not shelled.is_empty() and shelled.volume() > 1e-6:
                target.manifold = shelled
                target.update_render_mesh()
        except Exception as e:
            print(f"ShellFeature boolean subtraction error: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "thickness": self.thickness,
            "open_faces": self.open_faces,
        }


class MoveFeature(Feature):
    """Translates and/or rotates a 3D solid body."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        pivot: str = "center",
    ):
        super().__init__(feature_id, "move", name)
        self.target_body_id = target_body_id
        self.dx = float(dx)
        self.dy = float(dy)
        self.dz = float(dz)
        self.rx = float(rx)
        self.ry = float(ry)
        self.rz = float(rz)
        self.pivot = pivot if pivot in ("origin", "center") else "center"

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return

        m = target.manifold
        center = np.array([0.0, 0.0, 0.0])
        if self.pivot == "center":
            if target.render_mesh is not None:
                center = (np.asarray(target.render_mesh.bounds_min, dtype=float) + np.asarray(target.render_mesh.bounds_max, dtype=float)) * 0.5
            else:
                mesh = m.to_mesh()
                pts = mesh.vert_properties[:, :3]
                if len(pts):
                    center = (pts.min(axis=0) + pts.max(axis=0)) * 0.5

        # Rotation around pivot point
        if abs(self.rx) > 1e-4 or abs(self.ry) > 1e-4 or abs(self.rz) > 1e-4:
            if self.pivot == "center":
                m = m.translate(-center).rotate([self.rx, self.ry, self.rz]).translate(center)
            else:
                m = m.rotate([self.rx, self.ry, self.rz])

        # Translation
        if abs(self.dx) > 1e-4 or abs(self.dy) > 1e-4 or abs(self.dz) > 1e-4:
            m = m.translate([self.dx, self.dy, self.dz])

        target.manifold = m
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "dx": self.dx,
            "dy": self.dy,
            "dz": self.dz,
            "rx": self.rx,
            "ry": self.ry,
            "rz": self.rz,
            "pivot": self.pivot,
        }


class ImportMeshFeature(Feature):
    """Imports a 3D solid mesh from external files (e.g. 3MF, STL)."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        vertices: List[List[float]],
        triangles: List[List[int]],
        source_file: str = "",
        created_body_id: Optional[str] = None,
    ):
        super().__init__(feature_id, "import_mesh", name)
        self.vertices = vertices
        self.triangles = triangles
        self.source_file = source_file
        self.created_body_id = created_body_id or f"body_{feature_id}"

    def execute(self, doc: Any) -> None:
        verts = np.asarray(self.vertices, dtype=np.float32)
        tris = np.asarray(self.triangles, dtype=np.int32)
        mesh = m3d.Mesh(vert_properties=verts, tri_verts=tris)
        solid = m3d.Manifold(mesh)
        body = Body(body_id=self.created_body_id, name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "vertices": self.vertices,
            "triangles": self.triangles,
            "source_file": self.source_file,
            "created_body_id": self.created_body_id,
        }




class Timeline:
    """Manages the history of parametric features and replay."""

    def __init__(self):
        self.features: List[Feature] = []
        self.marker_index: int = 0  # Replay index (points to after the active feature)

    def add_feature(self, feature: Feature) -> None:
        # If marker is in the middle of history, truncate forward history (like Fusion 360)
        if self.marker_index < len(self.features):
            self.features = self.features[:self.marker_index]
        self.features.append(feature)
        self.marker_index = len(self.features)

    def recompute(self, doc: Any) -> None:
        """Clears bodies and sketches and executes all unsuppressed features up to marker."""
        if hasattr(doc, "refresh_parameters"):
            doc.refresh_parameters()  # formulas pick up the current parameter values first
        active = getattr(doc, "active_sketch", None)
        doc.bodies.clear()
        doc.sketches.clear()

        limit = min(self.marker_index, len(self.features))
        doc.step_states = {}  # step index -> {body id: manifold} as it was before that step (patterns diff these)
        for i in range(limit):
            doc.step_states[i] = {bid: b.manifold for bid, b in doc.bodies.items()}
            feat = self.features[i]
            if not feat.suppressed:
                try:
                    feat.execute(doc)
                except Exception as e:
                    print(f"Error executing feature {feat.name}: {e}")

        doc.step_states[limit] = {bid: b.manifold for bid, b in doc.bodies.items()}
        if active and active.sketch_id not in doc.sketches:
            doc.sketches[active.sketch_id] = active

    def step_to(self, index: int, doc: Any) -> None:
        self.marker_index = max(0, min(index, len(self.features)))
        self.recompute(doc)

    def step_forward(self, doc: Any) -> None:
        if self.marker_index < len(self.features):
            self.marker_index += 1
            self.recompute(doc)

    def step_backward(self, doc: Any) -> None:
        if self.marker_index > 0:
            self.marker_index -= 1
            self.recompute(doc)

    def rewind(self, doc: Any) -> None:
        self.marker_index = 0
        self.recompute(doc)

    def fast_forward(self, doc: Any) -> None:
        self.marker_index = len(self.features)
        self.recompute(doc)
