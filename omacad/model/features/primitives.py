"""
Omacad - Primitive Features (Box, Cylinder, Sphere) and SketchFeature
"""

from typing import Dict, Any
from omacad.model.kernel import CadKernel
from omacad.model.sketch import Sketch
from omacad.model.features.base import Feature, Body


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
