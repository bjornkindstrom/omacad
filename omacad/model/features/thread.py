"""
Omacad - Thread Feature
Parametric 3D-printable helical thread feature.
"""

from typing import Dict, Any, Optional
import math
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.features.base import Feature, Body, combine_with_bodies


class ThreadFeature(Feature):
    """Parametric helical thread feature optimized for 3D printing or standard CAD."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        diameter: float,
        pitch: float,
        length: float,
        is_female: bool = False,
        clearance: float = 0.25,
        profile: str = "trapezoidal_45",
        taper_lead_in: bool = True,
        taper_turns: float = 0.75,
        target_body_id: Optional[str] = None,
        operation: str = "new_body",  # "new_body", "join", "cut"
        plane_origin: Any = None,
        plane_normal: Any = None,
        plane_u: Any = None,
        plane_v: Any = None,
        anchor: str = "bottom",
        anchor_gap: float = 0.0,
        host_length: Optional[float] = None,
        grow: float = 0.0,
    ):
        super().__init__(feature_id, "thread", name)
        # Where along a cylinder the thread sits: `anchor` "bottom"/"top" is the end it starts from, `anchor_gap` the
        # distance kept free at that end and `host_length` the cylinder's length (None: attached to a plain face).
        self.anchor = "top" if anchor == "top" else "bottom"
        self.anchor_gap = float(anchor_gap)
        self.host_length = float(host_length) if host_length is not None else None
        self.grow = float(grow)       # profile offset in mm (set by Offset Face on a thread surface)
        self.diameter = float(diameter)
        self.pitch = float(pitch)
        self.length = float(length)
        self.is_female = bool(is_female)
        self.clearance = float(clearance)
        self.profile = str(profile)
        self.taper_lead_in = bool(taper_lead_in)
        self.taper_turns = float(taper_turns)
        self.target_body_id = str(target_body_id) if target_body_id else None
        self.operation = str(operation)
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None

    def start_offset(self) -> float:
        """Distance from the stored plane origin (the cylinder's bottom) to where the thread starts, along its axis."""
        if self.host_length is None:
            return 0.0
        if self.anchor == "top":
            return max(0.0, self.host_length - self.length - self.anchor_gap)
        return self.anchor_gap

    def surface_sign(self, point, normal, shifts, tol: float = 0.01) -> int:
        """+1 / -1 when the picked surface point lies on this thread's coil and the surface faces the same way as /
        against the coil's own outward normal (so offsetting it by d grows / shrinks the coil by d); 0 when it is
        not on the coil. `shifts` are the places the body may have been moved to since (translations only)."""
        mesh = self.build_solid().to_mesh()
        v = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
        t = np.asarray(mesh.tri_verts)
        a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
        cross = np.cross(b - a, c - a)
        area2 = np.linalg.norm(cross, axis=1)
        n_tri = cross / np.where(area2 > 1e-12, area2, 1.0)[:, None]
        reach = float(np.max(np.linalg.norm(b - a, axis=1))) * 1.5 + tol
        centroid = (a + b + c) / 3.0
        n = np.asarray(normal, dtype=float)
        for shift in shifts:
            p = np.asarray(point, dtype=float) - np.asarray(shift, dtype=float)
            for i in np.where(np.linalg.norm(centroid - p, axis=1) < reach)[0]:
                # the point lies in this triangle (to within tol) when its distance to the plane is small and the
                # barycentric coordinates are inside
                d = float(n_tri[i] @ (p - a[i]))
                if abs(d) > tol or abs(float(n_tri[i] @ n)) < 0.8 or area2[i] < 1e-12:
                    continue
                q = p - d * n_tri[i]
                w = [float(np.cross(e1 - e0, q - e0) @ n_tri[i]) / area2[i]
                     for e0, e1 in ((a[i], b[i]), (b[i], c[i]), (c[i], a[i]))]
                if min(w) >= -tol:
                    return 1 if n_tri[i] @ n > 0 else -1
        return 0

    def build_solid(self) -> m3d.Manifold:
        include_core = (self.operation == "new_body" or not self.target_body_id) and not self.is_female
        attached = bool(self.target_body_id and self.operation == "join" and not self.is_female)
        solid = CadKernel.create_thread(
            diameter=self.diameter,
            pitch=self.pitch,
            length=self.length,
            is_female=self.is_female,
            clearance=self.clearance,
            profile=self.profile,
            taper_lead_in=self.taper_lead_in,
            taper_turns=self.taper_turns,
            include_core=include_core,
            attached_to_cylinder=attached,
            grow=self.grow,
        )

        if self.plane_origin is not None and self.plane_normal is not None:
            n = np.array(self.plane_normal, dtype=float)
            n_len = float(np.linalg.norm(n))
            if n_len > 1e-12:
                n = n / n_len
                if self.plane_u is not None and self.plane_v is not None:
                    u = np.array(self.plane_u, dtype=float)
                    u = u / max(float(np.linalg.norm(u)), 1e-12)
                    v = np.array(self.plane_v, dtype=float)
                    v = v / max(float(np.linalg.norm(v)), 1e-12)
                else:
                    hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                    u = hint - np.dot(hint, n) * n
                    u /= np.linalg.norm(u)
                    v = np.cross(n, u)
                origin = np.array(self.plane_origin, dtype=float) + n * self.start_offset()
                mat = np.column_stack([u, v, n, origin]).astype(float)
                solid = solid.transform(mat)
        return solid

    def execute(self, doc: Any) -> None:
        tool = self.build_solid()

        if self.target_body_id and self.target_body_id in doc.bodies:
            target = doc.bodies[self.target_body_id]
            if self.operation == "cut" or self.is_female:
                target.manifold = target.manifold - tool
            elif self.operation == "join":
                target.manifold = target.manifold + tool
            else:
                body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=tool)
                body.update_render_mesh()
                doc.bodies[body.body_id] = body
                return
            target.update_render_mesh()
        else:
            body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=tool)
            body.update_render_mesh()
            doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": "thread",
            "name": self.name,
            "diameter": self.diameter,
            "pitch": self.pitch,
            "length": self.length,
            "is_female": self.is_female,
            "clearance": self.clearance,
            "profile": self.profile,
            "taper_lead_in": self.taper_lead_in,
            "taper_turns": self.taper_turns,
            "target_body_id": self.target_body_id,
            "operation": self.operation,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
            "anchor": self.anchor,
            "anchor_gap": self.anchor_gap,
            "host_length": self.host_length,
            "grow": self.grow,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThreadFeature":
        return cls(
            feature_id=data["feature_id"],
            name=data.get("name", "Thread"),
            diameter=data["diameter"],
            pitch=data["pitch"],
            length=data["length"],
            is_female=data.get("is_female", False),
            clearance=data.get("clearance", 0.25),
            profile=data.get("profile", "trapezoidal_45"),
            taper_lead_in=data.get("taper_lead_in", True),
            taper_turns=data.get("taper_turns", 0.75),
            target_body_id=data.get("target_body_id"),
            operation=data.get("operation", "new_body"),
            plane_origin=data.get("plane_origin"),
            plane_normal=data.get("plane_normal"),
            plane_u=data.get("plane_u"),
            plane_v=data.get("plane_v"),
            anchor=data.get("anchor", "bottom"),
            anchor_gap=data.get("anchor_gap", 0.0),
            host_length=data.get("host_length"),
            grow=data.get("grow", 0.0),
        )
