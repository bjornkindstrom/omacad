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
from omacad.ui.expr_spin import ExprDoubleSpinBox
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QFontMetrics
from OpenGL import GL
from OpenGL.GL import shaders

from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.model.timeline import profile_cross_section
from omacad.model.faces import ray_hit_face
import manifold3d as m3d
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch import (
    Sketch, SketchPlane, SketchLine, SketchRect, SketchCircle,
    SketchCenterRect, SketchArc, SketchSlot, move_entity, entity_key_points,
    point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex, ref_id, ref_segment, EDGE_PTS
)
from omacad.model.sketch_snap import SketchSnapper, SnapResult
from omacad.ui.math3d import perspective, look_at, ray_from_screen, ray_plane_intersect
from omacad.ui.viewcube import ViewCube
from omacad.ui import dyn_input
from omacad.model import expr as expr_lib
from omacad.ui.dyn_input import DynInput
from omacad.ui.sketch_palette import SketchPalette
from omacad.ui import theme
from omacad.ui.theme import qcolor


# Shaders
VERTEX_SHADER_SOLID = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_normal;
uniform mat4 u_mvp;
varying vec3 v_normal;
void main() {
    v_normal = in_normal;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_SOLID = """
#version 120
varying vec3 v_normal;
uniform vec4 u_color;
void main() {
    vec3 n = normalize(v_normal);
    // Two-point CAD lighting setup
    vec3 light1 = normalize(vec3(0.5, 0.7, 1.0));
    vec3 light2 = normalize(vec3(-0.5, -0.6, 0.4));
    float diff1 = max(dot(n, light1), 0.0);
    float diff2 = max(dot(n, light2), 0.0) * 0.35;
    float ambient = 0.38;
    float lighting = clamp(diff1 + diff2 + ambient, 0.0, 1.0);
    gl_FragColor = vec4(u_color.rgb * lighting, u_color.a);
}
"""

VERTEX_SHADER_FLAT = """
#version 120
attribute vec3 in_pos;
uniform mat4 u_mvp;
void main() {
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_FLAT = """
#version 120
uniform vec4 u_color;
void main() {
    gl_FragColor = u_color;
}
"""

VERTEX_SHADER_TEXTURE = """
#version 120
attribute vec3 in_pos;
attribute vec2 in_uv;
uniform mat4 u_mvp;
varying vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_TEXTURE = """
#version 120
varying vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_opacity;
void main() {
    vec4 col = texture2D(u_tex, v_uv);
    gl_FragColor = vec4(col.rgb, col.a * u_opacity);
}
"""



# Screen-space thick lines (glLineWidth > 1 is invalid in this context)
VERTEX_SHADER_THICK = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_other;
attribute float in_side;
uniform mat4 u_mvp;
uniform vec2 u_viewport;
uniform float u_width;
void main() {
    vec4 c0 = u_mvp * vec4(in_pos, 1.0);
    vec4 c1 = u_mvp * vec4(in_other, 1.0);
    vec2 s0 = c0.xy / c0.w * u_viewport * 0.5;
    vec2 s1 = c1.xy / c1.w * u_viewport * 0.5;
    vec2 d = s0 - s1;
    float len = length(d);
    d = len > 1e-6 ? d / len : vec2(1.0, 0.0);
    vec2 n = vec2(-d.y, d.x);
    vec2 off = (n * in_side + d) * (u_width * 0.5);
    gl_Position = c0 + vec4(off / (u_viewport * 0.5) * c0.w, 0.0, 0.0);
}
"""


class Viewport3D(QOpenGLWidget):
    """Modern OpenGL 3D CAD canvas with Fusion 360 look and feel."""

    selection_changed = Signal()
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
    status_message = Signal(str)
    edges_selection_changed = Signal()
    extrude_handle_dragged = Signal(float)  # signed distance along the extrude arrow while it is dragged
    face_extrude_requested = Signal(object)  # a flat face to extrude (pull in = cut, out = build up)
    edge_pick_cancelled = Signal()

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.on_document_changed)

        # Camera parameters
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.azimuth: float = 45.0      # Orbit around Z (deg)
        self.elevation: float = 30.0    # Elevation above ground (deg)
        self.distance: float = 140.0    # Distance to target (mm)
        self.fovy: float = 45.0

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
        self._profile_fill_cache: Dict[Tuple[str, int], np.ndarray] = {}
        self.preview_mesh = None
        self.preview_op: str = "new_body"

        # Sketch element selection (click / Ctrl+click, Delete)
        self.selected_entities: set = set()
        self.hover_entity_id: Optional[str] = None
        self._ref_segments_cache = None  # (sketch_id, segments) of body edges lying in the sketch plane

        # Dimension tool: elements picked so far, and a point-to-point pair waiting for its placement click
        self._dim_pending: list = []
        self._dim_place = None
        self._dim_side = None  # "near"/"far": which circle edge a guided edge-distance measures to

        # Constraint glyphs drawn on the sketch (rect -> constraint id), rebuilt each paint
        self.constraint_badges: List[Tuple[QRectF, str]] = []

        # Moving sketch elements (mouse drag or Move tool)
        self._drag = None   # pending/active mouse drag: dict(press_uv, press_pos, moved)
        self._move = None   # active move: dict(ids, orig, before, delta)

        # Tab dimension entry while drawing
        self.dyn = DynInput()
        self.dyn_live: Dict[str, float] = {}
        self._raw_mouse_uv: Optional[Tuple[float, float]] = None

        # Extrude arrow (drag to set the distance)
        self.extrude_handle = None   # dict(origin, axis, dist)
        self._handle_drag = False
        self._handle_hover = False

        # Edge selection for fillet / chamfer
        self.edge_pick_mode: bool = False
        self.hover_edge = None            # PlanarEdge under the cursor
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
        self.hover_plane = None  # ("origin", name) or ("face", PlanarFace)

        # ViewCube overlay
        self.viewcube = ViewCube(size=90, on_face_clicked=self.set_view)

        # Floating Sketch Palette
        self.sketch_palette = SketchPalette(self)
        self.sketch_palette.finish_clicked.connect(self.finish_sketch_requested)
        self.sketch_palette.look_at_clicked.connect(self.look_at_active_plane)
        self.sketch_palette.settings_changed.connect(self.update)
        self.sketch_palette.hide()

        # Fillet tool state
        self.fillet_first_line = None
        self.fillet_hover_corner = None
        self.fillet_preview = None

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
        self._drag = self._move = None
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

    # ---- Moving sketch elements --------------------------------------------
    def _begin_move(self, ids):
        sk = self.doc.active_sketch
        self._move = {
            "ids": set(ids),
            "orig": {e.entity_id: copy.deepcopy(e) for e in sk.entities if e.entity_id in ids},
            "before": sk.to_dict(),
            "delta": (0.0, 0.0),
        }

    def _apply_move(self, du: float, dv: float):
        """Positions the moving entities at original + (du, dv)."""
        m = self._move
        if not m:
            return
        sk = self.doc.active_sketch
        for i, ent in enumerate(sk.entities):
            orig = m["orig"].get(ent.entity_id)
            if orig is not None:
                moved = copy.deepcopy(orig)
                move_entity(moved, du, dv)
                sk.entities[i] = moved
        sk.solve_profiles()
        m["delta"] = (du, dv)
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
        if commit and (abs(du) > 1e-9 or abs(dv) > 1e-9) and sk.constraints:
            res = solve_sketch(sk, fixed_ids=m["ids"])
            if not res.ok:
                sk.restore_from_dict(m["before"])
                self.status_message.emit(res.message + " - move cancelled.")
                self.doc.notify_changed()
                self.update()
                return
        if commit and (abs(du) > 1e-9 or abs(dv) > 1e-9):
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
        if m["text"]:
            self.status_message.emit("Measure: " + "  |  ".join(m["text"]))
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

    # ---- Section view -------------------------------------------------------------------
    def set_section(self, origin, normal, offset: float, flip: bool = False, show_plane: bool = True):
        """Cuts every body along a plane (base origin + normal * offset) and shows the cut face. View only."""
        from omacad.model.sketch import SketchPlane
        n = np.asarray(normal, dtype=float)
        n = n / np.linalg.norm(n)
        p = np.asarray(origin, dtype=float) + n * float(offset)
        keep = n if flip else -n                       # the side that stays (the other side faces the viewer)
        plane = SketchPlane.from_face(n, p)
        inv = np.linalg.inv(np.vstack([plane.get_transform_matrix_3x4(), [0, 0, 0, 1]]))[:3]
        meshes, cap_cs = {}, None
        for bid, body in self.doc.bodies.items():
            if not body.visible:
                continue
            try:
                kept = body.manifold.trim_by_plane(tuple(keep), float(keep @ p))
                meshes[bid] = CadKernel.extract_render_mesh(kept)   # empty when the whole body is cut away
                polys = body.manifold.transform(inv).slice(1e-4 if not flip else -1e-4).to_polygons()
                if polys:
                    cs = m3d.CrossSection(polys)
                    cap_cs = cs if cap_cs is None else cap_cs + cs
            except Exception:
                continue
        cap = None
        if cap_cs is not None:
            slab = m3d.Manifold.extrude(cap_cs, 0.08).translate((0, 0, -0.04))
            slab = slab.transform(plane.get_transform_matrix_3x4())
            cap = CadKernel.extract_render_mesh(slab)
        self.section = {"origin": np.asarray(origin, dtype=float), "normal": n, "offset": float(offset), "flip": flip,
                        "meshes": meshes, "cap": cap}
        self.set_preview_plane(plane if show_plane else None)
        self.update()

    def clear_section(self):
        self.section = None
        self.set_preview_plane(None)
        self.clear_extrude_handle()
        self.update()

    def sync_section(self):
        """Shows the document's active saved section (if any); not while one is being edited."""
        if getattr(self, "section_editing", False):
            return
        act = self.doc.active_section()
        if act is None:
            if self.section is not None:
                self.section = None
                self.update()
            return
        sec = act[1]
        self.set_section(sec["origin"], sec["normal"], sec["offset"], sec["flip"], show_plane=False)

    def render_section_cap(self, mvp: np.ndarray):
        """The cut face, in the highlight colour, so the inside of the model reads clearly."""
        sec = self.section
        if not sec or sec["cap"] is None or not self.prog_flat or len(sec["cap"].vertices) == 0:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform4f(loc_col, *theme.palette().highlight01(0.0), 1.0)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, sec["cap"].vertices)
        GL.glUseProgram(0)

    # ---- Extrude arrow ------------------------------------------------------------------
    def set_extrude_handle(self, origin, axis, dist: float, color=None):
        """Draggable arrow. `color` (r, g, b) overrides the theme highlight, e.g. when that would blend into the scene."""
        self.extrude_handle = {"origin": np.asarray(origin, dtype=float), "axis": np.asarray(axis, dtype=float), "dist": float(dist),
                               "color": color}
        self.update()

    def clear_extrude_handle(self):
        self.extrude_handle = None
        self._handle_drag = False
        self._handle_hover = False
        self.update()

    def _handle_screen(self):
        h = self.extrude_handle
        tip = h["origin"] + h["axis"] * h["dist"]
        return self.world_to_screen(h["origin"]), self.world_to_screen(tip), tip

    def _handle_hit(self, x: float, y: float) -> bool:
        if not self.extrude_handle:
            return False
        so, st, _ = self._handle_screen()
        if so is None or st is None:
            return False
        if math.hypot(x - st[0], y - st[1]) < 18:
            return True
        return self._point_to_segment_dist((x, y), so, st) < 9

    def _handle_value(self, x: float, y: float):
        """Distance along the arrow's axis that is closest to the mouse ray."""
        h = self.extrude_handle
        proj, view, _ = self.get_matrices()
        r0, rd = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        r0, rd = np.asarray(r0, dtype=float), np.asarray(rd, dtype=float)
        a, w = h["axis"], h["origin"] - r0
        b, d1, e = float(a @ rd), float(a @ w), float(rd @ w)
        denom = 1.0 - b * b
        if abs(denom) < 1e-6:
            return None
        t = (b * e - d1) / denom
        step = 0.1 if abs(t) < 10 else 0.5 if abs(t) < 50 else 1.0
        return round(t / step) * step

    def render_extrude_handle(self, mvp: np.ndarray):
        h = self.extrude_handle
        if not h or self.prog_flat is None or self.prog_thick is None:
            return
        origin, axis, dist = h["origin"], h["axis"], h["dist"]
        sign = 1.0 if dist >= 0 else -1.0
        tip = origin + axis * dist
        size = self.distance * 0.04
        lit = self._handle_hover or self._handle_drag
        from omacad.ui.settings import get_settings
        custom_arrow = get_settings().arrow_color_rgb01()
        if h.get("color"):
            col = (*(min(1.0, c + (0.2 if lit else 0.0)) for c in h["color"]), 1.0)
        elif custom_arrow is not None:
            col = (*(min(1.0, c + (0.2 if lit else 0.0)) for c in custom_arrow), 1.0)
        else:
            col = (*theme.palette().highlight01(0.15 if lit else 0.0), 1.0)
        GL.glDisable(GL.GL_DEPTH_TEST)
        shaft_end = tip - axis * sign * size * 0.8
        self.draw_thick_lines(mvp, [*origin, *shaft_end], col, 4.0, halo=True)
        # arrow head: a cone around the axis
        u = np.cross(axis, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(axis, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        v_ = np.cross(axis, u)
        apex, base = tip + axis * sign * size * 0.4, tip - axis * sign * size * 0.8
        ring = [base + size * 0.5 * (math.cos(t) * u + math.sin(t) * v_) for t in np.linspace(0, 2 * math.pi, 17)]
        tris = []
        for i in range(16):
            tris += [*apex, *ring[i], *ring[i + 1], *base, *ring[i + 1], *ring[i]]
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform4f(loc_col, *col)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, np.array(tris, dtype=np.float32))
        GL.glUseProgram(0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    # ---- Edge selection (fillet / chamfer) ------------------------------------------
    def begin_edge_pick(self):
        self.edge_pick_mode = True
        self.hover_edge = None
        self.selected_edges = []
        self.setFocus()
        self.update()

    def end_edge_pick(self, cancelled: bool = False):
        self.edge_pick_mode = False
        self.hover_edge = None
        self.selected_edges = []
        if cancelled:
            self.edge_pick_cancelled.emit()
        self.update()

    @staticmethod
    def _same_edge(a, b) -> bool:
        return a.same_as(b)

    def _pick_edge(self, x: float, y: float):
        """The straight edge between two flat faces nearest the cursor (within 8 px, and not hidden)."""
        proj, view, _ = self.get_matrices()
        origin, _ = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_d = None, 8.0
        for body in self.doc.bodies.values():
            if not body.visible:
                continue
            for e in body.edges:
                pts = e.polyline()
                screen = [self.world_to_screen(p) for p in pts]
                d, near = best_d, None
                for i in range(len(screen) - 1):
                    if screen[i] is None or screen[i + 1] is None:
                        continue
                    dd = self._point_to_segment_dist((x, y), screen[i], screen[i + 1])
                    if dd < d:
                        d, near = dd, i
                if near is None:
                    continue
                # hidden behind a face? test the point of the edge nearest the cursor
                mid = (pts[near] + pts[near + 1]) / 2.0
                direction = mid - origin
                dist = float(np.linalg.norm(direction))
                direction = direction / dist if dist > 1e-9 else direction
                blocked = any((t := ray_hit_face(f, origin, direction)) is not None and t < dist - 1e-3
                              for bd in self.doc.bodies.values() if bd.visible for f in bd.faces)
                if not blocked:
                    best, best_d = e, d
        return best

    def _edge_loop(self, e):
        """Double-click: the edges joined end to end around one flat face (e.g. the whole top of a box).
        Of the two faces an edge borders, the one facing the camera is used."""
        if e.kind in ("circle", "loop"):
            return [e]
        proj, view, _ = self.get_matrices()
        eye = np.linalg.inv(view)[:3, 3]
        mid = (e.p0 + e.p1) / 2.0
        to_eye = eye - mid
        n = e.n1 if float(e.n1 @ to_eye) >= float(e.n2 @ to_eye) else e.n2
        d = float(n @ e.p0)
        candidates = [c for b in self.doc.bodies.values() if b.visible for c in b.edges if c.kind == "line"
                      and abs(float(n @ c.p0) - d) < 1e-4 and abs(float(n @ c.p1) - d) < 1e-4]
        chain, frontier = [e], [e]
        while frontier:
            cur = frontier.pop()
            for c in candidates:
                if any(c.same_as(k) for k in chain):
                    continue
                if any(np.linalg.norm(a - b) < 1e-4 for a in (cur.p0, cur.p1) for b in (c.p0, c.p1)):
                    chain.append(c)
                    frontier.append(c)
        return chain

    def _update_edge_hover(self, x: float, y: float):
        e = self._pick_edge(x, y)
        if (e is None) != (self.hover_edge is None) or (e is not None and not self._same_edge(e, self.hover_edge)):
            self.hover_edge = e
            self.update()

    def _toggle_edge(self, e):
        for i, sel in enumerate(self.selected_edges):
            if self._same_edge(sel, e):
                del self.selected_edges[i]
                break
        else:
            self.selected_edges.append(e)
        self.edges_selection_changed.emit()
        self.update()

    def render_edge_pick(self, mvp: np.ndarray):
        if not self.edge_pick_mode or self.prog_thick is None:
            return
        GL.glDisable(GL.GL_DEPTH_TEST)
        def flat(edges):
            out = []
            for e in edges:
                pts = e.polyline()
                for i in range(len(pts) - 1):
                    out += [*pts[i], *pts[i + 1]]
            return out

        if self.hover_edge is not None and not any(self._same_edge(self.hover_edge, s) for s in self.selected_edges):
            self.draw_thick_lines(mvp, flat([self.hover_edge]), (1.0, 1.0, 1.0, 1.0), 3.5)
        if self.selected_edges:
            self.draw_thick_lines(mvp, flat(self.selected_edges), (*theme.palette().highlight01(), 1.0), 4.0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    # ---- Sketch element selection --------------------------------------------
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
        active = self._can_select_sketch_entities() or (self.doc.active_sketch is not None and (self.sketch_tool == "DIMENSION" or self.measure is not None))
        ent = self._pick_entity(x, y) if active else None
        hid = ent.entity_id if ent else None
        if hid != self.hover_entity_id:
            self.hover_entity_id = hid
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
            res = self.prompt_dimension_value("Offset", "Distance (positive = outward / to the left of a line, negative = the other way):",
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
                self._apply_move(p2[0] - p1[0], p2[1] - p1[1])
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
        elif self.sketch_tool == "CENTER_RECT":
            if p1 != p2:
                created = sketch.add_center_rect(p1, p2, is_construction=is_const)
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
        end, live = self.dyn.resolve(self.sketch_start_uv, mouse)
        self.sketch_current_uv = end
        self.dyn_live = live
        if self.sketch_tool == "MOVE" and self._move:
            self._apply_move(end[0] - self.sketch_start_uv[0], end[1] - self.sketch_start_uv[1])
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
            self.dyn.type_char(text)  # a parameter name such as width or Höjd
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
        elif tool in ("RECT", "CENTER_RECT"):
            if tool == "RECT":
                c1, c2 = a, b
            else:
                c1, c2 = (2 * a[0] - b[0], 2 * a[1] - b[1]), b
            p_bl, p_br = scr((c1[0], c1[1])), scr((c2[0], c1[1]))
            p_tr = scr((c2[0], c2[1]))
            if p_bl and p_br and p_tr:
                anchors["Width"] = QPointF((p_bl.x() + p_br.x()) / 2, (p_bl.y() + p_br.y()) / 2 + 22)
                anchors["Height"] = QPointF((p_br.x() + p_tr.x()) / 2 + 48, (p_br.y() + p_tr.y()) / 2)
        elif tool == "MOVE":
            anchors["X"] = QPointF((sa.x() + sb.x()) / 2, (sa.y() + sb.y()) / 2 + 24)
            anchors["Y"] = QPointF(sb.x() + 52, sb.y())
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
                txt = f"{val:.2f}"
            txt += "°" if name == "Angle" else " mm"
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
        (a pattern both adds and removes material)."""
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

    def render_profile_fills(self, mvp: np.ndarray):
        """Translucent fills for the hovered and selected sketch profiles."""
        if not self.prog_flat or self.doc.active_sketch:
            return
        entries = []
        if self.hover_profile and self.hover_profile != self.doc.selected_profile:
            entries.append((self.hover_profile, (*theme.palette().highlight01(0.35), 0.30)))
        if self.doc.selected_profile:
            entries.append((self.doc.selected_profile, (*theme.palette().highlight01(0.1), 0.50)))
        for key in self.doc.selected_extra:
            entries.append((key, (*theme.palette().highlight01(0.1), 0.50)))
        if not entries:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(-1.0, -1.0)
        for key, col in entries:
            tris = self._profile_fill(key)
            if tris is not None:
                GL.glUniform4f(loc_col, *col)
                self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def render_preview(self, mvp: np.ndarray):
        """Translucent preview of a pending feature (e.g. extrude)."""
        if getattr(self, "preview_extra", None) is not None:
            mesh2, op2 = self.preview_extra
            self._render_preview_mesh(mvp, mesh2, op2)
        self._render_preview_mesh(mvp, self.preview_mesh, self.preview_op)

    def _render_preview_mesh(self, mvp: np.ndarray, mesh, op: str):
        if mesh is None or len(mesh.vertices) == 0 or not self.prog_flat:
            return
        colors = {
            "cut": (0.92, 0.25, 0.20), "intersect": (0.95, 0.80, 0.20),
            "join": (0.30, 0.78, 0.50), "new_body": (0.30, 0.65, 0.95),
        }
        r, g, b = colors.get(op, colors["new_body"])
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        inside = op in ("cut", "intersect")   # these sit inside the body: show them through its surface
        if inside:
            GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUniform4f(loc_col, r, g, b, 0.50 if inside else 0.38)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices)
        GL.glDepthMask(GL.GL_TRUE)
        if len(mesh.sharp_lines) > 0:
            GL.glUniform4f(loc_col, r, g, b, 1.0)
            self.set_line_width(2.0)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, mesh.sharp_lines)
        if inside:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def set_sketch_tool(self, tool_name: str):
        """Sets the active 2D sketching tool and resets temporary anchors."""
        self._dim_pending = []
        self._dim_place = None
        self._dim_side = None
        self.fillet_first_line = None
        self.fillet_hover_corner = None
        self.fillet_preview = None
        if self._move:
            self._end_move(False)
        if tool_name == "MOVE" and not self.selected_entities:
            self.status_message.emit("Move: select the sketch elements to move first (click, Ctrl+click), then press M.")
            tool_name = "NONE"
        self.sketch_tool = tool_name
        self.dyn.reset()
        self.sketch_start_uv = None
        self.sketch_second_uv = None
        self.sketch_current_uv = None
        self.sketch_tool_changed.emit(tool_name)
        if tool_name == "FILLET":
            if self.selected_entities:
                self.fillet_selected_or_prompt()
            else:
                self.status_message.emit("Fillet: Klicka på ett hörn mellan två linjer, eller klicka två linjer (Esc avbryter).")
        self.update()

    def prompt_fillet_radius(self, line_a, line_b, corner_pt=None):
        """Interactive fillet creation with live OpenGL preview."""
        sk = self.doc.active_sketch
        if not sk:
            return
        from omacad.ui.settings import get_settings
        default_r = float(get_settings().get("fillet_default_radius", 2.0))

        def preview(radius):
            segs = []
            if radius > 0.05:
                from omacad.model.sketch import Sketch
                tmp = Sketch.from_dict(sk.to_dict())
                la = tmp.get_entity(line_a.entity_id)
                lb = tmp.get_entity(line_b.entity_id)
                if la and lb:
                    try:
                        arc, _ = tmp.fillet_corner(la, lb, radius, corner_pt)
                        if arc:
                            for a, b in arc.to_lines(24):
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                            for a, b in la.to_lines():
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                            for a, b in lb.to_lines():
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                    except Exception:
                        pass
            self.fillet_preview = np.array(segs, dtype=np.float32) if segs else None
            self.update()

        try:
            res = self.prompt_dimension_value("Fillet", "Radius:", default_r, lo=0.1, hi=2000.0, on_change=preview)
        finally:
            self.fillet_preview = None
            self.update()

        if res is None or res[0] <= 0.001:
            return

        radius = res[0]
        before = sk.to_dict()
        arc, msg = sk.fillet_corner(line_a, line_b, radius, corner_pt)
        if not arc:
            self.status_message.emit(f"Fillet: {msg}")
            return

        get_settings().set("fillet_default_radius", radius)
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {arc.entity_id}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit(f"Fillet: hörnet avrundat med radie {radius:g} mm.")
        self.update()

    def fillet_selected_or_prompt(self):
        """Fillet corner(s) from current selection (2 lines or a shape like rectangle/polygon)."""
        sk = self.doc.active_sketch
        if not sk or not self.selected_entities:
            return
        from omacad.model.sketch import SketchLine
        cands = [sk.get_entity(eid) for eid in self.selected_entities if isinstance(sk.get_entity(eid), SketchLine)]
        if len(cands) == 2:
            self.prompt_fillet_radius(cands[0], cands[1])
            return
        elif len(cands) > 2:
            corners = sk.find_corners(cands)
            if corners:
                from omacad.ui.settings import get_settings
                default_r = float(get_settings().get("fillet_default_radius", 2.0))
                res = self.prompt_dimension_value("Fillet", f"Radie för {len(corners)} hörn:", default_r, lo=0.1, hi=2000.0)
                if res and res[0] > 0.001:
                    radius = res[0]
                    before = sk.to_dict()
                    created_arcs = []
                    for pt, la, lb, ea, eb in corners:
                        arc, msg = sk.fillet_corner(la, lb, radius, pt)
                        if arc:
                            created_arcs.append(arc)
                    if created_arcs:
                        get_settings().set("fillet_default_radius", radius)
                        self.doc.record_sketch_change(sk, before)
                        self.selected_entities = {a.entity_id for a in created_arcs}
                        self.selection_changed.emit()
                        self.doc.timeline.recompute(self.doc)
                        self.doc.notify_changed()
                        self.status_message.emit(f"Fillet: {len(created_arcs)} hörn avrundade med radie {radius:g} mm.")
                        self.update()
                    return
        self.status_message.emit("Fillet: Klicka på ett hörn mellan två linjer, eller klicka två linjer (Esc avbryter).")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sketch_palette'):
            self.sketch_palette.place_default(self.size())

    # ---- Sketch plane picking ---------------------------------------------
    def begin_plane_pick(self, purpose: str = "sketch"):
        self.plane_pick_purpose = purpose
        self.plane_pick_mode = True
        self.hover_plane = None
        self.setFocus()
        self.update()

    def end_plane_pick(self, cancelled: bool = False):
        self.plane_pick_mode = False
        self.hover_plane = None
        if cancelled:
            self.plane_pick_cancelled.emit()
        self.plane_pick_purpose = "sketch"
        self.update()

    def _origin_plane_half_size(self) -> float:
        ext = 30.0
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh is not None and len(b.render_mesh.vertices):
                ext = max(ext, float(np.abs(b.render_mesh.bounds_min).max()) * 1.2,
                          float(np.abs(b.render_mesh.bounds_max).max()) * 1.2)
        return ext

    def _pick_plane_target(self, x: float, y: float):
        """Nearest origin plane (within its drawn quad) or planar body face under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_t = None, float("inf")
        half = self._origin_plane_half_size()
        candidates = [(("origin", n), pl) for n, pl in self.doc.origin_planes.items()]
        only_origin = self.plane_pick_mode and self.plane_pick_purpose == "offset_base"
        if not only_origin:
            candidates += [(("cplane", pid), self.doc.construction_plane(pid))
                           for pid, c in self.doc.construction_planes.items() if c.get("visible", True)]
        for key, plane in candidates:
            hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
            if hit is None:
                continue
            u, v = plane.world_to_uv(hit)
            t = float(np.linalg.norm(hit - origin))
            if abs(u) <= half and abs(v) <= half and t < best_t:
                best, best_t = key, t
        # Body faces take priority over origin planes (a plane passing through a body
        # would otherwise hide the faces behind it)
        face_best, face_t = None, float("inf")
        for body in ([] if only_origin else self.doc.bodies.values()):
            if not body.visible:
                continue
            for face in body.faces:
                t = ray_hit_face(face, origin, ray_dir)
                if t is not None and t < face_t:
                    face_best, face_t = ("face", face), t
        if face_best is not None:
            return face_best
        return best

    def _update_plane_hover(self, x: float, y: float):
        hover = self._pick_plane_target(x, y)

        def key(h):
            return None if h is None else (h[0], h[1] if h[0] in ("origin", "cplane") else (h[1].body_id, h[1].index))
        if key(hover) != key(self.hover_plane):
            self.hover_plane = hover
            self.update()

    def set_preview_plane(self, plane):
        self.preview_plane = plane
        self.update()

    def _pick_surface(self, x: float, y: float):
        """Any body surface under the cursor (curved ones too): the hit point and its smooth patch of vertices."""
        from omacad.model.faces import ray_mesh_hit, smooth_patch_vertices
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], mesh, hit[1])
        if best is None:
            return None
        t, mesh, tri = best
        return {"point": np.asarray(origin, dtype=float) + t * np.asarray(ray_dir, dtype=float),
                "patch": smooth_patch_vertices(mesh, tri)}

    def plane_from_target(self, target):
        from omacad.model.sketch import SketchPlane
        kind, payload = target
        if kind == "origin":
            return SketchPlane.create_named(payload)
        if kind == "cplane":
            return self.doc.construction_plane(payload)
        return SketchPlane.from_face(payload.normal, payload.origin)

    def render_plane_pick(self, mvp: np.ndarray):
        """Translucent origin-plane quads and hovered face while choosing a sketch plane."""
        cplanes = [(pid, self.doc.construction_plane(pid)) for pid, c in self.doc.construction_planes.items() if c.get("visible", True)]
        if self.plane_pick_mode and self.plane_pick_purpose in ("offset_base", "offset_surface"):
            cplanes = []
        if (not self.plane_pick_mode and self.ctx_face is None and not cplanes and self.preview_plane is None) or not self.prog_flat:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        half = self._origin_plane_half_size()
        base = {"XY": (0.30, 0.55, 1.0), "XZ": (0.35, 0.85, 0.40), "YZ": (1.0, 0.40, 0.35)}
        for name, plane in (self.doc.origin_planes.items() if self.plane_pick_mode and self.plane_pick_purpose != "offset_surface" else ()):
            hovered = self.hover_plane == ("origin", name)
            corners = [plane.uv_to_world(-half, -half), plane.uv_to_world(half, -half),
                       plane.uv_to_world(half, half), plane.uv_to_world(-half, half)]
            quad = np.array([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]], dtype=np.float32)
            r, g, b = base[name]
            GL.glUniform4f(loc_col, r, g, b, 0.45 if hovered else 0.14)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, quad)
            outline = np.array([c for i in range(4) for c in (corners[i], corners[(i + 1) % 4])], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.9 if hovered else 0.5)
            self.set_line_width(1.5)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        extra = [(("cplane", pid), pl, (0.75, 0.55, 0.95)) for pid, pl in cplanes]
        if self.preview_plane is not None:
            extra.append((None, self.preview_plane, (1.0, 0.65, 0.2)))
        for key, plane, (r, g, b) in extra:
            hovered = key is not None and self.plane_pick_mode and self.hover_plane == key
            strong = hovered or key is None
            corners = [plane.uv_to_world(-half, -half), plane.uv_to_world(half, -half),
                       plane.uv_to_world(half, half), plane.uv_to_world(-half, half)]
            quad = np.array([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.40 if hovered else (0.25 if key is None else 0.10))
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, quad)
            outline = np.array([c for i in range(4) for c in (corners[i], corners[(i + 1) % 4])], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.95 if strong else 0.55)
            self.set_line_width(1.5)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        shown = self.hover_plane if self.plane_pick_mode else (("face", self.ctx_face) if self.ctx_face is not None else None)
        if shown and shown[0] == "face":
            face = shown[1]
            lift = face.normal * 0.05  # avoid z-fighting with the body surface
            tris = (face.tris + lift).reshape(-1, 3).astype(np.float32)
            GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 0.55)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def align_to_plane(self, plane):
        """Orbits the camera so it looks straight at the given sketch plane."""
        n = np.asarray(plane.normal, dtype=np.float64)
        el = math.degrees(math.asin(max(-1.0, min(1.0, float(n[2])))))
        if abs(n[2]) > 0.999:
            self.azimuth = 0.0
            self.elevation = 89.9 if n[2] > 0 else -89.9
        else:
            self.azimuth = math.degrees(math.atan2(n[0], -n[1])) % 360.0
            self.elevation = el
        self.update()

    def look_at_active_plane(self):
        """Aligns camera orthogonally to current active sketch plane."""
        if self.doc.active_sketch:
            self.align_to_plane(self.doc.active_sketch.plane)

    def toggle_construction_mode(self):
        """Toggles construction geometry creation mode (X key)."""
        self.construction_mode = not self.construction_mode
        self.construction_mode_changed.emit(self.construction_mode)
        self.update()

    def world_to_screen(self, world_pt: np.ndarray) -> Optional[Tuple[float, float]]:
        """Projects a 3D point in world space to 2D screen viewport coordinates."""
        proj, view, _ = self.get_matrices()
        pv = proj @ view
        p4 = np.array([world_pt[0], world_pt[1], world_pt[2], 1.0], dtype=np.float32)
        clip = pv @ p4
        if clip[3] <= 0.001:
            return None
        ndc_x = clip[0] / clip[3]
        ndc_y = clip[1] / clip[3]
        sx = (ndc_x + 1.0) * 0.5 * float(self.width())
        sy = (1.0 - ndc_y) * 0.5 * float(self.height())
        return sx, sy

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
        proj = perspective(self.fovy, aspect, 1.0, 5000.0)

        rad_az = math.radians(self.azimuth)
        rad_el = math.radians(self.elevation)

        eye_x = self.target[0] + self.distance * math.cos(rad_el) * math.sin(rad_az)
        eye_y = self.target[1] - self.distance * math.cos(rad_el) * math.cos(rad_az)
        eye_z = self.target[2] + self.distance * math.sin(rad_el)
        eye = np.array([eye_x, eye_y, eye_z], dtype=np.float32)

        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        # Flip up when looking straight down or up to avoid singularity
        if abs(self.elevation) > 89.0:
            up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        view = look_at(eye, self.target, up)
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
        if cid in self._canvas_textures:
            return self._canvas_textures[cid]
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
            self._canvas_textures[cid] = tex_id
            return tex_id
        except Exception as e:
            print(f"Error creating canvas texture for {cid}: {e}")
            return None

    def render_canvases(self, mvp: np.ndarray):
        """Renders calibrated reference images on their respective 3D planes."""
        canvases = getattr(self.doc, "canvases", {})
        if not canvases or not self.prog_tex:
            return

        for cid, c in canvases.items():
            if not c.get("visible", True) or not c.get("image_data"):
                continue

            plane_id = c.get("plane_id", "XY")
            plane = None
            if plane_id in self.doc.origin_planes:
                plane = self.doc.origin_planes[plane_id]
            elif plane_id in self.doc.construction_planes:
                plane = self.doc.construction_plane(plane_id)
            if plane is None:
                continue

            tex_id = self._get_canvas_texture(cid, c["image_data"])
            if not tex_id:
                continue

            w_mm = float(c.get("width_mm", 100.0))
            h_mm = float(c.get("height_mm", 100.0))
            ox, oy = c.get("origin_uv", [-w_mm / 2.0, -h_mm / 2.0])
            rot_deg = float(c.get("rotation_deg", 0.0))
            opacity = float(c.get("opacity", 0.5))

            # 4 Corners in plane UV coordinates with rotation
            cx, cy = ox + w_mm / 2.0, oy + h_mm / 2.0
            rad = math.radians(rot_deg)
            cos_r, sin_r = math.cos(rad), math.sin(rad)

            def rot_pt(u, v):
                du, dv = u - cx, v - cy
                return cx + du * cos_r - dv * sin_r, cy + du * sin_r + dv * cos_r

            uv_corners = [
                rot_pt(ox, oy),
                rot_pt(ox + w_mm, oy),
                rot_pt(ox + w_mm, oy + h_mm),
                rot_pt(ox, oy + h_mm),
            ]
            w_pts = [plane.uv_to_world(u, v) for u, v in uv_corners]

            quad_pos = np.array([
                w_pts[0], w_pts[1], w_pts[2],
                w_pts[0], w_pts[2], w_pts[3]
            ], dtype=np.float32)

            quad_uv = np.array([
                [0.0, 1.0], [1.0, 1.0], [1.0, 0.0],
                [0.0, 1.0], [1.0, 0.0], [0.0, 0.0]
            ], dtype=np.float32)

            GL.glUseProgram(self.prog_tex)
            loc_mvp = GL.glGetUniformLocation(self.prog_tex, "u_mvp")
            loc_op = GL.glGetUniformLocation(self.prog_tex, "u_opacity")
            loc_tex = GL.glGetUniformLocation(self.prog_tex, "u_tex")
            loc_pos = GL.glGetAttribLocation(self.prog_tex, "in_pos")
            loc_uv = GL.glGetAttribLocation(self.prog_tex, "in_uv")

            GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
            GL.glUniform1f(loc_op, opacity)
            GL.glUniform1i(loc_tex, 0)

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)

            GL.glBindVertexArray(self.vao)
            pos_bytes = np.ascontiguousarray(quad_pos, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_pos)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_bytes.nbytes, pos_bytes, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(loc_pos)
            GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

            uv_bytes = np.ascontiguousarray(quad_uv, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_norm)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, uv_bytes.nbytes, uv_bytes, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(loc_uv)
            GL.glVertexAttribPointer(loc_uv, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

            GL.glDepthMask(GL.GL_FALSE)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
            GL.glDepthMask(GL.GL_TRUE)

            GL.glDisableVertexAttribArray(loc_pos)
            GL.glDisableVertexAttribArray(loc_uv)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glBindVertexArray(0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            GL.glUseProgram(0)

            # Draw canvas boundary border
            if self.prog_flat:
                border_lines = np.array([
                    w_pts[0], w_pts[1],
                    w_pts[1], w_pts[2],
                    w_pts[2], w_pts[3],
                    w_pts[3], w_pts[0]
                ], dtype=np.float32)
                GL.glUseProgram(self.prog_flat)
                loc_m = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
                loc_c = GL.glGetUniformLocation(self.prog_flat, "u_color")
                loc_p = GL.glGetAttribLocation(self.prog_flat, "in_pos")
                GL.glUniformMatrix4fv(loc_m, 1, GL.GL_TRUE, mvp.flatten())
                GL.glUniform4f(loc_c, 0.2, 0.65, 1.0, 0.7)
                self.draw_buffer_arrays(GL.GL_LINES, loc_p, border_lines)
                GL.glUseProgram(0)

    def render_ground_grid(self, mvp: np.ndarray):
        """Renders concentric grid and colored X/Y/Z coordinate axes."""
        if not self.prog_flat:
            return

        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")

        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

        # Draw Grid Lines
        grid_lines = []
        grid_extent = 150.0
        step_minor = 10.0

        num_steps = int(grid_extent / step_minor)
        for i in range(-num_steps, num_steps + 1):
            coord = i * step_minor
            # lines parallel to X
            grid_lines.extend([-grid_extent, coord, 0.0, grid_extent, coord, 0.0])
            # lines parallel to Y
            grid_lines.extend([coord, -grid_extent, 0.0, coord, grid_extent, 0.0])

        grid_data = np.array(grid_lines, dtype=np.float32)

        GL.glUniform4f(loc_col, *theme.palette().grid_rgb01(), 0.5)
        self.set_line_width(1.0)
        self.draw_buffer_arrays(GL.GL_LINES, loc_pos, grid_data)

        # Draw Center Axes (X: Red, Y: Green, Z: Blue)
        axis_len = 100.0
        # X Axis
        GL.glUniform4f(loc_col, 0.92, 0.25, 0.25, 0.9)
        self.set_line_width(2.0)
        x_axis = np.array([0.0, 0.0, 0.0, axis_len, 0.0, 0.0], dtype=np.float32)
        self.draw_buffer_arrays(GL.GL_LINES, loc_pos, x_axis)

        # Y Axis
        GL.glUniform4f(loc_col, 0.25, 0.78, 0.35, 0.9)
        y_axis = np.array([0.0, 0.0, 0.0, 0.0, axis_len, 0.0], dtype=np.float32)
        self.draw_buffer_arrays(GL.GL_LINES, loc_pos, y_axis)

        # Z Axis
        GL.glUniform4f(loc_col, 0.25, 0.55, 0.95, 0.9)
        z_axis = np.array([0.0, 0.0, 0.0, 0.0, 0.0, axis_len], dtype=np.float32)
        self.draw_buffer_arrays(GL.GL_LINES, loc_pos, z_axis)

        GL.glUseProgram(0)

    def render_bodies(self, mvp: np.ndarray):
        """Renders shaded CAD bodies with sharp silhouette edges."""
        if not self.prog_solid or not self.prog_flat:
            return

        for body in self.doc.bodies.values():
            if not body.visible or not body.render_mesh:
                continue

            mesh = body.render_mesh
            if self.section is not None and body.body_id in self.section["meshes"]:
                mesh = self.section["meshes"][body.body_id]   # the part left after the cut
            if len(mesh.vertices) == 0:
                continue

            is_selected = body.selected

            # 1. Shaded Surfaces
            if not self.wireframe_only:
                GL.glUseProgram(self.prog_solid)
                loc_mvp = GL.glGetUniformLocation(self.prog_solid, "u_mvp")
                loc_col = GL.glGetUniformLocation(self.prog_solid, "u_color")
                loc_pos = GL.glGetAttribLocation(self.prog_solid, "in_pos")
                loc_norm = GL.glGetAttribLocation(self.prog_solid, "in_normal")

                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

                # Color: Orange tint if selected, else body color
                if is_selected:
                    GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 1.0)
                else:
                    c = body.color
                    GL.glUniform4f(loc_col, c[0], c[1], c[2], c[3])

                # Push depth back slightly so crisp edges render cleanly on top
                GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glPolygonOffset(1.0, 1.0)

                self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices, loc_norm, mesh.normals)

                GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glUseProgram(0)

            # 2. Crisp Sharp Feature Edges
            if (self.show_edges or self.wireframe_only) and len(mesh.sharp_lines) > 0:
                GL.glUseProgram(self.prog_flat)
                loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
                loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
                loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")

                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

                if is_selected:
                    GL.glUniform4f(loc_col, *theme.palette().highlight01(), 1.0)  # theme highlight
                    self.set_line_width(2.2)
                else:
                    GL.glUniform4f(loc_col, 0.12, 0.13, 0.15, 1.0)  # Dark CAD Edge
                    self.set_line_width(1.6)

                self.draw_buffer_arrays(GL.GL_LINES, loc_pos, mesh.sharp_lines)
                GL.glUseProgram(0)

    def draw_thick_lines(self, mvp: np.ndarray, flat_segments, rgba, width_px: float, halo: bool = True):
        """Draws line segments (flat [x1,y1,z1,x2,y2,z2,...]) as screen-space quads.
        A dark halo under the coloured core keeps them readable on light faces and dark grid alike."""
        if self.prog_thick is None or self.vbo_thick is None:
            return
        segs = np.asarray(flat_segments, dtype=np.float32).reshape(-1, 2, 3)
        if len(segs) == 0:
            return
        a, b = segs[:, 0], segs[:, 1]
        n = len(segs)
        # Vertex order: A(-1) A(+1) B(+1)  |  A(+1) B(-1) B(+1)
        pos = np.stack([a, a, b, a, b, b], axis=1)
        oth = np.stack([b, b, a, b, a, a], axis=1)
        side = np.tile(np.array([-1, 1, 1, 1, -1, 1], dtype=np.float32), (n, 1))[..., None]
        data = np.concatenate([pos, oth, side], axis=2).reshape(-1, 7).astype(np.float32)

        prog = self.prog_thick
        GL.glUseProgram(prog)
        dpr = self.devicePixelRatioF()
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform2f(GL.glGetUniformLocation(prog, "u_viewport"), self.width() * dpr, self.height() * dpr)
        loc_col = GL.glGetUniformLocation(prog, "u_color")
        loc_w = GL.glGetUniformLocation(prog, "u_width")
        locs = [GL.glGetAttribLocation(prog, nm) for nm in ("in_pos", "in_other", "in_side")]

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_thick)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
        stride = 7 * 4
        for loc, size, off in zip(locs, (3, 3, 1), (0, 12, 24)):
            if loc >= 0:
                GL.glEnableVertexAttribArray(loc)
                GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(off))

        passes = []
        if halo:
            passes.append(((0.03, 0.04, 0.06, 0.85), width_px + 3.5))
        passes.append((rgba, width_px))
        for col, w in passes:
            GL.glUniform4f(loc_col, *col)
            GL.glUniform1f(loc_w, w * dpr)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(data))

        for loc in locs:
            if loc >= 0:
                GL.glDisableVertexAttribArray(loc)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
        GL.glUseProgram(self.prog_flat)

    def render_sketches(self, mvp: np.ndarray):
        """Renders 2D sketch lines, closed profiles, and sketch planes."""
        if not self.prog_flat:
            return

        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")

        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

        # Draw all visible sketches
        for sketch in self.doc.sketches.values():
            if not sketch.visible:
                continue

            is_active = (sketch == self.doc.active_sketch)
            # The active sketch is always drawn on top (it may lie on or inside a body);
            # other sketches get a small depth bias so they don't z-fight with faces.
            if is_active:
                GL.glDisable(GL.GL_DEPTH_TEST)
            else:
                GL.glEnable(GL.GL_DEPTH_TEST)
            plane = sketch.plane

            # Render Sketch Entities
            normal_lines = []
            construction_lines = []
            selected_lines = []
            hover_lines = []
            for ent in sketch.entities:
                if is_active and (ent.entity_id in self.selected_entities or ent.entity_id in self._dim_highlight_ids()):
                    dest = selected_lines
                elif is_active and ent.entity_id == self.hover_entity_id:
                    dest = hover_lines
                else:
                    dest = construction_lines if ent.is_construction else normal_lines
                for p1, p2 in ent.to_lines():
                    w1 = plane.uv_to_world(p1[0], p1[1])
                    w2 = plane.uv_to_world(p2[0], p2[1])
                    dest.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])

            if normal_lines:
                if is_active:
                    from omacad.ui.settings import get_settings
                    scol = get_settings().sketch_line_color_rgb01()
                    self.draw_thick_lines(mvp, normal_lines, (*scol, 1.0), 2.4)
                else:
                    self.draw_thick_lines(mvp, normal_lines, (1.0, 0.65, 0.20, 1.0), 2.0)  # Orange sketch

            if hover_lines:
                self.draw_thick_lines(mvp, hover_lines, (1.0, 1.0, 1.0, 1.0), 3.0)
            if selected_lines:
                from omacad.ui.settings import get_settings
                hl_col = get_settings().highlight_color_rgb01() or theme.palette().highlight01()
                self.draw_thick_lines(mvp, selected_lines, (*hl_col, 1.0), 3.4)

            if construction_lines:
                from omacad.ui.settings import get_settings
                ccol = get_settings().sketch_construction_color_rgb01()
                self.draw_thick_lines(mvp, construction_lines, (*ccol, 1.0), 1.6)

        GL.glEnable(GL.GL_DEPTH_TEST)

        # Render Active Live Drawing Preview
        GL.glDisable(GL.GL_DEPTH_TEST)
        if self.doc.active_sketch and self.sketch_start_uv and self.sketch_current_uv:
            plane = self.doc.active_sketch.plane
            u1, v1 = self.sketch_start_uv
            u2, v2 = self.sketch_current_uv

            preview_lines = []
            if self.sketch_tool == "LINE":
                w1 = plane.uv_to_world(u1, v1)
                w2 = plane.uv_to_world(u2, v2)
                preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "RECT":
                corners = [(min(u1, u2), min(v1, v2)), (max(u1, u2), min(v1, v2)),
                           (max(u1, u2), max(v1, v2)), (min(u1, u2), max(v1, v2))]
                for i in range(4):
                    w1 = plane.uv_to_world(corners[i][0], corners[i][1])
                    w2 = plane.uv_to_world(corners[(i + 1) % 4][0], corners[(i + 1) % 4][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "CENTER_RECT":
                cx, cy = u1, v1
                dx, dy = abs(u2 - cx), abs(v2 - cy)
                corners = [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx + dx, cy + dy), (cx - dx, cy + dy)]
                for i in range(4):
                    w1 = plane.uv_to_world(corners[i][0], corners[i][1])
                    w2 = plane.uv_to_world(corners[(i + 1) % 4][0], corners[(i + 1) % 4][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                # Diagonals from center to corners
                for i in range(4):
                    w1 = plane.uv_to_world(cx, cy)
                    w2 = plane.uv_to_world(corners[i][0], corners[i][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "POLYGON":
                pts = Sketch.polygon_points((u1, v1), (u2, v2), self._polygon_sides())
                for i in range(len(pts)):
                    w1 = plane.uv_to_world(*pts[i])
                    w2 = plane.uv_to_world(*pts[(i + 1) % len(pts)])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "CIRCLE":
                r = math.hypot(u2 - u1, v2 - v1)
                segs = 36
                for i in range(segs):
                    a1 = 2.0 * math.pi * i / segs
                    a2 = 2.0 * math.pi * (i + 1) / segs
                    w1 = plane.uv_to_world(u1 + r * math.cos(a1), v1 + r * math.sin(a1))
                    w2 = plane.uv_to_world(u1 + r * math.cos(a2), v1 + r * math.sin(a2))
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "ARC":
                if self.sketch_second_uv is None:
                    w1 = plane.uv_to_world(u1, v1)
                    w2 = plane.uv_to_world(u2, v2)
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                else:
                    p1 = self.sketch_start_uv
                    p2 = self.sketch_second_uv
                    p_mid = (u2, v2)
                    arc_temp = SketchArc("temp", p1, p_mid, p2)
                    for seg_p1, seg_p2 in arc_temp.to_lines(24):
                        w1 = plane.uv_to_world(seg_p1[0], seg_p1[1])
                        w2 = plane.uv_to_world(seg_p2[0], seg_p2[1])
                        preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "SLOT":
                if self.sketch_second_uv is None:
                    w1 = plane.uv_to_world(u1, v1)
                    w2 = plane.uv_to_world(u2, v2)
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                else:
                    c1 = self.sketch_start_uv
                    c2 = self.sketch_second_uv
                    d = self._point_to_segment_dist((u2, v2), c1, c2)
                    slot_temp = SketchSlot("temp", c1, c2, max(1.0, d))
                    for seg_p1, seg_p2 in slot_temp.to_lines(16):
                        w1 = plane.uv_to_world(seg_p1[0], seg_p1[1])
                        w2 = plane.uv_to_world(seg_p2[0], seg_p2[1])
                        preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])

            if preview_lines:
                col = (1.0, 0.75, 0.25, 1.0) if self.construction_mode else (1.0, 0.92, 0.25, 1.0)
                self.draw_thick_lines(mvp, preview_lines, col, 2.2)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def draw_painter_overlays(self, painter: QPainter):
        """Draws ViewCube, sketch status banner, and HUD controls."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()

        # 1. ViewCube
        self.viewcube.draw(painter, w, h, self.azimuth, self.elevation)
        self._draw_measure(painter)

        # Fillet hover corner marker and arrow
        if self.doc.active_sketch and self.sketch_tool == "FILLET" and self.fillet_hover_corner:
            pt, la, lb = self.fillet_hover_corner
            scr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*pt))
            if scr:
                painter.setPen(QPen(QColor(255, 170, 60), 2))
                painter.setBrush(QColor(255, 170, 60, 160))
                painter.drawEllipse(QPointF(*scr), 6.0, 6.0)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                # Bisector arrow pointing into the corner
                try:
                    def line_dir(line):
                        p1 = np.array(line.p1)
                        p2 = np.array(line.p2)
                        d1 = float(np.linalg.norm(p1 - pt))
                        d2 = float(np.linalg.norm(p2 - pt))
                        far = p2 if d1 < d2 else p1
                        d = far - pt
                        norm = float(np.linalg.norm(d))
                        return d / norm if norm > 1e-6 else np.array([1.0, 0.0])

                    da = line_dir(la)
                    db = line_dir(lb)
                    bisect = da + db
                    b_norm = float(np.linalg.norm(bisect))
                    if b_norm > 1e-6:
                        bisect = bisect / b_norm
                        from omacad.ui.settings import get_settings
                        def_r = float(get_settings().get("fillet_default_radius", 2.0))
                        arrow_len = max(6.0, min(30.0, def_r * 2.5))
                        arrow_uv = np.array(pt) + bisect * arrow_len
                        scr_arr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*arrow_uv))
                        if scr_arr:
                            painter.setPen(QPen(QColor(0, 195, 255), 2.5))
                            painter.drawLine(QPointF(*scr), QPointF(*scr_arr))
                            # Arrow head
                            angle = math.atan2(scr_arr[1] - scr[1], scr_arr[0] - scr[0])
                            head_len = 9.0
                            h1 = QPointF(scr_arr[0] - head_len * math.cos(angle - 0.45), scr_arr[1] - head_len * math.sin(angle - 0.45))
                            h2 = QPointF(scr_arr[0] - head_len * math.cos(angle + 0.45), scr_arr[1] - head_len * math.sin(angle + 0.45))
                            painter.drawLine(QPointF(*scr_arr), h1)
                            painter.drawLine(QPointF(*scr_arr), h2)
                            # Handle circle at tip
                            painter.setBrush(QColor(0, 195, 255, 180))
                            painter.drawEllipse(QPointF(*scr_arr), 4.5, 4.5)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            # Label
                            painter.setFont(QFont("sans-serif", 9, QFont.Weight.Bold))
                            painter.setPen(QColor(0, 225, 255))
                            painter.drawText(QPointF(scr_arr[0] + 8, scr_arr[1] - 4), f"R {def_r:g} mm")
                except Exception:
                    pass

        # 2. Sketch Profiles Shading (when active or in sketch mode)
        if self.doc.active_sketch and self.sketch_palette.chk_show_profiles.isChecked():
            sketch = self.doc.active_sketch
            plane = sketch.plane
            for prof in sketch.profiles:
                poly_scr = []
                for pu, pv in prof.exterior_pts:
                    wpt = plane.uv_to_world(pu, pv)
                    scr = self.world_to_screen(wpt)
                    if scr:
                        poly_scr.append(QPointF(scr[0], scr[1]))
                if len(poly_scr) >= 3:
                    painter.setPen(QPen(qcolor(226, 109, 40, 200), 1.5))
                    painter.setBrush(QBrush(qcolor(226, 109, 40, 45)))  # Fusion Orange translucent profile fill
                    painter.drawPolygon(QPolygonF(poly_scr))

        self.draw_constraint_badges(painter)
        self.draw_dim_picks(painter)

        # 3. Snapping Indicators & Guide Lines
        if self.doc.active_sketch and self.active_snap and self.active_snap.snap_type != "NONE":
            plane = self.doc.active_sketch.plane
            snap = self.active_snap

            # Orthogonal guide line
            if snap.guide_line is not None:
                g1, g2 = snap.guide_line
                scr1 = self.world_to_screen(plane.uv_to_world(g1[0], g1[1]))
                scr2 = self.world_to_screen(plane.uv_to_world(g2[0], g2[1]))
                if scr1 and scr2:
                    pen_guide = QPen(qcolor(56, 189, 248, 180), 1, Qt.PenStyle.DashLine)
                    painter.setPen(pen_guide)
                    painter.drawLine(QPointF(scr1[0], scr1[1]), QPointF(scr2[0], scr2[1]))

            # Snap Target Marker
            target_uv = snap.target_uv or snap.uv
            tgt_world = plane.uv_to_world(target_uv[0], target_uv[1])
            scr_tgt = self.world_to_screen(tgt_world)
            if scr_tgt:
                sx, sy = scr_tgt
                if snap.snap_type == "ORIGIN":
                    painter.setPen(QPen(qcolor(226, 109, 40), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(sx, sy), 8, 8)
                    painter.drawEllipse(QPointF(sx, sy), 3, 3)
                elif snap.snap_type == "ENDPOINT":
                    painter.setPen(QPen(qcolor(56, 189, 248), 2))
                    painter.setBrush(QBrush(qcolor(56, 189, 248, 60)))
                    painter.drawRect(QRectF(sx - 5, sy - 5, 10, 10))
                elif snap.snap_type == "EDGE":
                    painter.setPen(QPen(qcolor(250, 204, 21), 2))
                    painter.setBrush(QBrush(qcolor(250, 204, 21, 70)))
                    painter.drawPolygon(QPolygonF([QPointF(sx, sy - 6), QPointF(sx + 6, sy),
                                                   QPointF(sx, sy + 6), QPointF(sx - 6, sy)]))
                elif snap.snap_type == "MIDPOINT":
                    painter.setPen(QPen(qcolor(74, 222, 128), 2))
                    painter.setBrush(QBrush(qcolor(74, 222, 128, 60)))
                    tri = QPolygonF([QPointF(sx, sy - 6), QPointF(sx - 6, sy + 5), QPointF(sx + 6, sy + 5)])
                    painter.drawPolygon(tri)
                elif snap.snap_type in ("ORTHO_H", "ORTHO_V"):
                    painter.setPen(QPen(qcolor(56, 189, 248), 1.5))
                    painter.setBrush(QBrush(qcolor(24, 28, 34, 220)))
                    badge_rect = QRectF(sx + 10, sy - 20, 20, 16)
                    painter.drawRoundedRect(badge_rect, 3, 3)
                    painter.setPen(QPen(qcolor(255, 255, 255)))
                    font_ortho = QFont(theme.font_family(), 8, QFont.Weight.Bold)
                    painter.setFont(font_ortho)
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "H" if snap.snap_type == "ORTHO_H" else "V")

        # 4. Floating Real-time Dimension Badge (the Tab entry boxes already show these values for
        #    line/rect/circle/move, so showing both only made them cover each other)
        entry_boxes_shown = self.dyn.active and dyn_input.supports(self.sketch_tool) and self._dyn_can_start()
        if (self.doc.active_sketch and self.sketch_start_uv and self.sketch_current_uv
                and self.sketch_palette.chk_show_dims.isChecked() and not entry_boxes_shown):
            u1, v1 = self.sketch_start_uv
            u2, v2 = self.sketch_current_uv
            dim_text = ""

            if self.sketch_tool == "LINE":
                length = math.hypot(u2 - u1, v2 - v1)
                angle = math.degrees(math.atan2(v2 - v1, u2 - u1))
                if angle < 0:
                    angle += 360.0
                dim_text = f"L: {length:.1f} mm  |  ∠ {angle:.1f}°"
            elif self.sketch_tool == "RECT":
                w_rect = abs(u2 - u1)
                h_rect = abs(v2 - v1)
                dim_text = f"W: {w_rect:.1f} mm  ×  H: {h_rect:.1f} mm"
            elif self.sketch_tool == "CENTER_RECT":
                w_rect = 2.0 * abs(u2 - u1)
                h_rect = 2.0 * abs(v2 - v1)
                dim_text = f"W: {w_rect:.1f} mm  ×  H: {h_rect:.1f} mm"
            elif self.sketch_tool == "POLYGON":
                n_p = self._polygon_sides()
                r_p = math.hypot(u2 - u1, v2 - v1)
                dim_text = f"{n_p} sides  ·  side: {2 * r_p * math.sin(math.pi / n_p):.2f} mm  (R: {r_p:.1f} mm)"
            elif self.sketch_tool == "CIRCLE":
                r_circ = math.hypot(u2 - u1, v2 - v1)
                dim_text = f"Ø: {2*r_circ:.1f} mm  (R: {r_circ:.1f} mm)"
            elif self.sketch_tool == "ARC":
                if self.sketch_second_uv is None:
                    chord = math.hypot(u2 - u1, v2 - v1)
                    dim_text = f"Chord: {chord:.1f} mm  (Pick End Point)"
                else:
                    p1 = self.sketch_start_uv
                    p2 = self.sketch_second_uv
                    p_mid = (u2, v2)
                    arc_temp = SketchArc("temp", p1, p_mid, p2)
                    params = arc_temp.get_circle_params()
                    if params:
                        dim_text = f"R: {params[1]:.1f} mm  (Pick Arc Point)"
                    else:
                        dim_text = "Pick Arc Point"
            elif self.sketch_tool == "SLOT":
                if self.sketch_second_uv is None:
                    length = math.hypot(u2 - u1, v2 - v1)
                    dim_text = f"L: {length:.1f} mm  (Pick Center 2)"
                else:
                    c1 = self.sketch_start_uv
                    c2 = self.sketch_second_uv
                    d = self._point_to_segment_dist((u2, v2), c1, c2)
                    r_slot = max(2.0, d)
                    dim_text = f"Ø: {2*r_slot:.1f} mm  |  R: {r_slot:.1f} mm"

            if dim_text:
                plane = self.doc.active_sketch.plane
                w_cur = plane.uv_to_world(u2, v2)
                scr_cur = self.world_to_screen(w_cur)
                if scr_cur:
                    bx = scr_cur[0] + 16
                    by = scr_cur[1] - 32
                    font_dim = QFont(theme.font_family(), 9, QFont.Weight.Bold)
                    painter.setFont(font_dim)
                    fm = painter.fontMetrics()
                    badge_w = fm.horizontalAdvance(dim_text) + 18
                    badge_h = 24
                    b_rect = QRectF(bx, by, badge_w, badge_h)

                    painter.setPen(QPen(qcolor(226, 109, 40), 1.2))
                    painter.setBrush(QBrush(qcolor(22, 25, 30, 235)))
                    painter.drawRoundedRect(b_rect, 4, 4)

                    painter.setPen(QPen(qcolor(245, 247, 250)))
                    painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

        # 4b. Parametric Dimension Annotations & Interactive Badges
        self.draw_dimensions(painter)

        self.draw_dyn_fields(painter)  # on top of everything else

        # 5. Sketch Mode Active Banner
        if self.doc.active_sketch:
            sketch = self.doc.active_sketch
            banner_text = (f"✏️ SKETCH MODE: {sketch.name} ({sketch.plane.name})"
                           + (f"  ·  {self.doc.sketch_status(sketch)}" if self.doc.sketch_status(sketch) else ""))
            banner_font = QFont()
            banner_font.setBold(True)
            banner_font.setPointSize(11)
            banner_w = max(320, QFontMetrics(banner_font).horizontalAdvance(banner_text) + 40)
            banner_rect = QRectF(w / 2.0 - banner_w / 2.0, 16, banner_w, 36)
            painter.setPen(QPen(qcolor(226, 109, 40), 1))
            painter.setBrush(QBrush(qcolor(30, 34, 40, 230)))
            painter.drawRoundedRect(banner_rect, 6, 6)

            painter.setPen(QPen(qcolor(255, 255, 255)))
            font = QFont()
            font.setBold(True)
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                banner_rect,
                Qt.AlignmentFlag.AlignCenter,
                banner_text
            )

        # 6. Bottom HUD Navigation Bar
        hud_w = 260
        hud_h = 36
        hud_rect = QRectF((w - hud_w) / 2.0, h - 50, hud_w, hud_h)
        painter.setPen(QPen(qcolor(60, 65, 75), 1))
        painter.setBrush(QBrush(qcolor(26, 28, 32, 220)))
        painter.drawRoundedRect(hud_rect, 6, 6)

        # HUD Icons / Labels
        font_hud = QFont()
        font_hud.setPointSize(10)
        font_hud.setBold(True)
        painter.setFont(font_hud)

        labels = [("🔄 Orbit", 0), ("✋ Pan", 65), ("🔲 Fit", 130), ("📐 Grid", 195)]
        for text, x_off in labels:
            btn_rect = QRectF(hud_rect.x() + x_off + 4, hud_rect.y() + 4, 60, 28)
            painter.setPen(QPen(qcolor(200, 205, 215)))
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, text)

        # 7. Viewport Details (lower left)
        painter.setPen(QPen(qcolor(140, 145, 155)))
        font_small = QFont()
        font_small.setPointSize(9)
        painter.setFont(font_small)
        cam_info = f"Azimuth: {self.azimuth:.1f}° | Elevation: {self.elevation:.1f}° | Zoom: {self.distance:.0f} mm"
        painter.drawText(16, h - 16, cam_info)

    def draw_dimensions(self, painter: QPainter):
        """Renders dimension extension lines, arrows, and interactive value badges."""
        if not self.doc.active_sketch or not self.sketch_palette.chk_show_dims.isChecked():
            self.dim_badges.clear()
            return

        sketch = self.doc.active_sketch
        plane = sketch.plane
        self.dim_badges.clear()

        font_dim = QFont(theme.font_family(), 9, QFont.Weight.Bold)
        painter.setFont(font_dim)
        fm = painter.fontMetrics()

        pen_ext = QPen(qcolor(160, 180, 205, 180), 1, Qt.PenStyle.DashLine)
        pen_dim_line = QPen(qcolor(200, 225, 255, 230), 1.2, Qt.PenStyle.SolidLine)

        for dim in sketch.dimensions:
            ent = sketch.get_entity(dim.target_entity_id)
            if not ent:
                continue

            lines_to_draw = []
            badge_pos_uv = None
            dim_p1_uv = None
            dim_p2_uv = None
            badge_text = f"{dim.dim_id}: {dim.value:.1f} mm"

            if dim.dim_type == "RECT_WIDTH":
                if isinstance(ent, SketchRect):
                    x1 = min(ent.p1[0], ent.p2[0])
                    x2 = max(ent.p1[0], ent.p2[0])
                    y_base = min(ent.p1[1], ent.p2[1])
                elif isinstance(ent, SketchCenterRect):
                    c1, c2, _, _ = ent.get_corners()
                    x1, x2 = c1[0], c2[0]
                    y_base = c1[1]
                else:
                    continue
                y_dim = y_base - dim.offset_distance
                ext1 = ((x1, y_base), (x1, y_dim - 2.0))
                ext2 = ((x2, y_base), (x2, y_dim - 2.0))
                dim_line = ((x1, y_dim), (x2, y_dim))
                lines_to_draw = [ext1, ext2, dim_line]
                dim_p1_uv = (x1, y_dim)
                dim_p2_uv = (x2, y_dim)
                badge_pos_uv = ((x1 + x2) * 0.5, y_dim)

            elif dim.dim_type == "RECT_HEIGHT":
                if isinstance(ent, SketchRect):
                    x_base = max(ent.p1[0], ent.p2[0])
                    y1 = min(ent.p1[1], ent.p2[1])
                    y2 = max(ent.p1[1], ent.p2[1])
                elif isinstance(ent, SketchCenterRect):
                    c1, c2, c3, _ = ent.get_corners()
                    x_base = c2[0]
                    y1, y2 = c1[1], c3[1]
                else:
                    continue
                x_dim = x_base + dim.offset_distance
                ext1 = ((x_base, y1), (x_dim + 2.0, y1))
                ext2 = ((x_base, y2), (x_dim + 2.0, y2))
                dim_line = ((x_dim, y1), (x_dim, y2))
                lines_to_draw = [ext1, ext2, dim_line]
                dim_p1_uv = (x_dim, y1)
                dim_p2_uv = (x_dim, y2)
                badge_pos_uv = (x_dim, (y1 + y2) * 0.5)

            elif dim.dim_type == "LENGTH":
                if isinstance(ent, SketchLine):
                    p1, p2 = ent.p1, ent.p2
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    length = math.hypot(dx, dy)
                    if length > 1e-4:
                        nx = -dy / length
                        ny = dx / length
                        off = dim.offset_distance
                        p1_off = (p1[0] + nx * off, p1[1] + ny * off)
                        p2_off = (p2[0] + nx * off, p2[1] + ny * off)
                        ext1 = (p1, (p1_off[0] + nx * 2.0, p1_off[1] + ny * 2.0))
                        ext2 = (p2, (p2_off[0] + nx * 2.0, p2_off[1] + ny * 2.0))
                        dim_line = (p1_off, p2_off)
                        lines_to_draw = [ext1, ext2, dim_line]
                        dim_p1_uv = p1_off
                        dim_p2_uv = p2_off
                        badge_pos_uv = ((p1_off[0] + p2_off[0]) * 0.5, (p1_off[1] + p2_off[1]) * 0.5)
                elif isinstance(ent, SketchSlot):
                    c1, c2 = ent.center1, ent.center2
                    dx = c2[0] - c1[0]
                    dy = c2[1] - c1[1]
                    length = math.hypot(dx, dy)
                    if length > 1e-4:
                        nx = -dy / length
                        ny = dx / length
                        off = dim.offset_distance + ent.radius
                        p1_off = (c1[0] + nx * off, c1[1] + ny * off)
                        p2_off = (c2[0] + nx * off, c2[1] + ny * off)
                        ext1 = (c1, p1_off)
                        ext2 = (c2, p2_off)
                        dim_line = (p1_off, p2_off)
                        lines_to_draw = [ext1, ext2, dim_line]
                        dim_p1_uv = p1_off
                        dim_p2_uv = p2_off
                        badge_pos_uv = ((p1_off[0] + p2_off[0]) * 0.5, (p1_off[1] + p2_off[1]) * 0.5)

            elif dim.dim_type in ("DIAMETER", "RADIUS") and isinstance(ent, (SketchCircle, SketchSlot)):
                cx, cy = ent.center if isinstance(ent, SketchCircle) else ent.center2
                r = ent.radius
                ang = math.pi * 0.25
                edge_pt = (cx + r * math.cos(ang), cy + r * math.sin(ang))
                leader_pt = (cx + (r + dim.offset_distance) * math.cos(ang), cy + (r + dim.offset_distance) * math.sin(ang))
                leader_ext = (edge_pt, leader_pt)
                lines_to_draw = [leader_ext]
                dim_p1_uv = edge_pt
                dim_p2_uv = leader_pt
                badge_pos_uv = leader_pt
                symbol = "Ø" if dim.dim_type == "DIAMETER" else "R"
                badge_text = f"{symbol} {dim.value:.1f} mm ({dim.dim_id})"

            elif dim.dim_type == "RADIUS" and isinstance(ent, SketchArc):
                params = ent.get_circle_params()
                if params:
                    cx, cy = params[0]
                    r = params[1]
                    mid = ent.p_mid
                    ang = math.atan2(mid[1] - cy, mid[0] - cx)
                    leader_pt = (cx + (r + dim.offset_distance) * math.cos(ang), cy + (r + dim.offset_distance) * math.sin(ang))
                    lines_to_draw = [(mid, leader_pt)]
                    dim_p1_uv = mid
                    dim_p2_uv = leader_pt
                    badge_pos_uv = leader_pt
                    badge_text = f"R {dim.value:.1f} mm ({dim.dim_id})"

            elif dim.dim_type == "ANGLE":
                other = sketch.get_entity(dim.refs[0]) if dim.refs else None
                if isinstance(ent, SketchLine) and isinstance(other, SketchLine) and len(dim.pts) == 2:
                    ua, ub = arm_vector(ent, dim.pts[0]), arm_vector(other, dim.pts[1])
                    na, nb = math.hypot(*ua), math.hypot(*ub)
                    if na > 1e-6 and nb > 1e-6:
                        # vertex: where the two lines (extended) meet, else the nearest ends' midpoint
                        pa, pb = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
                        det = ua[0] * ub[1] - ua[1] * ub[0]
                        if abs(det) > 1e-9 * na * nb:
                            t = ((pb[0] - pa[0]) * ub[1] - (pb[1] - pa[1]) * ub[0]) / det
                            vtx = (pa[0] + ua[0] * t, pa[1] + ua[1] * t)
                        else:
                            vtx = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
                        a0 = math.atan2(ua[1], ua[0])
                        sweep = math.atan2(ua[0] * ub[1] - ua[1] * ub[0], ua[0] * ub[0] + ua[1] * ub[1])
                        radius = 8.0 + dim.offset_distance * 0.6
                        arc = [(vtx[0] + radius * math.cos(a0 + sweep * k / 24.0),
                                vtx[1] + radius * math.sin(a0 + sweep * k / 24.0)) for k in range(25)]
                        painter.setPen(pen_dim_line)
                        for q1, q2 in zip(arc, arc[1:]):
                            s1 = self.world_to_screen(plane.uv_to_world(q1[0], q1[1]))
                            s2 = self.world_to_screen(plane.uv_to_world(q2[0], q2[1]))
                            if s1 and s2:
                                painter.drawLine(QPointF(s1[0], s1[1]), QPointF(s2[0], s2[1]))
                        mid = a0 + sweep / 2.0
                        badge_pos_uv = (vtx[0] + (radius + 6.0) * math.cos(mid), vtx[1] + (radius + 6.0) * math.sin(mid))
                        badge_text = f"∠ {dim.value:.1f}° ({dim.dim_id})"

            elif dim.dim_type in ("DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST"):
                other = sketch.get_entity(dim.refs[0]) if dim.refs else None
                edge = ref_segment(dim.refs[0]) if dim.refs else None
                if edge is not None:  # measured to a fixed face edge
                    other = SketchLine("edge", edge[0], edge[1])
                if other is not None and dim.pts:
                    if (dim.dim_type == "PT_LINE_DIST" and isinstance(other, SketchLine)
                            and dim.pts[0] in EDGE_PTS and isinstance(ent, SketchCircle)):
                        (x1, y1), (x2, y2) = other.p1, other.p2
                        L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                        if L2 > 1e-12:
                            cx, cy = ent.center
                            t = ((cx - x1) * (x2 - x1) + (cy - y1) * (y2 - y1)) / L2
                            foot = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                            dx, dy = cx - foot[0], cy - foot[1]
                            dl = math.hypot(dx, dy) or 1.0
                            sgn = -1.0 if dim.pts[0] == "edge_near" else 1.0
                            edge_pt = (cx + sgn * ent.radius * dx / dl, cy + sgn * ent.radius * dy / dl)
                            lines_to_draw = [(foot, edge_pt)]
                            dim_p1_uv, dim_p2_uv = foot, edge_pt
                            badge_pos_uv = ((foot[0] + edge_pt[0]) / 2.0, (foot[1] + edge_pt[1]) / 2.0)
                    elif dim.dim_type == "PT_LINE_DIST" and isinstance(other, SketchLine):
                        P = point_of(ent, dim.pts[0])
                        (x1, y1), (x2, y2) = other.p1, other.p2
                        L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                        if P and L2 > 1e-12:
                            t = ((P[0] - x1) * (x2 - x1) + (P[1] - y1) * (y2 - y1)) / L2
                            foot = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                            lines_to_draw = [(P, foot)]
                            dim_p1_uv, dim_p2_uv = P, foot
                            badge_pos_uv = ((P[0] + foot[0]) / 2.0, (P[1] + foot[1]) / 2.0)
                    elif len(dim.pts) == 2:
                        A, B = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
                        off = dim.offset_distance
                        if A and B and dim.dim_type == "HORIZ_DIST":
                            y_dim = max(A[1], B[1]) + off
                            lines_to_draw = [((A[0], A[1]), (A[0], y_dim)), ((B[0], B[1]), (B[0], y_dim)),
                                             ((A[0], y_dim), (B[0], y_dim))]
                            dim_p1_uv, dim_p2_uv = (A[0], y_dim), (B[0], y_dim)
                            badge_pos_uv = ((A[0] + B[0]) / 2.0, y_dim)
                        elif A and B and dim.dim_type == "VERT_DIST":
                            x_dim = max(A[0], B[0]) + off
                            lines_to_draw = [((A[0], A[1]), (x_dim, A[1])), ((B[0], B[1]), (x_dim, B[1])),
                                             ((x_dim, A[1]), (x_dim, B[1]))]
                            dim_p1_uv, dim_p2_uv = (x_dim, A[1]), (x_dim, B[1])
                            badge_pos_uv = (x_dim, (A[1] + B[1]) / 2.0)
                        elif A and B:
                            L = math.hypot(B[0] - A[0], B[1] - A[1])
                            if L > 1e-6:
                                nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
                                a_off = (A[0] + nx * off, A[1] + ny * off)
                                b_off = (B[0] + nx * off, B[1] + ny * off)
                                lines_to_draw = [(A, a_off), (B, b_off), (a_off, b_off)]
                                dim_p1_uv, dim_p2_uv = a_off, b_off
                                badge_pos_uv = ((a_off[0] + b_off[0]) / 2.0, (a_off[1] + b_off[1]) / 2.0)

            if dim.expr and badge_text:
                badge_text += f"   ƒ {dim.expr}"

            # Draw lines
            for idx, (u_a, u_b) in enumerate(lines_to_draw):
                w_a = plane.uv_to_world(u_a[0], u_a[1])
                w_b = plane.uv_to_world(u_b[0], u_b[1])
                s_a = self.world_to_screen(w_a)
                s_b = self.world_to_screen(w_b)
                if s_a and s_b:
                    if idx < 2 and len(lines_to_draw) >= 3:
                        painter.setPen(pen_ext)
                    else:
                        painter.setPen(pen_dim_line)
                    painter.drawLine(QPointF(s_a[0], s_a[1]), QPointF(s_b[0], s_b[1]))

            # Draw Arrowheads on dimension line
            if dim_p1_uv and dim_p2_uv:
                w1 = plane.uv_to_world(dim_p1_uv[0], dim_p1_uv[1])
                w2 = plane.uv_to_world(dim_p2_uv[0], dim_p2_uv[1])
                s1 = self.world_to_screen(w1)
                s2 = self.world_to_screen(w2)
                if s1 and s2:
                    if dim.dim_type in ("DIAMETER", "RADIUS"):
                        self._draw_single_arrowhead(painter, s1, s2)
                    else:
                        self._draw_arrowheads(painter, s1, s2)

            # Draw Dimension Badge
            if badge_pos_uv:
                w_badge = plane.uv_to_world(badge_pos_uv[0], badge_pos_uv[1])
                s_badge = self.world_to_screen(w_badge)
                if s_badge:
                    bw = fm.horizontalAdvance(badge_text) + 20
                    bh = 22
                    bx = s_badge[0] - bw * 0.5
                    by = s_badge[1] - bh * 0.5
                    badge_rect = QRectF(bx, by, bw, bh)

                    self.dim_badges[dim.dim_id] = (badge_rect, sketch.sketch_id, dim.dim_id, dim.value)

                    is_hovered = (self.hovered_dim_id == dim.dim_id)
                    if is_hovered:
                        painter.setPen(QPen(qcolor(255, 255, 255), 1.5))
                        painter.setBrush(QBrush(qcolor(226, 109, 40, 245)))
                        painter.drawRoundedRect(badge_rect, 4, 4)
                        painter.setPen(QPen(qcolor(255, 255, 255)))
                        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, f"✏️ {badge_text}")
                    else:
                        painter.setPen(QPen(qcolor(70, 115, 160, 210), 1.0))
                        painter.setBrush(QBrush(qcolor(22, 26, 32, 230)))
                        painter.drawRoundedRect(badge_rect, 4, 4)
                        painter.setPen(QPen(qcolor(215, 230, 250)))
                        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_arrowheads(self, painter: QPainter, s1: Tuple[float, float], s2: Tuple[float, float]):
        """Draws small CAD arrowheads at the endpoints of a dimension line."""
        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        dist = math.hypot(dx, dy)
        if dist < 12.0:
            return

        ux = dx / dist
        uy = dy / dist
        px = -uy
        py = ux

        arrow_len = 7.0
        arrow_half_w = 3.0

        painter.setPen(QPen(qcolor(200, 225, 255, 240), 1.0))
        painter.setBrush(QBrush(qcolor(200, 225, 255, 240)))

        # Arrowhead at s1 pointing towards s2
        a1_tip = QPointF(s1[0], s1[1])
        a1_b1 = QPointF(s1[0] + ux * arrow_len + px * arrow_half_w, s1[1] + uy * arrow_len + py * arrow_half_w)
        a1_b2 = QPointF(s1[0] + ux * arrow_len - px * arrow_half_w, s1[1] + uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a1_tip, a1_b1, a1_b2]))

        # Arrowhead at s2 pointing towards s1
        a2_tip = QPointF(s2[0], s2[1])
        a2_b1 = QPointF(s2[0] - ux * arrow_len + px * arrow_half_w, s2[1] - uy * arrow_len + py * arrow_half_w)
        a2_b2 = QPointF(s2[0] - ux * arrow_len - px * arrow_half_w, s2[1] - uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a2_tip, a2_b1, a2_b2]))

    def _draw_single_arrowhead(self, painter: QPainter, s1: Tuple[float, float], s2: Tuple[float, float]):
        """Draws a single arrowhead at s1 pointing towards s2 (for leader lines)."""
        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        dist = math.hypot(dx, dy)
        if dist < 6.0:
            return

        ux = dx / dist
        uy = dy / dist
        px = -uy
        py = ux

        arrow_len = 7.0
        arrow_half_w = 3.0

        painter.setPen(QPen(qcolor(200, 225, 255, 240), 1.0))
        painter.setBrush(QBrush(qcolor(200, 225, 255, 240)))

        a_tip = QPointF(s1[0], s1[1])
        a_b1 = QPointF(s1[0] + ux * arrow_len + px * arrow_half_w, s1[1] + uy * arrow_len + py * arrow_half_w)
        a_b2 = QPointF(s1[0] + ux * arrow_len - px * arrow_half_w, s1[1] + uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a_tip, a_b1, a_b2]))

    def prompt_edit_dimension(self, sketch_id: str, dim_id: str, current_value: float):
        """Edit a dimension value (type the number, press Enter); the solver updates the geometry."""
        sk = self.doc.sketches.get(sketch_id)
        dim = next((d for d in sk.dimensions if d.dim_id == dim_id), None) if sk else None
        is_angle = dim is not None and dim.dim_type == "ANGLE"
        res = self.prompt_dimension_value(
            f"Parametric Dimension ({dim_id})",
            f"Enter new value for {dim_id} ({'degrees' if is_angle else 'mm'}); a formula or parameter name works too:",
            current_value, 0.1, 179.9 if is_angle else 50000.0, " °" if is_angle else " mm",
            expr=dim.expr if dim is not None else None)
        val, ex = res if res is not None else (None, None)
        if val is not None and val > 0.001:
            if not self.doc.update_dimension(sketch_id, dim_id, val, expr=ex):
                self.status_message.emit(self.doc.last_message)
            self.update()

    # ---- Dimension tool ----------------------------------------------------------
    def _dim_highlight_ids(self) -> set:
        ids = {p[1].entity_id for p in self._dim_pending if p[0] in ("ent", "pt")}  # "ref" picks are edges, not entities
        if self._dim_place:
            ids |= {self._dim_place["a"][1].entity_id, self._dim_place["b"][1].entity_id}
        return ids

    def _dim_pick(self, u: float, v: float):
        """('pt', entity, point name) near an end point/centre, else ('ent', entity), else None."""
        sk = self.doc.active_sketch
        tol = self._entity_tolerance()
        best = None
        for e in sk.entities:
            names = ("p1", "p2") if isinstance(e, SketchLine) else ("center",) if isinstance(e, SketchCircle) else ()
            for n in names:
                pt = point_of(e, n)
                d = math.hypot(u - pt[0], v - pt[1])
                if d <= tol * 1.3 and (best is None or d < best[0]):
                    best = (d, e, n)
        if best:
            return ("pt", best[1], best[2])
        ent = sk.hit_test(u, v, tol)
        if ent:
            return ("ent", ent)
        # the outline of the face the sketch is on (and other in-plane body edges)
        near = None
        for seg in sk.reference_segments:
            d = self._point_to_segment_dist((u, v), seg[0], seg[1])
            if d <= tol and (near is None or d < near[0]):
                near = (d, seg)
        return ("ref", near[1]) if near else None

    def prompt_dimension_value(self, title: str, label: str, value: float, lo: float = 0.1,
                               hi: float = 50000.0, suffix: str = " mm", expr: str = None, on_change=None):
        """Value dialog with the number pre-selected: type it and press Enter. Returns None on cancel."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        spin = ExprDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setSuffix(suffix)
        spin.setValue(max(lo, min(hi, float(value))))
        if expr:
            spin.set_expression(expr)  # keep showing the formula that drives this dimension
        spin.setToolTip("Type a value, a formula (10-1, 2x(3+5)) or a parameter name (width/2)")
        lay.addWidget(spin)
        if on_change is not None:
            spin.valueChanged.connect(lambda *_: on_change(spin.value()))
            QTimer.singleShot(0, lambda: on_change(spin.value()))   # show the first preview at once
        row = QHBoxLayout()
        row.addStretch()
        cancel, ok = QPushButton("Cancel"), QPushButton("OK")
        ok.setDefault(True)
        cancel.clicked.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        QTimer.singleShot(0, lambda: (spin.setFocus(), spin.selectAll()))
        from omacad.ui.dialogs import run_docked
        if run_docked(dlg) != QDialog.DialogCode.Accepted:
            return None
        spin.interpretText()  # evaluates a formula that was typed but not yet committed
        return spin.value(), spin.expression()

    def _dim_create(self, dim_type, target, measured, refs=(), pts=(), offset=12.0, label="", lo=0.1, hi=50000.0, suffix=" mm"):
        sk = self.doc.active_sketch
        res = self.prompt_dimension_value(f"New dimension", label, measured, lo, hi, suffix)
        if res is None:
            return
        val, ex = res
        self.doc.add_dimension_constraint(sk.sketch_id, dim_type, target, val, refs=refs, pts=pts, offset=offset, expr=ex)
        self.status_message.emit(self.doc.last_message)
        self.update()

    def _dim_existing(self, dim_type, target, refs=(), pts=()):
        sk = self.doc.active_sketch
        refs = list(refs)
        for d in sk.dimensions:
            if d.dim_type != dim_type:
                continue
            same = d.target_entity_id == target and d.refs == refs and (not pts or d.pts == list(pts))
            swapped = dim_type == "ANGLE" and refs and d.target_entity_id == refs[0] and d.refs == [target]
            if same or swapped:
                return d
        return None

    def _dim_circle(self, circ):
        sk = self.doc.active_sketch
        existing = next((d for d in sk.dimensions
                         if d.target_entity_id == circ.entity_id and d.dim_type in ("DIAMETER", "RADIUS")), None)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            self._dim_create("DIAMETER", circ.entity_id, circ.radius * 2.0, label="Diameter (mm):")

    def _dim_length(self, line):
        sk = self.doc.active_sketch
        existing = self._dim_existing("LENGTH", line.entity_id)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            L = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
            self._dim_create("LENGTH", line.entity_id, L, label="Length (mm):")

    def _dim_angle(self, a, b):
        sk = self.doc.active_sketch
        ea, eb = nearest_ends_to_vertex(a, b)
        existing = self._dim_existing("ANGLE", a.entity_id, refs=[b.entity_id])
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("ANGLE", a.entity_id, arm_angle_deg(a, ea, b, eb), refs=[b.entity_id], pts=[ea, eb],
                         offset=12.0, label="Angle (degrees):", lo=0.1, hi=179.9, suffix=" °")

    def _dim_pt_line(self, pt_pick, line):
        ent, pname = pt_pick[1], pt_pick[2]
        if ent is line:
            return
        P = point_of(ent, pname)
        (x1, y1), (x2, y2) = line.p1, line.p2
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = abs((P[0] - x1) * (y2 - y1) - (P[1] - y1) * (x2 - x1)) / L
        existing = self._dim_existing("PT_LINE_DIST", ent.entity_id, refs=[line.entity_id], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", ent.entity_id, dist, refs=[line.entity_id], pts=[pname], label="Distance to line (mm):", lo=0.0)

    def _dim_edge_to_circle(self, line_pick, circ, u: float, v: float):
        """Distance from a face edge / line to the near or far edge of a circle. Which one is decided
        by where on the circle you clicked: the side facing the line is the near edge."""
        if line_pick[0] == "ref":
            seg, line_ref, line_ent = line_pick[1], ref_id(line_pick[1]), None
        else:
            line_ent = line_pick[1]
            seg, line_ref = (line_ent.p1, line_ent.p2), line_ent.entity_id
        (x1, y1), (x2, y2) = seg
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = lambda px, py: abs((px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)) / L
        dc = dist(*circ.center)
        near = dist(u, v) < dc
        if self._dim_side in ("near", "far"):  # chosen explicitly from the right-click menu
            near = self._dim_side == "near"
        self._dim_side = None
        pname = "edge_near" if near else "edge_far"
        measured = max(0.0, dc - circ.radius) if near else dc + circ.radius
        existing = self._dim_existing("PT_LINE_DIST", circ.entity_id, refs=[line_ref], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", circ.entity_id, measured, refs=[line_ref], pts=[pname],
                         label=f"Distance to the circle's {'near' if near else 'far'} edge (mm):", lo=0.0)

    def _dim_pt_ref(self, pt_pick, seg):
        """Distance from a point (or circle centre) to a face edge, which stays fixed."""
        ent, pname = pt_pick[1], pt_pick[2]
        P = point_of(ent, pname)
        (x1, y1), (x2, y2) = seg
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = abs((P[0] - x1) * (y2 - y1) - (P[1] - y1) * (x2 - x1)) / L
        existing = self._dim_existing("PT_LINE_DIST", ent.entity_id, refs=[ref_id(seg)], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", ent.entity_id, dist, refs=[ref_id(seg)], pts=[pname],
                         label="Distance to edge (mm):", lo=0.0)

    def _dim_finish_points(self, u: float, v: float):
        """Placement click for a point-to-point distance: the side you click on picks the kind
        (above/below = horizontal, left/right = vertical, diagonal = aligned)."""
        place, self._dim_place = self._dim_place, None
        (ea, na), (eb, nb) = (place["a"][1], place["a"][2]), (place["b"][1], place["b"][2])
        A, B = point_of(ea, na), point_of(eb, nb)
        xmin, xmax = sorted((A[0], B[0]))
        ymin, ymax = sorted((A[1], B[1]))
        inside_x, inside_y = xmin <= u <= xmax, ymin <= v <= ymax
        if inside_x and not inside_y:
            dim_type, measured, offset = "HORIZ_DIST", abs(A[0] - B[0]), v - ymax
        elif inside_y and not inside_x:
            dim_type, measured, offset = "VERT_DIST", abs(A[1] - B[1]), u - xmax
        else:
            dim_type = "DISTANCE"
            measured = math.hypot(A[0] - B[0], A[1] - B[1])
            L = measured or 1.0
            nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
            offset = (u - A[0]) * nx + (v - A[1]) * ny
        existing = self._dim_existing(dim_type, ea.entity_id, refs=[eb.entity_id], pts=[na, nb])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create(dim_type, ea.entity_id, measured, refs=[eb.entity_id], pts=[na, nb], offset=offset,
                         label={"HORIZ_DIST": "Horizontal distance (mm):", "VERT_DIST": "Vertical distance (mm):"}.get(dim_type, "Distance (mm):"),
                         lo=0.0)

    def handle_dimension_tool_click(self, u: float, v: float) -> bool:
        """Dimension tool: circle = diameter; line + click away = length; line + line = angle;
        point + point = distance (click again to place); point + line = distance to line.
        Clicking a dimension that already exists edits it. Always consumes the click."""
        if not self.doc.active_sketch:
            return False
        if self._dim_place:
            self._dim_finish_points(u, v)
            self.update()
            return True
        pick = self._dim_pick(u, v)
        pend = self._dim_pending
        if not pend:
            if pick is None:
                self.status_message.emit("Dimension: click a line, circle or end point.")
            elif pick[0] == "ent" and isinstance(pick[1], SketchCircle):
                pend.append(pick)
                self.status_message.emit(
                    "Dimension: click away for the diameter, or click an edge/line to measure to the circle's edge "
                    "(click the centre point instead to measure from the centre).")
            elif pick[0] == "ent" and not isinstance(pick[1], SketchLine):
                self.status_message.emit("Dimension: this element type can't be dimensioned here yet.")
            elif pick[0] == "ref":
                pend.append(pick)
                self.status_message.emit("Dimension: now click the point or circle centre to measure from this edge.")
            else:
                pend.append(pick)
                self.status_message.emit(
                    "Dimension: click another line for an angle, an end point for a distance, or click away to dimension the length."
                    if pick[0] == "ent" else
                    "Dimension: click a second end point (distance) or a line (distance to line).")
            self.update()
            return True

        first = pend[0]
        self._dim_pending = []
        circle_pick = lambda p_: p_ and p_[0] == "ent" and isinstance(p_[1], SketchCircle)
        if first[0] == "ent" and isinstance(first[1], SketchCircle):  # a circle is waiting
            if pick and (pick[0] == "ref" or (pick[0] == "ent" and isinstance(pick[1], SketchLine))):
                self._dim_edge_to_circle(pick, first[1], u, v)
            else:
                self._dim_circle(first[1])
        elif first[0] == "ref" and circle_pick(pick):
            self._dim_edge_to_circle(first, pick[1], u, v)
        elif first[0] == "ent" and isinstance(first[1], SketchLine) and circle_pick(pick):
            self._dim_edge_to_circle(first, pick[1], u, v)
        elif first[0] == "ref":  # a face edge is waiting
            if pick and pick[0] == "pt":
                self._dim_pt_ref(pick, first[1])
            else:
                self.status_message.emit("Dimension: click an end point or a circle centre.")
        elif first[0] == "pt" and pick and pick[0] == "ref":
            self._dim_pt_ref(first, pick[1])
        elif first[0] == "ent":  # a line is waiting
            line = first[1]
            if pick and pick[0] == "ref":
                self.status_message.emit("Dimension: to measure from a face edge, click the point or circle centre first.")
            elif pick and pick[0] == "ent" and isinstance(pick[1], SketchLine) and pick[1] is not line:
                self._dim_angle(line, pick[1])
            elif pick and pick[0] == "pt" and pick[1] is not line:
                self._dim_pt_line(pick, line)
            else:
                self._dim_length(line)
        else:                  # a point is waiting
            if pick and pick[0] == "pt" and (pick[1].entity_id, pick[2]) != (first[1].entity_id, first[2]):
                self._dim_place = {"a": first, "b": pick}
                self.status_message.emit("Dimension: click where to place it (above/below = horizontal, beside = vertical, diagonal = aligned).")
            elif pick and pick[0] == "ent" and isinstance(pick[1], SketchLine):
                self._dim_pt_line(first, pick[1])
            else:
                self.status_message.emit("Dimension cancelled.")
        self.update()
        return True

    def _point_to_segment_dist(self, pt: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        px, py = pt
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        dy = y2 - y1
        l2 = dx*dx + dy*dy
        if l2 == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / l2))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    # ------------------ Mouse & Navigation ------------------

    def set_view(self, view_name: str):
        """Snaps camera to preset orthographic or isometric views."""
        v = view_name.upper()
        if v == "HOME":
            self.azimuth = 45.0
            self.elevation = 30.0
        elif v == "TOP":
            self.azimuth = 0.0
            self.elevation = 89.9
        elif v == "BOTTOM":
            self.azimuth = 0.0
            self.elevation = -89.9
        elif v == "FRONT":
            self.azimuth = 0.0
            self.elevation = 0.0
        elif v == "BACK":
            self.azimuth = 180.0
            self.elevation = 0.0
        elif v == "RIGHT":
            self.azimuth = 90.0
            self.elevation = 0.0
        elif v == "LEFT":
            self.azimuth = -90.0
            self.elevation = 0.0
        self.update()

    def zoom_fit(self):
        """Centers and fits camera to visible bodies or origin."""
        all_pts = []
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                all_pts.append(b.render_mesh.bounds_min)
                all_pts.append(b.render_mesh.bounds_max)

        if all_pts:
            pts = np.vstack(all_pts)
            b_min = pts.min(axis=0)
            b_max = pts.max(axis=0)
            self.target = (b_min + b_max) * 0.5
            diag = float(np.linalg.norm(b_max - b_min))
            self.distance = max(40.0, diag * 1.8)
        else:
            self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.distance = 140.0
        self.update()

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
        if event.button() == Qt.MouseButton.LeftButton and self.extrude_handle and self._handle_hit(x, y):
            self._handle_drag = True
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

        # Check Dimension Badge Clicks
        if self.doc.active_sketch and event.button() == Qt.MouseButton.LeftButton:
            for dim_id, (rect, s_id, d_id, val) in list(self.dim_badges.items()):
                if rect.contains(x, y):
                    self.prompt_edit_dimension(s_id, d_id, val)
                    return

        # Handle Dimension Tool Click near geometry
        if self.doc.active_sketch and self.sketch_tool == "DIMENSION" and event.button() == Qt.MouseButton.LeftButton:
            uv = self.get_sketch_plane_uv(x, y)
            if uv and self.handle_dimension_tool_click(uv[0], uv[1]):
                return

        self.last_mouse_pos = event.position().toPoint()

        # Handle Fillet Tool Click
        if self.doc.active_sketch and self.sketch_tool == "FILLET":
            if event.button() == Qt.MouseButton.RightButton:
                if self.fillet_first_line:
                    self.fillet_first_line = None
                    self.status_message.emit("Fillet: Klicka på ett hörn mellan två linjer, eller klicka två linjer (Esc avbryter).")
                    self.update()
                    return
                self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                if self.fillet_hover_corner:
                    pt, la, lb = self.fillet_hover_corner
                    self.prompt_fillet_radius(la, lb, pt)
                    return
                ent = self._pick_entity(x, y)
                from omacad.model.sketch import SketchLine
                if ent and isinstance(ent, SketchLine):
                    if self.fillet_first_line is None:
                        self.fillet_first_line = ent
                        self.status_message.emit("Fillet: Klicka nu på den andra linjen för att runda hörnet mellan dem.")
                    else:
                        first = self.fillet_first_line
                        self.fillet_first_line = None
                        if first.entity_id != ent.entity_id:
                            self.prompt_fillet_radius(first, ent)
                        else:
                            self.status_message.emit("Fillet: Välj två olika linjer.")
                    self.update()
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
                self.update()
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
        if (event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities()
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            ent = self._pick_entity(x, y)
            if ent is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.selected_entities ^= {ent.entity_id}
                    self.selection_changed.emit()
                    self.update()
                    return
                if ent.entity_id not in self.selected_entities:
                    self.selected_entities = {ent.entity_id}
                    self.selection_changed.emit()
                uv = self.get_sketch_plane_uv(x, y)
                if uv is not None:
                    self._drag = {"press_uv": uv, "press_pos": event.position(), "moved": False, "ent_id": ent.entity_id}
                self.update()
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
                for c in self._edge_loop(e):
                    if not any(self._same_edge(c, k) for k in self.selected_edges):
                        self.selected_edges.append(c)
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

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()

        # Check ViewCube hover
        if self.viewcube.handle_mouse_move(int(x), int(y), self.width()):
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
                else:
                    self._update_plane_hover(x, y)
        else:
            self._update_profile_hover(x, y)
            if not self.is_orbiting and not self.is_panning:
                self._update_entity_hover(x, y)

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
        elif self.sketch_tool in ("LINE", "RECT", "CENTER_RECT", "CIRCLE", "POLYGON", "ARC", "SLOT", "FILLET", "DIMENSION", "MOVE"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if hovered != prev_hovered:
            self.update()

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
        menu = QMenu(self)
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

        chosen = menu.exec(event.globalPosition().toPoint())
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
            self.offset_selected()
        elif key == "delete":
            self.delete_selected_entities()

    def _show_face_menu(self, event):
        """Right-click on a flat face: offer to sketch on it directly."""
        target = self._pick_plane_target(event.position().x(), event.position().y())
        if target is None or target[0] != "face":
            return
        face = target[1]
        self.ctx_face = face
        self.update()
        menu = QMenu(self)
        act_sketch = theme.action_with_icon(menu, "✏️ Create Sketch on this Face")
        act_extrude = theme.action_with_icon(menu, "⬆️ Extrude this Face…")
        act_extrude.setToolTip("Pull the face into the body to cut it away, or out to add material.")
        menu.setToolTipsVisible(True)
        chosen = menu.exec(event.globalPosition().toPoint())
        self.ctx_face = None
        self.update()
        if chosen is act_sketch:
            self.plane_picked.emit(self.plane_from_target(("face", face)))
        elif chosen is act_extrude:
            self.face_extrude_requested.emit(face)

    def mouseReleaseEvent(self, event):
        if (self.measure is not None and self.measure["mode"] == "model" and event.button() == Qt.MouseButton.LeftButton
                and self._press_pos is not None and (event.position() - self._press_pos).manhattanLength() < 4):
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            self._measure_click(event.position().x(), event.position().y())
            return
        if self._handle_drag and event.button() == Qt.MouseButton.LeftButton:
            self._handle_drag = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._handle_hover else Qt.CursorShape.ArrowCursor)
            self.update()
            return
        if event.button() == Qt.MouseButton.RightButton and self._rpress is not None:
            moved = (event.position() - self._rpress).manhattanLength()
            self._rpress = None
            self.is_panning = False
            if moved < 4 and not self.plane_pick_mode and not self.edge_pick_mode:
                if not self.doc.active_sketch:
                    self._show_face_menu(event)
                elif self.sketch_tool in ("NONE", "DIMENSION") and not self._move:
                    ent = self._pick_entity(event.position().x(), event.position().y())
                    if ent is not None:
                        self._show_element_menu(event, ent)
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
        if was_click and self.edge_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            e = self._pick_edge(event.position().x(), event.position().y())
            if e is not None:
                self._toggle_edge(e)
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
            target = self._pick_plane_target(event.position().x(), event.position().y())
            if target is not None:
                plane = self.plane_from_target(target)
                purpose = self.plane_pick_purpose
                self.end_plane_pick()
                if purpose == "offset_base":
                    self.offset_base_picked.emit(plane)
                elif purpose == "section_base":
                    self.section_base_picked.emit(plane)
                elif purpose == "extrude_target":
                    self.target_plane_picked.emit(plane)
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
                elif not chosen or chosen[0][0] == picked[0]:   # profiles must belong to the same sketch
                    chosen.append(picked)
                doc.selected_profile = chosen[0] if chosen else None
                doc.selected_extra = chosen[1:]
                self.profile_picked.emit()
                self.update()
            elif picked != doc.selected_profile or doc.selected_extra:
                doc.selected_profile = picked
                doc.selected_extra = []
                self.profile_picked.emit()
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
        if self.measure is not None and event.key() == Qt.Key.Key_Escape:
            self.end_measure()
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
            elif event.key() == Qt.Key.Key_M:
                self.set_sketch_tool("MOVE")
                return
            elif event.key() == Qt.Key.Key_O:
                self.offset_selected()
                return
            elif event.key() == Qt.Key.Key_F:
                self.set_sketch_tool("FILLET")
                return
            elif event.key() == Qt.Key.Key_I:
                self.begin_measure()
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
            else:
                self.set_sketch_tool("NONE")
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
