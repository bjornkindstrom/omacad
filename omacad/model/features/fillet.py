"""
Omacad - Fillet and Chamfer Features
Rounds (fillet) or bevels (chamfer) straight and circular edges on solid bodies.
"""

from typing import Dict, Any, List
import math
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.faces import edge_from_ref, fuzzy_edge_from_ref, compute_planar_edges
from omacad.model.features.base import Feature


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
        if e and e[0] == "wrapped":
            return ("wrapped", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]), bool(e[4]))
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
        adjacent face boundaries, holes, or opposite walls on either adjacent face. At the foot of a wall (concave)
        the fillet touches each face `size / tan(half the angle)` from the edge, so that reach is what must fit."""
        if getattr(edge, "kind", "") == "wrapped":
            limit = min(requested_size, edge.radius*.1)
            patch_ids = {p.index for p in edge.patches}
            for other in body.edges:
                if (other.kind == "wrapped" and other is not edge
                        and patch_ids.intersection(p.index for p in other.patches)):
                    gap = abs(edge.radius-other.radius)
                    if gap > 1e-3:
                        limit = min(limit, .49*gap)
            return limit
        if getattr(edge, "kind", "") != "line" or requested_size <= 1e-6:
            return requested_size
        t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
        L = float(np.linalg.norm(edge.p1 - edge.p0))
        limit = requested_size
        half = math.acos(float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0))) / 2.0
        reach_per_size = 1.0 if edge.convex else 1.0 / max(math.tan(half), 1e-6)
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
                                limit = min(limit, dist * 0.99 / reach_per_size)
                elif k in ("circle", "loop"):
                    pts = other.pts if k == "loop" else [other.center]
                    if all(abs(float((p - edge.p0) @ n)) < 1e-3 for p in pts):
                        t_vals = [float((p - edge.p0) @ t) for p in pts]
                        if max(min(t_vals), 0.0) < min(max(t_vals), L) - 1e-3:
                            d_vals = [float((p - edge.p0) @ d) for p in pts]
                            r_sub = other.radius if k == "circle" else 0.0
                            dist = min(d_vals) - r_sub
                            if dist > 1e-4:
                                limit = min(limit, dist * 0.99 / reach_per_size)
        return max(limit, 0.01)

    @staticmethod
    def _circular_neighbor_tool(body, edge, size: float):
        """Build the concave blend between a straight face and an axial circular face.

        The ordinary edge tool treats both neighbours as tangent planes. For a cylinder
        that substitutes a tangent line for the curved wall and can leave a lip. This
        section uses the true circle as the second boundary and is extruded along the edge.
        """
        if size <= 1e-6 or getattr(edge, "kind", "") != "line" or edge.convex:
            return None
        t = np.asarray(edge.p1 - edge.p0, dtype=float)
        length = float(np.linalg.norm(t))
        if length <= 1e-8:
            return None
        t /= length
        midpoint = (edge.p0 + edge.p1) * 0.5
        matches = []
        for circle in body.edges:
            if getattr(circle, "kind", "") != "circle" or abs(float(circle.axis @ t)) < 0.999:
                continue
            center_mid = circle.center + t * float((midpoint - circle.center) @ t)
            radial = midpoint - center_mid
            radial -= t * float(radial @ t)
            radial_len = float(np.linalg.norm(radial))
            if radial_len <= 1e-8 or abs(radial_len - circle.radius) > max(0.15, 0.01 * circle.radius):
                continue
            radial /= radial_len
            alignments = (abs(float(radial @ edge.n1)), abs(float(radial @ edge.n2)))
            if max(alignments) < 0.98:
                continue
            # The other adjacent face is the straight profile wall.
            plane_normal = np.asarray(edge.n2 if alignments[0] > alignments[1] else edge.n1, dtype=float)
            matches.append((max(alignments), circle, plane_normal))
        if not matches:
            return None

        _alignment, circle, plane_normal = max(matches, key=lambda item: item[0])
        u = np.cross(t, plane_normal)
        u_len = float(np.linalg.norm(u))
        if u_len <= 1e-8:
            return None
        u /= u_len
        # Orient the section consistently with the adjacent planar face.
        if abs(float(u @ edge.d1)) < abs(float(u @ edge.d2)):
            u = -u
        v = np.cross(t, u)
        v /= max(float(np.linalg.norm(v)), 1e-12)

        origin = np.asarray(edge.p0, dtype=float)
        center = np.array(circle.center, dtype=float, copy=True)
        center -= t * float((center - origin) @ t)
        circle_center = np.array([float((center - origin) @ u), float((center - origin) @ v)])
        radius = float(circle.radius)
        half_chord_sq = radius * radius - circle_center[1] * circle_center[1]
        if half_chord_sq <= 1e-8:
            return None
        half_chord = math.sqrt(half_chord_sq)
        qx = min((circle_center[0] - half_chord, circle_center[0] + half_chord), key=abs)
        corner = np.array([qx, 0.0])

        face_angle = math.acos(float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0)))
        half_angle = face_angle / 2.0
        bisector = edge.d1 + edge.d2
        bisector /= max(float(np.linalg.norm(bisector)), 1e-12)
        expected = corner + np.array([bisector @ u, bisector @ v]) * size / max(math.sin(half_angle), 1e-8)

        centers = []
        for side in (-1.0, 1.0):
            cy = side * size
            for offset in (-1.0, 1.0):
                center_distance = radius + offset * size
                if center_distance <= 1e-8:
                    continue
                dx_sq = center_distance**2 - (cy - circle_center[1])**2
                if dx_sq < -1e-8:
                    continue
                dx = math.sqrt(max(0.0, dx_sq))
                centers.extend((np.array([circle_center[0] - dx, cy]),
                                np.array([circle_center[0] + dx, cy])))
        if not centers:
            return None
        blend_center = min(centers, key=lambda p: float(np.linalg.norm(p - expected)))
        center_distance = float(np.linalg.norm(blend_center - circle_center))
        if center_distance <= 1e-8:
            return None
        line_touch = np.array([blend_center[0], 0.0])
        circle_touch = circle_center + (blend_center - circle_center) * (radius / center_distance)

        def arc_points(c, r, a, b, segments):
            a0 = math.atan2(float(a[1] - c[1]), float(a[0] - c[0]))
            a1 = math.atan2(float(b[1] - c[1]), float(b[0] - c[0]))
            sweep = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
            return [c + r * np.array([math.cos(a0 + sweep * i / segments),
                                      math.sin(a0 + sweep * i / segments)])
                    for i in range(1, segments)]

        section = ([corner, line_touch]
                   + arc_points(blend_center, size, line_touch, circle_touch, 32)
                   + [circle_touch]
                   + arc_points(circle_center, radius, circle_touch, corner, 48))
        area = sum(section[i][0] * section[(i + 1) % len(section)][1]
                   - section[(i + 1) % len(section)][0] * section[i][1]
                   for i in range(len(section)))
        if abs(area) <= 1e-8:
            return None
        if area < 0:
            section.reverse()
        cross_section = m3d.CrossSection([[list(map(float, p)) for p in section]])
        if cross_section.is_empty():
            return None
        solid = m3d.Manifold.extrude(cross_section, length)
        transform = np.column_stack((u, v, t, origin)).astype(float)
        return solid.transform(transform)

    def _mitred_tool(self, body, edge, edges, size):
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
        tool = CadKernel.round_tool(edge, size, self.kind, extend=tuple(ext))
        for m, off in trims:
            tool = tool.trim_by_plane([float(x) for x in m], off)
        return tool

    def edges_in(self, manifolds: dict) -> list:
        """The edges this step rounds, found in the bodies as they were before it (`manifolds`: body id -> solid),
        so the view can show which edges a step in the timeline is about."""
        cands = []
        for m in manifolds.values():
            try:
                bb = np.array(m.bounding_box())
                cands.append((compute_planar_edges(m), 0.75 * float(np.linalg.norm(bb[3:] - bb[:3]))))
            except Exception:
                pass
        out = []
        for ref in self.edges:
            hit = next((e for edges, _ in cands if (e := edge_from_ref(ref, edges)) is not None), None)
            if hit is None:
                hit = next((e for edges, reach in cands
                            if (e := fuzzy_edge_from_ref(ref, edges, used=out, reach=reach)) is not None), None)
            if hit is not None:
                out.append(hit)
        return out

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
            curved_fill = (self._circular_neighbor_tool(body, edge, self.size)
                           if self.kind == "fillet" and not edge.convex else None)
            if curved_fill is not None:
                tool = curved_fill
            elif getattr(edge, "kind", "") == "loop" and not edge.convex:
                tool = CadKernel.foot_fill_tool(body.manifold, edge, self.size, self.kind)
            elif not edge.convex and getattr(edge, "kind", "") == "line":
                tool = self._mitred_tool(body, edge, [e for b, e in seen if b is body], eff_size)
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
