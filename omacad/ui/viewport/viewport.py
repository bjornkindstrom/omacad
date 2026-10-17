from omacad.ui.viewport.shaders import (
    VERTEX_SHADER_SOLID, FRAGMENT_SHADER_SOLID, VERTEX_SHADER_FLAT,
    FRAGMENT_SHADER_FLAT, VERTEX_SHADER_TEXTURE, FRAGMENT_SHADER_TEXTURE,
    VERTEX_SHADER_THICK, SKETCH_GROUP_ICONS
)
from omacad.ui.viewport.render_mixin import RenderGLMixin
from omacad.ui.viewport.gizmo_mixin import GizmoMixin
from omacad.ui.viewport.picker_mixin import PickerMixin
from omacad.ui.viewport.overlay_mixin import OverlayMixin
"""
Omacad - 3D CAD OpenGL Viewport
Interactive 3D canvas with CAD shading, sharp edge outlines, dynamic ground grid,
interactive ViewCube, sketch overlay, and navigation controls.
"""

import copy
import ctypes
import math
from typing import Optional, List, Tuple, Dict
import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QPointF, Signal, QEvent, QTimer
from PySide6.QtWidgets import (QWidget, QMenu, QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton)
import omacad.ui.viewport as _vp_module
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.model import quality
from omacad.model.hover_info import describe_entity
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QFontMetrics
from OpenGL import GL
from OpenGL.GL import shaders

from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.model.timeline import profile_cross_section
from omacad.model.faces import ray_hit_face, tangent_chain
import manifold3d as m3d
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch import (
    Sketch, SketchPlane, SketchLine, SketchRect, SketchCircle,
    SketchCenterRect, SketchArc, SketchSlot, move_entity, rotate_entity, rotate_point, entity_key_points,
    point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex, ref_id, ref_segment, EDGE_PTS
)
from omacad.model.sketch_snap import SketchSnapper, SnapResult
from omacad.ui.sketch_tools import SKETCH_TOOLS
from omacad.ui.math3d import REF_FOVY, camera_matrices, ray_from_screen, ray_plane_intersect
from omacad.ui.viewcube import ViewCube
from omacad.ui import dyn_input
from omacad.model import expr as expr_lib
from omacad.ui.dyn_input import DynInput
from omacad.ui import smart_circle
from omacad.ui.smart_circle import SmartCircle
from omacad.ui.sketch_palette import SketchPalette
from omacad.ui import theme
from omacad.ui.theme import qcolor


