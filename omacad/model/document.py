"""
Omacad - Document Model
Holds active bodies, sketches, origin reference geometry, and timeline.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List, Callable, Tuple, Any
import copy
import functools
import numpy as np
import manifold3d as m3d
from omacad.model.timeline import (
    PatternFeature, FilletFeature, Body, Timeline, BoxFeature, CylinderFeature, PrismFeature,
    SphereFeature, ExtrudeFeature, EmbossFeature, RevolveFeature, HoleFeature, DeleteBodyFeature, SketchFeature, SplitBodyFeature, ShellFeature, MoveFeature,
    ImportMeshFeature, ThreadFeature, OffsetFaceFeature, HoneycombFeature
)
from omacad.model.sketch import Sketch, SketchPlane, SketchConstraint
from omacad.model.sketch_solver import solve_sketch, SolveResult
from omacad.model import expr as exprlib
from omacad.model.faces import in_plane_edges


def undoable(label: str):
    """Marks a Document method as one undo step. Only the outermost call counts (a step that calls other steps is one
    step), and only if it changed something; the whole document state before it is kept."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if self._undo_depth > 0 or self._restoring:
                return fn(self, *args, **kwargs)
            self._undo_depth += 1
            before = self.snapshot()
            try:
                return fn(self, *args, **kwargs)
            finally:
                self._undo_depth -= 1
                try:
                    self._push_doc_undo(label, before)
                except Exception as e:   # never let book-keeping break the operation itself
                    print(f"Undo book-keeping failed for {label}: {e}")
        return wrapper
    return deco


@dataclass
class Parameter:
    """A named value usable in any numeric field: 'width', or a formula such as 'width/2 + 3'."""
    name: str
    expr: str
    comment: str = ""


ORIGIN_GROUPS = {"axis": "axes", "plane": "planes"}   # kind -> key in Document.origin_vis


def default_origin_vis() -> Dict[str, object]:
    """Axes shown, planes hidden (they only appear while picking a plane), as before this was configurable."""
    return {"all": True, "axes": {"X": True, "Y": True, "Z": True}, "planes": {"XY": False, "XZ": False, "YZ": False}}


