"""
Omacad - Emboss Feature
Fusion's Emboss: raise a sketch profile (typically text) from a face by a depth (Emboss, adds material) or press it
into the face (Deboss, removes material). The sign of the depth decides, like in Fusion; Flip reverses the side;
Horizontal / Vertical distance and Rotation move the shape on the face.
"""

import math
from typing import Any, Dict, List, Optional

import manifold3d as m3d
from shapely import affinity

from omacad.model.features.base import combine_with_bodies, region_cross_section
from omacad.model.features.extrude import ExtrudeFeature

EPS = 0.02      # the tool starts a hair behind the face, so a join never leaves a coplanar skin


class EmbossFeature(ExtrudeFeature):
    """An extrusion with Emboss's vocabulary: depth (+ emboss, - deboss), flip, shift and turn on the face."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, depth: float = 1.0,
                 flip: bool = False, dx: float = 0.0, dy: float = 0.0, rotation: float = 0.0,
                 extra_profiles=None, extra_refs=None):
        super().__init__(feature_id, name, sketch_id, profile_idx, depth, "join" if depth > 0 else "cut",
                         extra_profiles=extra_profiles, extra_refs=extra_refs)
        self.feature_type = "emboss"
        self.depth = float(depth)
        self.flip = bool(flip)
        self.dx, self.dy, self.rotation = float(dx), float(dy), float(rotation)

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
        lo, hi = (-EPS, self.depth) if self.depth > 0 else (self.depth, EPS)      # along the sketch normal
        if self.flip:
            lo, hi = -hi, -lo
            if self.depth > 0:
                hi = min(hi, 0.0)       # flipped, the letters go into the body: no hair-thin skin standing on the face
        solid = m3d.Manifold.extrude(cs, height=float(hi - lo)).translate((0.0, 0.0, float(lo)))
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        return solid if not solid.is_empty() else None

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
            **self.profile_refs_dict(),
        }
