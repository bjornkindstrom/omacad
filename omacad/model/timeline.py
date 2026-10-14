"""
Omacad - Parametric Timeline & Feature History
Tracks the sequential history of modeling operations and enables parametric recomputation.
All feature classes are modularized in `omacad.model.features.*` and re-exported here for compatibility.
"""

from typing import List, Any
from omacad.model.features import (
    Body,
    Feature,
    ProfileRefs,
    profile_cross_section,
    profile_signature,
    find_profile,
    region_cross_section,
    combine_with_bodies,
    _bbox_overlap,
    _profile_matches,
    _planes_coincide,
    profile_polygon_in,
    BoxFeature,
    CylinderFeature,
    SphereFeature,
    SketchFeature,
    ExtrudeFeature,
    RevolveFeature,
    FilletFeature,
    HoleFeature,
    hole_tool,
    DeleteBodyFeature,
    CombineFeature,
    SplitBodyFeature,
    ShellFeature,
    PatternFeature,
    _best_pattern,
    MoveFeature,
    ImportMeshFeature,
    ThreadFeature,
)


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


__all__ = [
    "Timeline",
    "Body",
    "Feature",
    "ProfileRefs",
    "profile_cross_section",
    "profile_signature",
    "find_profile",
    "region_cross_section",
    "combine_with_bodies",
    "_bbox_overlap",
    "_profile_matches",
    "_planes_coincide",
    "profile_polygon_in",
    "BoxFeature",
    "CylinderFeature",
    "SphereFeature",
    "SketchFeature",
    "ExtrudeFeature",
    "RevolveFeature",
    "FilletFeature",
    "HoleFeature",
    "hole_tool",
    "DeleteBodyFeature",
    "CombineFeature",
    "SplitBodyFeature",
    "ShellFeature",
    "PatternFeature",
    "MoveFeature",
    "ImportMeshFeature",
]
