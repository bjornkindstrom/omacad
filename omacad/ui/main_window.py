"""
Omacad - Main CAD Application Window
Connects Ribbon, Viewport, Browser, Timeline, and Menu Bar.
"""

from pathlib import Path
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget,
    QFileDialog, QMessageBox, QLabel, QMenu
)
from PySide6.QtGui import QAction, QKeySequence, QIcon

from omacad.model.document import Document
from omacad.model.timeline import CombineFeature
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.ui.ribbon import Ribbon
from omacad.ui.viewport import Viewport3D
from omacad.ui.browser import BrowserTree
from omacad.ui.timeline_bar import TimelineBar
from omacad.model.timeline import ExtrudeFeature
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog,
    SphereDialog, CombineDialog
)
from omacad.io.exporter import Exporter


class MainWindow(QMainWindow):
    """Main Fusion 360 style window for Omacad."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Omacad - Native CAD for Omarchy")
        self.resize(1340, 860)

        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Apply Fusion 360 Dark Theme
        style(self, theme._BASE_CSS)
        self.apply_theme_font()
        self.theme_watcher = theme.ThemeWatcher(self)
        self.theme_watcher.changed.connect(self.on_theme_changed)

        # Active Document
        self.doc = Document("Omacad - Untitled")
        self.current_path: Optional[str] = None

        # Central Layout Container
        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Top Ribbon
        self.ribbon = Ribbon(self.doc, self)
        central_layout.addWidget(self.ribbon)

        # 2. 3D Viewport
        self.viewport = Viewport3D(self.doc, self)
        # right-hand panel: every tool dialog docks here so it never covers the model
        from omacad.ui import dialogs as _dialogs
        view_row = QHBoxLayout()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(0)
        view_row.addWidget(self.viewport, stretch=1)
        self.side_panel = QWidget()
        self.side_panel.setFixedWidth(350)
        self.side_layout = QVBoxLayout(self.side_panel)
        self.side_layout.setContentsMargins(8, 8, 8, 8)
        self.side_layout.addStretch()
        self.side_panel.hide()
        view_row.addWidget(self.side_panel)
        central_layout.addLayout(view_row, stretch=1)
        _dialogs.SIDE_HOST = self

        # 3. Bottom Timeline
        self.timeline_bar = TimelineBar(self.doc, self)
        central_layout.addWidget(self.timeline_bar)

        self.setCentralWidget(central_container)

        # 4. Left Browser Panel (DockWidget)
        self.browser_dock = QDockWidget("Browser", self)
        self.browser_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.browser_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.browser = BrowserTree(self.doc, self)
        self.browser_dock.setWidget(self.browser)
        self.browser_dock.setMinimumWidth(230)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser_dock)

        # 5. Status Bar
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label)
        self.statusBar().addPermanentWidget(QLabel("Units: mm  |  Omarchy Wayland Native"))

        # Setup Menus & Actions
        self.setup_menu_bar()

        # Connect Ribbon Signals
        self.ribbon.create_sketch_clicked.connect(self.prompt_create_sketch)
        self.viewport.plane_picked.connect(self.on_plane_picked)
        self.viewport.face_extrude_requested.connect(self.on_extrude_face)
        self.ribbon.constraint_clicked.connect(self.viewport.apply_constraint)
        self.viewport.status_message.connect(self.status_label.setText)
        self.viewport.plane_pick_cancelled.connect(self.on_plane_pick_cancelled)
        self.ribbon.extrude_clicked.connect(self.prompt_extrude)
        self.ribbon.pattern_clicked.connect(self.prompt_pattern)
        self.ribbon.offset_plane_clicked.connect(self.prompt_offset_plane)
        self.ribbon.section_clicked.connect(self.prompt_section)
        self.ribbon.fillet_clicked.connect(lambda: self.prompt_round_edges("fillet"))
        self.ribbon.chamfer_clicked.connect(lambda: self.prompt_round_edges("chamfer"))
        self.ribbon.parameters_clicked.connect(self.on_change_parameters)
        self.ribbon.revolve_clicked.connect(self.prompt_revolve)
        self.ribbon.box_clicked.connect(self.prompt_box)
        self.ribbon.cylinder_clicked.connect(self.prompt_cylinder)
        self.ribbon.sphere_clicked.connect(self.prompt_sphere)
        self.ribbon.combine_clicked.connect(self.prompt_combine)
        self.ribbon.delete_clicked.connect(self.on_delete_selected)
        self.ribbon.inspect_clicked.connect(self.on_inspect)
        self.ribbon.sketch_tool_selected.connect(self.on_sketch_tool_selected)
        self.viewport.sketch_tool_changed.connect(self.sync_sketch_tool_from_viewport)
        self.ribbon.toggle_construction_clicked.connect(self.viewport.toggle_construction_mode)
        self.viewport.construction_mode_changed.connect(self.ribbon.btn_construct.setChecked)
        self.ribbon.finish_sketch_clicked.connect(self.on_finish_sketch)
        self.viewport.finish_sketch_requested.connect(self.on_finish_sketch)

        # Connect Browser Signals
        self.browser.start_sketch_on_plane.connect(self.start_sketch_on_plane)
        self.browser.edit_sketch_requested.connect(self.on_edit_sketch)
        self.browser.start_sketch_on_cplane.connect(self.start_sketch_on_cplane)
        self.viewport.offset_base_picked.connect(self.on_offset_base_picked)
        self.viewport.section_base_picked.connect(self.on_section_base_picked)
        self.browser.edit_section_requested.connect(self.edit_section)
        self.timeline_bar.edit_sketch_requested.connect(self.on_edit_sketch)
        self.browser.export_body_stl.connect(self.export_single_body_stl)

    def setup_menu_bar(self):
        menubar = self.menuBar()

        # File Menu
        menu_file = menubar.addMenu("File")

        act_new = QAction("New Design", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.on_file_new)
        menu_file.addAction(act_new)

        act_open = QAction("Open Project (.omacad)...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.on_file_open)
        menu_file.addAction(act_open)

        act_save = QAction("Save Project (.omacad)", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.on_file_save)
        menu_file.addAction(act_save)

        act_save_as = QAction("Save Project As...", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self.on_file_save_as)
        menu_file.addAction(act_save_as)

        menu_file.addSeparator()

        act_export_stl = QAction("Export All as STL...", self)
        act_export_stl.triggered.connect(self.on_export_all_stl)
        menu_file.addAction(act_export_stl)

        menu_file.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Edit Menu
        menu_edit = menubar.addMenu("Edit")
        act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self.on_undo)
        menu_edit.addAction(act_undo)
        act_redo = QAction("Redo", self)
        act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        act_redo.triggered.connect(self.on_redo)
        menu_edit.addAction(act_redo)

        # Create Menu
        menu_create = menubar.addMenu("Create")
        menu_create.addAction("Create Sketch", self.prompt_create_sketch)
        act_extrude = QAction("Extrude  (E)", self)
        act_extrude.setShortcuts([QKeySequence("E"), QKeySequence("Ctrl+E")])
        act_extrude.triggered.connect(self.prompt_extrude)
        menu_create.addAction(act_extrude)
        menu_create.addAction("Offset Plane…", self.prompt_offset_plane)
        menu_create.addSeparator()
        menu_create.addAction("Box", self.prompt_box)
        menu_create.addAction("Cylinder", self.prompt_cylinder)
        menu_create.addAction("Sphere", self.prompt_sphere)

        # Modify Menu
        menu_modify = menubar.addMenu("Modify")
        act_fillet = QAction("Fillet…", self)
        act_fillet.triggered.connect(lambda: self.prompt_round_edges("fillet"))
        menu_modify.addAction(act_fillet)
        act_chamfer = QAction("Chamfer…", self)
        act_chamfer.triggered.connect(lambda: self.prompt_round_edges("chamfer"))
        menu_modify.addAction(act_chamfer)
        act_pattern = QAction("Pattern / Mirror…", self)
        act_pattern.triggered.connect(self.prompt_pattern)
        menu_modify.addAction(act_pattern)
        act_params = QAction("Change Parameters…", self)
        act_params.setShortcut(QKeySequence("Ctrl+P"))
        act_params.triggered.connect(self.on_change_parameters)
        menu_modify.addAction(act_params)
        menu_modify.addAction("Combine", self.prompt_combine)
        menu_modify.addAction("Delete Selected", self.on_delete_selected, QKeySequence.StandardKey.Delete)

        # View Menu
        menu_view = menubar.addMenu("View")
        menu_view.addAction("Fit View (Home)", self.viewport.zoom_fit, QKeySequence("F"))
        menu_view.addAction("Section View…", self.prompt_section)
        menu_view.addAction("Toggle Ground Grid", self.toggle_grid)
        menu_view.addAction("Toggle Feature Edges", self.toggle_edges)

        # Help Menu
        menu_help = menubar.addMenu("Help")
        menu_help.addAction("About Omacad", self.on_about)

        # Icons for the menu entries (drawn from emoji at a size the menu font can't give)
        icons = {
            "New Design": "📄", "Open Project": "📂", "Save Project As": "💾", "Save Project": "💾", "Export All as STL": "📤",
            "Exit": "🚪", "Undo": "↩️", "Redo": "↪️", "Create Sketch": "✏️", "Extrude": "⬆️",
            "Box": "📦", "Cylinder": "🥫", "Sphere": "⚽", "Combine": "🔗", "Change Parameters": "🧮", "Pattern": "🔁", "Fillet": "🔘", "Chamfer": "◢", "Delete Selected": "🗑️",
            "Fit View": "🔲", "Section View": "✂️", "Toggle Ground Grid": "📐", "Toggle Feature Edges": "🔳", "About": "ℹ️",
        }
        for menu in menubar.findChildren(QMenu):
            for act in menu.actions():
                for label, emoji in icons.items():
                    if act.text().startswith(label):
                        act.setIcon(theme.emoji_icon(emoji, 24))
                        break

    # ------------------ Action Handlers ------------------

    def apply_theme_font(self):
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None and not isinstance(app.style(), theme.BigIconStyle):
            app.setStyle(theme.BigIconStyle("Fusion"))  # larger icons in menus, trees and buttons
        if app is not None:
            f = QFont(theme.font_family())
            f.setPixelSize(13)
            app.setFont(f)

    def on_theme_changed(self):
        """The Omarchy theme was switched: stylesheets were already re-applied by theme.refresh()."""
        self.apply_theme_font()
        self.viewport.update()
        self.status_label.setText("Omarchy theme updated.")

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
        dlg = RoundEdgesDialog(self.viewport, kind, embedded=True)   # a small panel inside the view, draggable
        dlg.place(self.viewport.size())
        self._round_dlg = dlg
        self.viewport.begin_edge_pick()
        self.status_label.setText("Fillet/Chamfer: click edges (double-click selects the whole loop around a face). "
                                  "Circles, holes and inside corners work too. Esc cancels.")

        def preview():
            from omacad.model.kernel import CadKernel
            edges = self.viewport.selected_edges
            dlg.set_count(len(edges))
            solid, problem = None, None
            for e in edges:
                try:
                    tool = CadKernel.round_tool(e, dlg.spn_size.value(), dlg.kind())
                    solid = tool if solid is None else solid + tool
                except Exception as ex:
                    problem = str(ex) or "This edge can't be rounded with that size."
            if problem:
                self.status_label.setText(f"Fillet/Chamfer: {problem}")
            self.viewport.set_preview(solid, "new_body")

        def on_cancel_pick():
            dlg.reject()

        def on_finished(result):
            self.viewport.edges_selection_changed.disconnect(preview)
            self.viewport.edge_pick_cancelled.disconnect(on_cancel_pick)
            edges = [e.ref() for e in self.viewport.selected_edges]
            self._round_dlg = None
            dlg.deleteLater()
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
        dlg.changed.connect(preview)
        dlg.finished.connect(on_finished)
        dlg.show()

    def dock(self, dlg):
        """Put a tool dialog into the right-hand panel (it leaves again when it finishes)."""
        if dlg.parent() is self.side_panel:
            return
        dlg._embedded = False
        dlg.setParent(self.side_panel)
        dlg.setWindowFlags(Qt.WindowType.Widget)
        dlg.setMinimumWidth(0)
        dlg.setFixedWidth(334)
        dlg.unsetCursor()
        self.side_layout.insertWidget(self.side_layout.count() - 1, dlg)
        self.side_panel.show()
        dlg.show()

        def undock(*_):
            self.side_layout.removeWidget(dlg)
            dlg.hide()
            if self.side_layout.count() <= 1:
                self.side_panel.hide()
        dlg.finished.connect(undock)

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

        dlg.changed.connect(preview)
        preview()
        ok = dlg.exec()
        self.viewport.set_preview(None)
        if ok and dlg.source_ids():
            feat = self.doc.add_pattern(dlg.source_ids(), dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())
            self.status_label.setText(f"{feat.name}: {feat.copies} copies.")

    def on_change_parameters(self):
        from omacad.ui.parameters_dialog import ParametersDialog
        ParametersDialog(self.doc, self).exec()
        self.viewport.update()

    def on_undo(self):
        name = self.doc.undo()
        self.status_label.setText(f"Undo ({name})." if name else "Nothing to undo.")

    def on_redo(self):
        name = self.doc.redo()
        self.status_label.setText(f"Redo ({name})." if name else "Nothing to redo.")

    def prompt_create_sketch(self):
        """Pick the sketch plane directly in the viewport (origin plane or planar face)."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick()
        self.status_label.setText("Create Sketch: click an origin plane or a flat face (Esc to cancel).")

    def on_plane_picked(self, plane):
        sketch = self.doc.start_sketch_on_plane(plane)
        self.viewport.align_to_plane(plane)
        where = f"{plane.name} plane" if plane.name != "FACE" else "face"
        self.status_label.setText(f"Active Sketch: {sketch.name} on {where}. Select a tool (Line, Rect, Circle) to draw.")

    def prompt_offset_plane(self):
        """Offset Plane in two clicks: 1) which of X/Y/Z-planes the new plane is parallel to, 2) the surface it touches."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick("offset_base")
        self.status_label.setText("Offset Plane (1/2): click the XY, XZ or YZ plane the new plane should be parallel to (Esc cancels).")

    def on_offset_base_picked(self, base):
        from omacad.model.sketch import SketchPlane
        n = np.asarray(base.normal, dtype=float)
        o = np.asarray(base.origin, dtype=float)
        self.viewport.begin_plane_pick("offset_surface")
        self.status_label.setText(f"Offset Plane (2/2): point at any face of a body (flat or curved) and click: "
                                  f"a plane parallel to {base.name} is created touching it (Esc cancels).")

        def plane_at(hit):
            rel = float((hit["point"] - o) @ n)
            proj = (hit["patch"] - o) @ n
            dist = float(proj.max() if rel >= 0 else proj.min())
            if abs(rel) < 1e-6:
                dist = float(proj[np.abs(proj).argmax()])
            return dist

        def on_hover(hit):
            if hit is None:
                self.viewport.set_preview_plane(None)
            else:
                self.viewport.set_preview_plane(SketchPlane.from_face(n, o + n * plane_at(hit), name="PLANE"))

        def done(*_):
            for sig, fn in ((self.viewport.surface_hover, on_hover), (self.viewport.surface_picked, on_picked),
                            (self.viewport.plane_pick_cancelled, done)):
                try:
                    sig.disconnect(fn)
                except (RuntimeError, TypeError):
                    pass
            self.viewport.set_preview_plane(None)

        def on_picked(hit):
            dist = plane_at(hit)
            done()
            pid = self.doc.add_construction_plane(base, dist)
            self.status_label.setText(f"{self.doc.construction_planes[pid]['name']} created at {dist:.3f} mm from {base.name}. "
                                      "Right-click it in the browser to sketch on it.")

        self.viewport.surface_hover.connect(on_hover)
        self.viewport.surface_picked.connect(on_picked)
        self.viewport.plane_pick_cancelled.connect(done)

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

    def start_sketch_on_cplane(self, pid: str):
        if pid in self.doc.construction_planes:
            self.on_plane_picked(self.doc.construction_plane(pid))

    def on_plane_pick_cancelled(self):
        self.status_label.setText("Face selection cancelled." if getattr(self, "_extrude_dlg", None) else "Create Sketch cancelled.")

    def start_sketch_on_plane(self, plane_name: str):
        sketch = self.doc.start_sketch(plane_name)
        # Smoothly orient camera facing normal to sketch plane
        if plane_name.upper() == "XY":
            self.viewport.azimuth = 0.0
            self.viewport.elevation = 89.9
        elif plane_name.upper() == "XZ":
            self.viewport.azimuth = 0.0
            self.viewport.elevation = 0.0
        elif plane_name.upper() == "YZ":
            self.viewport.azimuth = 90.0
            self.viewport.elevation = 0.0
        self.viewport.update()
        self.status_label.setText(f"Active Sketch: {sketch.name} on {plane_name} plane. Select a tool (Line, Rect, Circle) to draw.")

    def on_edit_sketch(self, sketch_id: str):
        sketch = self.doc.edit_sketch(sketch_id)
        if sketch:
            self.viewport.align_to_plane(sketch.plane)
            self.viewport.update()
            self.status_label.setText(f"Editing {sketch.name}. Double-click dimension badges to edit dimensions.")

    def on_sketch_tool_selected(self, tool_name: str):
        self.viewport.set_sketch_tool(tool_name)
        self.status_label.setText(f"Sketch Tool: {tool_name}. Click on grid plane to place points.")

    def sync_sketch_tool_from_viewport(self, tool_name: str):
        self.ribbon.btn_line.setChecked(tool_name == "LINE")
        self.ribbon.btn_rect.setChecked(tool_name == "RECT")
        self.ribbon.btn_crect.setChecked(tool_name == "CENTER_RECT")
        self.ribbon.btn_circle.setChecked(tool_name == "CIRCLE")
        self.ribbon.btn_arc.setChecked(tool_name == "ARC")
        self.ribbon.btn_slot.setChecked(tool_name == "SLOT")
        self.ribbon.btn_dim.setChecked(tool_name == "DIMENSION")
        self.ribbon.btn_move.setChecked(tool_name == "MOVE")
        if tool_name != "NONE":
            self.status_label.setText(f"Sketch Tool: {tool_name}. Click on grid plane to place points.")
        else:
            self.status_label.setText("Ready.")

    def on_finish_sketch(self):
        self.viewport.set_sketch_tool("NONE")
        sketch = self.doc.finish_sketch()
        if sketch:
            self.status_label.setText(f"Finished {sketch.name} ({len(sketch.profiles)} closed profiles found).")
        self.viewport.update()

    def on_extrude_face(self, face):
        """Right-click > Extrude this Face: the face outline becomes the profile; default is 5 mm into the body."""
        sk, idx = self.doc.face_to_sketch(face)
        if idx is None:
            self.status_label.setText("That face has no closed outline to extrude.")
            return
        self.doc.selected_profile = (sk.sketch_id, idx)
        dlg = getattr(self, "_extrude_dlg", None)
        if dlg is not None:
            dlg.reload_profiles()
            dlg.select_profile((sk.sketch_id, idx))
            dlg.set_distance(-5.0)
            dlg.raise_()
            return
        self.prompt_extrude(default_distance=-5.0)

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
            self.viewport.set_extrude_handle(origin, sk.plane.normal, tip)

        def on_handle_dragged(t):
            direction = dlg.get_direction()[0]
            value = abs(t) * 2.0 if direction == "symmetric" else (max(t, 0.1) if direction == "two_sides" else t)
            dlg.spn_dist.setValue(value)

        def extras(s_id):
            return [i for (sid, i) in self.doc.selected_extra if sid == s_id]

        def refresh_preview():
            s_id, p_idx, dist, op = dlg.get_values()
            direction, dist2 = dlg.get_direction()
            solid = None
            if s_id is not None:
                feat = ExtrudeFeature("preview", "preview", s_id, p_idx, dist, op, direction, dist2, extra_profiles=extras(s_id))
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
                    self.doc.extrude_profile(s_id, p_idx, dist, op, direction=direction, distance2=dist2,
                                             extra_profiles=extras(s_id))
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

    def prompt_revolve(self):
        QMessageBox.information(self, "Revolve", "Revolve dialog will be activated in the next step!")

    def prompt_box(self):
        dlg = BoxDialog(self)
        if dlg.exec():
            l, w, h, center = dlg.get_values()
            body = self.doc.add_box(l, w, h, center)
            self.doc.timeline.features[-1].exprs = dlg.get_expressions()
            self.viewport.zoom_fit()
            self.status_label.setText(f"Created {body.name} ({l}x{w}x{h} mm).")

    def prompt_cylinder(self):
        dlg = CylinderDialog(self)
        if dlg.exec():
            r, h, center = dlg.get_values()
            body = self.doc.add_cylinder(r, h, center)
            self.doc.timeline.features[-1].exprs = dlg.get_expressions()
            self.viewport.zoom_fit()
            self.status_label.setText(f"Created {body.name} (R={r}, H={h} mm).")

    def prompt_sphere(self):
        dlg = SphereDialog(self)
        if dlg.exec():
            r = dlg.get_values()
            body = self.doc.add_sphere(r)
            self.doc.timeline.features[-1].exprs = dlg.get_expressions()
            self.viewport.zoom_fit()
            self.status_label.setText(f"Created {body.name} (R={r} mm).")

    def prompt_combine(self):
        if len(self.doc.bodies) < 2:
            QMessageBox.information(
                self, "Combine", "You need at least 2 bodies in the document to perform a boolean combine!"
            )
            return

        dlg = CombineDialog(self.doc, self)
        if dlg.exec():
            target_id, tool_id, op = dlg.get_values()
            if target_id and tool_id:
                feat_id = f"combine_{len(self.doc.timeline.features) + 1}"
                feat = CombineFeature(feat_id, f"Combine ({op})", target_id, tool_id, op)
                self.doc.timeline.add_feature(feat)
                feat.execute(self.doc)
                self.doc.notify_changed()
                self.status_label.setText(f"Combined bodies with operation: {op}.")

    def on_delete_selected(self):
        # In sketch mode Delete removes the selected sketch elements
        if self.doc.active_sketch and self.viewport.selected_entities:
            n = self.viewport.delete_selected_entities()
            self.status_label.setText(f"Deleted {n} sketch element{'s' if n != 1 else ''}.")
            return
        for b_id in list(self.doc.selected_body_ids):
            self.doc.delete_body(b_id)
        self.status_label.setText("Deleted selected body.")

    def on_inspect(self):
        num_bodies = len(self.doc.bodies)
        num_sketches = len(self.doc.sketches)
        num_features = len(self.doc.timeline.features)
        QMessageBox.information(
            self, "Document Statistics",
            f"Bodies: {num_bodies}\nSketches: {num_sketches}\nParametric Features: {num_features}\nUnits: mm"
        )

    def toggle_grid(self):
        self.viewport.show_grid = not self.viewport.show_grid
        self.viewport.update()

    def toggle_edges(self):
        self.viewport.show_edges = not self.viewport.show_edges
        self.viewport.update()

    def attach_document(self, doc: Document, path: Optional[str] = None) -> None:
        """Make `doc` the document every panel shows (used by New and Open)."""
        self.doc = doc
        self.current_path = path
        self.viewport.set_document(doc)
        for panel, refresh in ((self.browser, "refresh_tree"), (self.timeline_bar, "refresh_timeline"),
                               (self.ribbon, "sync_active_tab")):
            panel.doc = doc
            doc.add_change_listener(getattr(panel, refresh))
        self.update_window_title()
        doc.notify_changed()

    def update_window_title(self):
        name = Path(self.current_path).name if getattr(self, "current_path", None) else "Untitled"
        self.setWindowTitle(f"{name} - Omacad")

    def on_file_new(self):
        self.attach_document(Document("Omacad - Untitled"))
        self.status_label.setText("Created new design.")

    def on_file_save(self):
        """Ctrl+S: save to the current file, or ask for a name the first time."""
        if getattr(self, "current_path", None):
            self._save_to(self.current_path)
        else:
            self.on_file_save_as()

    def on_file_save_as(self):
        start = self.current_path if getattr(self, "current_path", None) else f"{self.doc.name.replace('Omacad - ', '')}.omacad"
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project As", start, "Omacad (*.omacad)")
        if filepath:
            if not filepath.endswith(".omacad"):
                filepath += ".omacad"
            self._save_to(filepath)

    def _save_to(self, filepath: str):
        if self.doc.active_sketch:
            self.on_finish_sketch()  # an unfinished sketch is not part of the history and would be lost
        try:
            self.doc.name = Path(filepath).stem
            Exporter.save_project(self.doc, filepath)
        except OSError as e:
            QMessageBox.critical(self, "Save failed", f"Could not save {filepath}:\n{e}")
            return
        self.current_path = filepath
        self.update_window_title()
        self.doc.notify_changed()
        self.status_label.setText(f"Saved {filepath}")

    def on_file_open(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Omacad (*.omacad *.om360)")
        if not filepath:
            return
        try:
            doc = Exporter.load_project(filepath)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, "Open failed", f"Could not open {filepath}:\n{e}")
            return
        self.attach_document(doc, filepath)
        self.viewport.zoom_fit()
        self.status_label.setText(f"Opened {filepath}")

    def on_export_all_stl(self):
        if not self.doc.bodies:
            QMessageBox.information(self, "Export STL", "No bodies to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export All Bodies to STL", "", "STL Files (*.stl)")
        if filepath:
            if not filepath.endswith(".stl"):
                filepath += ".stl"
            ok = Exporter.export_all_to_stl(self.doc, filepath)
            if ok:
                QMessageBox.information(self, "Export STL", f"Successfully exported STL to:\n{filepath}")
                self.status_label.setText(f"Exported STL to {filepath}")

    def export_single_body_stl(self, body_id: str):
        body = self.doc.bodies.get(body_id)
        if not body:
            return

        filepath, _ = QFileDialog.getSaveFileName(self, f"Export {body.name} to STL", f"{body.name}.stl", "STL Files (*.stl)")
        if filepath:
            ok = Exporter.export_body_to_stl(body, filepath)
            if ok:
                QMessageBox.information(self, "Export STL", f"Successfully exported {body.name} to:\n{filepath}")

    def on_about(self):
        QMessageBox.about(
            self, "About Omacad",
            "<h3>Omacad</h3>"
            "<p>A native CAD application for <b>Omarchy Linux</b>.</p>"
            "<p>Inspired by Autodesk Fusion 360, built with Python, PySide6 (Qt6), and Manifold3D.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Watertight Solid CSG Modeling (Manifold3D)</li>"
            "<li>2D Sketching & Closed Profile Extrusion</li>"
            "<li>Parametric Feature Timeline & History Replay</li>"
            "<li>Interactive 3D ViewCube & Dynamic Grid</li>"
            "<li>Native Wayland Integration on Omarchy</li>"
            "<li>Direct STL & OBJ Export for 3D Printing</li>"
            "</ul>"
        )
