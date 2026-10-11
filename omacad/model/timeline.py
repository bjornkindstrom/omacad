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
        self.kind = kind                    # "linear", "mirror", "circular"
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
        funcs = self._transforms(centre, (lo + hi) / 2.0, bmax - bmin)
        if not funcs:
            return None
        rem = None
        add = None
        for f in funcs:
            if not removed.is_empty():
                t = f(removed)
                rem = t if rem is None else rem + t
            if not added.is_empty():
                t = f(added)
                add = t if add is None else add + t
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
