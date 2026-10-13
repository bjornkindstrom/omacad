"""
Omacad - Move and Import Mesh Features
"""

from typing import Dict, Any, Optional, List
import numpy as np
import manifold3d as m3d
from omacad.model.features.base import Feature, Body


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
