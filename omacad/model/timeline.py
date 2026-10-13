"""
Omacad - Parametric Timeline & Feature History
Tracks the sequential history of modeling operations and enables parametric recomputation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import math
import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from omacad.model.kernel import CadKernel, RenderMesh
from omacad.model.faces import PlanarFace, compute_planar_faces, PlanarEdge, compute_planar_edges, match_edge, edge_from_ref, fuzzy_edge_from_ref
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


def _bbox_overlap(a: m3d.Manifold, b: m3d.Manifold, tol: float = 1e-6) -> bool:
    a0, a1 = np.array(a.bounding_box()[:3]), np.array(a.bounding_box()[3:])
    b0, b1 = np.array(b.bounding_box()[:3]), np.array(b.bounding_box()[3:])
    return bool(np.all(a0 <= b1 + tol) and np.all(b0 <= a1 + tol))


def combine_with_bodies(doc: Any, feature_id: str, name: str, operation: str, tool: m3d.Manifold) -> None:
    """Shared by Extrude and Revolve: add `tool` as a new body, or join/cut/intersect it with every body it touches."""
    def new_body():
        body = Body(body_id=f"body_{feature_id}", name=name, manifold=tool)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    if operation == "new_body":
        new_body()
        return

    # Combine operations act on every body the tool actually touches
    targets = [
        b for b in doc.bodies.values()
        if _bbox_overlap(b.manifold, tool)
        and (operation == "join" or not (b.manifold ^ tool).is_empty())
    ]

    if operation == "join":
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
        if operation == "cut":
            result = body.manifold - tool
        elif operation == "intersect":
            result = body.manifold ^ tool
        else:
            continue
        if result.is_empty():
            doc.bodies.pop(body.body_id, None)
        else:
            body.manifold = result
            body.update_render_mesh()


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


def profile_signature(profile: Any) -> Tuple[float, float, float]:
    """(centroid u, centroid v, area) of a sketch profile: what identifies it when the numbering of a sketch's
    profiles changes (a different curve smoothness, a re-drawn neighbour...)."""
    poly = Polygon(profile.exterior_pts, profile.interior_holes)
    c = poly.centroid
    return (float(c.x), float(c.y), float(poly.area))


def _profile_matches(profile: Any, sig, area_tol: float = 0.03) -> bool:
    u, v, a = profile_signature(profile)
    if abs(a - sig[2]) > max(area_tol * abs(sig[2]), 1e-3):
        return False
    return math.hypot(u - sig[0], v - sig[1]) <= max(0.25, 0.02 * math.sqrt(abs(sig[2])))


def _planes_coincide(a, b) -> bool:
    n1, n2 = np.asarray(a.normal, dtype=float), np.asarray(b.normal, dtype=float)
    return abs(abs(float(n1 @ n2)) - 1.0) < 1e-6 and abs(float((np.asarray(b.origin, dtype=float) - np.asarray(a.origin, dtype=float)) @ n1)) < 1e-4


def profile_polygon_in(profile: Any, src_plane: Any, dst_plane: Any) -> Polygon:
    """The profile as a shapely polygon in the (u, v) frame of `dst_plane` (both sketches lie in one plane)."""
    def conv(pts):
        if src_plane is dst_plane:
            return [tuple(p) for p in pts]
        return [tuple(dst_plane.world_to_uv(src_plane.uv_to_world(float(u), float(v)))) for u, v in pts]
    return Polygon(conv(profile.exterior_pts), [conv(h) for h in profile.interior_holes])


def find_profile(sketch: Any, idx: int, sig) -> Optional[int]:
    """Index of the profile of `sketch` that looks like `sig` (centre and area), preferring `idx`."""
    if 0 <= idx < len(sketch.profiles) and _profile_matches(sketch.profiles[idx], sig):
        return idx
    best, best_d = None, float("inf")
    for j, pr in enumerate(sketch.profiles):
        if _profile_matches(pr, sig):
            u, v, _a = profile_signature(pr)
            d = math.hypot(u - sig[0], v - sig[1])
            if d < best_d:
                best, best_d = j, d
    return best


def region_cross_section(geom) -> m3d.CrossSection:
    """CrossSection of a shapely polygon or multipolygon (holes included)."""
    from types import SimpleNamespace
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    cs = None
    for poly in polys:
        if poly.is_empty or poly.area < 1e-9:
            continue
        part = profile_cross_section(SimpleNamespace(exterior_pts=list(poly.exterior.coords)[:-1],
                                                     interior_holes=[list(r.coords)[:-1] for r in poly.interiors]))
        cs = part if cs is None else cs + part
    return cs if cs is not None else m3d.CrossSection([])


class ProfileRefs:
    """Mixin for steps that point at sketch profiles by number (Extrude, Revolve). Besides the numbers they
    remember each profile's signature, and when the numbers no longer fit (the sketch was solved again with a
    different curve smoothness, say) the profile is found again by its centre and area."""

    profile_sigs = None
    _sigs_for = None

    def resolve_profile_refs(self, sketch) -> None:
        profiles = sketch.profiles
        idxs = [self.profile_idx] + list(self.extra_profiles)
        current = (self.profile_idx, tuple(self.extra_profiles))
        if self.profile_sigs is None or self._sigs_for != current or len(self.profile_sigs) != len(idxs):
            if all(0 <= i < len(profiles) for i in idxs):   # first sight (or edited): remember what they look like
                self.profile_sigs = [profile_signature(profiles[i]) for i in idxs]
                self._sigs_for = current
            return
        new, taken = [], set()
        for i, sig in zip(idxs, self.profile_sigs):
            if 0 <= i < len(profiles) and i not in taken and _profile_matches(profiles[i], sig):
                new.append(i)
            else:
                best, best_d = None, float("inf")
                for j, pr in enumerate(profiles):
                    if j in taken or not _profile_matches(pr, sig):
                        continue
                    u, v, _a = profile_signature(pr)
                    d = math.hypot(u - sig[0], v - sig[1])
                    if d < best_d:
                        best, best_d = j, d
                new.append(best if best is not None else i)
            taken.add(new[-1])
        if new != idxs:
            self.profile_idx, self.extra_profiles = new[0], new[1:]
            self._sigs_for = (self.profile_idx, tuple(self.extra_profiles))

    def profile_refs_dict(self) -> dict:
        if self.profile_sigs is None:
            return {}
        return {"profile_sigs": [list(s) for s in self.profile_sigs],
                "profile_sigs_for": [self.profile_idx, list(self.extra_profiles)]}

    def load_profile_refs(self, data: dict) -> None:
        sigs, for_ = data.get("profile_sigs"), data.get("profile_sigs_for")
        if sigs and for_:
            self.profile_sigs = [tuple(float(x) for x in s) for s in sigs]
            self._sigs_for = (int(for_[0]), tuple(int(i) for i in for_[1]))


class ExtrudeFeature(ProfileRefs, Feature):
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
        extra_refs=None,
        holes=None,
    ):
        super().__init__(feature_id, "extrude", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.extra_profiles = [int(i) for i in (extra_profiles or [])]   # more profiles of the same sketch, extruded together
        # profiles of other sketches in the same plane that were Shift+clicked in: (sketch_id, index, signature)
        self.extra_refs = [(str(r[0]), int(r[1]), tuple(float(x) for x in r[2])) for r in (extra_refs or [])]
        # shapes of other sketches in the same plane lying inside the chosen profile: left open, as Fusion does
        # (sketch_id, index, signature)
        self.holes = [(str(r[0]), int(r[1]), tuple(float(x) for x in r[2])) for r in (holes or [])]
        self.distance = float(distance)
        self.operation = operation
        self.direction = direction
        self.distance2 = float(distance2)

    def region(self, doc: Any, sketch: Any, idxs) -> Any:
        """What is extruded, as a shapely geometry in the sketch's plane: the chosen profiles (also those of
        other sketches in the plane), minus the shapes that were left out."""
        from shapely.ops import unary_union
        parts = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes) for i in idxs]
        for sid, idx, sig in self.extra_refs:
            other = doc.sketches.get(sid)
            j = find_profile(other, idx, sig) if other is not None else None
            if j is not None and _planes_coincide(sketch.plane, other.plane):
                parts.append(profile_polygon_in(other.profiles[j], other.plane, sketch.plane))
        region = unary_union([p.buffer(0) for p in parts])
        cut = []
        for sid, idx, sig in self.holes:
            other = doc.sketches.get(sid)
            j = find_profile(other, idx, sig) if other is not None else None
            if j is not None and _planes_coincide(sketch.plane, other.plane):
                cut.append(profile_polygon_in(other.profiles[j], other.plane, sketch.plane).buffer(0))
        return region.difference(unary_union(cut)) if cut else region

    @staticmethod
    def selection_parts(doc: Any, sketch_id: str, profile_idx: int, selected_extra) -> tuple:
        """(extra_profiles, extra_refs, holes) for a click selection: the Shift+clicked profiles of the same sketch,
        those of other sketches in its plane, and the shapes inside that are left open."""
        extra = [i for (sid, i) in selected_extra if sid == sketch_id]
        refs = []
        for sid, i in selected_extra:
            other = doc.sketches.get(sid)
            if sid != sketch_id and other is not None and i < len(other.profiles):
                refs.append((sid, i, profile_signature(other.profiles[i])))
        return extra, refs, ExtrudeFeature.detect_holes(doc, sketch_id, profile_idx, extra, refs)

    @staticmethod
    def detect_holes(doc: Any, sketch_id: str, profile_idx: int, extra_profiles=(), extra_refs=()) -> list:
        """Profiles of other visible sketches in the same plane that lie inside the chosen ones and were not chosen
        themselves: they are left open when extruding (select them too, with Shift+click, to fill them)."""
        from shapely.ops import unary_union
        sketch = doc.sketches.get(sketch_id)
        if sketch is None or profile_idx >= len(sketch.profiles):
            return []
        idxs = [profile_idx] + [i for i in extra_profiles if i != profile_idx and i < len(sketch.profiles)]
        chosen = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes).buffer(0) for i in idxs]
        picked = set()
        for sid, idx in [(r[0], r[1]) for r in extra_refs]:
            other = doc.sketches.get(sid)
            if other is not None and idx < len(other.profiles) and _planes_coincide(sketch.plane, other.plane):
                chosen.append(profile_polygon_in(other.profiles[idx], other.plane, sketch.plane).buffer(0))
                picked.add((sid, idx))
        region = unary_union(chosen)
        out = []
        for sid, other in doc.sketches.items():
            if sid == sketch_id or not other.visible or not _planes_coincide(sketch.plane, other.plane):
                continue
            for j, pr in enumerate(other.profiles):
                if (sid, j) in picked or pr.area < 1e-6:
                    continue
                poly = profile_polygon_in(pr, other.plane, sketch.plane).buffer(0)
                if poly.area > 1e-6 and region.buffer(1e-6).contains(poly):
                    out.append((sid, j, profile_signature(pr)))
        return out

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
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles):
            return None
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        if self.extra_refs or self.holes:
            cs = region_cross_section(self.region(doc, sketch, idxs))
        else:
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

        combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

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
            "extra_refs": [[sid, i, list(sig)] for sid, i, sig in self.extra_refs],
            "holes": [[sid, i, list(sig)] for sid, i, sig in self.holes],
            **self.profile_refs_dict(),
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
        if e and e[0] == "arc":
            return ("arc", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]), float(e[4]), float(e[5]))
        if e and e[0] == "loop":
            return ("loop", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]))
        return (tuple(map(float, e[0])), tuple(map(float, e[1])))

    @staticmethod
    def _free_ends(body, edge, eps: float = 1e-3):
        """How far the tool may reach past each end of a convex edge: a hair (so it cuts cleanly through the end
        face) where the edge ends in open space, nothing where more material continues past the end (the foot of
        a rounded corner standing on a lower step): reaching there would cut a notch into that material."""
        t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
        inward = edge.d1 + edge.d2
        inward = inward / max(float(np.linalg.norm(inward)), 1e-12)
        probe = m3d.Manifold.cube((eps, eps, eps), True)
        out = []
        for end, direction in ((edge.p0, -t), (edge.p1, t)):
            q = end + direction * 3 * eps + inward * 3 * eps
            solid = not (probe.translate(tuple(q)) ^ body.manifold).is_empty()
            out.append(0.0 if solid else eps)
        return tuple(out)

    def _arc_reach(self, body, edge):
        """How far the tool of an open arc runs past each end (radians): a little where the arc ends in open air
        (the next face meets it at a slant, so a square end would leave a sliver), none where material continues."""
        if not edge.convex:
            return (0.0, 0.0)
        eps = 1e-3
        probe = m3d.Manifold.cube((eps, eps, eps), True)
        u, v = edge._basis()
        out = []
        for ang, sgn in ((edge.a0, -1.0), (edge.a0 + edge.sweep, 1.0)):
            radial = math.cos(ang) * u + math.sin(ang) * v
            tangent = sgn * (-math.sin(ang) * u + math.cos(ang) * v)
            end = edge.center + edge.radius * radial
            q = end + tangent * 3 * eps + (edge.s1 * radial + edge.s2 * edge.axis) * 3 * eps
            solid = not (probe.translate(tuple(q)) ^ body.manifold).is_empty()
            out.append(0.0 if solid else min(4.0 * self.size / max(edge.radius, 1e-6), math.radians(80.0)))
        return tuple(out)

    @staticmethod
    def _safe_edge_size(body, edge, requested_size: float) -> float:
        """Limits the rounding/bevel size on a convex straight edge so that it does not cut past
        adjacent face boundaries, holes, or opposite walls on either adjacent face."""
        if not edge.convex or getattr(edge, "kind", "") != "line" or requested_size <= 1e-6:
            return requested_size
        t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
        L = float(np.linalg.norm(edge.p1 - edge.p0))
        limit = requested_size
        for d, n in [(edge.d1, edge.n1), (edge.d2, edge.n2)]:
            for other in body.edges:
                if other is edge:
                    continue
                k = getattr(other, "kind", "line")
                if k == "line":
                    if abs(float((other.p0 - edge.p0) @ n)) < 1e-3 and abs(float((other.p1 - edge.p0) @ n)) < 1e-3:
                        t0 = float((other.p0 - edge.p0) @ t)
                        t1 = float((other.p1 - edge.p0) @ t)
                        if max(min(t0, t1), 0.0) < min(max(t0, t1), L) - 1e-3:
                            d0 = float((other.p0 - edge.p0) @ d)
                            d1 = float((other.p1 - edge.p0) @ d)
                            dist = min(d0, d1)
                            if dist > 1e-4:
                                limit = min(limit, dist * 0.99)
                elif k in ("circle", "loop"):
                    pts = other.pts if k == "loop" else [other.center]
                    if all(abs(float((p - edge.p0) @ n)) < 1e-3 for p in pts):
                        t_vals = [float((p - edge.p0) @ t) for p in pts]
                        if max(min(t_vals), 0.0) < min(max(t_vals), L) - 1e-3:
                            d_vals = [float((p - edge.p0) @ d) for p in pts]
                            r_sub = other.radius if k == "circle" else 0.0
                            dist = min(d_vals) - r_sub
                            if dist > 1e-4:
                                limit = min(limit, dist * 0.99)
        return max(limit, 0.01)

    def _mitred_tool(self, body, edge, edges):
        """Fill tool for a straight edge at the foot of a wall. Where the next selected foot edge meets it on the
        same floor, both bands run past the corner and are cut off along the bisector (mitred), so the roundings
        flow into each other with no notch."""
        ext = [0.0, 0.0]
        trims = []
        reach = 20.0 * self.size + 10.0
        for k, v in enumerate((edge.p0, edge.p1)):
            far = edge.p1 if k == 0 else edge.p0
            ta = (far - v) / max(float(np.linalg.norm(far - v)), 1e-12)
            for other in edges:
                if other is edge or other.convex != edge.convex or getattr(other, "kind", "") != "line":
                    continue
                q = None
                if np.linalg.norm(other.p0 - v) < 1e-4:
                    q = other.p1
                elif np.linalg.norm(other.p1 - v) < 1e-4:
                    q = other.p0
                if q is None:
                    continue
                tb = (q - v) / max(float(np.linalg.norm(q - v)), 1e-12)
                same_face = any(float(na @ nb) > 0.999 for na in (edge.n1, edge.n2) for nb in (other.n1, other.n2))
                if not same_face or abs(float(ta @ tb)) > 0.999:
                    continue
                m = ta - tb
                m = m / np.linalg.norm(m)
                ext[k] = reach
                trims.append((m, float(m @ v)))
                break
        tool = CadKernel.round_tool(edge, self.size, self.kind, extend=tuple(ext))
        for m, off in trims:
            tool = tool.trim_by_plane([float(x) for x in m], off)
        return tool

    def execute(self, doc: Any) -> None:
        """All edges are matched against the body as it is *before* this step and the tools are applied
        together; rounding them one after another would hide the neighbouring edges (the first
        rounding turns the faces next to it into curved ones)."""
        self.skipped = 0
        if self.size <= 1e-6:
            return
        cut, add = {}, {}
        seen = []

        def take(body, edge):
            if any(body is b and edge.same_as(e) for b, e in seen):
                return  # the same edge selected twice
            seen.append((body, edge))

        missing = []
        for ref in self.edges:
            hit = None
            for body in doc.bodies.values():
                edge = edge_from_ref(ref, body.edges)
                if edge is not None:
                    hit = (body, edge)
                    break
            if hit is None:
                missing.append(ref)
                continue
            take(*hit)
        # Edges that moved or changed size because something earlier in the history was edited: take the
        # nearest edge of the same kind instead of leaving the sharp corner behind.
        for ref in missing:
            best = None
            for body in doc.bodies.values():
                bb = np.array(body.manifold.bounding_box())
                reach = 0.75 * float(np.linalg.norm(bb[3:] - bb[:3]))
                edge = fuzzy_edge_from_ref(ref, body.edges, used=[e for b, e in seen if b is body], reach=reach)
                if edge is not None:
                    best = (body, edge)
                    break
            if best is None:
                self.skipped += 1
            else:
                take(*best)

        for body, edge in seen:
            ext = self._free_ends(body, edge) if edge.convex and getattr(edge, "kind", "") == "line" else 1e-3 if edge.convex else 0.0
            eff_size = self._safe_edge_size(body, edge, self.size)
            if getattr(edge, "kind", "") == "loop" and not edge.convex:
                tool = CadKernel.foot_fill_tool(body.manifold, edge, self.size, self.kind)
            elif not edge.convex and getattr(edge, "kind", "") == "line":
                tool = self._mitred_tool(body, edge, [e for b, e in seen if b is body])
            elif getattr(edge, "kind", "") == "circle" and edge.is_arc:
                tool = CadKernel.circle_round_tool(edge, self.size, self.kind, reach=self._arc_reach(body, edge))
            else:
                tool = CadKernel.round_tool(edge, eff_size, self.kind, extend=ext)
            (cut if edge.convex else add).setdefault(body.body_id, []).append(tool)

        # Inside corners of a face outline: the two bevel bands end square at the corner and leave a notch there.
        # Material survives only where one wall still allows it, so what must go is the overlap of both bands.
        convex = [(b, e) for b, e in seen if e.convex and getattr(e, "kind", "") == "line"]
        for i in range(len(convex)):
            for j in range(i + 1, len(convex)):
                (ba, ea), (bb, eb) = convex[i], convex[j]
                if ba is not bb:
                    continue
                shared = any(np.linalg.norm(p - q) < 1e-4 for p in (ea.p0, ea.p1) for q in (eb.p0, eb.p1))
                da = (ea.p1 - ea.p0) / max(np.linalg.norm(ea.p1 - ea.p0), 1e-12)
                db = (eb.p1 - eb.p0) / max(np.linalg.norm(eb.p1 - eb.p0), 1e-12)
                same_face = any(float(na @ nb) > 0.999 for na in (ea.n1, ea.n2) for nb in (eb.n1, eb.n2))
                if not shared or not same_face or abs(float(da @ db)) > 0.999:
                    continue
                sa = self._safe_edge_size(ba, ea, self.size)
                sb = self._safe_edge_size(bb, eb, self.size)
                ext = 40.0 * min(sa, sb) + 10.0
                try:
                    corner = (CadKernel.edge_round_tool(ea, sa, self.kind, extend=ext)
                              ^ CadKernel.edge_round_tool(eb, sb, self.kind, extend=ext))
                except Exception:
                    continue
                if not corner.is_empty():
                    cut.setdefault(ba.body_id, []).append(corner)

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


_LATTICE_CACHE: Dict[Any, Any] = {}


def _polygon_corners(foot):
    """Corner count of `foot` when it is a convex polygon of 3..8 sides, else 0."""
    try:
        hull = foot.convex_hull
        if hull.geom_type != "Polygon" or foot.area < 0.97 * hull.area:
            return 0
        bx0, by0, bx1, by1 = hull.bounds
        pts = list(hull.simplify(1e-3 * max(bx1 - bx0, by1 - by0, 1e-6)).exterior.coords)[:-1]
        return len(pts) if 3 <= len(pts) <= 8 else 0
    except Exception:
        return 0


def _tight_lattice(shape, gap, odd=False, refine=True, n_samples=720):
    """Densest lattice (v1, v2, area) of `shape` copies with `gap` mm between neighbours. Two copies are
    closer than `gap` when their offset lies inside K = (hull - hull) grown by gap; the densest lattice
    packing then puts u, v and v - u on the boundary of K, so it is searched along that boundary."""
    from shapely import affinity
    from shapely.geometry import MultiPoint
    pts = np.array(shape.convex_hull.exterior.coords)[:-1]
    diff = MultiPoint([tuple(p - q) for p in pts for q in pts]).convex_hull
    K = diff.buffer(gap * 1.0005, quad_segs=64)
    ring = K.exterior
    total = ring.length

    def at(frac):
        u = ring.interpolate(frac * total)
        u = np.array([u.x, u.y])
        cut = ring.intersection(affinity.translate(K, u[0], u[1]).exterior)
        best = None
        for q in getattr(cut, "geoms", [cut]):
            if q.geom_type != "Point":
                continue
            v = np.array([q.x, q.y])
            area = abs(u[0] * v[1] - u[1] * v[0])
            if area > 1e-9 and (best is None or area < best[2]):
                best = (u, v, area)
        return best

    best, best_f = None, 0.0
    for k in range(n_samples):
        r = at(k / n_samples)
        if r is not None and (best is None or r[2] < best[2] - 1e-9):
            best, best_f = r, k / n_samples
    if best is not None and refine:
        step = 1.0 / n_samples
        while step > 1e-7:
            for f in (best_f - step, best_f + step):
                r = at(f % 1.0)
                if r is not None and r[2] < best[2] - 1e-9:
                    best, best_f = r, f % 1.0
            step /= 2.0
    return best


def _best_pattern(foot, gap):
    """(members, v1, v2): copies per lattice cell as (turned 180 degrees?, offset) plus the lattice. Triangles,
    pentagons and heptagons also try pairs of a copy and one turned 180 degrees next to it."""
    from shapely import affinity
    key = (foot.wkb_hex, round(gap, 6))
    if key in _LATTICE_CACHE:
        return _LATTICE_CACHE[key]
    n = _polygon_corners(foot)
    res = None
    odd = n % 2 == 1
    single = _tight_lattice(foot, gap, odd)
    if single is not None:
        res = ([(False, (0.0, 0.0))], single[0], single[1])
        best_per = single[2]
        if odd:
            c = foot.centroid
            inv = affinity.rotate(foot, 180, origin=(c.x, c.y))
            pts = np.array(orient(foot.convex_hull, 1.0).exterior.coords)[:-1]   # counter-clockwise
            cands = []
            for k in range(len(pts)):
                e = pts[(k + 1) % len(pts)] - pts[k]
                ln = float(np.hypot(*e))
                if ln < 1e-9:
                    continue
                d = np.array([e[1], -e[0]]) / ln
                lo_, hi_ = 0.0, float(np.hypot(*np.ptp(pts, axis=0))) * 2 + gap
                for _ in range(40):
                    mid = (lo_ + hi_) / 2.0
                    lo_, hi_ = (lo_, mid) if foot.distance(affinity.translate(inv, d[0] * mid, d[1] * mid)) >= gap - 1e-9 else (mid, hi_)
                for shift in np.linspace(-0.5, 0.5, 11):   # slide the turned copy along the shared edge too
                    w = d * hi_ + np.array([-d[1], d[0]]) * ln * shift
                    if foot.distance(affinity.translate(inv, w[0], w[1])) < gap - 1e-6:
                        continue
                    pr = foot.union(affinity.translate(inv, w[0], w[1]))
                    lat = _tight_lattice(pr, gap, True, refine=False, n_samples=120)
                    if lat is not None:
                        cands.append((lat[2], w, pr))
            for _, w, pr in sorted(cands, key=lambda t: t[0])[:2]:
                lat = _tight_lattice(pr, gap, True)
                if lat is not None and lat[2] / 2.0 < best_per - 1e-6:
                    best_per = lat[2] / 2.0
                    res = ([(False, (0.0, 0.0)), (True, (float(w[0]), float(w[1])))], lat[0], lat[1])
    _LATTICE_CACHE[key] = res
    if len(_LATTICE_CACHE) > 64:
        _LATTICE_CACHE.pop(next(iter(_LATTICE_CACHE)))
    return res


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
                pg = Polygon([(float((v - o) @ ua), float((v - o) @ va)) for v in tri])   # relative to the plane origin, like `foot`
                if pg.is_valid and pg.area > 1e-9:
                    regions.append(pg)
        if not regions:
            return []
        raw_face = unary_union(regions + [foot.buffer(1e-4)])
        # Hairline cracks between the face's triangles (and along the spot the source feature left) would be widened
        # to margin-wide channels by the inset below, so no copies would be placed along them: close them first.
        raw_face = raw_face.buffer(0.02, join_style=2).buffer(-0.02, join_style=2)
        parts = [p for p in (raw_face.geoms if hasattr(raw_face, "geoms") else [raw_face]) if p.area > 1e-6]
        if not parts:
            return []
        # The margin is for the outer edge of the face; holes in it and whatever stands on it only get the gap.
        outline = unary_union([Polygon(p.exterior) for p in parts])
        inner = unary_union([Polygon(i) for p in parts for i in p.interiors] + ([all_obs] if all_obs and not all_obs.is_empty else []))
        room = outline.buffer(-margin) if margin > 0 else outline
        if not inner.is_empty:
            room = room.difference(inner.buffer(gap) if gap > 0 else inner)
        room = unary_union([p for p in (room.geoms if hasattr(room, "geoms") else [room]) if p.area > 1e-6])
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
        # Copies may be cut off only by the outer edge of the face. Where they would touch a hole or
        # something standing on the face they are left out whole, so no broken pieces appear mid-face.
        room_parts = list(room.geoms) if hasattr(room, "geoms") else [room]
        holes = unary_union([Polygon(g.exterior) for g in room_parts]).difference(room)
        prepared_holes = prep(holes) if not holes.is_empty else None

        def clear_of_holes(m):
            return prepared_holes is None or not prepared_holes.intersects(m) or m.intersection(holes).area < 1e-6

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
                            if prepared.intersects(m_up) and clear_of_holes(m_up) and m_up.intersection(room).area >= min_frac * foot_area:
                                vec = tuple(ua * p_up[0] + va * p_up[1])
                                funcs.append(lambda m, vec=vec: m.translate(vec))
                        elif prepared.contains(m_up):
                            vec = tuple(ua * p_up[0] + va * p_up[1])
                            funcs.append(lambda m, vec=vec: m.translate(vec))

                    # 2. Inverted candidate
                    p_inv = i * v1 + j * v2 + v_inv
                    m_inv = affinity.translate(foot_inv, *p_inv)
                    if min_frac > 0:
                        if prepared.intersects(m_inv) and clear_of_holes(m_inv) and m_inv.intersection(room).area >= min_frac * foot_area:
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

        if self.mirror_mode in ("stagger", "triangular") and _polygon_corners(foot):
            pat = _best_pattern(foot, gap)
            if pat is not None:
                members, v1, v2 = pat
                cc = foot.centroid
                M = np.eye(4)
                M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = ua, va, n, o
                M_inv = np.linalg.inv(M)
                foot_inv = affinity.rotate(foot, 180, origin=(cc.x, cc.y))
                rx0, ry0, rx1, ry1 = room.bounds
                reach = max(abs(rx1 - c0.x), abs(rx0 - c0.x), abs(ry1 - c0.y), abs(ry0 - c0.y)) + bw + bh
                step_sz = max(min(float(np.hypot(*v1)), float(np.hypot(*v2))) * abs(v1[0] * v2[1] - v1[1] * v2[0]) / max(float(np.hypot(*v1)) * float(np.hypot(*v2)), 1e-9), 1e-3)
                imax = int(reach / step_sz) + 2
                for j in range(-imax, imax + 1):
                    for i in range(-imax, imax + 1):
                        for mi, (inverted, off) in enumerate(members):
                            if i == 0 and j == 0 and mi == 0:
                                continue
                            px, py = i * v1[0] + j * v2[0] + off[0], i * v1[1] + j * v2[1] + off[1]
                            moved = affinity.translate(foot_inv if inverted else foot, px, py)
                            if min_frac > 0:
                                if not (prepared.intersects(moved) and clear_of_holes(moved) and moved.intersection(room).area >= min_frac * foot_area):
                                    continue
                            elif not prepared.contains(moved):
                                continue
                            if inverted:
                                T = np.eye(4)
                                T[0, 0] = -1.0; T[1, 1] = -1.0
                                T[0, 3] = 2.0 * cc.x + px
                                T[1, 3] = 2.0 * cc.y + py
                                mat = (M @ T @ M_inv)[:3]
                                funcs.append(lambda m, mat=mat: m.transform(mat))
                            else:
                                vec = tuple(ua * px + va * py)
                                funcs.append(lambda m, vec=vec: m.translate(vec))
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
                    if not prepared.intersects(moved) or not clear_of_holes(moved) or moved.intersection(room).area < min_frac * foot_area:
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

    @staticmethod
    def _enclosed_voids(body):
        """What is missing from the body's bounding box and does not reach its sides: holes and pockets
        made by the very step that created the body (a profile with a hole in it)."""
        lo, hi = np.array(body.bounding_box()[:3]), np.array(body.bounding_box()[3:])
        voids = m3d.Manifold.cube(tuple(hi - lo)).translate(tuple(lo)) - body
        keep = []
        for part in voids.decompose():
            b = part.bounding_box()
            if (b[0] > lo[0] + 1e-6 and b[1] > lo[1] + 1e-6 and b[3] < hi[0] - 1e-6 and b[4] < hi[1] - 1e-6):
                keep.append(part)
        return m3d.Manifold.batch_boolean(keep, m3d.OpType.Add) if keep else m3d.Manifold()

    def compute(self, doc, body_id: str):
        """(removed copies, added copies) for one body, or None if there is nothing to copy."""
        idx = doc.timeline.features.index(self) if self in doc.timeline.features else len(doc.timeline.features)
        pos = [i for i, f in enumerate(doc.timeline.features) if f.feature_id in self.source_ids and i < idx]
        if not pos:
            return None
        before = doc.step_states.get(min(pos), {}).get(body_id)
        after = doc.step_states.get(max(pos) + 1, {}).get(body_id)
        if after is None:
            return None
        if before is None or before.is_empty():   # the steps make the body itself: copy the holes inside its outline
            removed, added = self._enclosed_voids(after), m3d.Manifold()
            before = after + removed
        else:
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


class RevolveFeature(ProfileRefs, Feature):
    """Revolves sketch profiles around an axis, like Fusion 360's Revolve.

    axis: ("line", entity_id) a line of the same sketch (construction lines too), ("u",) / ("v",) the sketch's
    horizontal / vertical axis through its origin.
    direction: "one_side" (angle from the profile, negative flips), "symmetric" (angle is the total, half each way)
    or "two_sides" (angle one way, angle2 the other). angle >= 360 is a full turn."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, segments: int = 96,
                 operation: str = "new_body", axis=("v",), angle: float = 360.0, direction: str = "one_side",
                 angle2: float = 0.0, extra_profiles=None):
        super().__init__(feature_id, "revolve", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.extra_profiles = [int(i) for i in (extra_profiles or [])]
        self.segments = int(segments)
        self.operation = operation
        self.axis = tuple(axis)
        self.angle = float(angle)
        self.direction = direction
        self.angle2 = float(angle2)
        self.problem = ""

    def axis_uv(self, sketch):
        """((u, v) start, (u, v) end) of the axis in sketch coordinates, or None if it no longer exists."""
        if self.axis and self.axis[0] == "line":
            ent = sketch.get_entity(self.axis[1])
            if ent is None or getattr(ent, "entity_type", "") != "line":
                return None
            return tuple(ent.p1), tuple(ent.p2)
        if self.axis and self.axis[0] == "u":
            return (0.0, 0.0), (1.0, 0.0)
        return (0.0, 0.0), (0.0, 1.0)

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        from shapely import affinity
        self.problem = ""
        sketch = doc.sketches.get(self.sketch_id)
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles):
            return None
        ax = self.axis_uv(sketch)
        if ax is None:
            self.problem = "The axis line is gone."
            return None
        (au, av), (bu, bv) = ax
        L = math.hypot(bu - au, bv - av)
        if L < 1e-9:
            self.problem = "The axis has no length."
            return None
        d = ((bu - au) / L, (bv - av) / L)
        nrm = (-d[1], d[0])
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        polys = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes) for i in idxs]
        # which side of the axis the profile is on (the revolve only uses the positive side)
        side = 1.0
        mean_r = sum(((p.centroid.x - au) * nrm[0] + (p.centroid.y - av) * nrm[1]) * p.area for p in polys) / max(sum(p.area for p in polys), 1e-12)
        if mean_r < 0:
            side = -1.0
        # local coordinates: x = distance from the axis (profile side), y = position along the axis
        mat = [side * nrm[0], side * nrm[1], d[0], d[1], -(side * (au * nrm[0] + av * nrm[1])), -(au * d[0] + av * d[1])]
        local = [affinity.affine_transform(p, mat) for p in polys]
        if any(p.bounds[0] < -1e-6 for p in local):
            self.problem = "The profile crosses the axis."
            return None
        cs = None
        for p in local:
            q = profile_cross_section(type("P", (), {"exterior_pts": list(p.exterior.coords)[:-1],
                                                      "interior_holes": [list(h.coords)[:-1] for h in p.interiors]})())
            cs = q if cs is None else cs + q

        full = abs(self.angle) >= 360.0 - 1e-6 and self.direction == "one_side"
        if self.direction == "symmetric":
            sweep, start = abs(self.angle), -abs(self.angle) / 2.0
        elif self.direction == "two_sides":
            sweep, start = abs(self.angle) + abs(self.angle2), -abs(self.angle2)
        else:
            sweep, start = abs(self.angle), (0.0 if self.angle >= 0 else -abs(self.angle))
        sweep = min(sweep, 360.0)
        if sweep < 1e-6:
            return None
        if full or sweep >= 360.0 - 1e-6:
            solid = m3d.Manifold.revolve(cs, self.segments)
        else:
            solid = m3d.Manifold.revolve(cs, self.segments, float(sweep))
            if abs(start) > 1e-9:
                solid = solid.rotate((0.0, 0.0, float(start)))
        # axis frame in the world: z = along the axis, x = from the axis towards the profile
        plane = sketch.plane
        ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
        z = d[0] * ua + d[1] * va
        x = side * (nrm[0] * ua + nrm[1] * va)
        y = np.cross(z, x)
        o = np.asarray(plane.uv_to_world(au, av), dtype=float)
        solid = solid.transform(np.column_stack([x, y, z, o]).astype(float))
        return solid if not solid.is_empty() else None

    def resolve_operation(self, doc: Any) -> str:
        """The 'Auto' choice: into material -> cut, touching a body -> join, otherwise a new body."""
        tool = self.build_solid(doc)
        if tool is None:
            return "new_body"
        for body in doc.bodies.values():
            if not _bbox_overlap(body.manifold, tool):
                continue
            inter = body.manifold ^ tool
            if not inter.is_empty() and inter.volume() > 1e-6:
                return "cut"
        for body in doc.bodies.values():
            if _bbox_overlap(body.manifold, tool, 1e-4) and len((body.manifold + tool).decompose()) < 2:
                return "join"
        return "new_body"

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        if self.operation == "auto":
            self.operation = self.resolve_operation(doc)
        combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name, "suppressed": self.suppressed,
            "sketch_id": self.sketch_id, "profile_idx": self.profile_idx, "extra_profiles": list(self.extra_profiles),
            "segments": self.segments, "operation": self.operation, "axis": list(self.axis),
            "angle": self.angle, "direction": self.direction, "angle2": self.angle2,
            **self.profile_refs_dict(),
        }


