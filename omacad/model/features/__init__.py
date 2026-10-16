"""
Omacad - Parametric Features Package
Exports all history features, Body and base classes.
"""

from omacad.model.features.base import (
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
)
from omacad.model.features.primitives import (
    BoxFeature,
    CylinderFeature,
    SphereFeature,
    SketchFeature,
)
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.revolve import RevolveFeature
from omacad.model.features.fillet import FilletFeature
from omacad.model.features.hole import HoleFeature, hole_tool
from omacad.model.features.boolean import (
    DeleteBodyFeature,
    CombineFeature,
    SplitBodyFeature,
)
from omacad.model.features.shell import ShellFeature
from omacad.model.features.pattern import PatternFeature, _best_pattern
from omacad.model.features.transform import (
    MoveFeature,
    ImportMeshFeature,
)
from omacad.model.features.thread import ThreadFeature
from omacad.model.features.offset_face import OffsetFaceFeature

__all__ = [
    "OffsetFaceFeature",
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
    "ThreadFeature",
]
