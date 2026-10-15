"""Tool prompts mixin for MainWindow.
Handles opening feature dialogs, live 3D preview manipulation, snapping and executing parametric solid operations.
"""

import os
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from omacad.model.timeline import (
    ExtrudeFeature, CombineFeature, SplitBodyFeature, ShellFeature, MoveFeature
)
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog, OffsetPlaneDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog,
    SphereDialog, CombineDialog, SplitBodyDialog, ShellDialog, MoveBodyDialog,
    ThreadDialog
)
from omacad.ui.canvas_dialog import CanvasEditorDialog


class ToolPromptsMixin:
    """Mixin providing all prompt_* methods for MainWindow."""
    def prompt_round_edges(self, kind: str = "fillet"):
        """Fillet / Chamfer: click edges (outside or inside corners), type the size, OK."""
        if getattr(self, "_round_dlg", None) is not None:
            self._round_dlg.raise_()
            return
        if not any(b.edges for b in self.doc.bodies.values()):
            QMessageBox.information(self, "Fillet / Chamfer", "There are no straight edges between flat faces to round yet.")
            return
        self.doc.hide_used_sketches()  # finished sketches only get in the way of picking edges
        self.doc.notify_changed()
        dlg = RoundEdgesDialog(self.viewport, kind, embedded=True)
        self.dock(dlg)
        self._round_dlg = dlg
        self.viewport.begin_edge_pick()
        self.status_label.setText("Fillet/Chamfer: click an edge (joined edges follow, double-click = loop, Shift+double-click = loop on the other face, X or Alt = see-through, Ctrl+click = remove, Backspace = undo last, Ctrl+Backspace = clear). Esc cancels.")

        def update_arrow():
            edges = self.viewport.selected_edges
            if edges:
                e0 = edges[0]
                if hasattr(e0, "p0") and hasattr(e0, "p1"):
                    mid = (np.asarray(e0.p0) + np.asarray(e0.p1)) * 0.5
                    d1 = getattr(e0, "d1", None)
                    d2 = getattr(e0, "d2", None)
                    if d1 is not None and d2 is not None:
                        # For a convex edge, d1 + d2 points into the material (cutting direction)
                        axis = np.asarray(d1) + np.asarray(d2)
                        if not getattr(e0, "convex", True):
                            axis = -axis  # for inside corner, cut/fill bisector
                        n_axis = np.linalg.norm(axis)
                        axis = axis / n_axis if n_axis > 1e-6 else np.array([0.0, 0.0, 1.0])
                    else:
                        axis = np.array([0.0, 0.0, 1.0])
                elif hasattr(e0, "center") and hasattr(e0, "radius"):
                    # Circular edge: pick a point on the circle towards the camera or top
                    u, v_ = e0._basis() if hasattr(e0, "_basis") else (np.array([1., 0., 0.]), np.array([0., 1., 0.]))
                    mid = np.asarray(e0.center) + u * float(e0.radius)
                    # Bisector into the cut: radial inward plus wall inward
                    rad_inward = -u if e0.s1 < 0 else u
                    wall_inward = -np.asarray(e0.axis) * e0.s2
                    axis = rad_inward + wall_inward
                    n_axis = np.linalg.norm(axis)
                    axis = axis / n_axis if n_axis > 1e-6 else np.array([0.0, 0.0, 1.0])
                elif hasattr(e0, "c"):
                    mid = np.asarray(e0.c)
                    axis = np.asarray(getattr(e0, "n", [0.0, 0.0, 1.0]))
                elif hasattr(e0, "pts") and len(e0.pts):
                    mid = np.mean(e0.pts, axis=0)
                    axis = np.asarray(getattr(e0, "n", [0.0, 0.0, 1.0]))
                else:
                    mid = np.array([0.0, 0.0, 0.0])
                    axis = np.array([0.0, 0.0, 1.0])
                self.viewport.set_extrude_handle(mid, axis, max(0.5, dlg.spn_size.value()), color=(0.10, 0.75, 1.0))
            else:
                self.viewport.clear_extrude_handle()

        def preview():
            from omacad.model.kernel import CadKernel
            from omacad.model.timeline import FilletFeature
            edges = self.viewport.selected_edges
            dlg.set_count(len(edges))
            solid, problem = None, None
            # Find which body owns each edge for clearance checks
            doc_bodies = list(self.doc.bodies.values())
            for e in edges:
                try:
                    owner_body = next((b for b in doc_bodies if any(e.same_as(k) for k in b.edges)), doc_bodies[0] if doc_bodies else None)
                    eff_size = FilletFeature._safe_edge_size(owner_body, e, dlg.spn_size.value()) if owner_body else dlg.spn_size.value()
                    tool = CadKernel.round_tool(e, eff_size, dlg.kind())
                    solid = tool if solid is None else solid + tool
                except Exception as ex:
                    problem = str(ex) or "This edge can't be rounded with that size."
            if problem:
                self.status_label.setText(f"Fillet/Chamfer: {problem}")
            self.viewport.set_preview(solid, "new_body")
            update_arrow()

        def on_handle_drag(val: float):
            v = max(0.2, abs(val))
            dlg.spn_size.setValue(round(v, 2))

        def on_cancel_pick():
            dlg.reject()

        def on_finished(result):
            self.viewport.edges_selection_changed.disconnect(preview)
            self.viewport.edge_pick_cancelled.disconnect(on_cancel_pick)
            try:
                self.viewport.extrude_handle_dragged.disconnect(on_handle_drag)
            except Exception:
                pass
            self.viewport.clear_extrude_handle()
            edges = [e.ref() for e in self.viewport.selected_edges]
            self._round_dlg = None
            dlg.deleteLater()
            self.inspector.undock_tool()
            self.viewport.end_edge_pick()
            self.viewport.set_preview(None)
            if result and edges:
                spin = dlg.spn_size.value()
                feat = self.doc.add_fillet(edges, spin, dlg.kind(), exprs=dlg.get_expressions())
                note = f" ({feat.skipped} edge(s) could not be rounded)" if feat.skipped else ""
                self.status_label.setText(f"{feat.name}: {len(edges)} edge(s), {spin:g} mm.{note}")
            elif result:
                self.status_label.setText("No edges were selected.")

        self.viewport.edges_selection_changed.connect(preview)
        self.viewport.edge_pick_cancelled.connect(on_cancel_pick)
        self.viewport.extrude_handle_dragged.connect(on_handle_drag)
        dlg.changed.connect(preview)
        dlg.finished.connect(on_finished)
        dlg.show()


    def prompt_pattern(self):
        """Copy what some steps did: evenly spaced, mirrored around the body, or around an axis."""
        from omacad.model.timeline import PatternFeature
        if not any(f.feature_type != "pattern" for f in self.doc.timeline.features):
            QMessageBox.information(self, "Pattern / Mirror", "Make something first (for example a hole), then copy it.")
            return
        self.doc.timeline.recompute(self.doc)  # fresh before/after states of every step
        dlg = PatternDialog(self.doc, self)

        def preview():
            ids = dlg.source_ids()
            if not ids:
                dlg.lbl_info.setText("Tick the steps to copy (for example the hole's sketch, cut and chamfer).")
                self.viewport.set_preview(None)
                return
            feat = PatternFeature("tmp", "tmp", ids, dlg.kind(), **dlg.get_params())
            solid, op, extra, copies = None, "cut", None, 0
            for bid in list(self.doc.bodies):
                res = feat.compute(self.doc, bid)
                if res is None:
                    continue
                rem, add = res
                copies = feat.copies
                solid, op = (rem, "cut") if rem is not None else (add, "join")
                extra = add if rem is not None else None
                break
            dlg.lbl_info.setText(f"{copies} copies will be made." if solid is not None
                                 else "Nothing to copy with these settings (the chosen steps changed nothing, or it is already symmetric).")
            self.viewport.set_preview(solid, op, extra=extra, extra_op="join")

        def on_step_clicked(point):
            """Click on the thing to copy: tick the step that made that surface (and its sketch)."""
            idx = self.doc.step_at_point(point)
            if idx is None:
                self.status_label.setText("Pattern: no step claims that spot. Tick the steps in the list instead.")
                return
            feat = self.doc.timeline.features[idx]
            wanted = {feat.feature_id}
            sk_id = getattr(feat, "sketch_id", None)
            wanted |= {f.feature_id for f in self.doc.timeline.features if f.feature_type == "sketch" and sk_id and f.feature_id == sk_id}
            items = [dlg.lst.item(i) for i in range(dlg.lst.count())]
            main_item = next((it for it in items if it.data(Qt.ItemDataRole.UserRole) == feat.feature_id), None)
            state = Qt.CheckState.Unchecked if main_item is not None and main_item.checkState() == Qt.CheckState.Checked \
                else Qt.CheckState.Checked
            for item in items:
                if item.data(Qt.ItemDataRole.UserRole) in wanted:
                    item.setCheckState(state)
            self.status_label.setText(f"Pattern: {feat.name} is {'no longer' if state == Qt.CheckState.Unchecked else 'now'} part of the copy "
                                      "(click it again to toggle).")

        dlg.changed.connect(preview)
        self.dock(dlg)
        self.viewport.pick_step_mode = True
        self.viewport.step_point_clicked.connect(on_step_clicked)

        def on_body_clicked(bid: str):
            # If user clicked a body in 3D, check all features associated with that body or toggle body's features
            b = self.doc.bodies.get(bid)
            if not b:
                return
            # Find features in timeline that created or modified this body
            body_features = [f.feature_id for f in self.doc.timeline.features if getattr(f, "target_body_id", None) == bid or getattr(f, "body_id", None) == bid or f.feature_id == bid or f.name == b.name]
            for i in range(dlg.lst.count()):
                it = dlg.lst.item(i)
                if it.data(Qt.ItemDataRole.UserRole) in body_features or it.text() == b.name:
                    cur = it.checkState()
                    it.setCheckState(Qt.CheckState.Unchecked if cur == Qt.CheckState.Checked else Qt.CheckState.Checked)

        self.viewport.body_clicked.connect(on_body_clicked)
        self.status_label.setText("Pattern / Mirror: click the thing you want to copy in the 3D view, or tick steps in the list.")
        preview()

        def on_finished(ok):
            self.viewport.pick_step_mode = False
            try:
                self.viewport.step_point_clicked.disconnect(on_step_clicked)
            except Exception:
                pass
            try:
                self.viewport.body_clicked.disconnect(on_body_clicked)
            except Exception:
                pass
            self.viewport.set_preview(None)
            self.inspector.undock_tool()
            if ok and dlg.source_ids():
                feat = self.doc.add_pattern(dlg.source_ids(), dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())
                self.status_label.setText(f"{feat.name}: {feat.copies} copies.")

        dlg.finished.connect(on_finished)
        dlg.show()


    def prompt_create_sketch(self):
        """Pick the sketch plane directly in the viewport (origin plane or planar face)."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick()
        self.status_label.setText("Create Sketch: click an origin plane or a flat face (Esc to cancel).")

    def on_plane_picked(self, plane):
        self.doc.auto_include_edges = self.viewport.sketch_palette.chk_project.isChecked()
        sketch = self.doc.start_sketch_on_plane(plane)
        self.viewport.align_to_plane(plane)
        where = f"{plane.name} plane" if plane.name != "FACE" else "face"
        self.status_label.setText(f"Active Sketch: {sketch.name} on {where}. Select a tool (Line, Rect, Circle) to draw.")

    def prompt_offset_plane(self):
        """Offset Plane: pick an origin plane, construction plane, or flat face to offset from."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick("offset_base")
        self.status_label.setText("Offset Plane: click a plane (XY, XZ, YZ, construction plane) or a flat face to start from (Esc cancels).")

    def on_offset_base_picked(self, base):
        from omacad.model.sketch import SketchPlane
        n = np.asarray(base.normal, dtype=float)
        n = n / np.linalg.norm(n)
        o = np.asarray(base.origin, dtype=float)

        dlg = OffsetPlaneDialog(base.name, self)
        self.dock(dlg)
        self.status_label.setText("Offset Plane: type the distance in mm (or drag the 3D arrow). Click 'To surface…' to touch a surface.")

        def update_preview():
            dist = dlg.spn_dist.value()
            self.viewport.set_preview_plane(SketchPlane.from_face(n, o + n * dist, name="PLANE"))
            self.viewport.set_extrude_handle(o, n, dist if abs(dist) > 0.1 else 5.0, color=(0.75, 0.55, 0.95))

        def on_handle_drag(dist: float):
            dlg.spn_dist.setValue(round(dist, 3))

        dlg.changed.connect(update_preview)
        self.viewport.extrude_handle_dragged.connect(on_handle_drag)
        update_preview()

        # Surface pick mode if user clicks "To surface…"
        def plane_at(hit):
            rel = float((hit["point"] - o) @ n)
            proj = (hit["patch"] - o) @ n
            dist = float(proj.max() if rel >= 0 else proj.min())
            if abs(rel) < 1e-6:
                dist = float(proj[np.abs(proj).argmax()])
            return dist

        def on_surface_picked(hit):
            dist = plane_at(hit)
            dlg.spn_dist.setValue(round(dist, 3))
            self.viewport.end_plane_pick()
            self.status_label.setText(f"Offset set to {dist:.3f} mm from the surface. Adjust it or click OK.")

        def start_surface_pick():
            self.viewport.begin_plane_pick("offset_surface")
            try:
                self.viewport.surface_picked.disconnect(on_surface_picked)
            except Exception:
                pass
            self.viewport.surface_picked.connect(on_surface_picked)
            self.status_label.setText("Click a surface (flat or curved) to place the plane tangent to it.")

        dlg.surface_requested.connect(start_surface_pick)

        def cleanup():
            try:
                self.viewport.surface_picked.disconnect(on_surface_picked)
            except Exception:
                pass
            try:
                self.viewport.extrude_handle_dragged.disconnect(on_handle_drag)
            except Exception:
                pass
            self.viewport.set_preview_plane(None)
            self.viewport.clear_extrude_handle()
            self.viewport.end_plane_pick()
            self.inspector.undock_tool()

        if dlg.exec():
            dist = dlg.spn_dist.value()
            pid = self.doc.add_construction_plane(base, dist)
            self.status_label.setText(f"{self.doc.construction_planes[pid]['name']} created {dist:.3f} mm from {base.name}.")
        cleanup()

    def prompt_section(self):
        """Section view: pick a plane or face, then slide the cut through the model (view only)."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        if not self.doc.bodies:
            QMessageBox.information(self, "Section View", "There is nothing to cut through yet.")
            return
        if self.viewport.section is not None:
            self.viewport.clear_section()
        self.viewport.begin_plane_pick("section_base")
        self.status_label.setText("Section View: click an origin plane or a flat face to cut along (Esc cancels).")

    def on_section_base_picked(self, base, section_id=None):
        """Section dialog; Done saves it as a section view in the tree (new, or the one being changed)."""
        from omacad.ui.dialogs import SectionDialog
        n = np.asarray(base.normal, dtype=float)
        o = np.asarray(base.origin, dtype=float)
        meshes = [b.render_mesh for b in self.doc.bodies.values() if b.render_mesh is not None and len(b.render_mesh.vertices)]
        pts = np.array([m.bounds_min for m in meshes] + [m.bounds_max for m in meshes], dtype=float)
        centre = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        extent = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) / 2.0
        anchor = centre - n * float((centre - o) @ n)       # where the arrow stands on the base plane
        start = float((centre - o) @ n)                      # first cut: the middle of the model
        existing = self.doc.sections.get(section_id) if section_id else None
        dlg = SectionDialog("face" if base.name == "FACE" else f"{base.name} plane", extent + abs(start), self.viewport)
        if existing:
            dlg.setWindowTitle("Change Section View")
        dlg.place(self.viewport.size())
        self.viewport.section_editing = True

        def apply():
            off = dlg.offset()
            self.viewport.set_section(o, n, off, dlg.flip())
            self.viewport.set_extrude_handle(anchor, n, off, color=(0.10, 0.45, 1.0))   # blue: the cut face and plane are orange

        def dragged(val):
            dlg.set_offset(val)

        def finished(result):
            self.viewport.extrude_handle_dragged.disconnect(dragged)
            self.viewport.section_editing = False
            self.viewport.clear_section()
            self._section_dlg = None
            if result:
                if existing:
                    self.doc.update_section(section_id, origin=[float(x) for x in o], normal=[float(x) for x in n],
                                            offset=dlg.offset(), flip=dlg.flip())
                    self.doc.set_section_active(section_id, True)
                else:
                    self.doc.add_section(o, n, dlg.offset(), dlg.flip())
                self.status_label.setText("Section view saved in the tree: click its eye to turn it on and off.")
            else:
                self.viewport.sync_section()
                self.status_label.setText("Section view cancelled.")
            dlg.deleteLater()

        self._section_dlg = dlg
        self.viewport.extrude_handle_dragged.connect(dragged)
        dlg.changed.connect(apply)
        dlg.finished.connect(finished)
        dlg.show()
        dlg.set_offset(round(existing["offset"] if existing else start, 2))
        if existing:
            dlg.chk_flip.setChecked(bool(existing["flip"]))
        apply()
        self.status_label.setText("Section View: slide the offset until you are happy, then Done saves it in the tree.")

    def edit_section(self, sid: str):
        from omacad.model.sketch import SketchPlane
        sec = self.doc.sections.get(sid)
        if sec is None or getattr(self, "_section_dlg", None) is not None:
            return
        base = SketchPlane.from_face(np.array(sec["normal"]), np.array(sec["origin"]), name="PLANE")
        self.on_section_base_picked(base, sid)


    def prompt_extrude(self, default_distance=None):
        if not self.doc.sketches:
            QMessageBox.information(
                self, "Extrude",
                "No sketches found. Create a sketch with a rectangle or circle first, then extrude!"
            )
            return

        if getattr(self, "_extrude_dlg", None) is not None:
            self._extrude_dlg.raise_()
            return

        dlg = ExtrudeDialog(self.doc, self.viewport, embedded=True)   # a small panel in the view, draggable
        dlg.place(self.viewport.size())
        if default_distance is not None:
            dlg.set_distance(default_distance)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._extrude_dlg = dlg

        def show_handle(s_id, p_idx, dist, direction):
            """The arrow in the view: start at the profile's centre, tip at the current distance."""
            from shapely.geometry import Polygon
            sk = self.doc.sketches.get(s_id)
            if sk is None or p_idx >= len(sk.profiles):
                return
            prof = sk.profiles[p_idx]
            c = Polygon(prof.exterior_pts, prof.interior_holes).representative_point()
            origin = sk.plane.uv_to_world(c.x, c.y)
            tip = dist / 2.0 if direction == "symmetric" else dist
            self.viewport.set_extrude_handle(origin, sk.plane.normal, tip, show_value=True,
                                             value_scale=2.0 if direction == "symmetric" else 1.0)

        def on_handle_dragged(t):
            direction = dlg.get_direction()[0]
            value = abs(t) * 2.0 if direction == "symmetric" else (max(t, 0.1) if direction == "two_sides" else t)
            dlg.spn_dist.setValue(value)

        def parts(s_id, p_idx):
            return ExtrudeFeature.selection_parts(self.doc, s_id, p_idx, self.doc.selected_extra)

        def refresh_preview():
            s_id, p_idx, dist, op = dlg.get_values()
            direction, dist2 = dlg.get_direction()
            solid = None
            if s_id is not None:
                extra, refs, holes = parts(s_id, p_idx)
                feat = ExtrudeFeature("preview", "preview", s_id, p_idx, dist, op, direction, dist2, extra_profiles=extra,
                                      extra_refs=refs, holes=holes)
                try:
                    solid = feat.build_solid(self.doc)
                    if op == "auto":
                        op = feat.resolve_operation(self.doc)
                        dlg.set_auto_result(op)
                except Exception:
                    solid = None
            self.viewport.set_preview(solid, op)
            if s_id is not None:
                show_handle(s_id, p_idx, dist, direction)
            # Keep the viewport highlight in sync with the combo
            if s_id is not None and self.doc.selected_profile != (s_id, p_idx):
                self.doc.selected_profile = (s_id, p_idx)
                self.doc.selected_extra = []
                self.viewport.update()
            n = 1 + len(self.doc.selected_extra) if s_id is not None else 0
            self.status_label.setText(f"Extrude: {n} profile(s) selected. Click to choose, Shift+click to add or remove." if n
                                      else "Extrude: click a profile in the view (Shift+click for several).")

        def on_pick():
            if self.doc.selected_profile:
                dlg.select_profile(self.doc.selected_profile)
            refresh_preview()
            dlg.focus_distance()

        def on_pick_face():
            self.viewport.begin_plane_pick("extrude_target")
            self.status_label.setText("Extrude: click the face (or origin plane) to extrude up to (Esc to cancel).")

        def on_target_plane(plane):
            s_id, _, _, _ = dlg.get_values()
            if s_id is None:
                return
            sp = self.doc.sketches[s_id].plane
            n0, n1 = np.asarray(sp.normal, dtype=float), np.asarray(plane.normal, dtype=float)
            if abs(float(n0 @ n1)) < 0.999:
                self.status_label.setText("That face is not parallel to the sketch plane, so there is no single distance to it.")
            else:
                dist = float((np.asarray(plane.origin, dtype=float) - np.asarray(sp.origin, dtype=float)) @ n0)
                if abs(dist) < 1e-6:
                    self.status_label.setText("That face is in the sketch plane (distance 0).")
                else:
                    dlg.set_distance(dist)
                    self.status_label.setText(f"Extrude distance to the face: {dist:.3f} mm.")
            dlg.activateWindow()
            dlg.focus_distance()

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.target_plane_picked.disconnect(on_target_plane)
            self.viewport.extrude_handle_dragged.disconnect(on_handle_dragged)
            self.viewport.clear_extrude_handle()
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self._extrude_dlg = None
            if result:
                s_id, p_idx, dist, op = dlg.get_values()
                if s_id is not None:
                    direction, dist2 = dlg.get_direction()
                    extra, refs, holes = parts(s_id, p_idx)
                    self.doc.extrude_profile(s_id, p_idx, dist, op, direction=direction, distance2=dist2,
                                             extra_profiles=extra, extra_refs=refs, holes=holes)
                    self.doc.timeline.features[-1].exprs = dlg.get_expressions()
                    op = self.doc.timeline.features[-1].operation  # what Auto resolved to
                    self.doc.selected_profile = None
                    self.doc.selected_extra = []
                    self.viewport.zoom_fit()
                    self.status_label.setText(f"Extruded profile by {dist} mm ({op}).")

        dlg.changed.connect(refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.extrude_handle_dragged.connect(on_handle_dragged)
        self.viewport.target_plane_picked.connect(on_target_plane)
        self.viewport.profile_picked.connect(on_pick)
        dlg.finished.connect(on_finished)
        dlg.show()
        refresh_preview()
        dlg.focus_distance()
        QTimer.singleShot(0, dlg.focus_distance)

    def prompt_revolve(self):
        """Revolve: profile (click it in the view), axis, angle, direction and operation, with live preview."""
        if not self.doc.sketches or not any(sk.profiles for sk in self.doc.sketches.values()):
            QMessageBox.information(self, "Revolve", "Draw a closed sketch profile first (and a construction line for the axis), then revolve it.")
            return
        if getattr(self, "_revolve_dlg", None) is not None:
            self._revolve_dlg.raise_()
            return
        from omacad.model.timeline import RevolveFeature
        from omacad.ui.dialogs import RevolveDialog
        dlg = RevolveDialog(self.doc, self.viewport, embedded=True)
        dlg.place(self.viewport.size())
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._revolve_dlg = dlg

        def extras(s_id):
            return [i for (sid, i) in self.doc.selected_extra if sid == s_id]

        def make(operation=None):
            s_id, p_idx = dlg.get_values()
            if s_id is None:
                return None
            return RevolveFeature("preview", "preview", s_id, p_idx, operation=operation or dlg.get_operation(), axis=dlg.get_axis(),
                                  angle=dlg.spn_angle.value(), direction=dlg.get_direction(), angle2=dlg.spn_angle2.value(),
                                  extra_profiles=extras(s_id))

        def refresh_preview():
            feat = make()
            solid, op = None, dlg.get_operation()
            dlg.lbl_info.setText("")
            if feat is not None:
                try:
                    solid = feat.build_solid(self.doc)
                    if op == "auto":
                        op = feat.resolve_operation(self.doc)
                        dlg.set_auto_result(op)
                except Exception:
                    solid = None
                dlg.lbl_info.setText(feat.problem)
                if self.doc.selected_profile != dlg.get_values():
                    self.doc.selected_profile = dlg.get_values()
                    self.doc.selected_extra = []
                    self.viewport.update()
            self.viewport.set_preview(solid, op)
            self.status_label.setText("Revolve: click a profile, pick the axis, set the angle." if feat is None else
                                      f"Revolve: {1 + len(self.doc.selected_extra)} profile(s). Enter = OK, Esc = cancel.")

        def on_pick():
            if self.doc.selected_profile:
                dlg.select_profile(self.doc.selected_profile)
            refresh_preview()

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.set_preview(None)
            self._revolve_dlg = None
            if result:
                feat = make()
                if feat is not None:
                    new = self.doc.add_revolve(feat.sketch_id, feat.profile_idx, axis=feat.axis, angle=feat.angle, operation=feat.operation,
                                               direction=feat.direction, angle2=feat.angle2, extra_profiles=feat.extra_profiles,
                                               exprs=dlg.get_expressions())
                    self.doc.selected_profile = None
                    self.doc.selected_extra = []
                    self.viewport.zoom_fit()
                    self.status_label.setText(new.problem or f"{new.name}: {new.angle:g}° ({new.operation}).")
            self.viewport.update()

        dlg.changed.connect(refresh_preview)
        self.viewport.profile_picked.connect(on_pick)
        dlg.finished.connect(on_finished)
        dlg.show()
        refresh_preview()

    def prompt_box(self):
        from omacad.model.features.primitives import BoxFeature
        dlg = BoxDialog(self)

        def refresh_preview():
            l, w, h, center, po, pn, pu, pv = dlg.get_values()
            feat = BoxFeature("preview_box", "Preview", l, w, h, center,
                              plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv)
            try:
                solid = feat.build_solid()
            except Exception:
                solid = None
            self.viewport.set_preview(solid, "new_body")
            self.viewport.update()

        def on_pick_face():
            self.viewport.begin_plane_pick("primitive_face")
            self.status_label.setText("Box: Klicka på ytan eller planet där undersidan ska starta (Esc avbryter).")

        def on_face_picked(plane):
            dlg.set_target_plane(plane)
            dlg.activateWindow()

        def on_finished(result):
            try:
                dlg.changed.disconnect(refresh_preview)
            except Exception:
                pass
            try:
                dlg.pick_face_requested.disconnect(on_pick_face)
            except Exception:
                pass
            try:
                self.viewport.primitive_face_picked.disconnect(on_face_picked)
            except Exception:
                pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                l, w, h, center, po, pn, pu, pv = dlg.get_values()
                body = self.doc.add_box(l, w, h, center=center,
                                        plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv)
                self.doc.timeline.features[-1].exprs = dlg.get_expressions()
                self.viewport.zoom_fit()
                self.status_label.setText(f"Created {body.name} ({l}x{w}x{h} mm).")

        dlg.changed.connect(refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        dlg.finished.connect(on_finished)
        self.dock(dlg)
        refresh_preview()

    def prompt_cylinder(self):
        from omacad.model.features.primitives import CylinderFeature
        dlg = CylinderDialog(self)

        def refresh_preview():
            r, h, center, po, pn, pu, pv = dlg.get_values()
            feat = CylinderFeature("preview_cyl", "Preview", r, h, center,
                                   plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv)
            try:
                solid = feat.build_solid()
            except Exception:
                solid = None
            self.viewport.set_preview(solid, "new_body")
            self.viewport.update()

        def on_pick_face():
            self.viewport.begin_plane_pick("primitive_face")
            self.status_label.setText("Cylinder: Klicka på ytan eller planet där undersidan ska starta (Esc avbryter).")

        def on_face_picked(plane):
            dlg.set_target_plane(plane)
            dlg.activateWindow()

        def on_finished(result):
            try:
                dlg.changed.disconnect(refresh_preview)
            except Exception:
                pass
            try:
                dlg.pick_face_requested.disconnect(on_pick_face)
            except Exception:
                pass
            try:
                self.viewport.primitive_face_picked.disconnect(on_face_picked)
            except Exception:
                pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                r, h, center, po, pn, pu, pv = dlg.get_values()
                body = self.doc.add_cylinder(r, h, center=center,
                                            plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv)
                self.doc.timeline.features[-1].exprs = dlg.get_expressions()
                self.viewport.zoom_fit()
                self.status_label.setText(f"Created {body.name} (R={r}, H={h} mm).")

        dlg.changed.connect(refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        dlg.finished.connect(on_finished)
        self.dock(dlg)
        refresh_preview()

    def prompt_sphere(self):
        dlg = SphereDialog(self)
        if dlg.exec():
            r = dlg.get_values()
            body = self.doc.add_sphere(r)
            self.doc.timeline.features[-1].exprs = dlg.get_expressions()
            self.viewport.zoom_fit()
            self.status_label.setText(f"Created {body.name} (R={r} mm).")

    def prompt_thread(self):
        from omacad.model.features.thread import ThreadFeature
        selected_id = self.doc.selected_body_ids[0] if self.doc.selected_body_ids else None
        dlg = ThreadDialog(self.doc, self, preselected_body_id=selected_id)

        def refresh_preview():
            vals = dlg.get_values()
            feat = ThreadFeature("preview_thread", "Preview", **vals)
            try:
                solid = feat.build_solid()
            except Exception:
                solid = None
            op = "cut" if vals.get("operation") == "cut" else "new_body"
            self.viewport.set_preview(solid, op)
            self.viewport.update()

        def on_pick_face():
            self.viewport.begin_plane_pick("thread_surface")
            self.status_label.setText("Thread / Coil: Klicka på en plan yta eller direkt på utsidan/insidan av en cylinder (Esc avbryter).")

        def on_face_picked(plane):
            dlg.set_plane(plane)
            dlg.activateWindow()

        def on_cylinder_picked(cyl_info):
            dlg.apply_cylinder_info(cyl_info, body_id=cyl_info.get("body_id"))
            dlg.activateWindow()

        def on_finished(result):
            try:
                dlg.changed.disconnect(refresh_preview)
            except Exception:
                pass
            try:
                dlg.pick_face_requested.disconnect(on_pick_face)
            except Exception:
                pass
            try:
                self.viewport.primitive_face_picked.disconnect(on_face_picked)
            except Exception:
                pass
            try:
                self.viewport.cylinder_picked.disconnect(on_cylinder_picked)
            except Exception:
                pass
            try:
                self.viewport.body_clicked.disconnect(dlg.select_body)
            except Exception:
                pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                vals = dlg.get_values()
                body = self.doc.add_thread(**vals)
                self.viewport.zoom_fit()
                if body:
                    self.status_label.setText(f"Created {body.name} (D={vals['diameter']}, P={vals['pitch']} mm).")

        dlg.changed.connect(refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        self.viewport.cylinder_picked.connect(on_cylinder_picked)
        self.viewport.body_clicked.connect(dlg.select_body)
        dlg.finished.connect(on_finished)
        self.dock(dlg)
        refresh_preview()
        on_pick_face()

    def prompt_combine(self):
        if len(self.doc.bodies) < 2:
            QMessageBox.information(
                self, "Combine", "You need at least 2 bodies in the document to perform a boolean combine!"
            )
            return

        selected_id = self.doc.selected_body_ids[0] if self.doc.selected_body_ids else ""
        dlg = CombineDialog(self.doc, self, preselected_target_id=selected_id or None)
        self.dock(dlg)

        def on_body_clicked(bid: str):
            dlg.select_body(bid)

        self.viewport.body_clicked.connect(on_body_clicked)

        def on_finished(result):
            try:
                self.viewport.body_clicked.disconnect(on_body_clicked)
            except Exception:
                pass
            self.inspector.undock_tool()
            if result:
                target_id, tool_id, op, keep = dlg.get_values()
                if target_id and tool_id:
                    feat_id = f"combine_{len(self.doc.timeline.features) + 1}"
                    feat = CombineFeature(feat_id, f"Combine ({op})", target_id, tool_id, op, keep_tool=keep)
                    self.doc.timeline.add_feature(feat)
                    feat.execute(self.doc)
                    self.doc.notify_changed()
                    self.status_label.setText(f"Combined bodies with operation: {op}.")

        dlg.finished.connect(on_finished)
        dlg.show()

    def prompt_split_body(self, target_body_id: str = "", plane_id: str = ""):
        if not self.doc.bodies:
            QMessageBox.information(
                self, "Split Body", "No bodies found to split. Create a 3D body first!"
            )
            return

        selected_id = target_body_id or (self.doc.selected_body_ids[0] if self.doc.selected_body_ids else "")
        dlg = SplitBodyDialog(
            self.doc, self,
            preselected_body_id=selected_id or None,
            preselected_plane_id=plane_id or None,
        )
        self.dock(dlg)

        def on_body_clicked(bid: str):
            dlg.select_body(bid)

        self.viewport.body_clicked.connect(on_body_clicked)

        def on_finished(result):
            try:
                self.viewport.body_clicked.disconnect(on_body_clicked)
            except Exception:
                pass
            self.inspector.undock_tool()
            if result:
                b_id, p_id = dlg.get_values()
                if b_id and p_id:
                    feat = self.doc.split_body(b_id, p_id)
                    if feat:
                        target = self.doc.bodies.get(b_id)
                        new_body = self.doc.bodies.get(f"body_{feat.feature_id}")
                        t_name = target.name if target else b_id
                        n_name = new_body.name if new_body else "Split"
                        self.status_label.setText(f"Split body {t_name} into {t_name} and {n_name}.")
                        self.viewport.update()

        dlg.finished.connect(on_finished)
        dlg.show()

    def prompt_shell(self, target_body_id: str = ""):
        """Shell: hollow out a 3D solid body with specified wall thickness and optional open faces."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Shell", "Create a 3D body first before shelling!")
            return

        selected_id = target_body_id or (self.doc.selected_body_ids[0] if self.doc.selected_body_ids else "")
        dlg = ShellDialog(self.doc, self, preselected_body_id=selected_id or None)
        self.dock(dlg)
        self.doc.hide_used_sketches()

        current_hidden_id = [None]

        def refresh_preview():
            bid, thickness, open_faces = dlg.get_values()
            if not bid or bid not in self.doc.bodies or thickness <= 0:
                if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                    self.doc.bodies[current_hidden_id[0]].visible = True
                    current_hidden_id[0] = None
                self.viewport.set_preview(None)
                return

            if current_hidden_id[0] and current_hidden_id[0] != bid and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True

            body = self.doc.bodies[bid]
            body.visible = False
            current_hidden_id[0] = bid
            switched = self.viewport.shell_target_body_id != bid
            self.viewport.shell_target_body_id = bid
            if switched and dlg.open_faces:   # open faces belong to the previous body
                dlg.clear_faces()
                return

            shelled = ShellFeature.compute_shell(body.manifold, thickness, dlg.direction(),
                                                 dlg.spn_thickness2.value(), open_faces)
            if shelled is not None:
                self.viewport.set_preview(shelled, "new_body")
            else:
                self.viewport.set_preview(body.manifold, "new_body")

        def on_face_picked(plane):
            if getattr(plane, "face", None):
                dlg.toggle_face(plane.face)
                self.viewport.highlighted_faces = [f["_face"] for f in dlg.open_faces if "_face" in f]
                self.viewport.update()

        self.viewport.shell_face_picked.connect(on_face_picked)
        self.viewport.begin_plane_pick("shell_face")
        self.status_label.setText("Shell: choose the body and the wall thickness. Click faces in 3D to leave them open.")

        def cleanup():
            try:
                self.viewport.shell_face_picked.disconnect(on_face_picked)
            except Exception:
                pass
            try:
                self.viewport.body_clicked.disconnect(dlg.select_body)
            except Exception:
                pass
            self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True
                current_hidden_id[0] = None
            self.inspector.undock_tool()

        def on_finished(result):
            b_id, thickness, open_faces = dlg.get_values()
            cleanup()
            if result and b_id and thickness > 0:
                feat = self.doc.add_shell(b_id, thickness, open_faces, exprs=dlg.get_expressions(),
                                          direction=dlg.direction(), thickness2=dlg.spn_thickness2.value())
                if feat:
                    body = self.doc.bodies.get(b_id)
                    b_name = body.name if body else b_id
                    n_open = len(open_faces)
                    self.status_label.setText(f"Shell created on {b_name}: thickness {thickness:g} mm ({n_open} open faces).")
                    self.viewport.update()
            else:
                self.status_label.setText("Shell cancelled.")
                self.viewport.update()

        dlg.changed.connect(refresh_preview)
        dlg.finished.connect(on_finished)
        self.viewport.body_clicked.connect(dlg.select_body)
        refresh_preview()
        dlg.show()

    def prompt_move_body(self, target_body_id: str = ""):
        """Move / Rotate: Translates and rotates a 3D solid body parametrically with interactive 3D gizmo."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Move Body", "There are no bodies to move. Create a 3D body first!")
            return

        selected_id = target_body_id or (next(iter(self.doc.selected_body_ids)) if self.doc.selected_body_ids else "")
        if not selected_id or selected_id not in self.doc.bodies:
            selected_id = next(iter(self.doc.bodies.keys()))

        dlg = MoveBodyDialog(self.doc, self, preselected_body_id=selected_id)
        self.dock(dlg)

        current_hidden_id = [None]
        drag_state = {
            "dragging": False,
            "start_val": 0.0,
            "start_axis_val": 0.0,
        }

        def get_body_center(body):
            if body.render_mesh is not None and len(body.render_mesh.vertices) > 0:
                return (np.asarray(body.render_mesh.bounds_min, dtype=float) + np.asarray(body.render_mesh.bounds_max, dtype=float)) * 0.5
            pts = body.manifold.to_mesh().vert_properties[:, :3]
            if len(pts):
                return (pts.min(axis=0) + pts.max(axis=0)) * 0.5
            return np.array([0.0, 0.0, 0.0])

        def update_handle():
            bid, dx, dy, dz, rx, ry, rz, pivot, _ = dlg.get_values()
            if not bid or bid not in self.doc.bodies:
                self.viewport.clear_move_gizmo()
                return

            body = self.doc.bodies[bid]
            center = get_body_center(body)
            moved_center = center + np.array([dx, dy, dz]) if pivot == "center" else np.array([dx, dy, dz])
            self.viewport.set_move_gizmo(moved_center)
            if self.viewport.move_gizmo:
                self.viewport.move_gizmo["active_axis"] = dlg.active_axis

        def refresh_preview():
            bid, dx, dy, dz, rx, ry, rz, pivot, _ = dlg.get_values()
            if not bid or bid not in self.doc.bodies:
                if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                    self.doc.bodies[current_hidden_id[0]].visible = True
                    current_hidden_id[0] = None
                self.viewport.set_preview(None)
                self.viewport.clear_move_gizmo()
                return

            if current_hidden_id[0] and current_hidden_id[0] != bid and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True

            body = self.doc.bodies[bid]
            body.visible = False
            current_hidden_id[0] = bid

            m = body.manifold
            center = get_body_center(body)

            if abs(rx) > 1e-4 or abs(ry) > 1e-4 or abs(rz) > 1e-4:
                if pivot == "center":
                    m = m.translate(-center).rotate([rx, ry, rz]).translate(center)
                else:
                    m = m.rotate([rx, ry, rz])

            if abs(dx) > 1e-4 or abs(dy) > 1e-4 or abs(dz) > 1e-4:
                m = m.translate([dx, dy, dz])

            self.viewport.set_preview(m, "new_body")
            if not drag_state["dragging"]:
                update_handle()

        def on_gizmo_drag(axis: str, delta: float):
            if not drag_state["dragging"]:
                drag_state["dragging"] = True
                spn_map = {
                    "X": dlg.spn_dx, "Y": dlg.spn_dy, "Z": dlg.spn_dz,
                    "RX": dlg.spn_rx, "RY": dlg.spn_ry, "RZ": dlg.spn_rz
                }
                spn = spn_map.get(axis, dlg.spn_dx)
                drag_state["start_axis_val"] = spn.value()

            is_rot = axis in ("RX", "RY", "RZ")
            new_val = drag_state["start_axis_val"] + delta
            if is_rot:
                # Snap to 5° increments if Shift is held or by default 5 deg clean steps
                step = 5.0 if abs(delta) > 5.0 else 1.0
                new_val = round(new_val / step) * step
            else:
                new_val = round(new_val, 2)
            dlg.set_active_axis_value(new_val)

        def on_drag_finished():
            drag_state["dragging"] = False
            update_handle()

        def on_axis_changed(axis: str):
            drag_state["dragging"] = False
            if self.viewport.move_gizmo:
                self.viewport.move_gizmo["active_axis"] = axis
                self.viewport.update()

        def on_gizmo_axis_selected(axis: str):
            dlg.set_active_axis(axis)

        def on_face_picked(plane):
            face = getattr(plane, "face", None)
            if face is not None and hasattr(face, "body_id"):
                dlg.select_body(face.body_id)
                if dlg.btn_lay.isChecked() and face.body_id in self.doc.bodies:
                    from omacad.model.geometry import lay_on_ground_values
                    about_centre = dlg.cmb_pivot.currentIndex() == 0
                    vals = lay_on_ground_values(face.normal, face.origin, get_body_center(self.doc.bodies[face.body_id]), about_centre)
                    for spn, v in zip((dlg.spn_dx, dlg.spn_dy, dlg.spn_dz, dlg.spn_rx, dlg.spn_ry, dlg.spn_rz), vals):
                        spn.setValue(round(v, 4))
                    dlg.btn_lay.setChecked(False)
                    self.status_label.setText("Face laid on the ground. Adjust the numbers or press OK.")

        def cleanup():
            try:
                self.viewport.move_body_picked.disconnect(on_face_picked)
            except Exception:
                pass
            try:
                self.viewport.body_clicked.disconnect(dlg.select_body)
            except Exception:
                pass
            try:
                self.viewport.move_gizmo_dragged.disconnect(on_gizmo_drag)
            except Exception:
                pass
            try:
                self.viewport.move_gizmo_finished.disconnect(on_drag_finished)
            except Exception:
                pass
            try:
                self.viewport.move_gizmo_axis_selected.disconnect(on_gizmo_axis_selected)
            except Exception:
                pass
            self.viewport.end_plane_pick()
            self.viewport.clear_move_gizmo()
            self.viewport.set_preview(None)
            if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True
                current_hidden_id[0] = None
            self.inspector.undock_tool()

        def on_finished(result):
            bid, dx, dy, dz, rx, ry, rz, pivot, exprs = dlg.get_values()
            cleanup()
            if result and bid and bid in self.doc.bodies:
                feat = self.doc.move_body(bid, dx, dy, dz, rx, ry, rz, pivot=pivot, exprs=exprs)
                if feat:
                    b_name = self.doc.bodies[bid].name if bid in self.doc.bodies else bid
                    self.status_label.setText(f"Moved {b_name}: dx={dx:g}, dy={dy:g}, dz={dz:g} mm, rx={rx:g}°, ry={ry:g}°, rz={rz:g}°.")
                    self.viewport.update()
            else:
                self.status_label.setText("Move cancelled.")
                self.viewport.update()

        dlg.changed.connect(refresh_preview)
        dlg.axis_changed.connect(on_axis_changed)
        dlg.finished.connect(on_finished)
        self.viewport.move_gizmo_dragged.connect(on_gizmo_drag)
        self.viewport.move_gizmo_finished.connect(on_drag_finished)
        self.viewport.move_gizmo_axis_selected.connect(on_gizmo_axis_selected)
        self.viewport.move_body_picked.connect(on_face_picked)
        self.viewport.body_clicked.connect(dlg.select_body)
        self.viewport.begin_plane_pick("move_body")
        self.status_label.setText("Move / Rotate: drag the 3D arrows to move, or drag the circular rings to rotate (Fusion 360 style).")

        refresh_preview()
        dlg.show()

    def prompt_insert_canvas(self, preselected_plane_id: str = ""):
        """Insert reference image onto a plane, edit/crop/calibrate with tape measure."""
        dlg = CanvasEditorDialog(self.doc, self, preselected_plane_id=preselected_plane_id or None)
        if dlg.exec():
            data = dlg.get_canvas_data()
            if data and data.get("image_data"):
                cid = self.doc.add_canvas(**data)
                self.viewport.update()
                self.status_label.setText(f"Inserted image reference: {data['name']} ({data['width_mm']:.1f} × {data['height_mm']:.1f} mm).")

    def prompt_edit_canvas(self, cid: str):
        """Edit / calibrate an existing canvas reference image."""
        c = self.doc.canvases.get(cid)
        if not c:
            return
        dlg = CanvasEditorDialog(self.doc, self, existing_canvas_id=cid)
        if dlg.exec():
            data = dlg.get_canvas_data()
            if data:
                # Invalidate cached texture in viewport if image data or dimensions changed
                if hasattr(self.viewport, "_canvas_textures") and cid in self.viewport._canvas_textures:
                    del self.viewport._canvas_textures[cid]
                self.doc.update_canvas(cid, **data)
                self.viewport.update()
                self.status_label.setText(f"Updated image reference: {data.get('name', c.get('name'))}.")