def hole_tool(kind: str, diameter: float, depth: float, cb_diameter: float = 0.0, cb_depth: float = 0.0,
              cs_diameter: float = 0.0, cs_angle: float = 90.0, tip: str = "flat", tip_angle: float = 118.0,
              margin: float = 0.5, segments: int = 64) -> m3d.Manifold:
    """The drill: top face at z = 0, going down to z = -depth. kind: simple, counterbore, countersink."""
    r = diameter / 2.0
    top = margin
    pts = [(0.0, top)]
    if kind == "counterbore" and cb_diameter > diameter and cb_depth > 0:
        rc = cb_diameter / 2.0
        cbd = min(cb_depth, depth)
        pts += [(rc, top), (rc, -cbd), (r, -cbd)]
    elif kind == "countersink" and cs_diameter > diameter:
        rs = cs_diameter / 2.0
        t = math.tan(math.radians(max(10.0, min(cs_angle, 170.0))) / 2.0)
        h = (rs - r) / t
        pts += [(rs + top * t, top), (r, -min(h, depth))]
    else:
        pts += [(r, top)]
    pts.append((r, -depth))
    if tip == "angle":
        pts.append((0.0, -depth - r / math.tan(math.radians(tip_angle) / 2.0)))
    else:
        pts.append((0.0, -depth))
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area < 0:   # a cross-section must run counter-clockwise
        pts.reverse()
    return m3d.Manifold.revolve(m3d.CrossSection([[list(map(float, q)) for q in pts]]), segments)


