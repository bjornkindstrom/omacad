"""
Omacad - Sweep, Loft and Pipe (Björn #46)
Sweep: a sketch profile carried along a path of sketch lines and arcs. Pipe: a round (optionally hollow) section
along such a path. Loft: a skin through two or more profiles in order. Each adds a new body or joins/cuts/intersects
like Extrude.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature, ProfileRefs, combine_with_bodies, find_profile, profile_signature
from omacad.model.sweep_geometry import loft_solid, path_frames, pipe_solid, sweep_solid

PathRef = Tuple[str, List[str]]          # (sketch id, entity ids of the path's lines / arcs / circle)


def path_points(doc: Any, path_ref: PathRef, step_deg: float = 4.0):
    """World points along a path of sketch elements in travel order, and whether it closes."""
    from omacad.model.sketch_entities import SketchCircle
    from omacad.model.sketch_offset import build_chains, to_seg
    sketch_id, ids = path_ref
    sketch = doc.sketches.get(sketch_id)
    if sketch is None:
        raise ValueError("The path's sketch is gone.")
    ents = [e for e in sketch.entities if e.entity_id in set(ids)]
    circles = [e for e in ents if isinstance(e, SketchCircle)]
    if circles:
        c = circles[0]
        n = max(24, int(360 / step_deg))
        a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
        uv = np.column_stack([c.center[0] + c.radius * np.cos(a), c.center[1] + c.radius * np.sin(a)])
        closed = True
    else:
        segs = [s for s in (to_seg(e) for e in ents) if s is not None]
        if not segs:
            raise ValueError("Pick lines, arcs or a circle as the path.")
        chains = build_chains(segs)
        chain, closed = max(chains, key=lambda c: len(c[0]))
        if len(chains) > 1:
            raise ValueError("The path must be one connected chain of lines and arcs.")
        uv = [chain[0].p]
        for s in chain:
            pts = s.points(max(2, int(math.degrees(s.sweep()) / step_deg))) if s.kind == "arc" else [s.p, s.q]
            uv.extend(pts[1:])
        uv = np.asarray(uv, dtype=float)
        if closed:
            uv = uv[:-1]
    world = np.array([sketch.plane.uv_to_world(float(u), float(v)) for u, v in uv], dtype=float)
    keep = [0] + [i for i in range(1, len(world)) if np.linalg.norm(world[i] - world[i - 1]) > 1e-9]
    return world[keep], closed


def _profile_world(sketch, profile):
    to_w = lambda pts: np.array([sketch.plane.uv_to_world(float(u), float(v)) for u, v in pts], dtype=float)
    return to_w(profile.exterior_pts), [to_w(h) for h in profile.interior_holes]


class SweepFeature(ProfileRefs, Feature):
    """A profile swept along a path (Fusion's Sweep, single path). `twist` turns it over the length."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, path: PathRef,
                 operation: str = "new_body", twist: float = 0.0):
        super().__init__(feature_id, "sweep", name)
        self.sketch_id = sketch_id
        self.profile_idx = int(profile_idx)
        self.extra_profiles: List[int] = []
        self.path = (str(path[0]), [str(i) for i in path[1]])
        self.operation = operation
        self.twist = float(twist)

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if sketch is None:
            return None
        self.resolve_profile_refs(sketch)
        if not 0 <= self.profile_idx < len(sketch.profiles):
            return None
        path, closed = path_points(doc, self.path)
        outer, holes = _profile_world(sketch, sketch.profiles[self.profile_idx])
        centre = outer.mean(axis=0)
        if not closed and np.linalg.norm(path[-1] - centre) < np.linalg.norm(path[0] - centre):
            path = path[::-1]                               # start at the end the profile sits on
        start = path[0]
        _t, r, b, _s, _a = path_frames(path, closed, sketch.plane.u_axis)
        local = lambda pts: np.column_stack([(pts - start) @ r[0], (pts - start) @ b[0]])
        solid = sweep_solid(local(outer), path, closed, r[0], self.twist)
        for h in holes:
            solid = solid - sweep_solid(local(h), path, closed, r[0], self.twist)
        return solid if not solid.is_empty() else None

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "sketch_id": self.sketch_id, "profile_idx": self.profile_idx,
                "path": [self.path[0], list(self.path[1])], "operation": self.operation, "twist": self.twist,
                **self.profile_refs_dict()}


class PipeFeature(Feature):
    """Fusion's Pipe: a round section of `diameter` along a path; `thickness` > 0 makes it a tube."""

    def __init__(self, feature_id: str, name: str, path: PathRef, diameter: float = 5.0, thickness: float = 0.0,
                 operation: str = "new_body"):
        super().__init__(feature_id, "pipe", name)
        self.path = (str(path[0]), [str(i) for i in path[1]])
        self.diameter = float(diameter)
        self.thickness = float(thickness)
        self.operation = operation

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        from omacad.model import quality
        if self.diameter <= 1e-6:
            raise ValueError("The pipe needs a diameter.")
        path, closed = path_points(doc, self.path)
        solid = pipe_solid(path, closed, self.diameter, self.thickness, max(16, quality.circle_segments()))
        return solid if not solid.is_empty() else None

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "path": [self.path[0], list(self.path[1])],
                "diameter": self.diameter, "thickness": self.thickness, "operation": self.operation}


class LoftFeature(Feature):
    """Fusion's Loft: a skin through two or more profiles, in the order they were picked. Each profile is
    remembered as (sketch id, index, signature) and found again when the sketch changes. Holes are not lofted."""

    def __init__(self, feature_id: str, name: str, sections, operation: str = "new_body"):
        super().__init__(feature_id, "loft", name)
        self.sections = [(str(s[0]), int(s[1]), tuple(float(x) for x in s[2])) for s in sections]
        self.operation = operation

    @staticmethod
    def section_ref(doc: Any, sketch_id: str, idx: int):
        return (sketch_id, idx, profile_signature(doc.sketches[sketch_id].profiles[idx]))

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        rings, caps = [], []
        for sid, idx, sig in self.sections:
            sketch = doc.sketches.get(sid)
            j = find_profile(sketch, idx, sig) if sketch is not None else None
            if j is None:
                raise ValueError("A profile of the loft is gone.")
            prof = sketch.profiles[j]
            outer, _holes = _profile_world(sketch, prof)
            rings.append(outer)
            caps.append(np.asarray(prof.exterior_pts, dtype=float))
        solid = loft_solid(rings, [caps[0], caps[-1]])
        return solid if not solid.is_empty() else None

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "sections": [[s, i, list(sig)] for s, i, sig in self.sections],
                "operation": self.operation}