class Document:
    """The root CAD model document."""

    def __init__(self, name: str = "Omacad - Untitled"):
        self.name: str = name
        self.units: str = "mm"
        self.bodies: Dict[str, Body] = {}
        self.sketches: Dict[str, Sketch] = {}
        self.timeline: Timeline = Timeline()
        self.auto_include_edges: bool = True   # sketching on a face includes its outline as sketch lines

        # Origin reference planes
        self.origin_planes = {
            "XY": SketchPlane.create_named("XY"),
            "XZ": SketchPlane.create_named("XZ"),
            "YZ": SketchPlane.create_named("YZ"),
        }

        # Construction (offset) planes: id -> dict(name, origin, normal, visible); absolute, not associative
        self.construction_planes: Dict[str, dict] = {}

        # What the 3D view shows of the origin: master switch, the three axes and the three planes (view state, saved)
        self.origin_vis: Dict[str, object] = default_origin_vis()

        # Saved section views: id -> dict(name, origin, normal, offset, flip, active); at most one is active
        self.sections: Dict[str, dict] = {}

        # Canvases / calibrated reference images: id -> dict(name, plane_id, image_data, width_mm, height_mm, origin_uv, rotation_deg, opacity, visible)
        self.canvases: Dict[str, dict] = {}

        # Active sketch when in Sketch Mode
        self.active_sketch: Optional[Sketch] = None

        # Selection state
        self.selected_body_ids: List[str] = []
        self.selected_profile: Optional[Tuple[str, int]] = None  # (sketch_id, profile_idx)
        self.selected_extra: List[Tuple[str, int]] = []           # more profiles added with Shift+click

        # Undo / redo of sketch edits: entries are (sketch_id, snapshot_dict)
        self.parameters: List[Parameter] = []
        self.step_states: dict = {}
        self.last_message: str = ""  # feedback from the last constraint/dimension operation
        # Undo / redo: ("sketch", sketch_id, snapshot) for edits inside a sketch, ("doc", label, snapshot) for everything else
        self.undo_stack: List[tuple] = []
        self.redo_stack: List[tuple] = []
        self._undo_depth = 0
        self._restoring = False
        self.history_listeners: List[Callable[[], None]] = []   # told when the undo/redo stacks change

        # Callbacks
        self.change_listeners: List[Callable[[], None]] = []

    def add_change_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self.change_listeners:
            self.change_listeners.append(listener)

    def notify_changed(self) -> None:
        for listener in self.change_listeners:
            try:
                listener()
            except Exception as e:
                print(f"Error in document change listener: {e}")

    # ---- Undo / redo ------------------------------------------------------------
    UNDO_LIMIT = 200       # edits inside sketches
    DOC_UNDO_LIMIT = 100   # whole-document steps

    def snapshot(self) -> dict:
        """The whole document state as plain data. Big read-only data (imported meshes) is shared, not copied."""
        from omacad.io.exporter import Exporter
        data = Exporter.document_to_dict(self)
        memo = {}
        for f in data["timeline"]:
            for key in ("vertices", "triangles"):
                if key in f:
                    memo[id(f[key])] = f[key]
        return copy.deepcopy(data, memo)

    def restore(self, snapshot: dict) -> None:
        """Puts the document back to a snapshot, in place (same object, same listeners), and rebuilds all bodies."""
        from omacad.io.exporter import Exporter
        memo = {}
        for f in snapshot.get("timeline", []):
            for key in ("vertices", "triangles"):
                if key in f:
                    memo[id(f[key])] = f[key]
        data = copy.deepcopy(snapshot, memo)
        self._restoring = True
        try:
            Exporter.apply_dict(self, data)
        finally:
            self._restoring = False

    def _history_changed(self) -> None:
        for fn in self.history_listeners:
            try:
                fn()
            except Exception as e:
                print(f"Error in history listener: {e}")

    def _push_doc_undo(self, label: str, before: dict) -> bool:
        if before == self.snapshot():
            return False
        self.undo_stack.append(("doc", label, before))
        del self.undo_stack[:-(self.UNDO_LIMIT + self.DOC_UNDO_LIMIT)]
        self.redo_stack.clear()
        self._history_changed()
        return True

    def record_sketch_change(self, sketch: Sketch, before: dict) -> bool:
        """Call after mutating a sketch with `before = sketch.to_dict()` taken first.
        Pushes an undo step only if something actually changed."""
        if before == sketch.to_dict():
            return False
        self.undo_stack.append(("sketch", sketch.sketch_id, before))
        del self.undo_stack[:-(self.UNDO_LIMIT + self.DOC_UNDO_LIMIT)]
        self.redo_stack.clear()
        self._history_changed()
        return True

    def _swap_state(self, source: List, target: List) -> Optional[str]:
        while source:
            entry = source.pop()
            if entry[0] == "doc":
                _, label, snap = entry
                target.append(("doc", label, self.snapshot()))
                self.restore(snap)
                return label
            _, sketch_id, snap = entry
            sketch = self.sketches.get(sketch_id)
            if sketch is None:
                continue
            target.append(("sketch", sketch_id, sketch.to_dict()))
            sketch.restore_from_dict(snap)
            self.timeline.recompute(self)
            self.notify_changed()
            return sketch.name
        return None

    def step_changes(self, index: int):
        """(added, removed) material of timeline step `index` as manifolds (None where nothing), from the body
        states recorded before and after it. Steps beyond the replay marker have no states and give (None, None)."""
        before, after = self.step_states.get(index), self.step_states.get(index + 1)
        if before is None or after is None:
            return None, None
        added, removed = [], []
        for bid in set(before) | set(after):
            a, b = after.get(bid), before.get(bid)
            if a is None:
                removed.append(b)
            elif b is None:
                added.append(a)
            else:
                added.append(a - b)
                removed.append(b - a)
        def merge(parts):
            parts = [p for p in parts if not p.is_empty()]
            return m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if parts else None
        return merge(added), merge(removed)

    def step_at_point(self, point, tol: float = 0.4) -> Optional[int]:
        """Index of the latest timeline step whose added or removed material touches `point` (a point on a
        body surface): the step that made that surface. None if no step claims it."""
        probe = m3d.Manifold.cube((tol, tol, tol), True).translate(tuple(float(c) for c in point))
        for i in range(len(self.timeline.features) - 1, -1, -1):
            if self.timeline.features[i].feature_type in ("sketch", "pattern"):
                continue
            for part in self.step_changes(i):
                if part is not None and not (probe ^ part).is_empty():
                    return i
        return None

    def undo(self) -> Optional[str]:
        name = self._swap_state(self.undo_stack, self.redo_stack)
        self._history_changed()
        return name

    def redo(self) -> Optional[str]:
        name = self._swap_state(self.redo_stack, self.undo_stack)
        self._history_changed()
        return name

    @staticmethod
    def _entry_label(entry) -> str:
        return entry[1] if entry[0] == "doc" else "Sketch Edit"

    def undo_label(self) -> Optional[str]:
        return self._entry_label(self.undo_stack[-1]) if self.undo_stack else None

    def redo_label(self) -> Optional[str]:
        return self._entry_label(self.redo_stack[-1]) if self.redo_stack else None

    @undoable("Box")
    def add_box(self, length: float, width: float, height: float, center: Any = False, name: Optional[str] = None,
                plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None,
                wall_thickness: float = 0.0, outer_round: float = 0.0, outer_round_kind: str = "fillet",
                inner_round: float = 0.0, inner_round_kind: str = "fillet", taper_angle: float = 0.0,
                translation: Any = None) -> Body:
        feat_id = self._feature_id("box")
        feat_name = name or f"Box {len([f for f in self.timeline.features if f.feature_type == 'box']) + 1}"
        feat = BoxFeature(feat_id, feat_name, length, width, height, center,
                          plane_origin=plane_origin, plane_normal=plane_normal, plane_u=plane_u, plane_v=plane_v,
                          wall_thickness=wall_thickness, outer_round=outer_round, outer_round_kind=outer_round_kind,
                          inner_round=inner_round, inner_round_kind=inner_round_kind, taper_angle=taper_angle,
                          translation=translation)
        feat.execute(self)
        self.timeline.add_feature(feat)
        self.notify_changed()
        return self.bodies[f"body_{feat_id}"]

    @undoable("Cylinder")
    def add_cylinder(self, radius: float, height: float, center: Any = False, name: Optional[str] = None,
                     plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None,
                     wall_thickness: float = 0.0, outer_round: float = 0.0, outer_round_kind: str = "fillet",
                     inner_round: float = 0.0, inner_round_kind: str = "fillet", taper_angle: float = 0.0,
                     translation: Any = None) -> Body:
        feat_id = self._feature_id("cylinder")
        feat_name = name or f"Cylinder {len([f for f in self.timeline.features if f.feature_type == 'cylinder']) + 1}"
        feat = CylinderFeature(feat_id, feat_name, radius, height, center,
                               plane_origin=plane_origin, plane_normal=plane_normal, plane_u=plane_u, plane_v=plane_v,
                               wall_thickness=wall_thickness, outer_round=outer_round, outer_round_kind=outer_round_kind,
                               inner_round=inner_round, inner_round_kind=inner_round_kind, taper_angle=taper_angle,
                               translation=translation)
        feat.execute(self)
        self.timeline.add_feature(feat)
        self.notify_changed()
        return self.bodies[f"body_{feat_id}"]

    @undoable("Prism")
    def add_prism(self, across_flats: float, height: float, sides: int = 6, center: Any = False,
                  name: Optional[str] = None, **params) -> Body:
        """A regular prism (hexagon by default), with the same options as `add_cylinder`."""
        feat_id = self._feature_id("prism")
        label = "Hexagon" if int(sides) == 6 else "Prism"
        feat_name = name or f"{label} {len([f for f in self.timeline.features if f.feature_type == 'prism']) + 1}"
        feat = PrismFeature(feat_id, feat_name, across_flats, height, center, sides=sides, **params)
        feat.execute(self)
        self.timeline.add_feature(feat)
        self.notify_changed()
        return self.bodies[f"body_{feat_id}"]

    @undoable("Sphere")
    def add_sphere(self, radius: float, name: Optional[str] = None, translation: Any = None) -> Body:
        feat_id = self._feature_id("sphere")
        feat_name = name or f"Sphere {len([f for f in self.timeline.features if f.feature_type == 'sphere']) + 1}"
        feat = SphereFeature(feat_id, feat_name, radius, translation=translation)
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return self.bodies[f"body_{feat_id}"]

    @undoable("Thread")
    def add_thread(
        self,
        diameter: float,
        pitch: float,
        length: float,
        is_female: bool = False,
        clearance: float = 0.0,
        profile: str = "trapezoidal_45",
        taper_lead_in: bool = True,
        taper_turns: float = 0.75,
        target_body_id: Optional[str] = None,
        operation: str = "new_body",
        name: Optional[str] = None,
        plane_origin: Any = None,
        plane_normal: Any = None,
        plane_u: Any = None,
        plane_v: Any = None,
        anchor: str = "bottom",
        anchor_gap: float = 0.0,
        host_length: Optional[float] = None,
        follow_host: bool = False,
        host_offset: float = 0.0,
        exprs: Optional[Dict[str, str]] = None,
    ) -> Optional[Body]:
        feat_id = self._feature_id("thread")
        feat_name = name or f"Thread {len([f for f in self.timeline.features if f.feature_type == 'thread']) + 1}"
        feat = ThreadFeature(
            feat_id,
            feat_name,
            diameter=diameter,
            pitch=pitch,
            length=length,
            is_female=is_female,
            clearance=clearance,
            profile=profile,
            taper_lead_in=taper_lead_in,
            taper_turns=taper_turns,
            target_body_id=target_body_id,
            operation=operation,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            plane_u=plane_u,
            plane_v=plane_v,
            anchor=anchor,
            anchor_gap=anchor_gap,
            host_length=host_length,
            follow_host=follow_host,
            host_offset=host_offset,
        )
        if exprs:
            feat.exprs = {k: v for k, v in exprs.items() if v}
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        if target_body_id and target_body_id in self.bodies and operation != "new_body":
            return self.bodies[target_body_id]
        body_id = f"body_{feat_id}"
        return self.bodies.get(body_id)


    def refresh_sketch_references(self, sketch: Sketch) -> None:
        """Face outlines of the bodies that exist now, so regions bounded by them can be profiles."""
        sketch.reference_segments = in_plane_edges(self.bodies.values(), sketch.plane)
        sketch.solve_profiles()

    def _feature_id(self, prefix: str) -> str:
        """A new step id: "<prefix>_<n>", never one already in the history (ids counted from the length repeat after a delete)."""
        taken = {f.feature_id for f in self.timeline.features}
        n = len(self.timeline.features) + 1
        while f"{prefix}_{n}" in taken:
            n += 1
        return f"{prefix}_{n}"

    def _sketch_id(self):
        """A new sketch id and its number, unused by open sketches and by sketch steps rolled back or suppressed."""
        taken = set(self.sketches) | {f.sketch.sketch_id for f in self.timeline.features if f.feature_type == "sketch"}
        n = len(self.sketches) + 1
        while f"sketch_{n}" in taken:
            n += 1
        return f"sketch_{n}", n

    @undoable("Start Sketch")
    def start_sketch(self, plane_name: str = "XY") -> Sketch:
        plane = self.origin_planes.get(plane_name.upper(), self.origin_planes["XY"])
        sketch_id, n = self._sketch_id()
        sketch = Sketch(sketch_id, f"Sketch {n}", plane)
        self.refresh_sketch_references(sketch)
        self.active_sketch = sketch
        self.sketches[sketch_id] = sketch
        self.notify_changed()
        return sketch

    @undoable("Start Sketch")
    def start_sketch_on_plane(self, plane: SketchPlane) -> Sketch:
        """Starts a sketch on an arbitrary plane (origin plane or body face)."""
        sketch_id, n = self._sketch_id()
        sketch = Sketch(sketch_id, f"Sketch {n}", plane)
        face = getattr(plane, "face", None)
        if face is not None:
            from omacad.model.sketch_rotate import face_centroid
            sketch.face_center = face_centroid(plane, face.tris)
        if face is not None and getattr(face, "body_id", None):
            sketch.parent_body_id = face.body_id
        self.refresh_sketch_references(sketch)
        if getattr(plane, "name", "") == "FACE" and self.auto_include_edges:
            sketch.include_reference_edges()   # the face outline can be used like drawn lines (offset, snap, draw on)
        self.active_sketch = sketch
        self.sketches[sketch_id] = sketch
        self.notify_changed()
        return sketch

    @undoable("Face to Sketch")
    def face_to_sketch(self, face):
        """A flat body face as a sketch (its outline, holes included) so it can be extruded like any
        profile: pull it into the body to cut a pocket, or out to build up. Returns (sketch, profile
        index). The same face reuses its sketch."""
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        plane = SketchPlane.from_face(face.normal, face.origin)
        o = np.asarray(plane.origin, dtype=float)
        ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
        tris = [Polygon([(float((p - o) @ ua), float((p - o) @ va)) for p in tri]) for tri in face.tris]
        shape = unary_union([t for t in tris if t.is_valid and t.area > 0]).buffer(0)
        if shape.geom_type == "MultiPolygon":
            shape = max(shape.geoms, key=lambda g: g.area)
        shape = shape.simplify(1e-6)
        c = shape.representative_point()
        key = (round(float(face.normal[0]), 4), round(float(face.normal[1]), 4), round(float(face.normal[2]), 4),
               round(float(np.dot(face.normal, face.origin)), 3), round(shape.area, 2), round(c.x, 2), round(c.y, 2))

        def best_profile(sk):
            return min(range(len(sk.profiles)), key=lambda i: abs(sk.profiles[i].area - shape.area)) if sk.profiles else None

        for sk in self.sketches.values():
            if sk.face_key == key and sk.profiles:
                return sk, best_profile(sk)
        n = len([k for k in self.sketches.values() if k.face_key]) + 1
        sketch_id, _ = self._sketch_id()
        sk = Sketch(sketch_id, f"Face {n}", plane)
        sk.face_key = key
        from omacad.model.sketch_rotate import face_centroid
        sk.face_center = face_centroid(plane, face.tris)
        if getattr(face, "body_id", None):
            sk.parent_body_id = face.body_id
        sk.visible = False  # a helper: it only supplies the outline for extruding
        self.refresh_sketch_references(sk)
        sk.add_loop(list(shape.exterior.coords)[:-1])
        for ring in shape.interiors:
            sk.add_loop(list(ring.coords)[:-1])
        self.sketches[sketch_id] = sk
        self.timeline.add_feature(SketchFeature(f"feat_{sketch_id}", sk.name, sk))
        self.notify_changed()
        return sk, best_profile(sk)

    def hide_used_sketches(self) -> None:
        """Sketches that already made a solid (extrude/revolve) are hidden so they stop cluttering the
        view; the eye in the browser shows them again."""
        used = {getattr(f, "sketch_id", None) for f in self.timeline.features if f.feature_type in ("extrude", "revolve", "emboss")}
        for sk in self.sketches.values():
            if sk.sketch_id in used and sk is not self.active_sketch:
                sk.visible = False

    @undoable("Finish Sketch")
    def finish_sketch(self) -> Optional[Sketch]:
        if not self.active_sketch:
            return None
        sketch = self.active_sketch
        self.active_sketch = None
        # Add to timeline if not already there
        feat_id = f"feat_{sketch.sketch_id}"
        if not any(f.feature_id == feat_id for f in self.timeline.features):
            feat = SketchFeature(feat_id, sketch.name, sketch)
            self.timeline.add_feature(feat)
        else:
            # an existing sketch was edited: everything built on it must follow
            self.timeline.recompute(self)
        self.hide_used_sketches()
        self.notify_changed()
        return sketch

    def edit_sketch(self, sketch_id: str) -> Optional[Sketch]:
        sketch = self.sketches.get(sketch_id)
        if sketch:
            sketch.visible = True
            self.active_sketch = sketch
            self.notify_changed()
            return sketch
        return None

    @undoable("Fillet")
    def add_fillet(self, edges, size: float, kind: str = "fillet", exprs=None) -> FilletFeature:
        """Fillet or chamfer the given edges ((p0, p1) world coordinates each)."""
        n = len([f for f in self.timeline.features if f.feature_type == "fillet"]) + 1
        feat_id = self._feature_id("fillet")
        feat = FilletFeature(feat_id, f"{'Chamfer' if kind == 'chamfer' else 'Fillet'} {n}", edges, size, kind)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.hide_used_sketches()
        self.notify_changed()
        return feat

    @undoable("Pattern")
    def add_pattern(self, source_ids, kind: str = "linear", exprs=None, **params) -> PatternFeature:
        """Copy what the given steps did (evenly spaced, mirrored or around an axis)."""
        self.timeline.recompute(self)  # makes sure the before/after states of the steps are current
        n = len([f for f in self.timeline.features if f.feature_type == "pattern"]) + 1
        names = {"linear": "Pattern", "mirror": "Mirror", "circular": "Circular pattern", "fill": "Fill pattern"}
        feat = PatternFeature(self._feature_id("pattern"), f"{names.get(kind, 'Pattern')} {n}",
                              source_ids, kind, **params)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Extrude")
    def extrude_profile(
        self,
        sketch_id: str,
        profile_idx: int,
        distance: float,
        operation: str = "new_body",
        name: Optional[str] = None,
        direction: str = "one_side",
        distance2: float = 0.0,
        extra_profiles=None,
        extra_refs=None,
        holes=None,
        start_offset: float = 0.0,
    ) -> None:
        feat_id = self._feature_id("extrude")
        feat_name = name or f"Extrude {len([f for f in self.timeline.features if f.feature_type == 'extrude']) + 1}"
        feat = ExtrudeFeature(feat_id, feat_name, sketch_id, profile_idx, distance, operation, direction, distance2,
                              extra_profiles=extra_profiles, extra_refs=extra_refs, holes=holes,
                              start_offset=start_offset)
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.hide_used_sketches()
        self.notify_changed()

    @undoable("Emboss")
    def add_emboss(self, sketch_id: str, profile_idx: int, depth: float = 1.0, flip: bool = False, dx: float = 0.0,
                   dy: float = 0.0, rotation: float = 0.0, wrap: bool = True, extra_profiles=None, extra_refs=None, exprs=None):
        """Fusion's Emboss: raise (depth > 0) or press in (depth < 0) the chosen sketch profiles from the face they sit on."""
        feat_id = self._feature_id("emboss")
        feat_name = f"Emboss {len([f for f in self.timeline.features if f.feature_type == 'emboss']) + 1}"
        feat = EmbossFeature(feat_id, feat_name, sketch_id, profile_idx, depth, flip=flip, dx=dx, dy=dy, rotation=rotation,
                             wrap=wrap, extra_profiles=extra_profiles, extra_refs=extra_refs)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.hide_used_sketches()
        self.notify_changed()
        return feat

    @undoable("Revolve")
    def add_revolve(self, sketch_id: str, profile_idx: int, axis=("v",), angle: float = 360.0, operation: str = "new_body",
                    direction: str = "one_side", angle2: float = 0.0, extra_profiles=None, exprs=None):
        feat_id = self._feature_id("revolve")
        feat_name = f"Revolve {len([f for f in self.timeline.features if f.feature_type == 'revolve']) + 1}"
        feat = RevolveFeature(feat_id, feat_name, sketch_id, profile_idx, operation=operation, axis=axis, angle=angle,
                              direction=direction, angle2=angle2, extra_profiles=extra_profiles)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.hide_used_sketches()
        self.notify_changed()
        return feat

    @undoable("Hole")
    def add_hole(self, points, exprs=None, **params) -> HoleFeature:
        feat_id = self._feature_id("hole")
        feat = HoleFeature(feat_id, f"Hole {len([f for f in self.timeline.features if f.feature_type == 'hole']) + 1}", points, **params)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    def select_body(self, body_id: Optional[str], multi: bool = False) -> None:
        if not multi:
            for b in self.bodies.values():
                b.selected = False
            self.selected_body_ids = []

        if body_id and body_id in self.bodies:
            self.bodies[body_id].selected = True
            if body_id not in self.selected_body_ids:
                self.selected_body_ids.append(body_id)

        self.notify_changed()

    # ---- Parameters ---------------------------------------------------------------------
    def evaluate_parameters(self, params=None):
        """(values, errors). Parameters may refer to ones defined later; cycles and unknown names
        are reported per parameter."""
        pending = list(self.parameters if params is None else params)
        values: Dict[str, float] = {}
        progress = True
        while pending and progress:
            progress = False
            for q in list(pending):
                try:
                    values[q.name] = exprlib.evaluate(q.expr, values)
                except ValueError:
                    continue
                pending.remove(q)
                progress = True
        errors: Dict[str, str] = {}
        for q in pending:
            try:
                exprlib.evaluate(q.expr, values)
            except ValueError as e:
                msg = str(e)
                errors[q.name] = "circular or unresolved reference" if msg.startswith("unknown name") else msg
        return values, errors

    def parameter_values(self) -> Dict[str, float]:
        return self.evaluate_parameters()[0]

    def validate_parameters(self, params) -> List[str]:
        """Problems that make a parameter list unusable (empty/duplicate/reserved names, errors)."""
        problems, seen = [], set()
        for q in params:
            if not exprlib.is_valid_name(q.name):
                problems.append(f"'{q.name}' is not a valid parameter name (letters, digits and _, not starting with a digit; "
                                f"x, e, pi and function names are reserved).")
            elif q.name in seen:
                problems.append(f"The name '{q.name}' is used twice.")
            seen.add(q.name)
        _, errors = self.evaluate_parameters(params)
        problems += [f"{n}: {m}" for n, m in errors.items()]
        return problems

    @undoable("Change Parameters")
    def set_parameters(self, params) -> List[str]:
        """Replaces the parameter list and rebuilds the model. Returns problems (nothing is changed then)."""
        problems = self.validate_parameters(params)
        if problems:
            return problems
        old = self.parameters
        self.parameters = [Parameter(q.name.strip(), q.expr.strip(), q.comment) for q in params]
        # a renamed/removed parameter that is still used would leave formulas dangling: report it
        dangling = self.unresolved_formulas()
        if dangling:
            self.parameters = old
            return dangling
        self.timeline.recompute(self)
        self.notify_changed()
        return []

    def unresolved_formulas(self) -> List[str]:
        values = self.parameter_values()
        bad = []
        for sk in self.sketches.values():
            for d in sk.dimensions:
                if d.expr:
                    try:
                        exprlib.evaluate(d.expr, values)
                    except ValueError as e:
                        bad.append(f"{sk.name} {d.dim_id} uses '{d.expr}': {e}")
        for f in self.timeline.features:
            for key, e in f.exprs.items():
                try:
                    exprlib.evaluate(e, values)
                except ValueError as err:
                    bad.append(f"{f.name} {key} uses '{e}': {err}")
        return bad

    def refresh_parameters(self) -> List[str]:
        """Re-evaluates every formula against the current parameters and updates dimensions and steps."""
        values, errors = self.evaluate_parameters()
        exprlib.set_variables(values)
        messages = [f"{n}: {m}" for n, m in errors.items()]
        for sk in list(self.sketches.values()):
            for dim in sk.dimensions:
                if not dim.expr:
                    continue
                try:
                    v = exprlib.evaluate(dim.expr, values)
                except ValueError as e:
                    messages.append(f"{sk.name} {dim.dim_id}: {e}")
                    continue
                if abs(v - dim.value) > 1e-9:
                    if not self._apply_dimension_value(sk, dim, v):
                        messages.append(f"{sk.name} {dim.dim_id}: {self.last_message}")
        for f in self.timeline.features:
            for key, e in f.exprs.items():
                try:
                    v = float(exprlib.evaluate(e, values))
                    old = getattr(f, key)
                    if isinstance(old, int) and not isinstance(old, bool):
                        v = max(3, round(v)) if key == "sides" else round(v)   # counts stay whole numbers
                    setattr(f, key, v)
                except (ValueError, AttributeError) as err:
                    messages.append(f"{f.name} {key}: {err}")
        if messages:
            self.last_message = "; ".join(messages)
        return messages

    def _apply_dimension_value(self, sketch, dim, value: float) -> bool:
        """Sets a dimension and lets the solver move the geometry; restores it if that is impossible."""
        before = sketch.to_dict()
        if value <= 0.001 and dim.dim_type != "PT_LINE_DIST":
            self.last_message = "value must be positive"
            return False
        if not sketch.set_dimension_value(dim.dim_id, value):
            return False
        res = self._solve_anchored(sketch, dim)
        if not res.ok:
            sketch.restore_from_dict(before)
            self.last_message = res.message
            return False
        return True

    # ---- Editing the history (timeline) ----------------------------------------------
    EDITABLE = {
        "box": ("length", "width", "height", "center", "plane_origin", "plane_normal", "plane_u", "plane_v",
                "wall_thickness", "outer_round", "outer_round_kind", "inner_round", "inner_round_kind", "taper_angle"),
        "cylinder": ("radius", "height", "center", "plane_origin", "plane_normal", "plane_u", "plane_v",
                     "wall_thickness", "outer_round", "outer_round_kind", "inner_round", "inner_round_kind", "taper_angle"),
        "prism": ("across_flats", "sides", "height", "center", "plane_origin", "plane_normal", "plane_u", "plane_v",
                  "wall_thickness", "outer_round", "outer_round_kind", "inner_round", "inner_round_kind", "taper_angle"),
        "sphere": ("radius",),
        "extrude": ("sketch_id", "profile_idx", "distance", "direction", "distance2", "start_offset", "operation"),
        "emboss": ("sketch_id", "profile_idx", "depth", "flip", "dx", "dy", "rotation", "wrap"),
        "revolve": ("sketch_id", "profile_idx", "segments", "operation", "axis", "angle", "direction", "angle2", "extra_profiles"),
        "combine": ("target_body_id", "tool_body_id", "operation", "keep_tool"),
        "fillet": ("size", "kind"),
        "thread": ("diameter", "pitch", "length", "is_female", "clearance", "profile", "taper_lead_in", "taper_turns", "target_body_id", "operation", "plane_origin", "plane_normal", "plane_u", "plane_v", "anchor", "anchor_gap", "host_length", "grow", "follow_host", "host_offset"),
        "pattern": ("source_ids", "kind", "axis1", "count1", "spacing1", "axis2", "count2", "spacing2",
                    "mirror_mode", "about", "angle", "rotation_axis", "axis_origin", "axis_direction"),
        "split_body": ("target_body_id", "plane_id", "plane_origin", "plane_normal"),
        "shell": ("thickness", "direction", "thickness2", "open_faces"),
        "offset_face": ("distance",),
        "honeycomb": HoneycombFeature.PARAMS,
        "hole": ("points", "hole_type", "diameter", "depth", "through", "cb_diameter", "cb_depth", "cs_diameter", "cs_angle", "tip", "tip_angle"),
        "move": ("target_body_id", "dx", "dy", "dz", "rx", "ry", "rz", "pivot", "from_point", "to_point", "copy_body"),
    }

    @undoable("Edit Feature")
    def edit_feature(self, index: int, **params) -> bool:
        """Changes the parameters of a step and rebuilds everything after it."""
        if not (0 <= index < len(self.timeline.features)):
            return False
        feat = self.timeline.features[index]
        allowed = self.EDITABLE.get(feat.feature_type, ())
        changed = False
        if "exprs" in params:  # formulas for fields; fields without one go back to plain numbers
            new = {k: v for k, v in (params.pop("exprs") or {}).items() if k in allowed and v}
            if new != feat.exprs:
                feat.exprs = new
                changed = True
        for key, value in params.items():
            if key == "sides":
                value = max(3, int(round(value)))       # a prism needs at least three sides, as when it was made
            if key in allowed and getattr(feat, key) != value:
                setattr(feat, key, float(value) if isinstance(getattr(feat, key), float) else value)
                changed = True
        if changed:
            self.timeline.recompute(self)
            self.notify_changed()
        return changed

    @undoable("Rename")
    def rename_feature(self, index: int, name: str) -> bool:
        name = name.strip()
        if not name or not (0 <= index < len(self.timeline.features)):
            return False
        feat = self.timeline.features[index]
        feat.name = name
        if isinstance(feat, SketchFeature):
            feat.sketch.name = name
        self.timeline.recompute(self)  # bodies take their name from the feature that made them
        self.notify_changed()
        return True

    @undoable("Suppress")
    def toggle_suppress(self, index: int) -> bool:
        """Switches a step off/on without deleting it."""
        if not (0 <= index < len(self.timeline.features)):
            return False
        feat = self.timeline.features[index]
        feat.suppressed = not feat.suppressed
        self.timeline.recompute(self)
        self.notify_changed()
        return feat.suppressed

    def dependents_of(self, index: int) -> list:
        """Indices of later steps that need step `index` (extrudes of a sketch, combines/modifies of its bodies)."""
        feats = self.timeline.features
        feat = feats[index]
        out = []
        body_ids = {f"body_{feat.feature_id}"}
        for j in range(index + 1, len(feats)):
            other = feats[j]
            uses_sketch = (isinstance(feat, SketchFeature)
                           and getattr(other, "sketch_id", None) == feat.sketch.sketch_id)
            uses_body = (
                getattr(other, "target_body_id", None) in body_ids
                or getattr(other, "tool_body_id", None) in body_ids
                or (other.feature_type == "pattern" and feat.feature_id in (getattr(other, "source_ids", None) or []))
            )
            if uses_sketch or uses_body:
                out.append(j)
        return out

    @undoable("Delete Feature")
    def delete_feature(self, index: int, with_dependents: bool = True) -> list:
        """Removes a step (and, by default, the steps built on it). Returns the removed names."""
        if not (0 <= index < len(self.timeline.features)):
            return []
        doomed = {index} | (set(self.dependents_of(index)) if with_dependents else set())
        # dependents of dependents (e.g. a combine of a body made by a deleted extrude)
        grew = True
        while grew and with_dependents:
            grew = False
            for i in sorted(doomed):
                for j in self.dependents_of(i):
                    if j not in doomed:
                        doomed.add(j)
                        grew = True
        removed = [self.timeline.features[i].name for i in sorted(doomed)]
        t = self.timeline
        t.marker_index -= sum(1 for i in doomed if i < t.marker_index)
        t.features = [f for i, f in enumerate(t.features) if i not in doomed]
        t.marker_index = max(0, min(t.marker_index, len(t.features)))
        self.timeline.recompute(self)
        self.notify_changed()
        return removed

    @undoable("Rename")
    def rename_item(self, kind: str, item_id: str, name: str) -> bool:
        """Renames a sketch, body, section or construction plane. The creating feature is renamed too, so the name survives
        recompute, save and load."""
        name = name.strip()
        if not name:
            return False
        if kind == "sketch":
            sketch = self.sketches.get(item_id)
            if not sketch:
                return False
            sketch.name = name
            for f in self.timeline.features:
                if isinstance(f, SketchFeature) and f.sketch is sketch:
                    f.name = name
        elif kind == "section":
            if item_id not in self.sections:
                return False
            self.sections[item_id]["name"] = name
        elif kind == "cplane":
            if item_id not in self.construction_planes:
                return False
            self.construction_planes[item_id]["name"] = name
        elif kind == "body":
            body = self.bodies.get(item_id)
            if not body:
                return False
            body.name = name
            for f in self.timeline.features:
                if f"body_{f.feature_id}" == item_id:
                    f.name = name
                    if hasattr(f, "new_body_name"):
                        f.new_body_name = name
        else:
            return False
        self.notify_changed()
        return True


    @undoable("Combine")
    def combine_bodies(self, target_id: str, tool_id: str, operation: str = "join", keep_tool: bool = False):
        """Join / Cut / Intersect two bodies as one history step (the tool body goes away unless `keep_tool`)."""
        from omacad.model.features.boolean import CombineFeature
        if target_id == tool_id or target_id not in self.bodies or tool_id not in self.bodies:
            return None
        feat = CombineFeature(self._feature_id("combine"), f"Combine ({operation})", target_id, tool_id,
                              operation, keep_tool=keep_tool)
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Join")
    def join_bodies(self, body_ids: List[str]):
        """Joins all the given bodies into the first one (a right-click with several bodies selected)."""
        ids = [b for b in dict.fromkeys(body_ids) if b in self.bodies]
        if len(ids) < 2:
            return None
        target = ids[0]
        for other in ids[1:]:
            self.combine_bodies(target, other, "join")
        self.select_body(target)
        return self.bodies.get(target)

    @undoable("Split Body")
    def split_body(self, body_id: str, plane_id: str, new_body_name: Optional[str] = None) -> Optional[SplitBodyFeature]:
        """Splits an existing body using an offset (construction) plane or origin plane into two separate bodies."""
        if body_id not in self.bodies:
            return None
        n = len([f for f in self.timeline.features if f.feature_type == "split_body"]) + 1
        feat_id = self._feature_id("split")
        plane_origin, plane_normal = None, None
        if plane_id in self.construction_planes:
            cp = self.construction_planes[plane_id]
            plane_origin = list(cp["origin"])
            plane_normal = list(cp["normal"])
        elif plane_id in self.origin_planes:
            op = self.origin_planes[plane_id]
            plane_origin = list(op.origin)
            plane_normal = list(op.normal)
        feat = SplitBodyFeature(
            feat_id, f"Split Body {n}", body_id, plane_id,
            plane_origin=plane_origin, plane_normal=plane_normal,
            new_body_name=new_body_name
        )
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Shell")
    def add_shell(self, body_id: str, thickness: float, open_faces=None, exprs=None, direction: str = "inside", thickness2: float = 2.0) -> Optional[ShellFeature]:
        """Hollows out the body with a given wall thickness, optionally leaving selected faces open."""
        if body_id not in self.bodies:
            return None
        self.timeline.recompute(self)  # Shell reads the body's history (step_states): it must be current, as on reload
        n = len([f for f in self.timeline.features if f.feature_type == "shell"]) + 1
        feat_id = self._feature_id("shell")
        feat = ShellFeature(feat_id, f"Shell {n}", body_id, thickness, open_faces=open_faces, direction=direction, thickness2=thickness2)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.hide_used_sketches()
        self.notify_changed()
        return feat

    def _thread_offset(self, faces):
        """(thread feature, sign, shift) when every picked face belongs to the same thread: its coil, or the wall between
        the turns (a coaxial cylinder inside the threaded length). Else None."""
        if not faces or any(r.get("kind") not in ("surface", "cylinder") for r in faces):
            return None
        feats = self.timeline.features
        for i, f in enumerate(feats):
            if f.feature_type != "thread" or f.suppressed:
                continue
            shifts, here = [(0.0, 0.0, 0.0)], np.zeros(3)
            for g in feats[i + 1:]:                       # the body may have been moved (not turned) since
                if g.feature_type == "move" and not g.suppressed:
                    if abs(g.rx) > 1e-4 or abs(g.ry) > 1e-4 or abs(g.rz) > 1e-4:
                        break
                    here = here + (g.dx, g.dy, g.dz)
                    shifts.append(tuple(here))
            hits = [f.surface_sign(r["point"], r["normal"], shifts) if r["kind"] == "surface" else f.cylinder_sign(r, shifts)
                    for r in faces]
            keys = {(sign, tuple(shift) if shift is not None else None) for sign, shift in hits}
            if len(keys) == 1 and hits[0][0] != 0:
                return f, hits[0][0], hits[0][1]
        return None

    def thread_faces(self, faces):
        """The picked faces as one thread reference when they all belong to the same thread (see `_thread_offset`):
        Offset Face then cuts or adds a grown/shrunk copy of the threaded zone on this body only; else None."""
        hit = self._thread_offset(faces)
        if hit is None:
            return None
        feat, sign, shift = hit
        return [{"kind": "thread", "thread_id": feat.feature_id, "sign": int(sign), "shift": [float(x) for x in shift]}]

    @undoable("Offset Face")
    def add_offset_face(self, body_id: str, faces, distance: float, exprs=None) -> Optional[OffsetFaceFeature]:
        """Moves the given faces of a body by `distance` (+ adds material, - removes it)."""
        if body_id not in self.bodies or not faces:
            return None
        faces = self.thread_faces(faces) or faces    # a thread: only this body changes, the other part keeps its size
        n = len([f for f in self.timeline.features if f.feature_type == "offset_face"]) + 1
        feat = OffsetFaceFeature(self._feature_id("offset_face"), f"Offset Face {n}", body_id, faces, distance)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Jar with Lid")
    def add_jar(self, spec) -> Dict[str, str]:
        """A threaded jar and its screw lid (see model/jar.py) as one undo step: {"jar": body id, "lid": body id}."""
        from omacad.model.jar import build_jar
        return build_jar(self, spec)

    @undoable("Honeycomb")
    def add_honeycomb(self, body_id: str, faces, exprs=None, **params) -> Optional[HoneycombFeature]:
        """Cuts a lattice of cells (shape, size, wall, margin, depth or through, angle) into faces of a body."""
        if body_id not in self.bodies or not faces:
            return None
        n = len([f for f in self.timeline.features if f.feature_type == "honeycomb"]) + 1
        feat = HoneycombFeature(self._feature_id("honeycomb"), f"Honeycomb {n}", body_id, faces, **params)
        feat.exprs = dict(exprs or {})
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Move")
    def move_body(
        self,
        body_id: str,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        pivot: str = "center",
        exprs: Optional[dict] = None,
        from_point: Optional[dict] = None,
        to_point: Optional[dict] = None,
        copy_body: bool = False,
    ) -> Optional[MoveFeature]:
        """Translates and rotates a 3D solid body parametrically (optionally point to point, see MoveFeature)."""
        if body_id not in self.bodies:
            return None
        n = len([f for f in self.timeline.features if f.feature_type == "move"]) + 1
        feat_id = self._feature_id("move")
        target_name = self.bodies[body_id].name
        feat = MoveFeature(feat_id, f"Move {target_name} ({n})", body_id, dx, dy, dz, rx, ry, rz, pivot=pivot,
                           from_point=from_point, to_point=to_point, copy_body=copy_body)
        if exprs:
            feat.exprs = exprs
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    @undoable("Lay flat")
    def lay_face_on(self, body_id: str, face_normal, face_origin, plane_point, plane_normal) -> Optional[MoveFeature]:
        """Turns and moves a body so that one of its flat faces lies on a plane (the face then points
        against the plane's normal, like a part resting on it). Done as a normal Move step."""
        from omacad.model.geometry import rotation_aligning, euler_xyz_degrees
        body = self.bodies.get(body_id)
        if body is None or body.render_mesh is None:
            return None
        n = np.asarray(face_normal, dtype=float)
        n = n / np.linalg.norm(n)
        pn = np.asarray(plane_normal, dtype=float)
        pn = pn / np.linalg.norm(pn)
        R = rotation_aligning(n, -pn)
        rx, ry, rz = euler_xyz_degrees(R)
        centre = (np.asarray(body.render_mesh.bounds_min, dtype=float) + np.asarray(body.render_mesh.bounds_max, dtype=float)) * 0.5
        moved = centre + R @ (np.asarray(face_origin, dtype=float) - centre)
        shift = pn * float((np.asarray(plane_point, dtype=float) - moved) @ pn)   # only along the plane normal
        return self.move_body(body_id, float(shift[0]), float(shift[1]), float(shift[2]), rx, ry, rz, pivot="center")

    @undoable("Import")
    def import_mesh(
        self,
        name: str,
        vertices: List[List[float]],
        triangles: List[List[int]],
        source_file: str = "",
    ) -> ImportMeshFeature:
        """Adds an imported 3D mesh (e.g. from 3MF) as a parametric solid body."""
        feat_id = self._feature_id("import")
        feat = ImportMeshFeature(feat_id, name, vertices, triangles, source_file=source_file)
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.notify_changed()
        return feat

    # ---- Canvases / Reference Images ----------------------------------------
    @undoable("Insert Canvas")
    def add_canvas(self, name: str, plane_id: str, image_data: str, width_mm: float, height_mm: float,
                   origin_uv: Tuple[float, float] = (0.0, 0.0), rotation_deg: float = 0.0,
                   opacity: float = 0.5, visible: bool = True) -> str:
        cid = f"canvas_{len(self.canvases) + 1}"
        while cid in self.canvases:
            cid += "_"
        self.canvases[cid] = {
            "name": name or f"Canvas {len(self.canvases) + 1}",
            "plane_id": plane_id,
            "image_data": image_data,
            "width_mm": float(width_mm),
            "height_mm": float(height_mm),
            "origin_uv": [float(origin_uv[0]), float(origin_uv[1])],
            "rotation_deg": float(rotation_deg),
            "opacity": float(opacity),
            "visible": bool(visible),
        }
        self.notify_changed()
        return cid

    @undoable("Edit Canvas")
    def update_canvas(self, cid: str, **kw) -> None:
        if cid in self.canvases:
            self.canvases[cid].update(kw)
            self.notify_changed()

    @undoable("Delete Canvas")
    def delete_canvas(self, cid: str) -> None:
        if self.canvases.pop(cid, None) is not None:
            self.notify_changed()

    def toggle_canvas_visibility(self, cid: str) -> None:
        if cid in self.canvases:
            self.canvases[cid]["visible"] = not self.canvases[cid].get("visible", True)
            self.notify_changed()

    def toggle_body_visibility(self, body_id: str) -> None:
        if body_id in self.bodies:
            self.bodies[body_id].visible = not self.bodies[body_id].visible
            self.notify_changed()

    @undoable("Offset Plane")
    def add_construction_plane(self, base_plane, distance: float, name: str = None, origin=None) -> str:
        """A plane parallel to `base_plane`, `distance` mm along its normal.

        `origin` optionally supplies an in-plane-shifted base point.
        """
        n = np.asarray(base_plane.normal, dtype=float)
        n = n / np.linalg.norm(n)
        pid = f"plane_{len(self.construction_planes) + 1}"
        while pid in self.construction_planes:
            pid += "_"
        plane_origin = np.asarray(base_plane.origin if origin is None else origin, dtype=float) + n * float(distance)
        self.construction_planes[pid] = {"name": name or f"Plane {len(self.construction_planes) + 1}",
                                         "origin": [float(x) for x in plane_origin], "normal": [float(x) for x in n], "visible": True}
        self.notify_changed()
        return pid

    @undoable("Section View")
    def add_section(self, origin, normal, offset: float, flip: bool = False, name: str = None, activate: bool = True) -> str:
        sid = f"section_{len(self.sections) + 1}"
        while sid in self.sections:
            sid += "_"
        self.sections[sid] = {"name": name or f"Section {len(self.sections) + 1}", "origin": [float(x) for x in origin],
                              "normal": [float(x) for x in normal], "offset": float(offset), "flip": bool(flip), "active": False}
        if activate:
            self.set_section_active(sid, True)
        else:
            self.notify_changed()
        return sid

    @undoable("Edit Section View")
    def update_section(self, sid: str, **kw) -> None:
        if sid in self.sections:
            self.sections[sid].update(kw)
            self.notify_changed()

    def set_section_active(self, sid: str, on: bool) -> None:
        if sid not in self.sections:
            return
        for k, v in self.sections.items():
            v["active"] = (k == sid) and on        # one section at a time
        self.notify_changed()

    @undoable("Delete Section View")
    def delete_section(self, sid: str) -> None:
        if self.sections.pop(sid, None) is not None:
            self.notify_changed()

    def active_section(self):
        return next(((k, v) for k, v in self.sections.items() if v.get("active")), None)

    def construction_plane(self, pid: str):
        from omacad.model.sketch import SketchPlane
        c = self.construction_planes[pid]
        plane = SketchPlane.from_face(np.array(c["normal"]), np.array(c["origin"]), name="PLANE")
        # from_face chooses a canonical origin on the normal through world
        # origin. Construction planes also store an in-plane centre for their
        # viewport marker, so retain that exact point.
        plane.origin = np.asarray(c["origin"], dtype=np.float32)
        return plane

    @undoable("Delete Plane")
    def delete_construction_plane(self, pid: str) -> None:
        if self.construction_planes.pop(pid, None) is not None:
            self.notify_changed()

    def set_origin_visibility(self, kind: str, name: str, visible: bool) -> None:
        """kind: "all" (the whole origin), "axis" (X/Y/Z) or "plane" (XY/XZ/YZ). View state, not an undo step."""
        if kind == "all":
            self.origin_vis["all"] = bool(visible)
        elif kind in ORIGIN_GROUPS and name in self.origin_vis[ORIGIN_GROUPS[kind]]:
            self.origin_vis[ORIGIN_GROUPS[kind]][name] = bool(visible)
            if visible:
                self.origin_vis["all"] = True   # turning one part on shows the origin again
        else:
            return
        self.notify_changed()

    def origin_visible(self, kind: str = "all", name: str = "") -> bool:
        """Is this part drawn? An axis or plane needs both its own switch and the master switch."""
        if kind == "all":
            return bool(self.origin_vis["all"])
        return bool(self.origin_vis["all"] and self.origin_vis[ORIGIN_GROUPS[kind]].get(name, False))

    def toggle_construction_plane(self, pid: str) -> None:
        if pid in self.construction_planes:
            self.construction_planes[pid]["visible"] = not self.construction_planes[pid]["visible"]
            self.notify_changed()

    def feature_index_for(self, kind: str, item_id: str) -> Optional[int]:
        """The timeline step that made a sketch or body (for "Find in Timeline"), or None."""
        for i, f in enumerate(self.timeline.features):
            if kind == "sketch" and f.feature_type == "sketch" and f.sketch.sketch_id == item_id:
                return i
            if kind == "body" and (f.feature_id == item_id[5:] or getattr(f, "body_id", None) == item_id):
                return i
        if kind == "body":
            return next((i for i, f in enumerate(self.timeline.features) if getattr(f, "target_body_id", None) == item_id), None)
        return None

    def set_group_visibility(self, group: str, visible: bool) -> None:
        """The eye on a browser group: show or hide everything in it ("bodies", "sketches", "canvases", "planes")."""
        if group == "bodies":
            for b in self.bodies.values():
                b.visible = visible
        elif group == "sketches":
            for s in self.sketches.values():
                s.visible = visible
        elif group == "canvases":
            for c in self.canvases.values():
                c["visible"] = visible
        elif group == "planes":
            for c in self.construction_planes.values():
                c["visible"] = visible
        else:
            return
        self.notify_changed()

    def toggle_sketch_visibility(self, sketch_id: str) -> None:
        if sketch_id in self.sketches:
            self.sketches[sketch_id].visible = not self.sketches[sketch_id].visible
            self.notify_changed()

    @undoable("Delete Body")
    def delete_body(self, body_id: str) -> None:
        """A real step in the history, so it survives a rebuild (and can be undone)."""
        body = self.bodies.get(body_id)
        if body is None:
            return
        feat = DeleteBodyFeature(self._feature_id("delete"), f"Delete {body.name}", body_id)
        self.timeline.add_feature(feat)
        feat.execute(self)
        self.selected_body_ids = [b for b in self.selected_body_ids if b in self.bodies]
        self.notify_changed()

    def delete_sketch_entities(self, sketch_id: str, entity_ids) -> int:
        """Deletes sketch entities and recomputes features that depend on the sketch."""
        sketch = self.sketches.get(sketch_id)
        if not sketch:
            return 0
        before = sketch.to_dict()
        n = sketch.delete_entities(entity_ids)
        self.record_sketch_change(sketch, before)
        if n:
            self.timeline.recompute(self)
            self.notify_changed()
        return n

    # ---- Constraints ---------------------------------------------------------
    DRIVING_DIMS = ("LENGTH", "DIAMETER", "RADIUS")

    def add_constraints(self, sketch_id: str, specs) -> bool:
        """specs: [(ctype, [entity ids], [point names])]. Solves immediately; on a conflict the
        dimensions of the involved entities are released once, and if it still fails the sketch is
        restored. The outcome message is left in self.last_message."""
        sketch = self.sketches.get(sketch_id)
        if not sketch or not specs:
            return False
        before = sketch.to_dict()
        for ctype, refs, pts in specs:
            sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), ctype, list(refs), list(pts)))
        res = solve_sketch(sketch)
        released = 0
        if not res.ok:
            involved = {r for _, refs, _ in specs for r in refs}
            keep = [d for d in sketch.dimensions
                    if not (d.target_entity_id in involved and d.dim_type in self.DRIVING_DIMS)]
            released = len(sketch.dimensions) - len(keep)
            if released:
                sketch.dimensions = keep
                res = solve_sketch(sketch)
        if not res.ok:
            sketch.restore_from_dict(before)
            self.last_message = res.message + " - constraint not added."
            return False
        self.record_sketch_change(sketch, before)
        self.last_message = self.sketch_status(sketch) + (f" ({released} conflicting dimension(s) released)" if released else "")
        self.timeline.recompute(self)
        self.notify_changed()
        return True

    def auto_constrain(self, sketch: Sketch, specs) -> int:
        """Adds constraints without notifying or recording undo (used inside a drawing step that
        records its own undo). Constraints that would not solve are dropped. Returns how many stuck."""
        added = 0
        for ctype, refs, pts in specs:
            c = SketchConstraint(sketch.new_constraint_id(), ctype, list(refs), list(pts))
            sketch.constraints.append(c)
            snapshot = sketch.to_dict()
            if solve_sketch(sketch).ok:
                added += 1
            else:
                sketch.constraints.remove(c)
                sketch.restore_from_dict(snapshot)
        return added

    def remove_constraint(self, sketch_id: str, cid: str) -> bool:
        sketch = self.sketches.get(sketch_id)
        if not sketch or not any(c.cid == cid for c in sketch.constraints):
            return False
        before = sketch.to_dict()
        sketch.constraints = [c for c in sketch.constraints if c.cid != cid]
        solve_sketch(sketch)
        self.record_sketch_change(sketch, before)
        self.last_message = "Constraint removed. " + self.sketch_status(sketch)
        self.timeline.recompute(self)
        self.notify_changed()
        return True

    @staticmethod
    def sketch_status(sketch: Sketch) -> str:
        if sketch.dof is None:
            return ""
        return "Fully defined" if sketch.dof == 0 else f"Under defined ({sketch.dof} DOF)"

    def add_dimension_constraint(self, sketch_id: str, dim_type: str, target: str, value: float,
                                 refs=(), pts=(), offset: float = 12.0, expr: Optional[str] = None) -> bool:
        """Adds a driving dimension (angle, distance ...) and solves. Restores the sketch and returns
        False with a message if it conflicts with existing constraints."""
        sketch = self.sketches.get(sketch_id)
        if not sketch:
            return False
        before = sketch.to_dict()
        tgt = next((e for e in sketch.entities if e.entity_id == target), None)
        if tgt is not None and getattr(tgt, "group", None) and dim_type in ("LENGTH", "DIAMETER", "RADIUS"):
            # a regular polygon has one size: a new side/corner-circle dimension replaces the old one
            members = {m.entity_id for m in sketch.group_entities(tgt)}
            sketch.dimensions = [d for d in sketch.dimensions
                                 if not (d.target_entity_id in members and d.dim_type in ("LENGTH", "DIAMETER", "RADIUS"))]
        sketch.add_dimension(dim_type, target, value, offset_distance=offset, refs=list(refs), pts=list(pts))
        dim = sketch.dimensions[-1]
        dim.expr = expr
        res = self._solve_anchored(sketch, dim)
        if not res.ok:
            sketch.restore_from_dict(before)
            self.last_message = res.message + " - dimension not added."
            self.notify_changed()
            return False
        self.record_sketch_change(sketch, before)
        self.last_message = f"Added {dim.dim_id}. " + self.sketch_status(sketch)
        self.timeline.recompute(self)
        self.notify_changed()
        return True

    def _solve_anchored(self, sketch, dim) -> "SolveResult":
        """Solve holding the dimension's anchor still; if other constraints need that anchor to move
        (e.g. a diameter change that shifts a circle held at an edge distance) retry without it."""
        anchor = self._anchor_for(dim)
        ent = next((e for e in sketch.entities if e.entity_id == dim.target_entity_id), None)
        if ent is not None and getattr(ent, "group", None) and dim.dim_type in ("LENGTH", "DIAMETER", "RADIUS"):
            ctr = next((m for m in sketch.group_entities(ent) if m.entity_type == "circle"), None)
            if ctr is not None:   # a polygon grows round its centre
                anchor = {"pinned": [(ctr.entity_id, "center")]}
        res = solve_sketch(sketch, **anchor)
        if not res.ok and anchor:
            res = solve_sketch(sketch)
        return res

    @staticmethod
    def _anchor_for(dim) -> dict:
        """What stays put while a dimension is solved/edited: the dimension grows from its first object."""
        if any(r.startswith("ref:") for r in dim.refs):
            return {}  # measured to a fixed face edge: the dimensioned point is the only thing that can move
        if dim.dim_type == "ANGLE":
            return {"fixed_ids": [dim.target_entity_id]}
        if dim.dim_type == "PT_LINE_DIST" and dim.refs:
            return {"fixed_ids": [dim.refs[0]]}   # the line measured from stays put (also its direction)
        if dim.dim_type in ("DISTANCE", "HORIZ_DIST", "VERT_DIST") and dim.pts:
            return {"pinned": [(dim.target_entity_id, "center" if dim.pts[0] in ("edge_near", "edge_far") else dim.pts[0])]}
        if dim.dim_type == "LENGTH":
            return {"pinned": [(dim.target_entity_id, "p1")]}
        return {"pinned": [(dim.target_entity_id, "center")]}

    def update_dimension(self, sketch_id: str, dim_id: str, new_value: float, expr: Optional[str] = None) -> bool:
        """Parametrically updates a sketch dimension and recomputes all downstream timeline features."""
        sketch = self.sketches.get(sketch_id)
        before = sketch.to_dict() if sketch else None
        if sketch and sketch.set_dimension_value(dim_id, new_value):
            dim = next((d for d in sketch.dimensions if d.dim_id == dim_id), None)
            if dim is not None:
                dim.expr = expr
            res = self._solve_anchored(sketch, dim) if dim is not None else solve_sketch(sketch)
            if not res.ok:
                sketch.restore_from_dict(before)
                self.last_message = res.message + " - dimension unchanged."
                self.notify_changed()
                return False
            self.record_sketch_change(sketch, before)
            self.timeline.recompute(self)
            self.notify_changed()
            return True
        return False