class HoleFeature(Feature):
    """Drilled holes (Fusion 360 Hole): simple, counterbore or countersink, placed at points on faces.
    points: [{"origin": [x, y, z], "normal": [nx, ny, nz]}], the normal points out of the material."""

    def __init__(self, feature_id: str, name: str, points, hole_type: str = "simple", diameter: float = 6.0,
                 depth: float = 10.0, through: bool = False, cb_diameter: float = 12.0, cb_depth: float = 4.0,
                 cs_diameter: float = 12.0, cs_angle: float = 90.0, tip: str = "flat", tip_angle: float = 118.0):
        super().__init__(feature_id, "hole", name)
        self.points = [{"origin": [float(x) for x in p["origin"]], "normal": [float(x) for x in p["normal"]]} for p in points]
        self.hole_type = hole_type
        self.diameter, self.depth, self.through = float(diameter), float(depth), bool(through)
        self.cb_diameter, self.cb_depth = float(cb_diameter), float(cb_depth)
        self.cs_diameter, self.cs_angle = float(cs_diameter), float(cs_angle)
        self.tip, self.tip_angle = tip, float(tip_angle)

    def tools(self, doc: Any):
        """One drill per placed point, in world space."""
        out = []
        reach = 1.0
        for b in doc.bodies.values():
            bb = np.array(b.manifold.bounding_box())
            reach = max(reach, float(np.linalg.norm(bb[3:] - bb[:3])))
        depth = reach + 1.0 if self.through else max(self.depth, 0.01)
        tool = hole_tool(self.hole_type, self.diameter, depth, self.cb_diameter, self.cb_depth, self.cs_diameter,
                         self.cs_angle, "flat" if self.through else self.tip, self.tip_angle)
        for pt in self.points:
            n = np.array(pt["normal"], dtype=float)
            n = n / max(float(np.linalg.norm(n)), 1e-12)
            u = np.cross(n, [1.0, 0.0, 0.0])
            if np.linalg.norm(u) < 1e-6:
                u = np.cross(n, [0.0, 1.0, 0.0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            out.append(tool.transform(np.column_stack([u, v, n, np.array(pt["origin"], dtype=float)]).astype(float)))
        return out

    def execute(self, doc: Any) -> None:
        tools = self.tools(doc)
        if not tools:
            return
        cutter = m3d.Manifold.batch_boolean(tools, m3d.OpType.Add) if len(tools) > 1 else tools[0]
        for body in list(doc.bodies.values()):
            if not _bbox_overlap(body.manifold, cutter):
                continue
            result = body.manifold - cutter
            if result.is_empty():
                continue
            body.manifold = CadKernel.drop_slivers(result)
            body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name, "suppressed": self.suppressed,
                "points": self.points, "hole_type": self.hole_type, "diameter": self.diameter, "depth": self.depth,
                "through": self.through, "cb_diameter": self.cb_diameter, "cb_depth": self.cb_depth,
                "cs_diameter": self.cs_diameter, "cs_angle": self.cs_angle, "tip": self.tip, "tip_angle": self.tip_angle}


class DeleteBodyFeature(Feature):
    """Removes a body from the model (a step in the history, so a rebuild keeps it removed)."""

    def __init__(self, feature_id: str, name: str, target_body_id: str):
        super().__init__(feature_id, "delete_body", name)
        self.target_body_id = target_body_id

    def execute(self, doc: Any) -> None:
        doc.bodies.pop(self.target_body_id, None)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "target_body_id": self.target_body_id}


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
    """Hollows out a 3D solid body, optionally opening selected faces. direction: "inside" (wall grows inward by
    `thickness`), "outside" (wall grows outward by `thickness`) or "both" (`thickness` inward and `thickness2` outward)."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        thickness: float = 2.0,
        open_faces: Optional[List[Dict[str, Any]]] = None,
        direction: str = "inside",
        thickness2: float = 2.0,
    ):
        super().__init__(feature_id, "shell", name)
        self.target_body_id = target_body_id
        self.thickness = float(thickness)
        self.open_faces = list(open_faces or [])
        self.direction = direction if direction in ("inside", "outside", "both") else "inside"
        self.thickness2 = float(thickness2)

    def wall_sizes(self):
        """(inward, outward) wall thickness in mm."""
        if self.direction == "outside":
            return 0.0, self.thickness
        if self.direction == "both":
            return self.thickness, self.thickness2
        return self.thickness, 0.0

    @staticmethod
    def _grow(m, t):
        """The body with every surface moved outward by t. Convex bodies keep sharp corners (planes moved out
        and intersected); anything else is grown with a ball, which rounds its outer edges."""
        from omacad.model.faces import compute_planar_faces
        try:
            hull = m.hull() if hasattr(m, "hull") else None
        except Exception:
            hull = None
        if hull is not None and not hull.is_empty() and abs(hull.volume() - m.volume()) < 1e-6 * max(1.0, m.volume()):
            bb = np.array(m.bounding_box())
            size = float(np.max(bb[3:] - bb[:3])) + 4 * t + 10
            ctr = (bb[:3] + bb[3:]) / 2.0
            out = m3d.Manifold.cube((size, size, size), True).translate(tuple(ctr))
            for f in compute_planar_faces(m):
                n = np.asarray(f.normal, dtype=float)
                d = float(n @ np.asarray(f.origin, dtype=float)) + t
                out = out.trim_by_plane(tuple(-n), -d)   # keeps the side where -n.x >= -d, i.e. n.x <= d
            if not out.is_empty():
                return out
        return m.minkowski_sum(m3d.Manifold.sphere(t, 24))

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        t_in, t_out = self.wall_sizes()
        if not target or (t_in <= 0.001 and t_out <= 0.001):
            return
        body = target.manifold

        # 1. The empty space: the body eroded by the inside wall (or the body itself for an outside-only wall)
        cavity = body
        if t_in > 0.001:
            try:
                cavity = body.minkowski_difference(m3d.Manifold.sphere(t_in, 24))
            except Exception as e:
                print(f"ShellFeature Minkowski difference error: {e}")
                return
            if cavity.is_empty() or cavity.volume() < 1e-6:
                print(f"ShellFeature: wall thickness {t_in} mm is too thick for body {target.name}.")
                return

        # 2. The outer skin: the body grown by the outside wall
        outer = body
        if t_out > 0.001:
            try:
                outer = self._grow(body, t_out)
            except Exception as e:
                print(f"ShellFeature grow error: {e}")
                return

        # 3. Open faces: the outer skin ends flush with the open face, and the empty space is swept out
        # through the face (copies spaced so they overlap)
        for f in self.open_faces:
            nf = np.array(f.get("normal", [0, 0, 1]), dtype=float)
            ln = float(np.linalg.norm(nf))
            if ln > 1e-6 and t_out > 0.001:
                nf = nf / ln
                df = float(nf @ np.array(f.get("origin", [0, 0, 0]), dtype=float))
                outer = outer.trim_by_plane(tuple(-nf), -df)   # keep n.x <= d
        sweep = cavity
        total = t_in + t_out + 1.0
        for f in self.open_faces:
            norm = np.array(f.get("normal", [0, 0, 1]), dtype=float)
            ln = float(np.linalg.norm(norm))
            if ln < 1e-6:
                continue
            norm = norm / ln
            bb = np.array(cavity.bounding_box())
            ext = float(np.abs(norm) @ (bb[3:] - bb[:3]))        # how deep the cavity is along the normal
            step = max(0.25 * ext, 0.2)
            k = 1
            while k * step < total + step:
                sweep = sweep + cavity.translate(tuple(norm * min(k * step, total)))
                k += 1

        # 4. Wall = outer skin minus the empty space
        try:
            shelled = outer - sweep
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
            "direction": self.direction,
            "thickness2": self.thickness2,
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
