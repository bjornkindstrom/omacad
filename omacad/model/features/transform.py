"""
Omacad - Move and Import Mesh Features
"""

from typing import Dict, Any, Optional, List
import numpy as np
import manifold3d as m3d
from omacad.model.features.base import Feature, Body


class MoveFeature(Feature):
    """Translates and/or rotates a 3D solid body.

    Rotation is about the body's centre, the origin, or a picked point on the body (`pivot` = "point").
    Point to point: `from_point` (on the body) is carried onto `to_point` (on another body, or a fixed spot),
    and dx/dy/dz are added on top. A picked point is stored as {"body", "kind", "xyz"} and found again on
    the rebuilt body (the snap point of that kind nearest the stored spot), so the move follows when a
    radius or a size before it changes."""

    PIVOTS = ("center", "origin", "point")

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
        from_point: Optional[dict] = None,
        to_point: Optional[dict] = None,
    ):
        super().__init__(feature_id, "move", name)
        self.target_body_id = target_body_id
        self.dx = float(dx)
        self.dy = float(dy)
        self.dz = float(dz)
        self.rx = float(rx)
        self.ry = float(ry)
        self.rz = float(rz)
        self.pivot = pivot if pivot in self.PIVOTS else "center"
        self.from_point = from_point
        self.to_point = to_point

    @staticmethod
    def resolve_point(doc: Any, ref: Optional[dict]) -> Optional[np.ndarray]:
        """Where a stored point is now: the nearest snap point of its kind on its body, or the stored spot."""
        if not ref:
            return None
        xyz = np.asarray(ref["xyz"], dtype=float)
        body = doc.bodies.get(ref.get("body")) if ref.get("body") else None
        if body is not None and ref.get("kind") in ("end", "corner"):
            from omacad.model.body_points import nearest_point
            found = nearest_point(body, xyz, ref["kind"])
            if found is not None:
                return found.xyz
        return xyz

    @staticmethod
    def body_center(body: Body) -> np.ndarray:
        if body.render_mesh is not None and len(body.render_mesh.vertices) > 0:
            return (np.asarray(body.render_mesh.bounds_min, dtype=float) + np.asarray(body.render_mesh.bounds_max, dtype=float)) * 0.5
        bb = body.manifold.bounding_box()
        return (np.array(bb[:3], dtype=float) + np.array(bb[3:], dtype=float)) * 0.5

    @staticmethod
    def transform(m: m3d.Manifold, d, r, pivot_xyz, from_xyz=None, to_xyz=None) -> m3d.Manifold:
        """Rotate by r = (rx, ry, rz) degrees about pivot_xyz, then shift by d, plus (to - from) for point to point
        (the rotated from-point lands on the to-point)."""
        from omacad.model.geometry import euler_xyz_matrix
        pivot_xyz = np.asarray(pivot_xyz, dtype=float)
        shift = np.asarray(d, dtype=float)
        if any(abs(a) > 1e-4 for a in r):
            m = m.translate(-pivot_xyz).rotate(list(r)).translate(pivot_xyz)
        if from_xyz is not None and to_xyz is not None:
            moved_from = pivot_xyz + euler_xyz_matrix(*r) @ (np.asarray(from_xyz, dtype=float) - pivot_xyz)
            shift = shift + np.asarray(to_xyz, dtype=float) - moved_from
        if np.any(np.abs(shift) > 1e-9):
            m = m.translate(list(shift))
        return m

    def pivot_xyz(self, doc: Any, body: Body, from_xyz=None) -> np.ndarray:
        if self.pivot == "origin":
            return np.zeros(3)
        if self.pivot == "point" and from_xyz is not None:
            return np.asarray(from_xyz, dtype=float)
        return self.body_center(body)

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        from_xyz = self.resolve_point(doc, self.from_point)
        to_xyz = self.resolve_point(doc, self.to_point)
        target.manifold = self.transform(target.manifold, (self.dx, self.dy, self.dz), (self.rx, self.ry, self.rz),
                                         self.pivot_xyz(doc, target, from_xyz), from_xyz, to_xyz)
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
            "from_point": self.from_point,
            "to_point": self.to_point,
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
