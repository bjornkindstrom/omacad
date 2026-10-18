"""
Omacad - Parametric Timeline & Feature History
Tracks the sequential history of modeling operations and enables parametric recomputation.
All feature classes are modularized in `omacad.model.features.*` and re-exported here for compatibility.
"""

import copy
import json
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
    PrismFeature,
    SphereFeature,
    SketchFeature,
    ExtrudeFeature,
    EmbossFeature,
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
    OffsetFaceFeature,
    HoneycombFeature,
)


class Timeline:
    """Manages the history of parametric features and replay."""

    def __init__(self):
        self.features: List[Feature] = []
        self.marker_index: int = 0  # Replay index (points to after the active feature)
        self._state_cache: dict = {}  # step_index -> {"hash": str, "bodies": dict, "sketches": dict, "step_state": dict}

    def clear_cache(self) -> None:
        """Clears the incremental recompute cache."""
        self._state_cache.clear()

    def add_feature(self, feature: Feature) -> None:
        # Insert at the marker (like Fusion 360): rolled-back later steps stay, they come back when rolled forward
        idx = max(0, min(self.marker_index, len(self.features)))
        self.features.insert(idx, feature)
        self.marker_index = idx + 1
        for k in [k for k in self._state_cache if k >= idx]:
            del self._state_cache[k]

    def _feature_fingerprint(self, feat: Feature) -> str:
        """Generates a stable cache key for a feature and its evaluation expressions."""
        try:
            d = dict(feat.to_dict(), exprs=dict(getattr(feat, "exprs", {})), suppressed=feat.suppressed)
            return json.dumps(d, sort_keys=True, default=str)
        except Exception:
            return repr(feat)

    def recompute(self, doc: Any) -> None:
        """Executes all unsuppressed features up to marker incrementally, reusing cached states."""
        if hasattr(doc, "refresh_parameters"):
            doc.refresh_parameters()  # formulas pick up the current parameter values first
        active = getattr(doc, "active_sketch", None)

        limit = min(self.marker_index, len(self.features))
        hidden = {bid for bid, b in doc.bodies.items() if not getattr(b, "visible", True)}   # the user's eye clicks

        # Invalidate any cache entries beyond current marker or length
        for k in list(self._state_cache.keys()):
            if k > limit:
                del self._state_cache[k]

        # Find the latest valid checkpoint in cache
        start_step = 0
        for i in range(limit):
            if i in self._state_cache:
                feat = self.features[i]
                expected_hash = self._feature_fingerprint(feat)
                if self._state_cache[i].get("hash") == expected_hash:
                    start_step = i + 1
                    continue
            # Cache miss or invalidated feature: clear this and all downstream checkpoints
            for k in list(self._state_cache.keys()):
                if k >= i:
                    del self._state_cache[k]
            break

        # Restore state from latest valid checkpoint or start fresh
        if start_step > 0 and (start_step - 1) in self._state_cache:
            cp = self._state_cache[start_step - 1]
            doc.bodies = {bid: copy.copy(b) for bid, b in cp["bodies"].items()}
            doc.sketches = {sid: copy.deepcopy(s) for sid, s in cp["sketches"].items()}
            # a timeline sketch must stay the step's own object, as after a full run: edits go into a copy otherwise
            for f in self.features[:start_step]:
                if f.feature_type == "sketch" and not f.suppressed and f.sketch.sketch_id in doc.sketches:
                    doc.sketches[f.sketch.sketch_id] = f.sketch
            doc.step_states = dict(cp["step_states"])
        else:
            doc.bodies.clear()
            doc.sketches.clear()
            doc.step_states = {}
            start_step = 0

        # Execute only the changed / downstream features from start_step to limit
        for i in range(start_step, limit):
            doc.step_states[i] = {bid: b.manifold for bid, b in doc.bodies.items()}
            feat = self.features[i]
            if not feat.suppressed:
                try:
                    feat.execute(doc)
                except Exception as e:
                    print(f"Error executing feature {feat.name}: {e}")

            # Save checkpoint after executing feature i
            self._state_cache[i] = {
                "hash": self._feature_fingerprint(feat),
                "bodies": {bid: copy.copy(b) for bid, b in doc.bodies.items()},
                "sketches": {sid: copy.deepcopy(s) for sid, s in doc.sketches.items()},
                "step_states": dict(doc.step_states),
            }

        doc.step_states[limit] = {bid: b.manifold for bid, b in doc.bodies.items()}
        for bid in hidden:       # the rebuilt bodies are fresh objects: a body the user hid stays hidden
            if bid in doc.bodies:
                doc.bodies[bid].visible = False
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
    "PrismFeature",
    "SphereFeature",
    "SketchFeature",
    "ExtrudeFeature",
    "EmbossFeature",
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
