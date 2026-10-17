"""
Omacad - Emboss Feature
Fusion's Emboss: raise a sketch profile (typically text) from a face by a depth (Emboss, adds material) or press it
into the face (Deboss, removes material). The sign of the depth decides, like in Fusion; Flip reverses the side;
Horizontal / Vertical distance and Rotation move the shape on the face.
"""

import math
from typing import Any, Dict, List, Optional

import numpy as np
import manifold3d as m3d
from shapely import affinity

from omacad.model import quality
from omacad.model.features.base import combine_with_bodies, region_cross_section
from omacad.model.features.extrude import ExtrudeFeature

EPS = 0.02      # the tool starts a hair behind the face, so a join never leaves a coplanar skin


class EmbossFeature(ExtrudeFeature):
    """An extrusion with Emboss's vocabulary: depth (+ emboss, - deboss), flip, shift and turn on the face."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, depth: float = 1.0,
                 flip: bool = False, dx: float = 0.0, dy: float = 0.0, rotation: float = 0.0,
                 wrap: bool = True, extra_profiles=None, extra_refs=None):
        super().__init__(feature_id, name, sketch_id, profile_idx, depth, "join" if depth > 0 else "cut",
                         extra_profiles=extra_profiles, extra_refs=extra_refs)
        self.feature_type = "emboss"
        self.depth = float(depth)
        self.flip = bool(flip)
        self.dx, self.dy, self.rotation = float(dx), float(dy), float(rotation)
        self.wrap = bool(wrap)

    @property
    def effect(self) -> str:
        return "emboss" if self.depth > 0 else "deboss"

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles) or abs(self.depth) < 1e-6:
            return None
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        region = self.region(doc, sketch, idxs)
        if region.is_empty:
            return None
        if abs(self.rotation) > 1e-9:
            region = affinity.rotate(region, self.rotation, origin=region.centroid)
        if abs(self.dx) > 1e-9 or abs(self.dy) > 1e-9:
            region = affinity.translate(region, self.dx, self.dy)
        cs = region_cross_section(region)
        M = sketch.plane.get_transform_matrix_3x4()
        surface = None if self.flip else self._surface_behind(doc, M, region)
        if surface and surface["kind"] == "cylinder":
            solid = self._wrapped(cs, M, surface, region)
        else:
            z0 = surface["z"] if surface else 0.0      # a flat face behind the sketch plane: the letters start on it
            lo, hi = (-EPS, self.depth) if self.depth > 0 else (self.depth, EPS)      # along the sketch normal
            if self.flip:
                lo, hi = -hi, -lo
                if self.depth > 0:
                    hi = min(hi, 0.0)       # flipped, the letters go into the body: no hair-thin skin standing on the face
            solid = m3d.Manifold.extrude(cs, height=float(hi - lo)).translate((0.0, 0.0, float(lo + z0)))
            solid = solid.transform(M)
        return solid if solid is not None and not solid.is_empty() else None

    def _surface_behind(self, doc: Any, M, region) -> Optional[Dict[str, Any]]:
        """The first outer cylinder or flat face (parallel to the sketch plane) a ray from the letters hits going
        against the sketch normal, in sketch coordinates: {"kind", "z"} (+ axis data for a cylinder)."""
        from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit
        A = np.vstack([np.asarray(M, dtype=float).reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
        inv = np.linalg.inv(A)
        c = region.centroid
        reach = 1e4
        origin = (A @ np.array([c.x, c.y, reach, 1.0]))[:3]
        direction = -A[:3, 2] / np.linalg.norm(A[:3, 2])
        best = None
        for body in doc.bodies.values():
            mesh = body.render_mesh
            if mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, direction)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], mesh, hit[1])
        if best is None:
            return None
        t, mesh, tri = best
        z = reach - t
        cyl = detect_cylinder_surface(mesh, tri)
        if cyl is not None and not cyl["is_internal"]:
            axis = inv[:3, :3] @ np.asarray(cyl["axis"], dtype=float)
            pt = np.asarray(cyl["origin"], dtype=float)
            hit_pt = origin + direction * t
            centre = pt + ((hit_pt - pt) @ cyl["axis"]) * np.asarray(cyl["axis"], dtype=float)   # on the axis, level with the hit
            return {"kind": "cylinder", "z": z, "radius": float(cyl["radius"]), "centre": centre,
                    "axis": np.asarray(cyl["axis"], dtype=float), "zc": float((inv @ np.append(centre, 1.0))[2])}
        v = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3, 3)[tri]
        face_n = np.cross(v[1] - v[0], v[2] - v[0])
        face_n = face_n / max(float(np.linalg.norm(face_n)), 1e-12)
        if float(face_n @ -direction) > 0.9999:
            return {"kind": "plane", "z": z}
        return None

    def _wrapped(self, cs, M, surface, region=None) -> m3d.Manifold:
        """Letters that hug a cylinder: when `self.wrap` is True, the 2D profile is bent around the cylinder's
        circumference (theta = s_perp / r) so text wider than the diameter wraps all the way around; when False,
        it projects straight along the sketch normal and is clipped to the coaxial cylinder."""
        from omacad.model.features.offset_face import _frame
        r, d = float(surface["radius"]), float(self.depth)
        if self.wrap and r > 1e-4:
            A = np.vstack([np.asarray(M, dtype=float).reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
            inv = np.linalg.inv(A)
            centre_sk = (inv @ np.append(surface["centre"], 1.0))[:3]
            axis_sk = inv[:3, :3] @ np.asarray(surface["axis"], dtype=float)
            axis_uv = np.array([axis_sk[0], axis_sk[1]], dtype=float)
            norm_uv = float(np.linalg.norm(axis_uv))
            if norm_uv > 1e-4:
                e_par = axis_uv / norm_uv
                e_perp = np.array([-e_par[1], e_par[0]], dtype=float)
                u0, v0 = float(centre_sk[0]), float(centre_sk[1])
                if region is not None and not region.is_empty:
                    from shapely import segmentize
                    step = max(0.25, r * math.radians(3.0))
                    cs_fine = region_cross_section(segmentize(region, max_segment_length=step))
                else:
                    cs_fine = cs
                margin = 0.05 * r + 0.02
                r_in, r_out = (max(0.01, r - EPS), r + d) if d > 0 else (max(0.01, r + d), r + margin)
                prism = m3d.Manifold.extrude(cs_fine, height=1.0, n_divisions=2)

                def _warp_batch(pts):
                    du = pts[:, 0] - u0
                    dv = pts[:, 1] - v0
                    s_par = du * e_par[0] + dv * e_par[1]
                    s_perp = du * e_perp[0] + dv * e_perp[1]
                    theta = s_perp / r
                    rad = r_in + pts[:, 2] * (r_out - r_in)
                    sin_t = np.sin(theta)
                    cos_t = np.cos(theta)
                    u_new = u0 + s_par * e_par[0] + rad * sin_t * e_perp[0]
                    v_new = v0 + s_par * e_par[1] + rad * sin_t * e_perp[1]
                    z_new = float(surface["zc"]) + rad * cos_t
                    return np.column_stack([u_new, v_new, z_new])

                return prism.warp_batch(_warp_batch).transform(M)

        zc = surface["zc"]
        prism = m3d.Manifold.extrude(cs, height=float(r + abs(d) + 1.0)).translate((0.0, 0.0, float(zc)))
        prism = prism.transform(M)
        length = 2.0 * (r + abs(d)) + 2.0 * 1e4
        frame = _frame(surface["centre"], surface["axis"])
        def cylinder(radius):
            cyl = m3d.Manifold.extrude(m3d.CrossSection.circle(radius, quality.circle_segments()), length)
            return cyl.translate((0.0, 0.0, -length / 2.0)).transform(frame[:3, :])
        if d > 0:
            return prism ^ cylinder(r + d)
        margin = 0.05 * r + 0.01
        return prism ^ (cylinder(r + margin) - cylinder(max(r + d, 0.01)))

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        self.operation = "join" if self.depth > 0 else "cut"
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
            "extra_refs": [[sid, i, list(sig)] for sid, i, sig in self.extra_refs],
            "depth": self.depth,
            "flip": self.flip,
            "dx": self.dx,
            "dy": self.dy,
            "rotation": self.rotation,
            "wrap": self.wrap,
            **self.profile_refs_dict(),
        }
