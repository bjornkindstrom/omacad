"""
Omacad - Primitive Features (Box, Cylinder, Sphere) and SketchFeature
"""

from typing import Dict, Any
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.sketch import Sketch
from omacad.model.features.base import Feature, Body


class BoxFeature(Feature):
    def __init__(self, feature_id: str, name: str, length: float, width: float, height: float, center: Any = False,
                 plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None):
        super().__init__(feature_id, "box", name)
        self.length = float(length)
        self.width = float(width)
        self.height = float(height)
        self.center = center  # True (full center), False (corner), or "bottom_center" / "center" / "corner"
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None

    def build_solid(self) -> m3d.Manifold:
        is_centered = (self.center is True or self.center == "center")
        is_bottom = (self.center == "bottom_center")
        solid = CadKernel.create_box(self.length, self.width, self.height, is_centered)
        if is_bottom:
            solid = solid.translate((-self.length / 2.0, -self.width / 2.0, 0.0))

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
                mat = np.column_stack([u, v, n, np.array(self.plane_origin, dtype=float)]).astype(float)
                solid = solid.transform(mat)
        return solid

    def execute(self, doc: Any) -> None:
        solid = self.build_solid()
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
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
        }


class CylinderFeature(Feature):
    def __init__(self, feature_id: str, name: str, radius: float, height: float, center: Any = False,
                 plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None):
        super().__init__(feature_id, "cylinder", name)
        self.radius = float(radius)
        self.height = float(height)
        self.center = center  # True (full center), False / "bottom_center" (bottom centered on origin)
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None

    def build_solid(self) -> m3d.Manifold:
        is_centered = (self.center is True or self.center == "center")
        solid = CadKernel.create_cylinder(self.radius, self.height, center=is_centered)

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
                mat = np.column_stack([u, v, n, np.array(self.plane_origin, dtype=float)]).astype(float)
                solid = solid.transform(mat)
        return solid

    def execute(self, doc: Any) -> None:
        solid = self.build_solid()
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
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
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
