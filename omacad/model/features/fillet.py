"""
Omacad - Fillet and Chamfer Features
Rounds (fillet) or bevels (chamfer) straight and circular edges on solid bodies.
"""

from typing import Dict, Any, List
import math
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.faces import edge_from_ref, fuzzy_edge_from_ref
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