class Viewport3D(QOpenGLWidget, RenderGLMixin, GizmoMixin, PickerMixin, OverlayMixin):
    """Modern OpenGL 3D CAD canvas with Fusion 360 look and feel."""

    selection_changed = Signal()
    hover_info_changed = Signal(object)    # (title, [(label, text)]) of what the mouse rests on, or None
    sketch_finished = Signal()
    finish_sketch_requested = Signal()
    construction_mode_changed = Signal(bool)
    sketch_tool_changed = Signal(str)
    profile_picked = Signal()
    plane_picked = Signal(object)       # SketchPlane chosen for a new sketch
    plane_pick_cancelled = Signal()
    section_base_picked = Signal(object)   # plane a section view is cut along
    offset_base_picked = Signal(object)   # plane an offset plane is measured from
    surface_hover = Signal(object)        # same, while the mouse moves (None = no surface)
    surface_picked = Signal(object)       # dict(point, patch) of any body surface (planar or curved)
    target_plane_picked = Signal(object)  # plane chosen as an extrude target (distance to face)
    primitive_face_picked = Signal(object)  # plane chosen as origin/face for box or cylinder
    cylinder_picked = Signal(object)        # dict with cylinder parameters (radius, length, axis, origin, is_internal)
    shell_face_picked = Signal(object)   # plane/face chosen for hollow shell open face
    move_body_picked = Signal(object)    # plane/face chosen for move body selection
    status_message = Signal(str)
    edit_sketch_requested = Signal(str)     # right-click on a sketch > Edit Sketch
    extrude_sketch_requested = Signal(str)  # right-click on a sketch > Extrude
    edges_selection_changed = Signal()
    extrude_handle_dragged = Signal(float)  # signed distance along the extrude arrow while it is dragged
    extrude_handle_drag_finished = Signal()  # emitted when dragging the handle finishes
    move_gizmo_dragged = Signal(str, float)  # (axis: "X"|"Y"|"Z", delta_mm)
    move_gizmo_finished = Signal()
    move_gizmo_axis_selected = Signal(str)
    body_clicked = Signal(str)  # body_id of clicked 3D body
    plane_clicked = Signal(str)  # an origin plane ("XY") or construction plane id clicked without a tool
    join_bodies_requested = Signal(object)    # right-click with two or more bodies selected > Join
    split_plane_requested = Signal(str)   # right-click on a plane > Split Body with this plane
    face_extrude_requested = Signal(object)  # a flat face to extrude (pull in = cut, out = build up)
    edge_pick_cancelled = Signal()
    offset_face_picked = Signal(object, str)   # (face reference dict, body id) while Offset Face is open
    offset_face_requested = Signal(object)     # a flat face chosen from the right-click menu
    round_requested = Signal(str, object)      # ("fillet" | "chamfer", edges): start the tool with these edges picked
    lay_face_requested = Signal(object, str)   # (face, "ground" | "pick"): turn the body so this face rests on a plane
    lay_target_picked = Signal(object)         # the plane a face is to be laid on
    step_point_clicked = Signal(object)        # a point on a body surface clicked while choosing steps (Pattern/Mirror)
    menu_command = Signal(str)  # right-click menu entries the main window carries out: "undo", "redo", "sketch:XY"...

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.on_document_changed)

        # Camera parameters
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.azimuth: float = 45.0      # Orbit around Z (deg)
        self.elevation: float = 30.0    # Elevation above ground (deg)
        self.distance: float = 140.0    # Distance to target (mm)
        self.fovy: float = REF_FOVY   # zoom calibration only; the drawn field of view is the view_fov setting

        # Navigation state
        self.last_mouse_pos = QPoint()
        self.is_orbiting = False
        self.is_panning = False
        self.nav_mode = "ORBIT"  # "ORBIT", "PAN", "ZOOM"

        # Display flags
        self.show_grid = True
        self.show_edges = True
        self.wireframe_only = False

        # Sketch drawing interaction state
        self.sketch_tool = "NONE"  # "NONE", "LINE", "RECT", "CENTER_RECT", "CIRCLE", "ARC", "SLOT", "DIMENSION"
        self.sketch_start_uv: Optional[Tuple[float, float]] = None
        self.sketch_second_uv: Optional[Tuple[float, float]] = None
        self.sketch_current_uv: Optional[Tuple[float, float]] = None
        self.construction_mode: bool = False
        self.active_snap: Optional[SnapResult] = None
        self.dim_badges: Dict[str, Tuple[QRectF, str, str, float]] = {}
        self.hovered_dim_id: Optional[str] = None

        # Profile picking / extrude preview state
        self.hover_profile: Optional[Tuple[str, int]] = None
        self._press_pos: Optional[QPointF] = None
        self._profile_fill_cache: Dict[tuple, np.ndarray] = {}
        self.preview_mesh = None
        self.preview_op: str = "new_body"

        # Sketch element selection (click / Ctrl+click, Delete)
        self.selected_entities: set = set()
        self.hover_entity_id: Optional[str] = None
        self._ref_segments_cache = None  # (sketch_id, segments) of body edges lying in the sketch plane

        # Dimension tool: elements picked so far, and a point-to-point pair waiting for its placement click
        self._dim_pending: list = []
        self._dim_box = None          # floating value box while a point pair waits for its placement click
        self._dim_hover_uv = None
        self._dim_place = None
        self._dim_side = None  # "near"/"far": which circle edge a guided edge-distance measures to

        # Constraint glyphs drawn on the sketch (rect -> constraint id), rebuilt each paint
        self.constraint_badges: List[Tuple[QRectF, str]] = []

        # Moving sketch elements (mouse drag or Move tool)
        self._dim_drag = None   # pressed dimension badge: click = edit value, drag = move the dimension line
        self._drag = None   # pending/active mouse drag: dict(press_uv, press_pos, moved)
        self._move = None   # active move: dict(ids, orig, before, delta)

        # Tab dimension entry while drawing
        self.dyn = DynInput()
        self.smart = SmartCircle()   # the Smart Circle tool: numbers + Enter
        self.dyn_live: Dict[str, float] = {}
        self._raw_mouse_uv: Optional[Tuple[float, float]] = None

        # Extrude arrow (drag to set the distance)
        self.active_tool_title = lambda: None   # set by the main window: title of the open tool panel, if any
        self.pick_step_mode = False   # clicks on a body surface choose the step that made it
        self.extrude_handle = None   # dict(origin, axis, dist)
        self._handle_drag = False
        self._handle_hover = False
        self.move_gizmo = None  # dict(origin, length, active_axis, hover_axis, dragging, start_proj)

        # Edge selection for fillet / chamfer
        self.edge_pick_mode: bool = False
        self.edge_xray: bool = False   # pick edges through the model too (stairs, inside corners)
        self.hover_edge = None            # PlanarEdge under the cursor
        self.hover_face = None            # flat face under the cursor
        self.selected_edges: list = []    # PlanarEdge objects chosen so far

        # Right-click menu on a face
        self._rpress: Optional[QPointF] = None
        self.ctx_face = None

        # Sketch plane picking (origin planes + planar body faces)
        self.plane_pick_mode: bool = False
        self.measure = None         # active Measure tool: dict(mode, picks, text, segs)
        self.offset_preview = None  # flat segments of the sketch Offset being set up
        self.section = None         # active section view: dict(origin, normal, offset, flip, meshes, cap)
        self.preview_plane = None   # SketchPlane drawn while an Offset Plane is being set up
        self.plane_pick_purpose: str = "sketch"  # "sketch" or "extrude_target"
        self.shell_target_body_id: str = ""      # body whose faces "shell_face" picking may hit
        self.hover_plane = None  # ("origin", name) or ("face", PlanarFace)
        self.hover_patch = None  # triangle corners (n, 3) of the curved surface under the cursor (Offset Face)
        self._hover_patch_time = 0.0
        self.highlighted_faces: list = []  # list of faces or dicts to highlight (e.g. Shell open faces)

        # ViewCube overlay
        self.viewcube = ViewCube(size=90, on_face_clicked=self.set_view)

        # Floating Sketch Palette
        self.sketch_palette = SketchPalette(self)
        self.sketch_palette.finish_clicked.connect(self.finish_sketch_requested)
        self.sketch_palette.look_at_clicked.connect(self.look_at_active_plane)
        self.sketch_palette.settings_changed.connect(self.update)
        self.sketch_palette.hide()

        # Fillet tool state
        self._mirror_phase = "pick"
        self.fillet_first_line = None
        self.fillet_hover_corner = None
        self.fillet_preview = None
        self.fillet_picked = []   # corners picked with Shift: (point, line_a id, line_b id)
        self._rubber = None       # box selection in the sketch: dict(p0, p1, additive)

        from omacad.ui.settings import get_settings
        get_settings().changed.connect(self.update)

        # OpenGL shader handles
        self.prog_solid = None
        self.prog_flat = None
        self.prog_thick = None
        self.prog_tex = None
        self._canvas_textures = {}
        self.vbo_thick = None
        self.vao = None
        self.vbo_pos = None
        self.vbo_norm = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sketch_palette'):
            self.sketch_palette.place_default(self.size())
        if hasattr(self, '_on_viewport_resized') and callable(self._on_viewport_resized):
            self._on_viewport_resized(self.size())

    def set_document(self, document: Document) -> None:
        """Switch to another document (File > New/Open) and drop all state tied to the old one."""
        self.doc = document
        self.doc.add_change_listener(self.on_document_changed)
        self.selected_entities = set()
        self.hover_entity_id = None
        self.hover_profile = None
        self.hover_plane = None
        self.plane_pick_mode = False
        self.plane_pick_purpose = "sketch"
        self.sketch_tool = "NONE"
        self.sketch_start_uv = self.sketch_second_uv = self.sketch_current_uv = None
        self.active_snap = None
        self._drag = self._move = self._dim_drag = None
        self._dim_pending, self._dim_place = [], None
        self.dyn.reset()
        self.dyn_live = {}
        self.preview_mesh = None
        self.dim_badges.clear()
        self.constraint_badges = []
        self._profile_fill_cache.clear()
        self._ref_segments_cache = None
        self.on_document_changed()

    def on_document_changed(self):
        """Reacts to document updates and shows/hides Sketch Palette."""
        self._profile_fill_cache.clear()
        self._ref_segments_cache = None
        self.sync_section()
        if self.measure is not None and (self.measure["mode"] == "sketch") != bool(self.doc.active_sketch):
            self.measure = None   # sketch mode was entered or left: the picks no longer apply
        sk = self.doc.active_sketch
        if sk is None:
            self.selected_entities.clear()
        else:
            alive = {e.entity_id for e in sk.entities}
            self.selected_entities &= alive
        self.hover_entity_id = None
        sel = self.doc.selected_profile
        if sel and (sel[0] not in self.doc.sketches or sel[1] >= len(self.doc.sketches[sel[0]].profiles)):
            self.doc.selected_profile = None
        self.hover_profile = None
        if self.doc.active_sketch:
            self.sketch_palette.show()
            self.sketch_palette.raise_()
            self.sketch_palette.place_default(self.size())
        else:
            self.sketch_palette.hide()
            self.active_snap = None
            self.sketch_tool = "NONE"
            self.sketch_start_uv = None
            self.sketch_second_uv = None
            self.sketch_current_uv = None
        self.update()

    def _reference_segments(self):
        """Body edges lying in the active sketch plane, as 2D (u,v) segments (cached)."""
        sk = self.doc.active_sketch
        if sk is None:
            return np.zeros((0, 2, 2))
        if self._ref_segments_cache and self._ref_segments_cache[0] == sk.sketch_id:
            return self._ref_segments_cache[1]
        plane = sk.plane
        o = np.asarray(plane.origin, dtype=np.float64)
        ua = np.asarray(plane.u_axis, dtype=np.float64)
        va = np.asarray(plane.v_axis, dtype=np.float64)
        segs = []
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.sharp_lines) == 0:
                continue
            # Every body edge projected orthogonally onto the sketch plane: edges lying in the
            # plane keep their shape, perpendicular (e.g. vertical) edges collapse to points.
            pts = np.asarray(mesh.sharp_lines, dtype=np.float64).reshape(-1, 2, 3) - o
            uv = np.stack([pts @ ua, pts @ va], axis=-1)  # (N, 2, 2)
            segs.append(uv)
        if segs:
            allseg = np.concatenate(segs)
            # drop duplicates (top/bottom edges of a prism project onto each other)
            r = np.round(allseg, 3)
            swap = (r[:, 0, 0] > r[:, 1, 0]) | ((r[:, 0, 0] == r[:, 1, 0]) & (r[:, 0, 1] > r[:, 1, 1]))
            r[swap] = r[swap][:, ::-1]
            key = r.reshape(len(r), 4)
            _, idx = np.unique(key, axis=0, return_index=True)
            segs = allseg[np.sort(idx)]
        else:
            segs = np.zeros((0, 2, 2))
        self._ref_segments_cache = (sk.sketch_id, segs)
        return segs

    # ---- Constraints -----------------------------------------------------------
    CONSTRAINT_GLYPHS = {
        "HORIZONTAL": "H", "VERTICAL": "V", "PARALLEL": "∥", "PERPENDICULAR": "⟂",
        "EQUAL": "=", "TANGENT": "T", "CONCENTRIC": "◎", "COINCIDENT": "•", "FIX": "F", "POINT_ON_CIRCLE": "○",
    }
    CONSTRAINT_HINTS = {
        "HORIZONTAL": "Horizontal: select one or more lines.",
        "VERTICAL": "Vertical: select one or more lines.",
        "PARALLEL": "Parallel: select two or more lines.",
        "PERPENDICULAR": "Perpendicular: select two or more lines.",
        "EQUAL": "Equal: select two or more lines, or two or more circles.",
        "TANGENT": "Tangent: select a line and a circle, or two circles.",
        "CONCENTRIC": "Concentric: select two circles.",
        "COINCIDENT": "Coincident: select two lines (their nearest end points are joined).",
        "FIX": "Fix: select lines or circles to lock in place.",
    }

    def apply_constraint(self, ctype: str):
        """Applies a constraint to the selected sketch elements."""
        sk = self.doc.active_sketch
        if not sk:
            return
        sel = [e for e in sk.entities if e.entity_id in self.selected_entities]
        lines = [e for e in sel if isinstance(e, SketchLine)]
        circles = [e for e in sel if isinstance(e, SketchCircle)]
        unsupported = [e for e in sel if not isinstance(e, (SketchLine, SketchCircle))]
        specs = []
        if ctype in ("HORIZONTAL", "VERTICAL"):
            specs = [(ctype, [l.entity_id], []) for l in lines]
        elif ctype in ("PARALLEL", "PERPENDICULAR") and len(lines) >= 2:
            specs = [(ctype, [lines[0].entity_id, l.entity_id], []) for l in lines[1:]]
        elif ctype == "EQUAL":
            group = lines if len(lines) >= 2 else circles if len(circles) >= 2 else []
            specs = [(ctype, [group[0].entity_id, e.entity_id], []) for e in group[1:]]
        elif ctype == "TANGENT" and ((len(lines) == 1 and len(circles) == 1) or (not lines and len(circles) == 2)):
            pair = lines + circles if lines else circles
            specs = [(ctype, [pair[0].entity_id, pair[1].entity_id], [])]
        elif ctype == "CONCENTRIC" and len(circles) == 2 and not lines:
            specs = [(ctype, [circles[0].entity_id, circles[1].entity_id], [])]
        elif ctype == "COINCIDENT" and len(lines) == 2 and not circles:
            a, b = lines
            best = min(((pa, pb) for pa in ("p1", "p2") for pb in ("p1", "p2")),
                       key=lambda t: math.hypot(getattr(a, t[0])[0] - getattr(b, t[1])[0],
                                                getattr(a, t[0])[1] - getattr(b, t[1])[1]))
            specs = [(ctype, [a.entity_id, b.entity_id], list(best))]
        elif ctype == "FIX":
            specs = [(ctype, [e.entity_id], []) for e in lines + circles]

        requested = len(specs)
        existing = {(c.ctype, tuple(c.refs)) for c in sk.constraints}
        specs = [sp for sp in specs if (sp[0], tuple(sp[1])) not in existing]
        if not specs:
            if requested:
                self.status_message.emit("That constraint is already applied.")
            elif unsupported and not (lines or circles):
                self.status_message.emit("Constraints work on lines and circles for now (not rectangles, arcs or slots).")
            else:
                self.status_message.emit(self.CONSTRAINT_HINTS.get(ctype, ""))
            return
        self.doc.add_constraints(sk.sketch_id, specs)
        self.status_message.emit(self.doc.last_message)

    def draw_dim_picks(self, painter: QPainter):
        """Rings on the end points picked by the dimension tool, and a dashed link while placing."""
        sk = self.doc.active_sketch
        if not sk or self.sketch_tool != "DIMENSION":
            return
        for p in self._dim_pending:
            if p[0] == "ref":
                (a, b) = p[1]
                sa = self.world_to_screen(sk.plane.uv_to_world(a[0], a[1]))
                sb = self.world_to_screen(sk.plane.uv_to_world(b[0], b[1]))
                if sa and sb:
                    painter.setPen(QPen(qcolor(226, 109, 40), 3))
                    painter.drawLine(QPointF(sa[0], sa[1]), QPointF(sb[0], sb[1]))
        picks = [p for p in self._dim_pending if p[0] == "pt"]
        if self._dim_place:
            picks += [self._dim_place["a"], self._dim_place["b"]]
        plane = sk.plane
        screen = []
        for _, ent, name in picks:
            uv = point_of(ent, name)
            scr = self.world_to_screen(plane.uv_to_world(uv[0], uv[1])) if uv else None
            if scr:
                screen.append(QPointF(scr[0], scr[1]))
                painter.setPen(QPen(qcolor(226, 109, 40), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(scr[0], scr[1]), 7, 7)
        if self._dim_place and len(screen) >= 2:
            painter.setPen(QPen(qcolor(226, 109, 40, 200), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(screen[0], screen[1])

    def draw_constraint_badges(self, painter: QPainter):
        """Small glyphs next to constrained geometry; click one to remove the constraint."""
        self.constraint_badges = []
        sk = self.doc.active_sketch
        if not sk or not sk.constraints:
            return
        plane = sk.plane
        ents = {e.entity_id: e for e in sk.entities}
        stacked: Dict[str, int] = {}
        painter.setFont(QFont(theme.font_family(), 9, QFont.Weight.Bold))
        show_all = self.sketch_palette.chk_show_constraints.isChecked()
        focus = self.selected_entities | ({self.hover_entity_id} if self.hover_entity_id else set())
        for c in sk.constraints:
            ent = ents.get(c.refs[0]) if c.refs else None
            if ent is None:
                continue
            grp = {getattr(ents.get(r), "group", None) for r in c.refs}
            if len(grp) == 1 and None not in grp and c.ctype in ("POINT_ON_CIRCLE", "EQUAL", "COINCIDENT"):
                continue   # the built-in relations of a polygon stay out of sight
            if not show_all and not (set(c.refs) & focus):
                continue
            if c.ctype == "COINCIDENT" and c.pts:
                uv = getattr(ent, c.pts[0], None) or (0.0, 0.0)
            elif isinstance(ent, SketchLine):
                uv = ((ent.p1[0] + ent.p2[0]) / 2.0, (ent.p1[1] + ent.p2[1]) / 2.0)
            elif isinstance(ent, SketchCircle):
                uv = (ent.center[0] + ent.radius * 0.7071, ent.center[1] + ent.radius * 0.7071)
            else:
                continue
            scr = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            if scr is None:
                continue
            n = stacked.get(c.refs[0], 0)
            stacked[c.refs[0]] = n + 1
            rect = QRectF(scr[0] + 8 + n * 20, scr[1] - 24, 18, 18)
            painter.setBrush(QBrush(qcolor(30, 34, 40, 235)))
            painter.setPen(QPen(qcolor(56, 189, 248), 1.2))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(qcolor(230, 240, 250))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.CONSTRAINT_GLYPHS.get(c.ctype, "?"))
            self.constraint_badges.append((rect, c.cid))

    # ---- Moving and Rotating sketch elements ---------------------------------
    def _begin_move(self, ids):
        sk = self.doc.active_sketch
        ids = {i for i in ids if not getattr(sk.get_entity(i), "projected", False)}
        orig_ents = {e.entity_id: copy.deepcopy(e) for e in sk.entities if e.entity_id in ids}
        # Compute bounding center as rotation pivot
        all_kps = [kp for ent in orig_ents.values() for kp in entity_key_points(ent)]
        if all_kps:
            center_u = sum(p[0] for p in all_kps) / len(all_kps)
            center_v = sum(p[1] for p in all_kps) / len(all_kps)
        else:
            center_u, center_v = 0.0, 0.0

        self._move = {
            "ids": set(ids),
            "orig": orig_ents,
            "before": sk.to_dict(),
            "delta": (0.0, 0.0),
            "angle": 0.0,
            "pivot": (center_u, center_v),
        }

    def _apply_move(self, du: float, dv: float, angle_deg: float = 0.0):
        """Positions the moving entities at original + (du, dv) rotated by angle_deg around pivot."""
        m = self._move
        if not m:
            return
        sk = self.doc.active_sketch
        pivot = m.get("pivot", (0.0, 0.0))
        for i, ent in enumerate(sk.entities):
            orig = m["orig"].get(ent.entity_id)
            if orig is not None:
                moved = copy.deepcopy(orig)
                if abs(angle_deg) > 1e-4:
                    rotate_entity(moved, angle_deg, pivot)
                if abs(du) > 1e-9 or abs(dv) > 1e-9:
                    move_entity(moved, du, dv)
                sk.entities[i] = moved
        sk.solve_profiles()
        m["delta"] = (du, dv)
        m["angle"] = angle_deg
        self.update()

    def _end_move(self, commit: bool):
        m = self._move
        self._move = None
        self._drag = None
        self.active_snap = None
        if not m:
            return
        sk = self.doc.active_sketch
        if sk is None:
            return
        du, dv = m["delta"]
        ang = m.get("angle", 0.0)
        has_change = (abs(du) > 1e-9 or abs(dv) > 1e-9 or abs(ang) > 1e-4)
        if commit and has_change and sk.constraints:
            res = solve_sketch(sk, fixed_ids=m["ids"])
            if not res.ok:
                sk.restore_from_dict(m["before"])
                self.status_message.emit(res.message + " - move cancelled.")
                self.doc.notify_changed()
                self.update()
                return
        if commit and has_change:
            self.doc.record_sketch_change(sk, m["before"])
            self.doc.timeline.recompute(self.doc)
            self.doc.notify_changed()
        else:
            for i, ent in enumerate(sk.entities):
                orig = m["orig"].get(ent.entity_id)
                if orig is not None:
                    sk.entities[i] = orig
            sk.solve_profiles()
        self.update()

    def _snap_move_delta(self, du: float, dv: float):
        """Snaps the dragged elements' key points to geometry/edges, else the grid."""
        m = self._move
        sk = self.doc.active_sketch
        tol = max(0.3, min(8.0, self._entity_tolerance() * 1.25))

        class _Others:
            entities = [e for e in sk.entities if e.entity_id not in m["ids"]]

        refs = self._reference_segments()
        best = None
        kps = [kp for orig in m["orig"].values() for kp in entity_key_points(orig)][:32]
        for kp in kps:
            r = SketchSnapper.snap(raw_uv=(kp[0] + du, kp[1] + dv), sketch=_Others, snap_distance=tol,
                                   grid_step=0.0, enable_grid_snap=False, enable_geom_snap=True,
                                   reference_segments=refs)
            if r.snap_type in ("ORIGIN", "ENDPOINT", "MIDPOINT", "EDGE"):
                ddu, ddv = r.uv[0] - kp[0], r.uv[1] - kp[1]
                dist = math.hypot(ddu - du, ddv - dv)
                if best is None or dist < best[0]:
                    best = (dist, ddu, ddv, r)
        if best:
            self.active_snap = best[3]
            return best[1], best[2]
        self.active_snap = None
        if self.sketch_palette.chk_snap_grid.isChecked():
            return round(du / 5.0) * 5.0, round(dv / 5.0) * 5.0
        return du, dv

    def _drag_move(self, event):
        d = self._drag
        if not d["moved"]:
            if (event.position() - d["press_pos"]).manhattanLength() < 4:
                return
            d["moved"] = True
            self._begin_move(self.selected_entities)
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        if uv is None:
            return
        du, dv = self._snap_move_delta(uv[0] - d["press_uv"][0], uv[1] - d["press_uv"][1])
        self._apply_move(du, dv)

    def _drag_release(self, event):
        d = self._drag
        self._drag = None
        if d["moved"]:
            self._end_move(True)
        elif not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and len(self.selected_entities) > 1:
            self.selected_entities = {d["ent_id"]}  # plain click inside a multi-selection narrows it
            self.selection_changed.emit()
        self.update()

    # ---- Measure ----------------------------------------------------------------------------
    def begin_measure(self):
        """Measure tool: click a line (or edge) for its length, click a second one for the distance/angle between them."""
        self.measure = {"mode": "sketch" if self.doc.active_sketch else "model", "picks": [], "text": [], "segs": []}
        self.selected_entities.clear()
        self.sketch_tool = "NONE" if self.doc.active_sketch else self.sketch_tool
        from omacad.ui.settings import get_settings
        if self.sketch_palette and get_settings().get("autohide_palette_on_measure", True):
            self.sketch_palette.hide()
        self.status_message.emit("Measure: click a line, circle or edge; click a second one to measure between them. Esc ends.")
        self.setFocus()
        self.update()

    def end_measure(self):
        if self.measure is not None:
            self.measure = None
            if self.doc.active_sketch and self.sketch_palette:
                self.sketch_palette.show()
                self.sketch_palette.place_default(self.size())
            self.status_message.emit("Measure closed.")
            self.update()

    def _measure_click(self, x: float, y: float):
        from omacad.model.measure import measure_2d, measure_3d
        m = self.measure
        pick = self._pick_entity(x, y) if m["mode"] == "sketch" else self._pick_edge(x, y)
        if pick is None:
            m["picks"], m["text"], m["segs"] = [], [], []
            self.update()
            return
        same = lambda a, b: (a.entity_id == b.entity_id) if m["mode"] == "sketch" else self._same_edge(a, b)
        if any(same(pick, p) for p in m["picks"]):
            m["picks"] = [p for p in m["picks"] if not same(pick, p)]
        else:
            m["picks"] = (m["picks"] + [pick]) if len(m["picks"]) < 2 else [pick]
        if m["picks"]:
            m["text"], m["segs"] = (measure_2d if m["mode"] == "sketch" else measure_3d)(m["picks"])
        else:
            m["text"], m["segs"] = [], []
        m["set_distance"] = self._measure_set_distance_plan() if m["mode"] == "model" else None
        if m["text"]:
            self.status_message.emit("Measure: " + "  |  ".join(m["text"]) +
                                     ("  |  Press D to set this distance" if m["set_distance"] else ""))
        self.update()

    def _body_of_edge(self, edge):
        return next((b for b in self.doc.bodies.values() if any(e is edge for e in b.edges)), None)

    def _measure_set_distance_plan(self):
        """Two edges on different bodies: (moving body, unit direction away from the first body, current gap)."""
        m = self.measure
        if m is None or m["mode"] != "model" or len(m["picks"]) != 2 or not m["segs"]:
            return None
        first, second = (self._body_of_edge(p) for p in m["picks"])
        if first is None or second is None or first is second:
            return None
        a, b = (np.asarray(q, dtype=float) for q in m["segs"][0])
        gap = float(np.linalg.norm(b - a))
        if gap < 1e-6:
            return None                          # touching: there is no direction to move in
        return second, (b - a) / gap, gap

    def _measure_set_distance(self):
        """Measure tool, key D: type the wanted distance and the second body moves along the measured line."""
        plan = self._measure_set_distance_plan()
        if plan is None:
            self.status_message.emit("Set distance: measure between edges on two different bodies that are not touching.")
            return
        body, direction, gap = plan
        res = self.prompt_dimension_value("Set distance", f"Distance (mm); {body.name} moves along the measured line:",
                                          gap, 0.0, 50000.0, " mm")
        if res is None:
            return
        target = res[0]
        delta = (target - gap) * direction
        if np.linalg.norm(delta) > 1e-9:
            self.doc.move_body(body.body_id, float(delta[0]), float(delta[1]), float(delta[2]))
            self.status_message.emit(f"Moved {body.name} so the distance is {target:.3f} mm.")
        self.measure["picks"], self.measure["text"], self.measure["segs"], self.measure["set_distance"] = [], [], [], None
        self.update()

    def _draw_measure(self, painter: QPainter):
        m = self.measure
        if m is None:
            return
        sk = self.doc.active_sketch
        to_scr = (lambda q: self.world_to_screen(sk.plane.uv_to_world(q[0], q[1]))) if m["mode"] == "sketch" else \
                 (lambda q: self.world_to_screen(np.asarray(q, dtype=float)))
        from omacad.ui.settings import get_settings
        accent = get_settings().measure_color_qcolor()
        pen = QPen(accent, 3)
        painter.setPen(pen)
        for p in m["picks"]:
            pts = []
            if m["mode"] == "sketch":
                for a, b in p.to_lines():
                    pts.append((a, b))
            else:
                poly = p.polyline()
                pts = [(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]
            for a, b in pts:
                sa, sb = to_scr(a), to_scr(b)
                if sa is not None and sb is not None:
                    painter.drawLine(QPointF(*sa), QPointF(*sb))
        dash = QPen(accent, 2, Qt.PenStyle.DashLine)
        painter.setPen(dash)
        for a, b in m["segs"]:
            if len(m["picks"]) == 2 or m["mode"] == "model":
                sa, sb = to_scr(a), to_scr(b)
                if sa is not None and sb is not None:
                    painter.drawLine(QPointF(*sa), QPointF(*sb))
                    painter.setBrush(accent)
                    painter.drawEllipse(QPointF(*sa), 3.5, 3.5)
                    painter.drawEllipse(QPointF(*sb), 3.5, 3.5)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
        # result panel
        lines = m["text"] or ["Measure: click a line, circle or edge"]
        if m.get("set_distance"):
            lines = lines + [f"D: set the distance (moves {m['set_distance'][0].name})"]
        font = QFont(theme.font_family(), 11)
        painter.setFont(font)
        fm = painter.fontMetrics()
        wbox = max(fm.horizontalAdvance(t) for t in lines) + 28
        hbox = fm.height() * len(lines) + 18
        rect = QRectF((self.width() - wbox) / 2.0, 14, wbox, hbox)
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(theme.qcolor(30, 34, 40, 235))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(theme.qcolor(240, 240, 240))
        for i, t in enumerate(lines):
            painter.drawText(QPointF(rect.x() + 14, rect.y() + 9 + fm.ascent() + i * fm.height()), t)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _entity_tolerance(self) -> float:
        """8 screen pixels expressed in sketch units."""
        mm_per_px = self.distance * 2.0 * math.tan(math.radians(self.fovy) / 2.0) / max(1, self.height())
        return 8.0 * mm_per_px

    def _can_select_sketch_entities(self) -> bool:
        return bool(self.doc.active_sketch and self.sketch_tool == "NONE" and not self.plane_pick_mode)

    def _pick_entity(self, x: float, y: float):
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return None
        return self.doc.active_sketch.hit_test(uv[0], uv[1], self._entity_tolerance())

    def _update_entity_hover(self, x: float, y: float):
        active = self._can_select_sketch_entities() or (self.doc.active_sketch is not None and (self.sketch_tool in ("DIMENSION", "OFFSET") or self.measure is not None))
        ent = self._pick_entity(x, y) if active else None
        hid = ent.entity_id if ent else None
        if hid != self.hover_entity_id:
            self.hover_entity_id = hid
            self.hover_info_changed.emit(describe_entity(ent) if ent else None)
            self.update()

    def select_entity_at(self, x: float, y: float, additive: bool):
        ent = self._pick_entity(x, y)
        if ent is None:
            if not additive:
                self.selected_entities.clear()
        elif additive:
            self.selected_entities ^= {ent.entity_id}
        else:
            self.selected_entities = {ent.entity_id}
        self.selection_changed.emit()
        self.update()

    def _offset_status(self):
        n = len(self.selected_entities)
        self.status_message.emit(f"Offset: click a curve for its whole chain (Shift/Ctrl/Alt+click = add or drop single line). "
                                 f"{n} selected. Press Enter or right-click to set the distance. Esc cancels.")

    def _offset_go(self):
        if not self.selected_entities:
            self.status_message.emit("Offset: click the curves to offset first.")
            return
        self.offset_selected()
        self.set_sketch_tool("NONE")

    def offset_selected(self):
        """Offset (O): parallel copies of the selected sketch elements at a typed distance."""
        sk = self.doc.active_sketch
        if not sk:
            return
        if not self.selected_entities:
            self.status_message.emit("Offset: select the sketch elements first (click, Ctrl+click, double-click for a whole shape), then press O.")
            return
        ids = set(self.selected_entities)

        def preview(value):
            segs = []
            if abs(value) > 1e-9:
                from omacad.model.sketch import Sketch
                tmp = Sketch.from_dict(sk.to_dict())
                n0 = len(tmp.entities)
                try:
                    tmp.offset_entities(ids, value)
                except Exception:
                    tmp.entities = tmp.entities[:n0]
                for ent in tmp.entities[n0:]:
                    for a, b in ent.to_lines():
                        segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
            self.offset_preview = np.array(segs, dtype=np.float32) if segs else None
            self.update()

        try:
            res = self.prompt_dimension_value("Offset", "Distance (negative = inward for a closed shape, positive = outward; for a single line: positive = left of its direction):",
                                              5.0, lo=-5000.0, hi=5000.0, on_change=preview)
        finally:
            self.offset_preview = None
            self.update()
        if res is None or abs(res[0]) < 1e-9:
            return
        before = sk.to_dict()
        new = sk.offset_entities(self.selected_entities, res[0])
        if not new:
            self.status_message.emit("Offset: nothing could be offset by that distance (a shape can't shrink past its own size).")
            return
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {e.entity_id for e in new}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit(f"Offset: {len(new)} element(s) created {res[0]:g} mm away.")
        self.update()

    def delete_selected_entities(self) -> int:
        sk = self.doc.active_sketch
        if not sk or not self.selected_entities:
            return 0
        ids = set(self.selected_entities)
        self.selected_entities.clear()
        self.sketch_start_uv = None
        n = self.doc.delete_sketch_entities(sk.sketch_id, ids)
        self.selection_changed.emit()
        return n

    # ---- Sketch commit & Tab dimension entry ---------------------------------
    def _commit_sketch_point(self, p2: Tuple[float, float]):
        """Second (or later) click of the active tool: create/advance the shape."""
        sketch = self.doc.active_sketch
        p1 = self.sketch_start_uv
        if self.sketch_tool == "MOVE":
            if self._move:
                ang = self.dyn_live.get("Angle", 0.0) if hasattr(self, "dyn_live") else 0.0
                self._apply_move(p2[0] - p1[0], p2[1] - p1[1], angle_deg=ang)
                self._end_move(True)
            self.sketch_start_uv = None
            self.dyn.reset()
            self.dyn_live = {}
            self.set_sketch_tool("NONE")
            return
        before = sketch.to_dict()
        is_const = self.construction_mode
        created = None
        typed_formulas = {name: text for name, text in zip(self.dyn.names, self.dyn.texts)
                          if text.strip() and not expr_lib.is_plain_number(text)} if self.dyn.active else {}
        dims_before = len(sketch.dimensions)

        if self.sketch_tool == "LINE":
            if p1 != p2:
                created = sketch.add_line(p1, p2, is_construction=is_const)
                self.sketch_start_uv = p2  # continue chaining line
        elif self.sketch_tool == "RECT":
            if p1 != p2:
                created = sketch.add_rect(p1, p2, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "ROUNDED_RECT":
            if p1 != p2:
                created = sketch.add_rounded_rect(p1, p2, self._corner_radius(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CENTER_RECT":
            if p1 != p2:
                created = sketch.add_center_rect(p1, p2, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CENTER_ROUNDED_RECT":
            if p1 != p2:
                created = sketch.add_center_rounded_rect(p1, p2, self._corner_radius(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "POLYGON":
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 0.5:
                sketch.add_polygon(p1, p2, self._polygon_sides(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CIRCLE":
            r = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if r > 0.5:
                created = sketch.add_circle(p1, r, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "ARC":
            if self.sketch_second_uv is None:
                self.sketch_second_uv = p2
            else:
                sketch.add_arc(p1, p2, self.sketch_second_uv, is_construction=is_const)
                self.sketch_start_uv = None
                self.sketch_second_uv = None
        elif self.sketch_tool == "SLOT":
            if self.sketch_second_uv is None:
                self.sketch_second_uv = p2
            else:
                d = self._point_to_segment_dist(p2, p1, self.sketch_second_uv)
                r = max(2.0, d)
                sketch.add_slot(p1, self.sketch_second_uv, r, is_construction=is_const)
                self.sketch_start_uv = None
                self.sketch_second_uv = None

        for d_new in sketch.dimensions[dims_before:]:  # a typed "width/2" stays a formula on its dimension
            if d_new.name in typed_formulas:
                d_new.expr = typed_formulas[d_new.name]
        if isinstance(created, list):
            solve_sketch(sketch)  # rectangle: refresh the degrees-of-freedom status
        if created is not None and isinstance(created, SketchLine) and self.sketch_palette.chk_auto_constraints.isChecked():
            self._auto_constrain_line(sketch, created)
        self.doc.record_sketch_change(sketch, before)
        self.dyn.reset()
        self.dyn_live = {}
        self._arm_dyn()  # chained line: next segment starts with its first field active
        self.doc.notify_changed()

    def _arm_dyn(self):
        """After a start point exists the first dimension field is active so numbers can be typed at once."""
        self.dyn.reset()
        self.dyn_live = {}
        if self._dyn_can_start():
            self.dyn.start(self.sketch_tool)
            self.dyn.focus = 0

    def _auto_constrain_line(self, sketch, line):
        """Fusion-style inference: horizontal/vertical lines and end points that meet other lines."""
        eid = line.entity_id
        specs = []
        dx, dy = line.p2[0] - line.p1[0], line.p2[1] - line.p1[1]
        if abs(dy) < 1e-6 * max(1.0, abs(dx)):
            specs.append(("HORIZONTAL", [eid], []))
        elif abs(dx) < 1e-6 * max(1.0, abs(dy)):
            specs.append(("VERTICAL", [eid], []))
        for pname in ("p1", "p2"):
            mine = getattr(line, pname)
            for other in sketch.entities:
                if other is line or not isinstance(other, SketchLine):
                    continue
                for oname in ("p1", "p2"):
                    o = getattr(other, oname)
                    if math.hypot(mine[0] - o[0], mine[1] - o[1]) < 1e-6:
                        specs.append(("COINCIDENT", [eid, other.entity_id], [pname, oname]))
                        break
                else:
                    continue
                break
        if specs:
            self.doc.auto_constrain(sketch, specs)

    def _dyn_can_start(self) -> bool:
        return bool(
            self.doc.active_sketch
            and self.sketch_start_uv is not None
            and self.sketch_second_uv is None
            and dyn_input.supports(self.sketch_tool)
        )

    def _corner_radius(self) -> float:
        """Corner radius of the rounded rectangles: a typed Radius wins over the palette spinner."""
        if self.dyn.active and "Radius" in self.dyn.names:
            v = self.dyn.locked_values().get("Radius")
            if v is not None:
                return max(0.1, abs(v))
        return self.sketch_palette.spn_corner_radius.value()

    def _polygon_sides(self) -> int:
        """Sides for the Polygon tool: a typed value wins over the palette spinner."""
        n = self.sketch_palette.spn_sides.value()
        if self.dyn.active and self.dyn.tool == "POLYGON":
            v = self.dyn.locked_values().get("Sides")
            if v is not None:
                n = max(3, min(200, int(round(v))))
        return n

    def _refresh_dyn(self):
        """Re-resolves the pending end point from mouse + typed values."""
        if not (self.dyn.active and self._dyn_can_start()):
            return
        mouse = self._raw_mouse_uv or self.sketch_start_uv
        self.dyn.default_sides = self.sketch_palette.spn_sides.value()
        self.dyn.default_radius = self.sketch_palette.spn_corner_radius.value()
        end, live = self.dyn.resolve(self.sketch_start_uv, mouse)
        self.sketch_current_uv = end
        self.dyn_live = live
        if self.sketch_tool == "MOVE" and self._move:
            ang = live.get("Angle", 0.0)
            self._apply_move(end[0] - self.sketch_start_uv[0], end[1] - self.sketch_start_uv[1], angle_deg=ang)
        self.update()

    def _handle_dyn_key(self, event) -> bool:
        key = event.key()
        if (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.doc.active_sketch
                and self.sketch_start_uv is not None and self.sketch_tool != "NONE"
                and not dyn_input.supports(self.sketch_tool)):
            if self.sketch_current_uv is not None:  # ARC / SLOT: Enter confirms the current step
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if not self._dyn_can_start():
            return False
        text = event.text()
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.dyn.editing = True  # from now on letters go into the field (parameter names)
            self.dyn.start(self.sketch_tool)
            if not self._raw_mouse_uv:
                self._raw_mouse_uv = self.sketch_current_uv
            self.dyn.tab(backwards=(key == Qt.Key.Key_Backtab))
            self._refresh_dyn()
            return True
        cur = self.dyn.texts[self.dyn.focus] if (self.dyn.active and self.dyn.focus >= 0) else ""
        if text == "=" and self.dyn.active and self._dyn_can_start():
            self.dyn.editing = True  # "=" starts a formula/parameter name even for names that begin with a hotkey letter
            return True
        starts_name = text.isupper() or text.lower() not in "lrcaxdm"  # not a tool hotkey
        if (text and len(text) == 1 and (text.isalpha() or text == "_") and self.dyn.active
                and (cur or getattr(self.dyn, "editing", False) or starts_name)
                and not (text in "xX" and cur[-1:].isdigit())):
            self.dyn.type_char(text)  # a parameter name such as width or Height
            self._refresh_dyn()
            return True
        formula_char = text in ("+", "*", "/", "(", ")", "^", "×") or (text in ("x", "X") and cur[-1:].isdigit() or text in ("x", "X") and cur[-1:] == ")")
        if text and len(text) == 1 and (text in "0123456789.,-" or (formula_char and (cur or text == "("))):
            self.dyn.start(self.sketch_tool)
            self.dyn.type_char(text)
            self._refresh_dyn()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.dyn.active:
            # Enter = OK: finish the shape currently being drawn at the cursor
            if self.sketch_current_uv is not None:
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if not self.dyn.active:
            return False
        if key == Qt.Key.Key_Backspace:
            self.dyn.backspace()
            self._refresh_dyn()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._refresh_dyn()
            i = self.dyn.focus
            if self.dyn.invalid(i):
                self.status_message.emit(f"'{self.dyn.texts[i]}' is not a valid number or formula.")
                return True
            if i >= 0 and self.dyn.locked(i) is not None:
                # Enter locks the typed value and moves to the next open field; last one commits
                n = len(self.dyn.names)
                for step in range(1, n):
                    j = (i + step) % n
                    if self.dyn.locked(j) is None:
                        self.dyn.focus = j
                        self.update()
                        return True
            if self.sketch_current_uv is not None:
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if key == Qt.Key.Key_Escape:
            if any(self.dyn.texts):
                self.dyn.texts = [""] * len(self.dyn.names)
                self.dyn.focus = 0
                self._refresh_dyn()
                self.update()
                return True
            return False  # nothing typed: Esc cancels the shape as usual
        return False

    # ---- Smart Circle ------------------------------------------------------------
    def _smart_segments(self):
        """Straight lines a circle can be measured from: the sketch's own lines and the edges of the faces."""
        sk = self.doc.active_sketch
        segs = []
        for e in sk.entities:
            if isinstance(e, SketchLine):
                segs.append((tuple(e.p1), tuple(e.p2), e.entity_id))
        for a, b in self._reference_segments():
            a, b = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
            segs.append((a, b, ref_id((a, b))))
        return segs

    def _smart_key(self, event) -> bool:
        sc, key, text = self.smart, event.key(), event.text()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._smart_accept()
            return True
        if key == Qt.Key.Key_Backspace:
            if sc.text:
                sc.text = sc.text[:-1]
            else:
                sc.back()
            self.update()
            return True
        if key == Qt.Key.Key_Escape:
            if sc.text or sc.stage != smart_circle.SIZE:
                sc.reset()
                sc.mouse = self._raw_mouse_uv
                self.update()
                return True
            return False
        if text and len(text) == 1 and (text in "0123456789.,-+*/()^×" or (text.isalpha() and (sc.text or text == "="))):
            if text != "=":
                sc.text += text
            self.update()
            return True
        return False

    def _smart_accept(self):
        sc = self.smart
        if sc.mouse is None and self._raw_mouse_uv is not None:
            sc.mouse = self._raw_mouse_uv
        res = sc.accept()
        if res == "invalid":
            self.status_message.emit(f"'{sc.text}' is not a valid number or formula.")
        elif res == "need_size":
            self.status_message.emit("Smart Circle: type the diameter first.")
        elif res == "no_line":
            self.status_message.emit("Smart Circle: no straight line to measure from here (step 3 needs one that is not parallel to the first). Clear the field to use the cursor.")
        elif res == "next":
            self.status_message.emit("Smart Circle: distance from the circle's centre (at right angles) to "
                                     + ("the nearest line, any angle" if sc.stage == smart_circle.ACROSS
                                        else "the nearest line that is not parallel to the first")
                                     + ", Enter (empty = cursor).")
        elif res == "done":
            self._smart_create()
        self.update()

    def _smart_create(self):
        sc, sk = self.smart, self.doc.active_sketch
        centre, d = sc.centre(), sc.diameter
        dims = dict(sc.dimension)
        before = sk.to_dict()
        circle = sk.add_circle(centre, d / 2.0, is_construction=self.construction_mode)
        solve_sketch(sk)
        self.doc.record_sketch_change(sk, before)
        for stage in (smart_circle.ACROSS, smart_circle.DOWN):
            if stage in dims:
                seg, dist = dims[stage]
                self.doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", circle.entity_id, dist, refs=[seg[2]], pts=["center"])
        sc.reset()
        sc.mouse = self._raw_mouse_uv
        self.status_message.emit("Smart Circle: placed. Type the next diameter for another one, or Esc.")
        self.doc.notify_changed()

    def _draw_smart_dimensions(self, painter: QPainter, sc, scr, c, d, colour):
        """The numbers typed so far show up on screen as dimensions: the diameter on the circle and the distance
        from each wall to the centre, each with a value badge, before the circle is even created."""
        painter.setFont(QFont(theme.font_family(), 9))
        fm = painter.fontMetrics()

        def badge(at: QPointF, text: str):
            rect = QRectF(at.x() - (fm.horizontalAdvance(text) + 16) / 2, at.y() - 11, fm.horizontalAdvance(text) + 16, 22)
            painter.setBrush(QBrush(qcolor(37, 40, 44, 240)))
            painter.setPen(QPen(colour, 1.5))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(qcolor(255, 255, 255))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        def line(a: QPointF, b: QPointF, text: str):
            painter.setPen(QPen(colour, 1.5))
            painter.drawLine(a, b)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln * 5.0, dx / ln * 5.0
            for p in (a, b):                       # end ticks
                painter.drawLine(QPointF(p.x() - nx, p.y() - ny), QPointF(p.x() + nx, p.y() + ny))
            badge(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2), text)

        sc_c = scr(c)
        if d and sc.diameter is not None and sc_c is not None:       # diameter, once Enter was pressed
            r = sc.diameter / 2.0
            a, b = scr((c[0] - r * 0.7071, c[1] - r * 0.7071)), scr((c[0] + r * 0.7071, c[1] + r * 0.7071))
            if a is not None and b is not None:
                line(a, b, f"\u00d8 {sc.diameter:g} mm")
        for stage, (seg, dist) in sc.dimension.items():
            sf = scr(smart_circle.foot_on_line(seg, c))
            if sf is not None and sc_c is not None:
                line(sf, sc_c, f"{dist:g} mm")

    def draw_smart_circle(self, painter: QPainter):
        sc = self.smart
        if self.sketch_tool != "SMART_CIRCLE" or not self.doc.active_sketch or sc.mouse is None:
            return
        plane = self.doc.active_sketch.plane

        def scr(uv):
            p = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            return None if p is None else QPointF(p[0], p[1])

        orange, cyan = qcolor(226, 109, 40), qcolor(60, 190, 255)
        g = sc.guide()
        if g is not None:
            a, b = scr(g[0]), scr(g[1])
            if a is not None and b is not None:
                painter.setPen(QPen(cyan, 3))
                painter.drawLine(a, b)
        c = sc.centre()
        d = sc.diameter if sc.diameter is not None else (sc.typed() if sc.stage == smart_circle.SIZE else None)
        if c is not None and d:
            r = abs(d) / 2.0
            pts = [scr((c[0] + r * math.cos(2 * math.pi * i / 48), c[1] + r * math.sin(2 * math.pi * i / 48))) for i in range(49)]
            if all(p is not None for p in pts):
                painter.setPen(QPen(orange, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF(pts))
            sc_c = scr(c)
            if sc_c is not None and g is not None:   # dotted measure line from the guide to the centre
                sf = scr(smart_circle.foot_on_line(g, c))
                if sf is not None:
                    painter.setPen(QPen(cyan, 1, Qt.PenStyle.DashLine))
                    painter.drawLine(sf, sc_c)
        anchor = scr(c) if c is not None else None
        if anchor is None:
            return
        self._draw_smart_dimensions(painter, sc, scr, c, d, cyan)
        if not d:   # no size yet: a small shadow circle on the cursor shows that Smart Circle is the active tool
            painter.setPen(QPen(orange, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(qcolor(226, 109, 40, 55)))
            painter.drawEllipse(anchor, 14.0, 14.0)
            painter.drawPoint(anchor)
        painter.setFont(QFont(theme.font_family(), 9))
        label = smart_circle.LABELS[sc.stage]
        if sc.text:
            txt = sc.text + "|"
            v = sc.typed()
            if v is not None and not sc.text.replace(".", "", 1).lstrip("-").isdigit():
                txt += f" = {v:g}"
        else:
            txt = "type a value" if sc.stage == smart_circle.SIZE else "cursor"
        txt = f"{label}  {txt} mm"
        fm = painter.fontMetrics()
        rect = QRectF(anchor.x() + 18, anchor.y() - 36, fm.horizontalAdvance(txt) + 20, 24)
        painter.setBrush(QBrush(qcolor(37, 40, 44, 235)))
        painter.setPen(QPen(orange, 2))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(qcolor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)

    def event(self, e):
        # Tab would otherwise move Qt focus; route it to dimension entry while drawing
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if self._dyn_can_start():
                self.keyPressEvent(e)
                return True
        return super().event(e)

    def draw_dyn_fields(self, painter: QPainter):
        """Floating value boxes next to the shape being drawn."""
        if not (self.dyn.active and self._dyn_can_start() and self.sketch_current_uv):
            return
        plane = self.doc.active_sketch.plane
        a = self.sketch_start_uv
        b = self.sketch_current_uv

        def scr(uv):
            p = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            return None if p is None else QPointF(p[0], p[1])

        sa, sb = scr(a), scr(b)
        if sa is None or sb is None:
            return
        anchors: Dict[str, QPointF] = {}
        tool = self.dyn.tool
        if tool == "LINE":
            mid = (sa + sb) / 2.0
            d = sb - sa
            n = math.hypot(d.x(), d.y()) or 1.0
            anchors["Length"] = QPointF(mid.x() - d.y() / n * 26, mid.y() + d.x() / n * 26)
            anchors["Angle"] = QPointF(sa.x() + 30, sa.y() - 22)
        elif tool in ("RECT", "ROUNDED_RECT", "CENTER_RECT", "CENTER_ROUNDED_RECT"):
            if tool not in ("CENTER_RECT", "CENTER_ROUNDED_RECT"):
                c1, c2 = a, b
            else:
                c1, c2 = (2 * a[0] - b[0], 2 * a[1] - b[1]), b
            p_bl, p_br = scr((c1[0], c1[1])), scr((c2[0], c1[1]))
            p_tr = scr((c2[0], c2[1]))
            if p_bl and p_br and p_tr:
                anchors["Width"] = QPointF((p_bl.x() + p_br.x()) / 2, (p_bl.y() + p_br.y()) / 2 + 22)
                anchors["Height"] = QPointF((p_br.x() + p_tr.x()) / 2 + 48, (p_br.y() + p_tr.y()) / 2)
                anchors["Radius"] = QPointF(p_bl.x() + 62, p_bl.y() - 26)   # inside, by the corner it rounds
        elif tool == "MOVE":
            anchors["X"] = QPointF((sa.x() + sb.x()) / 2, (sa.y() + sb.y()) / 2 + 24)
            anchors["Y"] = QPointF(sb.x() + 52, sb.y())
            anchors["Angle"] = QPointF(sa.x() - 40, sa.y() - 24)
        elif tool == "CIRCLE":
            anchors["Diameter"] = QPointF(sb.x() + 46, sb.y() - 16)
        elif tool == "POLYGON":
            anchors["Side"] = QPointF(sb.x() + 46, sb.y() - 16)
            anchors["Sides"] = QPointF(sa.x() + 38, sa.y() - 24)

        font = QFont(theme.font_family(), 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        for i, name in enumerate(self.dyn.names):
            pt = anchors.get(name)
            if pt is None:
                continue
            locked = self.dyn.locked(i) is not None
            focused = (i == self.dyn.focus)
            if self.dyn.texts[i]:
                txt = self.dyn.texts[i] + ("|" if focused else "")
                result = self.dyn.locked(i)
                if result is not None and not self.dyn.texts[i].replace(".", "", 1).lstrip("-").isdigit():
                    txt += f" = {result:g}"  # a formula: show what it evaluates to
            else:
                val = self.dyn_live.get(name, 0.0)
                txt = f"{val:.0f}" if name == "Sides" else f"{val:.2f}"
            txt += {"Angle": "°", "Sides": ""}.get(name, " mm")
            if name == "Diameter" and not self.dyn.texts[i] and name in self.dyn_live:
                txt += f"  (R {self.dyn_live[name] / 2.0:.2f})"
            if tool == "MOVE":
                txt = f"{name}  {txt}"
            wbox = max(64, fm.horizontalAdvance(txt) + 18)
            rect = QRectF(pt.x() - wbox / 2, pt.y() - 12, wbox, 24)
            painter.setBrush(QBrush(qcolor(37, 40, 44, 235)))
            painter.setPen(QPen(qcolor(226, 109, 40) if focused else qcolor(110, 118, 128), 2 if focused else 1))
            painter.drawRoundedRect(rect, 4, 4)
            if focused and not self.dyn.texts[i]:
                # Ready for typing: value shown as selected text that the first digit replaces
                painter.setBrush(QBrush(qcolor(226, 109, 40, 200)))
                painter.setPen(QPen(qcolor(226, 109, 40), 2))
                painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(qcolor(255, 255, 255) if locked or focused else qcolor(170, 178, 188))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)

    # ---- Profile picking & feature preview ------------------------------
    def set_preview(self, manifold: Optional[m3d.Manifold], operation: str = "new_body", extra=None, extra_op: str = "join"):
        """Shows a translucent preview solid (None clears it). `extra` is a second solid in another colour
        (a pattern both adds and removes material). Under a section view only the kept side is shown, like the bodies."""
        manifold, extra = self.section_trim(manifold), self.section_trim(extra)
        if manifold is None or manifold.is_empty():
            self.preview_mesh = None
        else:
            self.preview_mesh = CadKernel.extract_render_mesh(manifold)
        self.preview_extra = (CadKernel.extract_render_mesh(extra), extra_op) if extra is not None and not extra.is_empty() else None
        self.preview_op = operation
        self.update()

    def pick_profile(self, x: float, y: float) -> Optional[Tuple[str, int]]:
        """Returns (sketch_id, profile_idx) of the smallest closed profile under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_area, best_t = None, 0.0, 0.0
        for s_id, sketch in self.doc.sketches.items():
            if not sketch.visible or sketch is self.doc.active_sketch or not sketch.profiles:
                continue
            plane = sketch.plane
            hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
            if hit is None:
                continue
            t = float(np.linalg.norm(hit - origin))
            u, v = plane.world_to_uv(hit)
            for idx, prof in enumerate(sketch.profiles):
                if not prof.contains_point(u, v):
                    continue
                # Nearest plane wins; on the same plane the smallest profile wins
                if best is None or t < best_t - 1e-3 or (abs(t - best_t) <= 1e-3 and prof.area < best_area):
                    best, best_area, best_t = (s_id, idx), prof.area, t
        return best

    def _sketches_share_plane(self, a: str, b: str) -> bool:
        from omacad.model.timeline import _planes_coincide
        sa, sb = self.doc.sketches.get(a), self.doc.sketches.get(b)
        return sa is not None and sb is not None and _planes_coincide(sa.plane, sb.plane)

    def _selection_fill(self) -> Optional[np.ndarray]:
        """Triangles of what an extrude of the current selection would take: the chosen profiles minus the shapes
        of other sketches inside them (those stay unshaded; Shift+click them to include them)."""
        doc = self.doc
        sid, idx = doc.selected_profile
        key = ("selection", sid, idx, tuple(doc.selected_extra))
        cached = self._profile_fill_cache.get(key)
        if cached is not None:
            return cached
        sketch = doc.sketches.get(sid)
        if not sketch or idx >= len(sketch.profiles):
            return None
        from omacad.model.timeline import ExtrudeFeature, region_cross_section
        extra, refs, holes = ExtrudeFeature.selection_parts(doc, sid, idx, doc.selected_extra)
        feat = ExtrudeFeature("sel", "sel", sid, idx, 1.0, extra_profiles=extra, extra_refs=refs, holes=holes)
        idxs = [idx] + [i for i in extra if i != idx and i < len(sketch.profiles)]
        solid = m3d.Manifold.extrude(region_cross_section(feat.region(doc, sketch, idxs)), height=0.02)
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        mesh = solid.to_mesh()
        tris = mesh.vert_properties[:, :3][mesh.tri_verts].reshape(-1, 3).astype(np.float32)
        self._profile_fill_cache[key] = tris
        return tris

    def _profile_fill(self, key: Tuple[str, int]) -> Optional[np.ndarray]:
        """World-space triangles for a profile's filled face (cached)."""
        cached = self._profile_fill_cache.get(key)
        if cached is not None:
            return cached
        sketch = self.doc.sketches.get(key[0])
        if not sketch or key[1] >= len(sketch.profiles):
            return None
        solid = m3d.Manifold.extrude(profile_cross_section(sketch.profiles[key[1]]), height=0.02)
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        mesh = solid.to_mesh()
        tris = mesh.vert_properties[:, :3][mesh.tri_verts].reshape(-1, 3).astype(np.float32)
        self._profile_fill_cache[key] = tris
        return tris

    def _update_profile_hover(self, x: float, y: float):
        hover = None
        if not self.doc.active_sketch and not self.is_orbiting and not self.is_panning:
            hover = self.pick_profile(x, y)
        if hover != self.hover_profile:
            self.hover_profile = hover
            self.update()

    def initializeGL(self):
        GL.glClearColor(*theme.palette().canvas_rgb01(), 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        # Blend colour only; keep destination alpha at 1 so the compositor never shows the desktop through
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ZERO, GL.GL_ONE)
        GL.glEnable(GL.GL_LINE_SMOOTH)

        # Create VAO and VBOs for modern OpenGL
        self.vao = GL.glGenVertexArrays(1)
        self.vbo_pos = GL.glGenBuffers(1)
        self.vbo_norm = GL.glGenBuffers(1)
        self._body_gpu_cache = {}  # (body_id, mesh_id) -> {"vao_solid", "vbo_pos", "vbo_norm", "vert_count", "vao_lines", "vbo_lines", "line_count"}

        # Compile solid shader
        try:
            vs_solid = shaders.compileShader(VERTEX_SHADER_SOLID, GL.GL_VERTEX_SHADER)
            fs_solid = shaders.compileShader(FRAGMENT_SHADER_SOLID, GL.GL_FRAGMENT_SHADER)
            self.prog_solid = shaders.compileProgram(vs_solid, fs_solid)

            vs_flat = shaders.compileShader(VERTEX_SHADER_FLAT, GL.GL_VERTEX_SHADER)
            fs_flat = shaders.compileShader(FRAGMENT_SHADER_FLAT, GL.GL_FRAGMENT_SHADER)
            self.prog_flat = shaders.compileProgram(vs_flat, fs_flat)

            vs_thick = shaders.compileShader(VERTEX_SHADER_THICK, GL.GL_VERTEX_SHADER)
            self.prog_thick = shaders.compileProgram(vs_thick, fs_flat)
            self.vbo_thick = GL.glGenBuffers(1)

            vs_tex = shaders.compileShader(VERTEX_SHADER_TEXTURE, GL.GL_VERTEX_SHADER)
            fs_tex = shaders.compileShader(FRAGMENT_SHADER_TEXTURE, GL.GL_FRAGMENT_SHADER)
            self.prog_tex = shaders.compileProgram(vs_tex, fs_tex)
        except Exception as e:
            print(f"Error compiling CAD shaders: {e}")

    def draw_buffer_arrays(self, mode, pos_loc, pos_data: np.ndarray, norm_loc=None, norm_data=None):
        """Safely draws arrays using bound VAO and VBO buffers for modern OpenGL."""
        if len(pos_data) == 0 or pos_loc < 0:
            return
        GL.glBindVertexArray(self.vao)

        pos_float = np.ascontiguousarray(pos_data, dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_pos)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_float.nbytes, pos_float, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(pos_loc)
        GL.glVertexAttribPointer(pos_loc, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        if norm_loc is not None and norm_loc >= 0 and norm_data is not None and len(norm_data) > 0:
            norm_float = np.ascontiguousarray(norm_data, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_norm)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, norm_float.nbytes, norm_float, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(norm_loc)
            GL.glVertexAttribPointer(norm_loc, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        count = pos_float.size // 3
        GL.glDrawArrays(mode, 0, count)

        GL.glDisableVertexAttribArray(pos_loc)
        if norm_loc is not None and norm_loc >= 0:
            GL.glDisableVertexAttribArray(norm_loc)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

    def set_line_width(self, width: float):
        """Safely sets line width avoiding GL_INVALID_VALUE in OpenGL Core Profile."""
        try:
            GL.glLineWidth(min(1.0, float(width)))
        except Exception:
            pass

    def resizeGL(self, w: int, h: int):
        GL.glViewport(0, 0, w, h)

    def get_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculates Model, View, and Projection matrices."""
        w = max(1, self.width())
        h = max(1, self.height())
        aspect = float(w) / float(h)
        from omacad.ui.settings import get_settings
        settings = get_settings()
        proj, view = camera_matrices(self.target, self.distance, self.azimuth, self.elevation, aspect,
                                     float(settings.get("view_fov", 30.0)),
                                     settings.get("view_projection", "perspective") == "orthographic")
        mvp = proj @ view
        return proj, view, mvp

    def paintGL(self):
        # QPainter (used for the overlay) resets GL state at the end of every frame,
        # so depth testing/blending must be re-enabled before each render.
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glEnable(GL.GL_BLEND)
        # Blend colour only; keep destination alpha at 1 so the compositor never shows the desktop through
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ZERO, GL.GL_ONE)
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glClearColor(*theme.palette().canvas_rgb01(), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        proj, view, mvp = self.get_matrices()

        # 1. Draw 3D Ground Grid
        if self.show_grid:
            self.render_ground_grid(mvp)
            sk = self.doc.active_sketch
            if sk is not None and sk.plane.name == "FACE":
                self.render_plane_grid(mvp, sk.plane)

        self.render_origin_axes(mvp)

        # 2. Draw Canvases / Reference Images
        self.render_canvases(mvp)

        # 3. Draw 3D Solid Bodies
        self.render_bodies(mvp)

        # 3. Draw Active or Visible Sketches
        self.render_sketches(mvp)
        self.render_profile_fills(mvp)
        self.render_preview(mvp)
        self.render_plane_pick(mvp)
        self.render_edge_pick(mvp)
        self.render_section_cap(mvp)
        self.render_extrude_handle(mvp)
        self.render_move_gizmo(mvp)
        if (self.offset_preview is not None or self.fillet_preview is not None) and self.prog_thick is not None:
            prev_lines = self.fillet_preview if self.fillet_preview is not None else self.offset_preview
            GL.glDisable(GL.GL_DEPTH_TEST)
            self.draw_thick_lines(mvp, prev_lines, (1.0, 0.65, 0.2, 1.0), 3.0, halo=True)
            GL.glEnable(GL.GL_DEPTH_TEST)

        # 4. Draw QPainter Overlay (ViewCube, HUD, sketch measurements)
        painter = QPainter(self)
        try:
            self.draw_painter_overlays(painter)
        finally:
            painter.end()

    def _get_canvas_texture(self, cid: str, b64_data: str) -> Optional[int]:
        key = hash(b64_data)
        cached = self._canvas_textures.get(cid)
        if cached is not None:
            if cached[0] == key:
                return cached[1]
            GL.glDeleteTextures([cached[1]])  # same id, new image (deleted + re-added, or other document)
            del self._canvas_textures[cid]
        try:
            import base64
            from PySide6.QtGui import QImage
            raw = base64.b64decode(b64_data)
            img = QImage()
            img.loadFromData(raw)
            if img.isNull():
                return None
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            tex_id = int(GL.glGenTextures(1))
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            bits = img.constBits()
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, bytes(bits))
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            self._canvas_textures[cid] = (key, tex_id)
            return tex_id
        except Exception as e:
            print(f"Error creating canvas texture for {cid}: {e}")
            return None

    def mousePressEvent(self, event):
        x = event.position().x()
        y = event.position().y()

        # Check ViewCube click first
        if self.viewcube.handle_mouse_press(int(x), int(y), self.width()):
            self.update()
            return

        if self.measure is not None and event.button() == Qt.MouseButton.LeftButton and self.measure["mode"] == "sketch":
            self._measure_click(x, y)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.move_gizmo:
            hit_ax = self._gizmo_hit(x, y)
            if hit_ax:
                g = self.move_gizmo
                g["dragging"] = True
                g["active_axis"] = hit_ax
                g["start_proj"] = self._gizmo_project_mouse(x, y, hit_ax)
                self.move_gizmo_axis_selected.emit(hit_ax)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
                return
        if event.button() == Qt.MouseButton.LeftButton and self.extrude_handle and self._handle_hit(x, y):
            self._handle_drag = True
            quality.set_interactive_mode(True)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Check HUD clicks
        h = self.height()
        w = self.width()
        hud_w, hud_h = 260, 36
        hud_rect = QRectF((w - hud_w) / 2.0, h - 50, hud_w, hud_h)
        if hud_rect.contains(x, y):
            rel_x = x - hud_rect.x()
            if rel_x < 65:
                self.nav_mode = "ORBIT"
            elif rel_x < 130:
                self.nav_mode = "PAN"
            elif rel_x < 195:
                self.zoom_fit()
            else:
                self.show_grid = not self.show_grid
            self.update()
            return

        # Dimension badge: a click edits the value, dragging it moves the dimension line out of the way
        if self.doc.active_sketch and event.button() == Qt.MouseButton.LeftButton:
            for dim_id, (rect, s_id, d_id, val) in list(self.dim_badges.items()):
                if rect.contains(x, y):
                    sk = self.doc.sketches.get(s_id)
                    dim = next((d for d in sk.dimensions if d.dim_id == d_id), None) if sk else None
                    self._dim_drag = {"sketch": sk, "dim": dim, "press": event.position(), "moved": False,
                                      "before": sk.to_dict() if sk else None, "value": val}
                    return

        # Handle Dimension Tool Click near geometry
        if self.doc.active_sketch and self.sketch_tool == "DIMENSION" and event.button() == Qt.MouseButton.LeftButton:
            uv = self.get_sketch_plane_uv(x, y)
            if uv and self.handle_dimension_tool_click(uv[0], uv[1]):
                return

        self.last_mouse_pos = event.position().toPoint()

        # Handle Offset Tool Click (Fusion style: a click takes the whole connected chain)
        if self.doc.active_sketch and self.sketch_tool == "OFFSET":
            if event.button() == Qt.MouseButton.RightButton:
                if self.selected_entities:
                    self._offset_go()
                else:
                    self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                ent = self._pick_entity(x, y)
                if ent is not None:
                    mods = event.modifiers()
                    single = bool(mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
                    if single:
                        # Toggle or deselect just this single entity
                        if ent.entity_id in self.selected_entities:
                            self.selected_entities.remove(ent.entity_id)
                        else:
                            self.selected_entities.add(ent.entity_id)
                    else:
                        ids = self.doc.active_sketch.connected_entities(ent.entity_id)
                        if ids <= self.selected_entities:
                            self.selected_entities -= ids
                        else:
                            self.selected_entities |= ids   # clicks add; click a picked chain again to drop it
                    self.selection_changed.emit()
                    self._offset_status()
                    self.update()
                    return
                if self._start_rubber(event):
                    return
                return

        # Handle Mirror Tool Click
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            if event.button() == Qt.MouseButton.RightButton:   # right-click: next step / back / cancel
                self.fillet_preview = None
                if self._mirror_phase == "pick" and self.selected_entities:
                    self._mirror_next()
                elif self._mirror_phase == "axis":
                    self._mirror_phase = "pick"
                    self._mirror_status()
                    self.update()
                else:
                    self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                if self._mirror_phase == "pick":
                    ent = self._pick_entity(x, y)
                    if ent is not None:
                        mods = event.modifiers()
                        single = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier))
                        if single:
                            if ent.entity_id in self.selected_entities:
                                self.selected_entities.remove(ent.entity_id)
                            else:
                                self.selected_entities.add(ent.entity_id)
                        else:
                            ids = self.doc.active_sketch.connected_entities(ent.entity_id)
                            self.selected_entities = (self.selected_entities - ids) if ids <= self.selected_entities else (self.selected_entities | ids)
                        self.selection_changed.emit()
                        self._mirror_status()
                        self.update()
                else:
                    self._mirror_at(x, y)
                return

        # Handle Trim Tool Click
        if self.doc.active_sketch and self.sketch_tool == "TRIM":
            if event.button() == Qt.MouseButton.RightButton:
                self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                self._trim_at(x, y)
                return

        # Handle Fillet Tool Click
        if self.doc.active_sketch and self.sketch_tool == "FILLET":
            if event.button() == Qt.MouseButton.RightButton:
                if self.fillet_first_line:
                    self.fillet_first_line = None
                    self.status_message.emit("Fillet: click a corner between two lines, or click two lines (Esc cancels).")
                    self.update()
                    return
                self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                if self.fillet_hover_corner:
                    pt, la, lb = self.fillet_hover_corner
                    item = (pt, la.entity_id, lb.entity_id)
                    here = next((c for c in self.fillet_picked if math.hypot(c[0][0] - pt[0], c[0][1] - pt[1]) < 1e-3), None)
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        # Shift+click collects corners; Enter (or a plain click on one more corner) rounds them all
                        if here is not None:
                            self.fillet_picked.remove(here)
                        else:
                            self.fillet_picked.append(item)
                        n = len(self.fillet_picked)
                        self.status_message.emit(f"Fillet: {n} corner(s) picked. Shift+click more, then press Enter (or click one more corner) to set the radius.")
                        self.update()
                        return
                    if self.fillet_picked:
                        if here is None:
                            self.fillet_picked.append(item)
                        self._fillet_apply_picked()
                        return
                    self.prompt_fillet_radius(la, lb, pt)
                    return
                ent = self._pick_entity(x, y)
                from omacad.model.sketch import SketchLine
                if ent and isinstance(ent, SketchLine):
                    if self.fillet_first_line is None:
                        self.fillet_first_line = ent
                        self.status_message.emit("Fillet: now click the second line to round the corner between them.")
                    else:
                        first = self.fillet_first_line
                        self.fillet_first_line = None
                        if first.entity_id != ent.entity_id:
                            self.prompt_fillet_radius(first, ent)
                        else:
                            self.status_message.emit("Fillet: pick two different lines.")
                    self.update()
                    return
                if self._start_rubber(event):
                    return
                return

        # Handle Sketch Drawing Click
        if self.doc.active_sketch and self.sketch_tool != "NONE":
            # Right click finishes current line chain or cancels step
            if event.button() == Qt.MouseButton.RightButton:
                if self.sketch_tool == "DIMENSION":
                    self._rpress = event.position()  # a plain right-click still opens the element menu
                    self._dim_pending, self._dim_place = [], None
                    self.update()
                    return
                if self._move:
                    self._end_move(False)
                self.sketch_start_uv = None
                self.sketch_second_uv = None
                self.dyn.reset()
                self.smart.reset()
                self.update()
                return

            if event.button() == Qt.MouseButton.LeftButton and self.sketch_tool == "SMART_CIRCLE":
                self._smart_accept()
                return

            if event.button() == Qt.MouseButton.LeftButton and self.sketch_current_uv is not None:
                snapped_u, snapped_v = self.sketch_current_uv

                if self.sketch_start_uv is None:
                    # First click
                    self.sketch_start_uv = (snapped_u, snapped_v)
                    if self.sketch_tool == "MOVE":
                        self._begin_move(self.selected_entities)
                    self._arm_dyn()
                else:
                    self._commit_sketch_point((snapped_u, snapped_v))
                self.update()
                return

        # Click on a constraint glyph removes that constraint
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            for rect, cid in self.constraint_badges:
                if rect.contains(x, y):
                    if self.doc.remove_constraint(self.doc.active_sketch.sketch_id, cid):
                        self.status_message.emit(self.doc.last_message)
                    return

        # Press on a sketch element: select it and prepare a drag-move
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            ent = self._pick_entity(x, y)
            if ent is not None:
                if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                    self.selected_entities ^= {ent.entity_id}   # Shift/Ctrl+click: add or remove one element
                    self._press_pos = None
                    self.selection_changed.emit()
                    self.update()
                    return
                if ent.entity_id not in self.selected_entities:
                    self.selected_entities = {ent.entity_id}
                    self.selection_changed.emit()
                uv = self.get_sketch_plane_uv(x, y)
                if uv is not None and not getattr(ent, "projected", False):   # edges of the body can't be dragged away
                    self._drag = {"press_uv": uv, "press_pos": event.position(), "moved": False, "ent_id": ent.entity_id}
                self.update()
                return

        # Box selection on empty sketch space (Alt+drag orbits instead)
        if (event.button() == Qt.MouseButton.LeftButton and self.doc.active_sketch and self.sketch_tool == "NONE"
                and not self.plane_pick_mode and self.measure is None and self._pick_entity(x, y) is None
                and self._start_rubber(event)):
            return

        # Standard Navigation
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.is_panning = True
            if event.button() == Qt.MouseButton.LeftButton and not self.doc.active_sketch:
                self._press_pos = event.position()   # Shift+click without moving selects (adds a profile); dragging still pans
        elif event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position()
            if self.nav_mode == "PAN":
                self.is_panning = True
            else:
                self.is_orbiting = True
        elif event.button() == Qt.MouseButton.RightButton:
            self._rpress = event.position()
            self.is_panning = True

    def mouseDoubleClickEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if self.doc.active_sketch and event.button() == Qt.MouseButton.LeftButton:
            for dim_id, (rect, s_id, d_id, val) in list(self.dim_badges.items()):
                if rect.contains(x, y):
                    self.prompt_edit_dimension(s_id, d_id, val)
                    return
        if event.button() == Qt.MouseButton.LeftButton and self.edge_pick_mode:
            e = self._pick_edge(x, y)
            if e is not None:
                for c in self._edge_loop(e, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                    if not any(self._same_edge(c, k) for k in self.selected_edges):
                        self.selected_edges.append(c)
                self.edges_selection_changed.emit()
                self.update()
            else:
                hit = self._pick_face(x, y)
                if hit is not None:
                    body, face = hit
                    face_edges = self._edges_of_face(face, body)
                    for fe in face_edges:
                        if not any(self._same_edge(fe, k) for k in self.selected_edges):
                            self.selected_edges.append(fe)
                    self.edges_selection_changed.emit()
                    self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            ent = self._pick_entity(x, y)
            if ent is not None:
                # Double-click selects everything joined to this element (e.g. a whole rectangle)
                self._drag = None
                self.selected_entities = self.doc.active_sketch.connected_entities(ent.entity_id)
                self.selection_changed.emit()
                self.update()
                return
        super().mouseDoubleClickEvent(event)

    @property
    def _dim_place(self):
        return self._dim_place_v

    @_dim_place.setter
    def _dim_place(self, value):
        self._dim_place_v = value
        if value is None:
            self._hide_dim_box()

    def _hide_dim_box(self):
        box, self._dim_box = getattr(self, "_dim_box", None), None
        if box is not None:
            box.hide()
            box.deleteLater()

    def _dim_drag_move(self, event):
        from omacad.model.dim_layout import offset_for_point
        d = self._dim_drag
        if not d["moved"] and (event.position() - d["press"]).manhattanLength() < 5:
            return
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        off = offset_for_point(d["sketch"], d["dim"], uv) if uv is not None and d["dim"] is not None else None
        if off is None:
            return                              # this kind of dimension has nothing to move: a click still edits it
        d["moved"] = True
        d["dim"].offset_distance = float(off)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def _dim_drag_release(self):
        d, self._dim_drag = self._dim_drag, None
        self.unsetCursor()
        if d["moved"]:
            self.doc.record_sketch_change(d["sketch"], d["before"])   # one undo step for the whole drag
            self.update()
        elif d["sketch"] is not None:
            self.prompt_edit_dimension(d["sketch"].sketch_id, d["dim"].dim_id, d["value"])

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if self._rubber is not None:
            self._rubber["p1"] = event.position()
            self.update()
            return

        # Check ViewCube hover
        if self.viewcube.handle_mouse_move(int(x), int(y), self.width()):
            self.update()

        if self.move_gizmo:
            g = self.move_gizmo
            if g.get("dragging"):
                cur_proj = self._gizmo_project_mouse(x, y, g["active_axis"])
                delta = cur_proj - g["start_proj"]
                self.move_gizmo_dragged.emit(g["active_axis"], delta)
                self.update()
                return
            else:
                hover_ax = self._gizmo_hit(x, y)
                if hover_ax != g.get("hover_axis"):
                    g["hover_axis"] = hover_ax
                    self.setCursor(Qt.CursorShape.OpenHandCursor if hover_ax else Qt.CursorShape.ArrowCursor)
                    self.update()

        if self._handle_drag:
            val = self._handle_value(x, y)
            if val is not None:
                self.extrude_handle["dist"] = val
                self.extrude_handle_dragged.emit(val)
                self.update()
            return
        if self.extrude_handle:
            hover = self._handle_hit(x, y)
            if hover != self._handle_hover:
                self._handle_hover = hover
                self.setCursor(Qt.CursorShape.OpenHandCursor if hover else Qt.CursorShape.ArrowCursor)
                self.update()
        if self._dim_place and self._dim_box is not None:
            uv = self.get_sketch_plane_uv(x, y)
            if uv is not None:
                self._dim_hover_uv = uv
                _kind, measured, label = self._dim_points_kind(self._dim_place, uv[0], uv[1])
                self._dim_box.set_measure(label, measured)
        if self._dim_drag is not None:
            self._dim_drag_move(event)
            return
        if self._drag is not None:
            self._drag_move(event)
            return
        if self.edge_pick_mode:
            if not self.is_orbiting and not self.is_panning:
                self._update_edge_hover(x, y)
        elif self.plane_pick_mode:
            if not self.is_orbiting and not self.is_panning:
                if self.plane_pick_purpose == "offset_surface":
                    self.surface_hover.emit(self._pick_surface(x, y))
                elif self.plane_pick_purpose == "offset_face":
                    self._update_offset_hover(x, y)
                else:
                    self._update_plane_hover(x, y)
        else:
            self._update_profile_hover(x, y)
            if not self.is_orbiting and not self.is_panning:
                self._update_entity_hover(x, y)
                if self._idle_hover_ok():
                    self._update_edge_hover(x, y)
                    if self.hover_edge is None and self.hover_face is None:
                        self._update_idle_plane_hover(x, y)
                    elif self.hover_plane is not None:
                        self.hover_plane = None
                        self.update()
                elif self.hover_edge is not None or self.hover_face is not None:
                    if self.hover_edge is not None:
                        self.hover_info_changed.emit(None)
                    self.hover_edge = self.hover_face = None
                    self.update()

        # Check Dimension Badge Hover
        prev_hovered = self.hovered_dim_id
        hovered = None
        if self.doc.active_sketch:
            for dim_id, (rect, s_id, d_id, val) in self.dim_badges.items():
                if rect.contains(x, y):
                    hovered = dim_id
                    break

        self.hovered_dim_id = hovered
        if hovered:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.sketch_tool in ("LINE", "RECT", "ROUNDED_RECT", "CENTER_RECT", "CENTER_ROUNDED_RECT", "CIRCLE", "SMART_CIRCLE", "POLYGON", "ARC", "SLOT", "FILLET", "TRIM", "MIRROR", "OFFSET", "DIMENSION", "MOVE"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if hovered != prev_hovered:
            self.update()

        if self.doc.active_sketch and self.sketch_tool == "TRIM":
            self._trim_hover(x, y)
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            self._mirror_hover(x, y)

        if self.doc.active_sketch and self.sketch_tool == "FILLET":
            sk = self.doc.active_sketch
            best_c = None
            corners = sk.find_corners()
            best_d = 16.0  # pixels
            for pt, la, lb, ea, eb in corners:
                scr = self.world_to_screen(sk.plane.uv_to_world(*pt))
                if scr:
                    d = math.hypot(x - scr[0], y - scr[1])
                    if d < best_d:
                        best_d = d
                        best_c = (pt, la, lb)
            if best_c != self.fillet_hover_corner:
                self.fillet_hover_corner = best_c
                self.update()

        # Active sketch snapping and preview tracking
        if self.doc.active_sketch and self.sketch_tool != "NONE":
            uv = self.get_sketch_plane_uv(x, y)
            if uv is not None:
                enable_grid = self.sketch_palette.chk_snap_grid.isChecked()
                enable_pts = self.sketch_palette.chk_snap_points.isChecked()
                grid_step = 5.0 if enable_grid else 0.0

                snap_res = SketchSnapper.snap(
                    raw_uv=uv,
                    sketch=self.doc.active_sketch,
                    start_uv=self.sketch_start_uv,
                    snap_distance=max(0.3, min(8.0, self._entity_tolerance() * 1.25)),  # ~10 screen px
                    reference_segments=self._reference_segments(),
                    grid_step=grid_step,
                    enable_grid_snap=enable_grid,
                    enable_geom_snap=enable_pts
                )
                self.active_snap = snap_res
                if self.sketch_tool == "SMART_CIRCLE":
                    if not self.hasFocus():
                        self.setFocus()
                    self.smart.mouse = uv
                    self.smart.segments = self._smart_segments()
                self.sketch_current_uv = snap_res.uv
                self._raw_mouse_uv = snap_res.uv
                self._refresh_dyn()
                self.update()
        else:
            if self.active_snap is not None:
                self.active_snap = None
                self.update()

        dx = x - self.last_mouse_pos.x()
        dy = y - self.last_mouse_pos.y()
        self.last_mouse_pos = event.position().toPoint()

        if self.is_orbiting:
            self.azimuth = (self.azimuth - dx * 0.5) % 360.0
            self.elevation = max(-89.9, min(89.9, self.elevation + dy * 0.5))
            self.update()
        elif self.is_panning:
            # Move target along camera's right and up vectors
            proj, view, _ = self.get_matrices()
            inv_view = np.linalg.inv(view)
            right = inv_view[:3, 0]
            up = inv_view[:3, 1]

            pan_speed = self.distance * 0.0018
            self.target -= right * (dx * pan_speed)
            self.target += up * (dy * pan_speed)
            self.update()

    # ---- Right-click menu on a sketch element ---------------------------------------
    def _start_guided_dimension(self, pending, hint: str, side=None):
        """Switches to the dimension tool with the first element already picked; the status bar says
        what to click next."""
        self.set_sketch_tool("DIMENSION")
        self._dim_pending = list(pending)
        self._dim_side = side
        self.status_message.emit(hint)
        self.update()

    def _show_element_menu(self, event, ent):
        """Right-click on a line/circle: dimensions and constraints for that element, with help text."""
        sk = self.doc.active_sketch
        self.selected_entities = {ent.entity_id}
        self.selection_changed.emit()
        self.update()
        menu = _vp_module.QMenu(self)
        menu.setToolTipsVisible(True)
        acts = {}

        def add(key, label, tip):
            a = theme.action_with_icon(menu, label)
            a.setToolTip(tip)
            a.setStatusTip(tip)
            acts[a] = key
            return a

        def heading(text):
            h = menu.addAction(text)
            h.setEnabled(False)

        members = sk.group_entities(ent)
        poly_circle = next((m for m in members if isinstance(m, SketchCircle)), None)
        poly_line = next((m for m in members if isinstance(m, SketchLine)), None)
        if poly_circle is not None and poly_line is not None:
            heading("Polygon - set a dimension")
            add("p_side", "📏 Side length…", "Type how long each side should be (all sides stay equal).")
            add("p_dia", "Ø Circle through the corners…", "Type the diameter of the circle the corners lie on (corner to corner across the centre).")
            add("p_centre", "◎ Distance from the centre to…", "Then click a point, a line or a face edge to measure from the middle of the polygon.")
            add("p_fix", "🔒 Fix the polygon in place", "Locks the whole polygon so it can't move.")
            menu.addSeparator()
        if isinstance(ent, SketchLine):
            heading("Line - set a dimension")
            add("length", "📏 Length…", "Type how long this line should be.")
            add("angle", "📐 Angle to another line…", "Then click the other line; you get an angle between them.")
            add("p1", "📍 Distance from start point to…", "Then click a point, another line or a face edge to measure to it.")
            add("p2", "📍 Distance from end point to…", "Then click a point, another line or a face edge to measure to it.")
            menu.addSeparator()
            heading("Make it")
            add("horizontal", "━ Horizontal", "Keeps the line level.")
            add("vertical", "┃ Vertical", "Keeps the line upright.")
            add("fix", "🔒 Fixed in place", "Locks the line so it can't move or change.")
        elif isinstance(ent, SketchCircle):
            heading("Circle - set a dimension")
            add("diameter", "Ø Diameter…", "Type the diameter of the circle.")
            add("centre", "◎ Distance from the centre to…", "Then click a point, a line or a face edge to measure from the centre.")
            add("near", "⭕ Distance from the nearest edge to…", "Then click a line or a face edge; measured from the side of the circle facing it.")
            add("far", "⭕ Distance from the far edge to…", "Then click a line or a face edge; measured from the side of the circle facing away.")
            menu.addSeparator()
            heading("Make it")
            add("fix", "🔒 Fixed in place", "Locks the circle so it can't move or change.")
        else:
            heading("Arcs and slots can't be dimensioned yet")
        menu.addSeparator()
        add("fillet", "╭ Fillet corner…  (F)", "Rounds a corner between lines with an arc.")
        add("offset", "↔️ Offset…  (O)", "Makes a parallel copy at a distance you type (select several, or double-click, to offset a whole shape).")
        add("delete", "🗑️ Delete", "Removes this element (and its dimensions).")
        menu.addSeparator()
        general: dict = {}
        self._add_history_and_view(menu, general, True)

        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen in general:
            self._run_general(*general[chosen])
            return
        key = acts.get(chosen)
        if key is None:
            return
        pt = lambda name: [("pt", ent, name)]
        if key == "p_side":
            self._dim_length(poly_line)
            return
        if key == "p_dia":
            self._dim_circle(poly_circle)
            return
        if key == "p_centre":
            self._start_guided_dimension([("pt", poly_circle, "center")], "Distance from the polygon's centre: click a point, a line or a face edge.")
            return
        if key == "p_fix":
            self.selected_entities = {m.entity_id for m in members}
            self.apply_constraint("FIX")
            return
        if key == "length":
            self._dim_length(ent)
        elif key == "diameter":
            self._dim_circle(ent)
        elif key == "angle":
            self._start_guided_dimension([("ent", ent)], "Angle: click the other line. (Click empty space instead to dimension the length.)")
        elif key in ("p1", "p2"):
            self._start_guided_dimension(pt(key), "Distance: click a point, another line or a face edge to measure to.")
        elif key == "centre":
            self._start_guided_dimension(pt("center"), "Distance from the centre: click a point, a line or a face edge.")
        elif key in ("near", "far"):
            self._start_guided_dimension([("ent", ent)], f"Distance from the {key} edge: click a line or a face edge to measure to.", side=key)
        elif key in ("horizontal", "vertical"):
            self.apply_constraint(key.upper())
        elif key == "fix":
            self.apply_constraint("FIX")
        elif key == "fillet":
            self.set_sketch_tool("FILLET")
        elif key == "offset":
            self.set_sketch_tool("OFFSET")
        elif key == "delete":
            self.delete_selected_entities()

    def _add_tool_entries(self, menu: QMenu, acts: dict):
        """While a tool panel (Extrude, Fillet, ...) is open: finish or cancel it from the menu."""
        title = self.active_tool_title()
        if not title:
            return
        acts[theme.action_with_icon(menu, f"✔️ Finish {title}")] = ("cmd", "tool_ok")
        acts[theme.action_with_icon(menu, f"✖️ Cancel {title}")] = ("cmd", "tool_cancel")
        menu.addSeparator()

    def _add_history_and_view(self, menu: QMenu, acts: dict, sketch: bool):
        """The entries every right-click menu ends with: undo/redo and view options (and Join with 2+ bodies selected)."""
        chosen = [b for b in self.doc.selected_body_ids if b in self.doc.bodies]
        if len(chosen) >= 2 and not sketch and not self.active_tool_title():
            names = ", ".join(self.doc.bodies[b].name for b in chosen)
            acts[theme.action_with_icon(menu, f"🔗 Join {len(chosen)} Bodies ({names})")] = ("join_bodies", list(chosen))
            menu.addSeparator()
        u, r = self.doc.undo_label(), self.doc.redo_label()
        a = theme.action_with_icon(menu, f"↩️ Undo {u}" if u else "↩️ Undo")
        a.setEnabled(u is not None)
        acts[a] = ("cmd", "undo")
        a = theme.action_with_icon(menu, f"↪️ Redo {r}" if r else "↪️ Redo")
        a.setEnabled(r is not None)
        acts[a] = ("cmd", "redo")
        menu.addSeparator()
        view = menu.addMenu("👁️ View")
        if sketch:
            acts[view.addAction("Look at sketch")] = ("look", None)
        else:
            for name in ("Home", "Top", "Front", "Right"):
                acts[view.addAction(name)] = ("view", name)
        acts[view.addAction("Fit to window")] = ("fit", None)
        view.addSeparator()
        g = view.addAction("Grid")
        g.setCheckable(True)
        g.setChecked(self.show_grid)
        acts[g] = ("grid", None)
        e = view.addAction("Edges")
        e.setCheckable(True)
        e.setChecked(self.show_edges)
        acts[e] = ("edges", None)

    def _run_general(self, kind, arg):
        if kind == "cmd":
            self.menu_command.emit(arg)
        elif kind == "view":
            self.set_view(arg)
        elif kind == "fit":
            self.zoom_fit()
        elif kind == "look" and self.doc.active_sketch:
            self.align_to_plane(self.doc.active_sketch.plane)
        elif kind == "grid":
            self.show_grid = not self.show_grid
            self.update()
        elif kind == "edges":
            self.show_edges = not self.show_edges
            self.update()
        elif kind == "round":
            self.round_requested.emit(*arg)
        elif kind == "offset_face":
            self.offset_face_requested.emit(arg)
        elif kind == "offset_plane":
            self.offset_base_picked.emit(arg)
        elif kind == "join_bodies":
            self.join_bodies_requested.emit(arg)
        elif kind == "split_plane":
            self.split_plane_requested.emit(arg)
        elif kind == "sketch_plane":
            self.plane_picked.emit(arg)
        elif kind == "hide_plane":
            if arg[0] == "origin":
                self.doc.set_origin_visibility("plane", arg[1], False)
            else:
                self.doc.toggle_construction_plane(arg[1])
            self.hover_plane = None
            self.update()
        elif kind == "tool":
            self.set_sketch_tool(arg)
        elif kind == "construction":
            self.toggle_construction_mode()
        elif kind == "finish":
            self.finish_sketch_requested.emit()
        elif kind == "sketch":
            self.menu_command.emit(f"sketch:{arg}")
        elif kind == "edit_sketch":
            self.edit_sketch_requested.emit(arg)
        elif kind == "extrude_sketch":
            self.extrude_sketch_requested.emit(arg)
        elif kind == "hide_sketch":
            self.doc.toggle_sketch_visibility(arg)

    def _sketch_line_at(self, x: float, y: float):
        """Id of the visible sketch whose lines or circles are under the cursor (model mode), else None."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        tol, best, best_t = self._entity_tolerance(), None, float("inf")
        for sid, sk in self.doc.sketches.items():
            if not sk.visible:
                continue
            hit = ray_plane_intersect(origin, ray_dir, sk.plane.origin, sk.plane.normal)
            if hit is None:
                continue
            u, v = sk.plane.world_to_uv(hit)
            t = float(np.linalg.norm(hit - origin))
            if t < best_t and sk.hit_test(u, v, tol) is not None:
                best, best_t = sid, t
        return best

    def _show_sketch_menu(self, event, sketch_id: str):
        """Right-click on a sketch (not in sketch mode): Edit Sketch first, as in Fusion 360."""
        sk = self.doc.sketches.get(sketch_id)
        if sk is None:
            return
        menu = _vp_module.QMenu(self)
        acts: dict = {}
        acts[theme.action_with_icon(menu, "✏️ Edit Sketch")] = ("edit_sketch", sketch_id)
        acts[theme.action_with_icon(menu, "⬆️ Extrude\tE")] = ("extrude_sketch", sketch_id)
        acts[theme.action_with_icon(menu, "👁️ Hide Sketch")] = ("hide_sketch", sketch_id)
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)

    def _show_profile_menu(self, event, key):
        """Right-click on a sketch profile (the shaded area inside closed lines): act on that profile only,
        without lighting up the face around it."""
        doc = self.doc
        if key != doc.selected_profile and key not in doc.selected_extra:
            doc.selected_profile, doc.selected_extra = key, []   # right-click selects it, like left-click
            self.profile_picked.emit()
        self.update()
        menu = _vp_module.QMenu(self)
        acts: dict = {}
        acts[theme.action_with_icon(menu, "✏️ Edit Sketch")] = ("edit_sketch", key[0])
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        n = 1 + len(doc.selected_extra)
        what = "profile" if n == 1 else f"{n} profiles"
        acts[theme.action_with_icon(menu, f"⬆️ Extrude this {what}…")] = ("cmd", "extrude")
        acts[theme.action_with_icon(menu, f"🔄 Revolve this {what}…")] = ("cmd", "revolve")
        acts[theme.action_with_icon(menu, "✖️ Deselect")] = ("deselect", None)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen is None:
            return
        if chosen[0] == "deselect":
            doc.selected_profile, doc.selected_extra = None, []
            self.profile_picked.emit()
            self.update()
        else:
            self._run_general(*chosen)

    def _show_axis_menu(self, event):
        """Right-click while the Move arrows are shown: pick the axis to drag along."""
        menu = _vp_module.QMenu(self)
        acts = {}
        for ax, label in (("X", "🔴 Move along X"), ("Y", "🟢 Move along Y"), ("Z", "🔵 Move along Z")):
            acts[theme.action_with_icon(menu, label)] = ax
        menu.addSeparator()
        general: dict = {}
        self._add_tool_entries(menu, general)
        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen in acts:
            self.move_gizmo["active_axis"] = acts[chosen]
            self.move_gizmo_axis_selected.emit(acts[chosen])
            self.update()
        elif chosen in general:
            self._run_general(*general[chosen])

    def _show_general_menu(self, event):
        """Right-click on empty space: what you can do next, depending on whether a sketch is open."""
        menu = _vp_module.QMenu(self)
        acts: dict = {}
        sketch = self.doc.active_sketch is not None
        self._add_tool_entries(menu, acts)
        if sketch:
            acts[theme.action_with_icon(menu, "✔️ Finish Sketch")] = ("finish", None)
            menu.addSeparator()
            groups: dict = {}
            for tool, label, group, sub in SKETCH_TOOLS:
                if group not in groups:
                    if sum(1 for t in SKETCH_TOOLS if t[2] == group) == 1:   # a lone tool needs no submenu
                        groups[group] = (menu, {})
                        label = f"{SKETCH_GROUP_ICONS.get(group, '')} {label}".strip()
                    else:
                        groups[group] = (menu.addMenu(f"{SKETCH_GROUP_ICONS.get(group, '')} {group}".strip()), {})
                parent, subs = groups[group]
                if sub:
                    if sub not in subs:
                        subs[sub] = parent.addMenu(sub)
                    parent = subs[sub]
                acts[parent.addAction(label)] = ("tool", tool)
            c = menu.addAction("Construction mode  (X)")
            c.setCheckable(True)
            c.setChecked(self.construction_mode)
            acts[c] = ("construction", None)
        else:
            new = menu.addMenu("✏️ New Sketch on")
            for name in ("XY", "XZ", "YZ"):
                acts[new.addAction(f"{name} plane")] = ("sketch", name)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, sketch)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)

    def _round_entries(self, menu, acts: dict, edges: list, what: str):
        """Fillet / Chamfer entries for the edges under the cursor (nothing while a tool panel is open)."""
        if self.active_tool_title():
            return
        for kind, icon in (("fillet", "🔵"), ("chamfer", "📐")):
            acts[theme.action_with_icon(menu, f"{icon} {kind.title()} {what}…")] = ("round", (kind, edges))
        menu.addSeparator()

    def _show_edge_menu(self, event, edge):
        """Right-click on a lit-up edge: fillet or chamfer it (and the edges joined to it smoothly)."""
        menu = _vp_module.QMenu(self)
        acts: dict = {}
        self._round_entries(menu, acts, tangent_chain(edge, self._visible_edges()), "this edge")
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)

    def _show_face_menu(self, event):
        """Right-click on a flat face: offer to sketch on it directly."""
        target = self._pick_plane_target(event.position().x(), event.position().y())
        if target is None or target[0] != "face":
            return
        face = target[1]
        self.ctx_face = face
        self.update()
        menu = _vp_module.QMenu(self)
        act_sketch = theme.action_with_icon(menu, "✏️ Create Sketch on this Face")
        act_extrude = theme.action_with_icon(menu, "⬆️ Extrude this Face…")
        act_extrude.setToolTip("Pull the face into the body to cut it away, or out to add material.")
        menu.setToolTipsVisible(True)
        acts: dict = {}
        if face.body_id in self.doc.bodies:
            menu.addSeparator()
            acts[theme.action_with_icon(menu, "⬇️ Lay this face on the ground (XY)")] = ("lay", "ground")
            acts[theme.action_with_icon(menu, "⬇️ Lay this face on a face or plane…")] = ("lay", "pick")
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        if not self.active_tool_title():
            acts[theme.action_with_icon(menu, "↔️ Offset Face…")] = ("offset_face", face)
            acts[theme.action_with_icon(menu, "📐 Offset Plane from this Face…")] = ("offset_plane", self.plane_from_target(("face", face)))
        body = self.doc.bodies.get(face.body_id)
        if body is not None:
            self._round_entries(menu, acts, self._edges_of_face(face, body), "edges of this face")
        self._add_history_and_view(menu, acts, False)
        chosen = menu.exec(event.globalPosition().toPoint())
        self.ctx_face = None
        self.update()
        if chosen in acts and acts[chosen][0] == "lay":
            self.lay_face_requested.emit(face, acts[chosen][1])
        elif chosen in acts:
            self._run_general(*acts[chosen])
        elif chosen is act_sketch:
            self.plane_picked.emit(self.plane_from_target(("face", face)))
        elif chosen is act_extrude:
            self.face_extrude_requested.emit(face)

    def _show_plane_menu(self, event, target):
        """Right-click on an origin or construction plane: split a body with it, offset from it, sketch on it, hide it."""
        menu = _vp_module.QMenu(self)
        acts: dict = {}
        plane = self.plane_from_target(target)
        name = f"{target[1]} plane" if target[0] == "origin" else self.doc.construction_planes[target[1]].get("name", "plane")
        menu.addSection(name)
        if not self.active_tool_title():
            if self.doc.bodies:
                acts[theme.action_with_icon(menu, "✂️ Split Body with this Plane…")] = ("split_plane", target[1])
            acts[theme.action_with_icon(menu, "📐 Offset Plane from this Plane…")] = ("offset_plane", plane)
            acts[theme.action_with_icon(menu, "✏️ Create Sketch on this Plane")] = ("sketch_plane", plane)
            menu.addSeparator()
        acts[theme.action_with_icon(menu, "👁 Hide Plane")] = ("hide_plane", target)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)

    def mouseReleaseEvent(self, event):
        if self._rubber is not None and event.button() == Qt.MouseButton.LeftButton:
            self._finish_rubber(event)
            return
        if (self.measure is not None and self.measure["mode"] == "model" and event.button() == Qt.MouseButton.LeftButton
                and self._press_pos is not None and (event.position() - self._press_pos).manhattanLength() < 4):
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            self._measure_click(event.position().x(), event.position().y())
            return
        if self.move_gizmo and self.move_gizmo.get("dragging") and event.button() == Qt.MouseButton.LeftButton:
            self.move_gizmo["dragging"] = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.move_gizmo.get("hover_axis") else Qt.CursorShape.ArrowCursor)
            self.move_gizmo_finished.emit()
            self.update()
            return
        if self._handle_drag and event.button() == Qt.MouseButton.LeftButton:
            self._handle_drag = False
            quality.set_interactive_mode(False)
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._handle_hover else Qt.CursorShape.ArrowCursor)
            self.extrude_handle_drag_finished.emit()
            self.update()
            return
        if event.button() == Qt.MouseButton.RightButton and self._rpress is not None:
            moved = (event.position() - self._rpress).manhattanLength()
            self._rpress = None
            self.is_panning = False
            if moved < 4 and not self.plane_pick_mode and not self.edge_pick_mode:
                if not self.doc.active_sketch and self.move_gizmo:
                    self._show_axis_menu(event)
                elif not self.doc.active_sketch and self.pick_profile(event.position().x(), event.position().y()) is not None:
                    self._show_profile_menu(event, self.pick_profile(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch and self._sketch_line_at(event.position().x(), event.position().y()) is not None:
                    self._show_sketch_menu(event, self._sketch_line_at(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch and not self.active_tool_title() and self._pick_edge(event.position().x(), event.position().y()) is not None:
                    self._show_edge_menu(event, self._pick_edge(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch:
                    target = self._pick_plane_target(event.position().x(), event.position().y())
                    if target is not None and target[0] == "face":
                        self._show_face_menu(event)
                    elif target is not None:
                        self._show_plane_menu(event, target)
                    else:
                        self._show_general_menu(event)
                elif self.sketch_tool in ("NONE", "DIMENSION") and not self._move:
                    ent = self._pick_entity(event.position().x(), event.position().y())
                    if ent is not None:
                        self._show_element_menu(event, ent)
                    else:
                        self._show_general_menu(event)
            return
        if self._dim_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dim_drag_release()
            return
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_release(event)
            return
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_pos is not None
            and not self.doc.active_sketch
            and (event.position() - self._press_pos).manhattanLength() < 4
        )
        if (event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None
                and self._can_select_sketch_entities()
                and (event.position() - self._press_pos).manhattanLength() < 4):
            additive = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            self.select_entity_at(event.position().x(), event.position().y(), additive)
            return
        if was_click and self.pick_step_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            hit = self._pick_surface(event.position().x(), event.position().y())
            if hit is not None:
                self.step_point_clicked.emit(hit["point"])
            return
        if was_click and self.edge_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            e = self._pick_edge(event.position().x(), event.position().y())
            if e is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:   # Ctrl+click only removes
                    chain = tangent_chain(e, self._visible_edges())
                    self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, c) for c in chain)]
                    self.edges_selection_changed.emit()
                    self.update()
                else:
                    self._toggle_edge(e)
            else:
                hit = self._pick_face(event.position().x(), event.position().y())
                if hit is not None:
                    body, face = hit
                    face_edges = self._edges_of_face(face, body)
                    if face_edges:
                        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                            # Ctrl+click removes all edges of this face
                            self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, fe) for fe in face_edges)]
                        else:
                            # If all edges of this face are already selected, toggle them off; otherwise select all
                            all_selected = all(any(self._same_edge(k, fe) for k in self.selected_edges) for fe in face_edges)
                            if all_selected:
                                self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, fe) for fe in face_edges)]
                            else:
                                for fe in face_edges:
                                    if not any(self._same_edge(k, fe) for k in self.selected_edges):
                                        self.selected_edges.append(fe)
                        self.edges_selection_changed.emit()
                        self.update()
            return
        if was_click and self.plane_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            if self.plane_pick_purpose == "offset_surface":
                hit = self._pick_surface(event.position().x(), event.position().y())
                if hit is not None:
                    self.end_plane_pick()
                    self.surface_picked.emit(hit)
                return
            if self.plane_pick_purpose == "offset_face":
                self._offset_face_click(event.position().x(), event.position().y())
                return
            if self.plane_pick_purpose == "thread_surface":
                cyl = self._pick_cylinder_surface(event.position().x(), event.position().y())
                if cyl is not None:
                    self.cylinder_picked.emit(cyl)
                    return
            target = self._pick_plane_target(event.position().x(), event.position().y())
            if target is not None:
                plane = self.plane_from_target(target)
                purpose = self.plane_pick_purpose
                if purpose not in ("move_body", "shell_face", "thread_surface", "offset_face"):
                    self.end_plane_pick()
                if purpose == "offset_base":
                    self.offset_base_picked.emit(plane)
                elif purpose == "section_base":
                    self.section_base_picked.emit(plane)
                elif purpose == "extrude_target":
                    self.target_plane_picked.emit(plane)
                elif purpose == "primitive_face":
                    self.primitive_face_picked.emit(plane)
                elif purpose == "shell_face":
                    self.shell_face_picked.emit(plane)
                elif purpose == "move_body":
                    self.move_body_picked.emit(plane)
                elif purpose == "lay_target":
                    self.lay_target_picked.emit(plane)
                else:
                    self.plane_picked.emit(plane)
            return
        self._press_pos = None
        self.is_orbiting = False
        self.is_panning = False
        if was_click:
            picked = self.pick_profile(event.position().x(), event.position().y())
            doc = self.doc
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and picked is not None:
                # Shift+click adds a profile to the selection, or removes it again
                chosen = ([doc.selected_profile] if doc.selected_profile else []) + list(doc.selected_extra)
                if picked in chosen:
                    chosen.remove(picked)
                elif not chosen or chosen[0][0] == picked[0] or self._sketches_share_plane(chosen[0][0], picked[0]):
                    chosen.append(picked)   # profiles of one sketch, or of sketches drawn in the same plane
                doc.selected_profile = chosen[0] if chosen else None
                doc.selected_extra = chosen[1:]
                self.profile_picked.emit()
                self.update()
            elif picked != doc.selected_profile or doc.selected_extra:
                doc.selected_profile = picked
                doc.selected_extra = []
                self.profile_picked.emit()
                self.update()
            if picked is None:
                clicked_body_id = self.pick_body(event.position().x(), event.position().y())
                if clicked_body_id is not None:
                    multi = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    doc.select_body(clicked_body_id, multi=multi)
                    self.body_clicked.emit(clicked_body_id)
                    self.update()
                else:
                    target = self._pick_plane_target(event.position().x(), event.position().y())
                    if target is not None and target[0] in ("origin", "cplane"):
                        self.plane_clicked.emit(target[1])     # e.g. Split Body takes it as its splitting plane
                    if doc.selected_body_ids:
                        doc.select_body(None)    # a click in empty space clears the body selection
                        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        from omacad.ui.settings import get_settings
        if get_settings().get("invert_zoom", False):
            delta = -delta
        factor = 0.9 if delta > 0 else 1.1
        self.distance = max(5.0, min(2000.0, self.distance * factor))
        self.update()

    def keyPressEvent(self, event):
        # If a feature tool dialog (e.g. Extrude) is open with an active distance input,
        # typing numbers, minus, period, comma, backspace or enter in the 3D view should
        # directly type into that field.
        if not self.doc.active_sketch:
            from omacad.ui import dialogs as _dialogs
            host = _dialogs.SIDE_HOST
            tool_dlg = getattr(host, "_extrude_dlg", None) or getattr(getattr(host, "inspector", None), "current_tool_dlg", None)
            if tool_dlg is not None and hasattr(tool_dlg, "spn_dist") and hasattr(tool_dlg, "focus_distance"):
                txt = event.text()
                if (txt and txt in "0123456789+-/*().,") or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                    tool_dlg.focus_distance()
                    if txt:
                        tool_dlg.spn_dist.lineEdit().event(event)
                    return
                elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    tool_dlg.accept()
                    return

        if self.measure is not None and event.key() == Qt.Key.Key_Escape:
            self.end_measure()
            return
        if self.measure is not None and self.measure["mode"] == "model" and event.key() == Qt.Key.Key_D:
            self._measure_set_distance()
            return
        if self.doc.active_sketch and self.sketch_tool == "FILLET" and self.fillet_picked:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._fillet_apply_picked()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.fillet_picked = []
                self.status_message.emit("Fillet: picked corners cleared.")
                self.update()
                return
        if self.doc.active_sketch and self.sketch_tool == "OFFSET":
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._offset_go()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.set_sketch_tool("NONE")
                return
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            k = event.key()
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._mirror_phase == "pick":
                self._mirror_next()
                return
            if k == Qt.Key.Key_Escape:
                self.fillet_preview = None
                self.set_sketch_tool("NONE")
                return
        if self.doc.active_sketch and self.sketch_tool == "SMART_CIRCLE" and self._smart_key(event):
            return
        if self._handle_dyn_key(event):
            return
        if (event.key() == Qt.Key.Key_Escape and self.sketch_tool == "DIMENSION"
                and (self._dim_pending or self._dim_place)):
            self._dim_pending, self._dim_place = [], None
            self.status_message.emit("Dimension cancelled.")
            self.update()
            return
        if self._can_select_sketch_entities():
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_entities:
                self.delete_selected_entities()
                return
            if event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.selected_entities = {e.entity_id for e in self.doc.active_sketch.entities}
                self.update()
                return
            if event.key() == Qt.Key.Key_Escape and self.selected_entities:
                self.selected_entities.clear()
                self.update()
                return
        if self.doc.active_sketch:
            if event.key() == Qt.Key.Key_L:
                self.set_sketch_tool("LINE")
                return
            elif event.key() == Qt.Key.Key_R:
                self.set_sketch_tool("RECT")
                return
            elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_sketch_tool("SMART_CIRCLE")
                return
            elif event.key() == Qt.Key.Key_C:
                self.set_sketch_tool("CIRCLE")
                return
            elif event.key() == Qt.Key.Key_P:
                self.set_sketch_tool("POLYGON")
                return
            elif event.key() == Qt.Key.Key_A:
                self.set_sketch_tool("ARC")
                return
            elif event.key() == Qt.Key.Key_X:
                self.toggle_construction_mode()
                return
            elif event.key() == Qt.Key.Key_D:
                self.set_sketch_tool("DIMENSION")
                return
            elif event.key() == Qt.Key.Key_M and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_sketch_tool("MIRROR")
                return
            elif event.key() == Qt.Key.Key_M:
                self.set_sketch_tool("MOVE")
                return
            elif event.key() == Qt.Key.Key_O:
                self.set_sketch_tool("OFFSET")
                return
            elif event.key() == Qt.Key.Key_F:
                self.set_sketch_tool("FILLET")
                return
            elif event.key() == Qt.Key.Key_T:
                self.set_sketch_tool("TRIM")
                return
            elif event.key() == Qt.Key.Key_I:
                self.begin_measure()
                return

        if self.edge_pick_mode and event.key() == Qt.Key.Key_X:
            self.edge_xray = not self.edge_xray
            self.status_message.emit("Edges: see-through " + ("ON - hidden edges can be picked too (X again to turn off, or hold Alt)." if self.edge_xray else "off."))
            self.update()
            return
        if self.edge_pick_mode and event.key() == Qt.Key.Key_Backspace and self.selected_edges:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.selected_edges = []   # Ctrl+Backspace: clear everything
            else:
                self.selected_edges.pop()   # undo the last picked edge
            self.edges_selection_changed.emit()
            self.update()
            return
        if event.key() == Qt.Key.Key_Escape and self.edge_pick_mode:
            self.end_edge_pick(cancelled=True)
            return
        if event.key() == Qt.Key.Key_Escape and self.plane_pick_mode:
            self.end_plane_pick(cancelled=True)
            return
        if event.key() == Qt.Key.Key_Escape:
            if self.sketch_second_uv is not None:
                self.sketch_second_uv = None
            elif self.sketch_start_uv is not None:
                if self._move:
                    self._end_move(False)
                self.sketch_start_uv = None
                self.dyn.reset()
            elif self.sketch_tool != "NONE":
                self.set_sketch_tool("NONE")
            elif self.active_tool_title():   # Esc always leaves the current function, also an open tool panel
                self.menu_command.emit("tool_cancel")
            elif self.doc.selected_profile or self.doc.selected_extra:
                self.doc.selected_profile = None
                self.doc.selected_extra = []
                self.profile_picked.emit()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        elif event.key() == Qt.Key.Key_F:
            self.zoom_fit()

    def get_sketch_plane_uv(self, screen_x: float, screen_y: float) -> Optional[Tuple[float, float]]:
        """Projects screen coordinate to 2D local (u, v) on the active sketch plane."""
        if not self.doc.active_sketch:
            return None

        plane = self.doc.active_sketch.plane
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(screen_x, screen_y, self.width(), self.height(), view, proj)

        pt_world = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
        if pt_world is None:
            return None

        return plane.world_to_uv(pt_world)

    def model_screen_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Returns (min_x, min_y, max_x, max_y) in screen pixels of visible bodies, or None."""
        corners = []
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                bmin = b.render_mesh.bounds_min
                bmax = b.render_mesh.bounds_max
                # 8 corners of the 3D bounding box
                for x in (bmin[0], bmax[0]):
                    for y in (bmin[1], bmax[1]):
                        for z in (bmin[2], bmax[2]):
                            corners.append(np.array([x, y, z], dtype=np.float32))

        # Also include preview_mesh if present
        if hasattr(self, "preview_mesh") and self.preview_mesh is not None and len(self.preview_mesh.vertices) > 0:
            bmin = self.preview_mesh.bounds_min
            bmax = self.preview_mesh.bounds_max
            for x in (bmin[0], bmax[0]):
                for y in (bmin[1], bmax[1]):
                    for z in (bmin[2], bmax[2]):
                        corners.append(np.array([x, y, z], dtype=np.float32))

        if not corners:
            return None

        screen_pts = []
        for c in corners:
            s = self.world_to_screen(c)
            if s is not None:
                screen_pts.append(s)

        if not screen_pts:
            return None

        xs = [p[0] for p in screen_pts]
        ys = [p[1] for p in screen_pts]
        return (min(xs), min(ys), max(xs), max(ys))
