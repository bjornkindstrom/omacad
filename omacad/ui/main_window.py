"""
Omacad - Main CAD Application Window
Connects Ribbon, Viewport, Browser, Timeline, and Menu Bar.
"""

from pathlib import Path
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget,
    QFileDialog, QMessageBox, QLabel, QMenu, QPushButton
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QShortcut

from omacad.model.document import Document
from omacad.model.timeline import ExtrudeFeature, CombineFeature, SplitBodyFeature, ShellFeature, MoveFeature
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.ui.ribbon import Ribbon, RECT_TOOLS
from omacad.ui.viewport import Viewport3D
from omacad.ui.browser import BrowserTree
from omacad.ui.timeline_bar import TimelineBar
from omacad.ui.side_panel import InspectorPanel
from omacad.ui.canvas_dialog import CanvasEditorDialog
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog, OffsetPlaneDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog,
    SphereDialog, CombineDialog, SplitBodyDialog, ShellDialog, MoveBodyDialog
)
from omacad.io.exporter import Exporter


class _LoggedLabel(QLabel):
    """The status line; everything shown there also goes into the log that travels with problem reports."""

    def setText(self, text):
        from omacad import applog
        applog.log("status", text)
        super().setText(text)


class MainWindow(QMainWindow):
    """Main Fusion 360 style window for Omacad."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Omacad {__import__('omacad').__version__} - Native CAD for Omarchy")
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
        self.inspector = InspectorPanel(self.doc, self)
        view_row.addWidget(self.inspector)
        self.inspector.set_palette(self.viewport.sketch_palette)
        central_layout.addLayout(view_row, stretch=1)
        _dialogs.SIDE_HOST = self
        self.doc.add_change_listener(self.inspector.refresh_info)
        self._init_undo_listener = True   # registered once the Edit menu exists (see _build_menus)

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
        self.status_label = _LoggedLabel("Ready")
        self.statusBar().addWidget(self.status_label)
        btn_report = QPushButton("🐞 Report problem (F9)")
        btn_report.setFlat(True)
        btn_report.setToolTip("Something wrong? Describe it: the AI gets a screenshot, the model and the log and fixes it")
        btn_report.clicked.connect(self.on_report_problem)
        self.statusBar().addPermanentWidget(btn_report)
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
        self.ribbon.measure_clicked.connect(self.viewport.begin_measure)
        self.ribbon.fillet_clicked.connect(lambda: self.prompt_round_edges("fillet"))
        self.ribbon.chamfer_clicked.connect(lambda: self.prompt_round_edges("chamfer"))
        self.ribbon.parameters_clicked.connect(self.on_change_parameters)
        self.ribbon.revolve_clicked.connect(self.prompt_revolve)
        self.ribbon.box_clicked.connect(self.prompt_box)
        self.ribbon.cylinder_clicked.connect(self.prompt_cylinder)
        self.ribbon.sphere_clicked.connect(self.prompt_sphere)
        self.ribbon.combine_clicked.connect(self.prompt_combine)
        self.ribbon.split_body_clicked.connect(self.prompt_split_body)
        self.ribbon.shell_clicked.connect(self.prompt_shell)
        self.ribbon.project_clicked.connect(lambda: self.viewport.project_edges())
        self.ribbon.move_clicked.connect(self.prompt_move_body)
        self.ribbon.canvas_clicked.connect(self.prompt_insert_canvas)
        self.ribbon.delete_clicked.connect(self.on_delete_selected)
        self.ribbon.inspect_clicked.connect(self.on_inspect)
        self.ribbon.settings_clicked.connect(self.on_open_settings)
        self.ribbon.sketch_tool_selected.connect(self.on_sketch_tool_selected)
        self.viewport.sketch_tool_changed.connect(self.sync_sketch_tool_from_viewport)
        self.ribbon.toggle_construction_clicked.connect(self.viewport.toggle_construction_mode)
        self.viewport.construction_mode_changed.connect(self.ribbon.btn_construct.setChecked)
        self.ribbon.finish_sketch_clicked.connect(self.on_finish_sketch)
        self.viewport.finish_sketch_requested.connect(self.on_finish_sketch)
        self.viewport.menu_command.connect(self.on_menu_command)
        self.viewport.active_tool_title = self._active_tool_title
        self.viewport.lay_face_requested.connect(self.on_lay_face_requested)
        self.viewport.lay_target_picked.connect(self.on_lay_target_picked)
        self._lay_face = None
        # Esc leaves the current function wherever the keyboard focus is (a tool panel field, the tree ...);
        # the viewport decides what that means, in the same order as when it has the focus itself
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._escape_pressed)

        # Connect Browser Signals
        self.browser.start_sketch_on_plane.connect(self.start_sketch_on_plane)
        self.browser.edit_sketch_requested.connect(self.on_edit_sketch)
        self.browser.start_sketch_on_cplane.connect(self.start_sketch_on_cplane)
        self.viewport.offset_base_picked.connect(self.on_offset_base_picked)
        self.viewport.section_base_picked.connect(self.on_section_base_picked)
        self.browser.edit_section_requested.connect(self.edit_section)
        self.timeline_bar.edit_sketch_requested.connect(self.on_edit_sketch)
        self.timeline_bar.highlight_changed.connect(
            lambda added, removed: self.viewport.set_preview(added, "join", extra=removed, extra_op="cut"))
        self.browser.export_body_stl.connect(self.export_single_body_stl)
        self.browser.export_body_step.connect(self.export_single_body_step)
        self.browser.move_body_requested.connect(self.prompt_move_body)
        self.browser.split_body_requested.connect(self.prompt_split_body)
        self.browser.shell_body_requested.connect(self.prompt_shell)
        self.browser.insert_canvas_requested.connect(self.prompt_insert_canvas)

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

        act_import_3mf = QAction("Import 3MF Model...", self)
        act_import_3mf.triggered.connect(self.on_import_3mf)
        menu_file.addAction(act_import_3mf)

        menu_file.addSeparator()

        act_export_stl = QAction("Export All as STL...", self)
        act_export_stl.triggered.connect(self.on_export_all_stl)
        menu_file.addAction(act_export_stl)

        act_export_step = QAction("Export All as STEP...", self)
        act_export_step.triggered.connect(self.on_export_all_step)
        menu_file.addAction(act_export_step)

        menu_file.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Edit Menu
        menu_edit = menubar.addMenu("Edit")
        act_undo = self.act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self.on_undo)
        menu_edit.addAction(act_undo)
        act_redo = self.act_redo = QAction("Redo", self)
        act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        act_redo.triggered.connect(self.on_redo)
        menu_edit.addAction(act_redo)
        self.doc.history_listeners.append(self._update_undo_actions)
        self._update_undo_actions()
        menu_edit.addSeparator()
        act_settings = QAction("Settings…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self.on_open_settings)
        menu_edit.addAction(act_settings)

        # Create Menu
        menu_create = menubar.addMenu("Create")
        menu_create.addAction("Create Sketch", self.prompt_create_sketch)
        act_extrude = QAction("Extrude  (E)", self)
        act_extrude.setShortcuts([QKeySequence("E"), QKeySequence("Ctrl+E")])
        act_extrude.triggered.connect(self.prompt_extrude)
        menu_create.addAction(act_extrude)
        menu_create.addAction("Offset Plane…", self.prompt_offset_plane)
        act_canvas = QAction("Insert Canvas (Image)…", self)
        act_canvas.triggered.connect(self.prompt_insert_canvas)
        menu_create.addAction(act_canvas)
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
        act_shell = QAction("Shell…", self)
        act_shell.triggered.connect(self.prompt_shell)
        menu_modify.addAction(act_shell)
        act_pattern = QAction("Pattern / Mirror…", self)
        act_pattern.triggered.connect(self.prompt_pattern)
        menu_modify.addAction(act_pattern)
        act_params = QAction("Change Parameters…", self)
        act_params.setShortcut(QKeySequence("Ctrl+P"))
        act_params.triggered.connect(self.on_change_parameters)
        menu_modify.addAction(act_params)
        menu_modify.addAction("Combine", self.prompt_combine)
        act_split = QAction("Split Body…", self)
        act_split.triggered.connect(self.prompt_split_body)
        menu_modify.addAction(act_split)
        act_move = QAction("Move Body… (M)", self)
        act_move.setShortcut(QKeySequence("M"))
        act_move.triggered.connect(self.prompt_move_body)
        menu_modify.addAction(act_move)
        menu_modify.addAction("Delete Selected", self.on_delete_selected, QKeySequence.StandardKey.Delete)

        # View Menu
        menu_view = menubar.addMenu("View")
        menu_view.addAction("Fit View (Home)", self.viewport.zoom_fit, QKeySequence("F"))
        menu_view.addAction("Measure", self.viewport.begin_measure, QKeySequence("I"))
        menu_view.addAction("Section View…", self.prompt_section)
        menu_view.addAction("Toggle Ground Grid", self.toggle_grid)
        menu_view.addAction("Toggle Feature Edges", self.toggle_edges)

        # Help Menu
        menu_help = menubar.addMenu("Help")
        act_report = QAction("Report problem…", self)
        act_report.setShortcut(QKeySequence("F9"))
        act_report.setToolTip("Describe what is wrong; the AI gets a screenshot, the model and the log, and fixes it")
        act_report.triggered.connect(self.on_report_problem)
        menu_help.addAction(act_report)
        menu_help.addAction("About Omacad", self.on_about)

        # Icons for the menu entries (drawn from emoji at a size the menu font can't give)
        icons = {
            "New Design": "📄", "Open Project": "📂", "Save Project As": "💾", "Save Project": "💾", "Export All as STL": "📤",
            "Exit": "🚪", "Undo": "↩️", "Redo": "↪️", "Create Sketch": "✏️", "Extrude": "⬆️", "Insert Canvas": "🖼️",
            "Box": "📦", "Cylinder": "🥫", "Sphere": "⚽", "Combine": "🔗", "Split Body": "🪚", "Shell": "🐚",
            "Change Parameters": "🧮", "Pattern": "🔁", "Fillet": "🔘", "Chamfer": "◢", "Delete Selected": "🗑️",
            "Fit View": "🔲", "Section View": "✂️", "Measure": "📏", "Toggle Ground Grid": "📐", "Toggle Feature Edges": "🔳", "About": "ℹ️",
            "Settings": "⚙️",
        }
        for menu in menubar.findChildren(QMenu):
            for act in menu.actions():
                for label, emoji in icons.items():
                    if act.text().startswith(label):
                        act.setIcon(theme.emoji_icon(emoji, 24))
                        break

    def on_open_settings(self):
        from omacad.ui.settings_dialog import SettingsDialog
        from omacad.ui.settings import get_settings
        before = get_settings().get("curve_segments")
        dlg = SettingsDialog(self)
        dlg.exec()
        if get_settings().get("curve_segments") != before:
            self.rebuild_for_curve_quality()

    def rebuild_for_curve_quality(self):
        """Round shapes are cut into pieces when sketches and steps are built, so a new smoothness needs a rebuild."""
        from PySide6.QtWidgets import QApplication
        self.status_label.setText("Rebuilding with the new curve smoothness…")
        QApplication.processEvents()
        for sk in self.doc.sketches.values():
            sk.solve_profiles()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.viewport.update()
        self.status_label.setText("Rebuilt with the new curve smoothness.")

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
        dlg = RoundEdgesDialog(self.viewport, kind, embedded=True)
        self.dock(dlg)
        self._round_dlg = dlg
        self.viewport.begin_edge_pick()
        self.status_label.setText("Fillet/Chamfer: click edges (double-click = loop, Shift+double-click = loop on the other face, X or Alt = see-through, Ctrl+click = remove, Backspace = undo last, Ctrl+Backspace = clear). Esc cancels.")

        def update_arrow():
            edges = self.viewport.selected_edges
            if edges:
                e0 = edges[0]
                if hasattr(e0, "p0") and hasattr(e0, "p1"):
                    mid = (np.asarray(e0.p0) + np.asarray(e0.p1)) * 0.5
                    d1 = getattr(e0, "d1", None)
                    d2 = getattr(e0, "d2", None)
                    if d1 is not None and d2 is not None:
                        axis = np.asarray(d1) + np.asarray(d2)
                        n_axis = np.linalg.norm(axis)
                        axis = axis / n_axis if n_axis > 1e-6 else np.array([0.0, 0.0, 1.0])
                    else:
                        axis = np.array([0.0, 0.0, 1.0])
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

    def dock(self, dlg):
        """Put a tool dialog into the right-hand inspector panel."""
        self.inspector.dock_tool(dlg)

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
        self.viewport.pick_step_mode = True
        self.viewport.step_point_clicked.connect(on_step_clicked)
        self.status_label.setText("Pattern / Mirror: click the thing you want to copy in the 3D view, or tick steps in the list.")
        preview()
        ok = dlg.exec()
        self.viewport.pick_step_mode = False
        self.viewport.step_point_clicked.disconnect(on_step_clicked)
        self.viewport.set_preview(None)
        if ok and dlg.source_ids():
            feat = self.doc.add_pattern(dlg.source_ids(), dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())
            self.status_label.setText(f"{feat.name}: {feat.copies} copies.")

    def on_change_parameters(self):
        from omacad.ui.parameters_dialog import ParametersDialog
        ParametersDialog(self.doc, self).exec()
        self.viewport.update()

    def _busy_reason(self):
        """Why undo/redo must wait: a tool panel is open or something is being dragged."""
        if self.inspector.current_tool_dlg is not None or any(getattr(self, a, None) is not None for a in ("_extrude_dlg", "_revolve_dlg", "_round_dlg")):
            return "Finish or cancel the open tool first (Esc)."
        if self.viewport.is_busy():
            return "Finish what you are doing first (Esc)."
        return None

    def _after_history_change(self):
        self.viewport.set_preview(None)
        self.viewport.clear_extrude_handle()
        self.viewport.update()
        self._update_undo_actions()

    def _update_undo_actions(self):
        u, r = self.doc.undo_label(), self.doc.redo_label()
        self.act_undo.setText(f"Undo {u}" if u else "Undo")
        self.act_undo.setEnabled(u is not None)
        self.act_redo.setText(f"Redo {r}" if r else "Redo")
        self.act_redo.setEnabled(r is not None)

    def on_undo(self):
        busy = self._busy_reason()
        if busy:
            self.status_label.setText(busy)
            return
        name = self.doc.undo()
        self._after_history_change()
        self.status_label.setText(f"Undo: {name}." if name else "Nothing to undo.")

    def _escape_pressed(self):
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        self.viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

    def _active_tool_title(self):
        dlg = self.inspector.current_tool_dlg
        return dlg.windowTitle() if dlg is not None else None

    def on_lay_face_requested(self, face, mode: str):
        if mode == "ground":
            self.doc.lay_face_on(face.body_id, face.normal, face.origin, (0, 0, 0), (0, 0, 1))
            self.viewport.update()
            self.status_label.setText("Laid the face on the ground. Undo (Ctrl+Z) turns it back.")
        else:
            self._lay_face = face
            self.viewport.begin_plane_pick("lay_target")
            self.status_label.setText("Lay flat: click the face or plane this face should rest on (Esc cancels).")

    def on_lay_target_picked(self, plane):
        face, self._lay_face = self._lay_face, None
        if face is None or face.body_id not in self.doc.bodies:
            return
        self.doc.lay_face_on(face.body_id, face.normal, face.origin, plane.origin, plane.normal)
        self.viewport.update()
        self.status_label.setText("Laid the face on the chosen plane.")

    def on_menu_command(self, cmd: str):
        """Entries of the viewport's right-click menus that need the main window."""
        if cmd in ("tool_ok", "tool_cancel"):
            dlg = self.inspector.current_tool_dlg
            if dlg is not None:
                dlg.accept() if cmd == "tool_ok" else dlg.reject()
        elif cmd == "extrude":
            self.prompt_extrude()
        elif cmd == "revolve":
            self.prompt_revolve()
        elif cmd == "undo":
            self.on_undo()
        elif cmd == "redo":
            self.on_redo()
        elif cmd.startswith("sketch:"):
            self.start_sketch_on_plane(cmd.split(":", 1)[1])

    def on_redo(self):
        busy = self._busy_reason()
        if busy:
            self.status_label.setText(busy)
            return
        name = self.doc.redo()
        self._after_history_change()
        self.status_label.setText(f"Redo: {name}." if name else "Nothing to redo.")

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
        self.status_label.setText("Offset Plane: Klicka på ett plan (XY, XZ, YZ, konstruktionsplan) eller en plan yta att utgå ifrån (Esc avbryter).")

    def on_offset_base_picked(self, base):
        from omacad.model.sketch import SketchPlane
        n = np.asarray(base.normal, dtype=float)
        n = n / np.linalg.norm(n)
        o = np.asarray(base.origin, dtype=float)

        dlg = OffsetPlaneDialog(base.name, self)
        self.dock(dlg)
        self.status_label.setText(f"Offset Plane: Ange avstånd i mm (eller dra i 3D-pilen). Klicka 'To surface…' för att tangera en yta.")

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
            self.status_label.setText(f"Offset satt till {dist:.3f} mm mot ytan. Justera eller klicka OK.")

        def start_surface_pick():
            self.viewport.begin_plane_pick("offset_surface")
            try:
                self.viewport.surface_picked.disconnect(on_surface_picked)
            except Exception:
                pass
            self.viewport.surface_picked.connect(on_surface_picked)
            self.status_label.setText("Klicka på en yta (plan eller krökt) för att sätta planet tangerande mot den.")

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
            self.status_label.setText(f"{self.doc.construction_planes[pid]['name']} skapad på {dist:.3f} mm från {base.name}.")
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
        self.ribbon.btn_rect.setChecked(tool_name in RECT_TOOLS)
        self.ribbon.btn_circle.setChecked(tool_name in ("CIRCLE", "SMART_CIRCLE"))
        self.ribbon.btn_polygon.setChecked(tool_name == "POLYGON")
        self.ribbon.btn_arc.setChecked(tool_name == "ARC")
        self.ribbon.btn_slot.setChecked(tool_name == "SLOT")
        self.ribbon.btn_trim_sk.setChecked(tool_name == "TRIM")
        self.ribbon.btn_mirror_sk.setChecked(tool_name == "MIRROR")
        self.ribbon.btn_offset_sk.setChecked(tool_name == "OFFSET")
        self.ribbon.btn_fillet_sk.setChecked(tool_name == "FILLET")
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

    def prompt_split_body(self, target_body_id: str = "", plane_id: str = ""):
        if not self.doc.bodies:
            QMessageBox.information(
                self, "Split Body", "No bodies found to split. Create a 3D body first!"
            )
            return

        dlg = SplitBodyDialog(
            self.doc, self,
            preselected_body_id=target_body_id or None,
            preselected_plane_id=plane_id or None,
        )
        if dlg.exec():
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

    def prompt_shell(self, target_body_id: str = ""):
        """Shell: hollow out a 3D solid body with specified wall thickness and optional open faces."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Shell", "Create a 3D body first before shelling!")
            return

        dlg = ShellDialog(self.doc, self, preselected_body_id=target_body_id or None)
        self.dock(dlg)

        def on_face_picked(plane):
            if getattr(plane, "face", None):
                dlg.toggle_face(plane.face)

        self.viewport.plane_picked.connect(on_face_picked)
        self.viewport.begin_plane_pick("shell_face")
        self.status_label.setText("Shell: Välj kropp och väggtjocklek. Klicka på ytor i 3D för att lämna dem öppna.")

        def cleanup():
            try:
                self.viewport.plane_picked.disconnect(on_face_picked)
            except Exception:
                pass
            self.viewport.end_plane_pick()
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
                    self.status_label.setText(f"Shell skapad på {b_name}: tjocklek {thickness:g} mm ({n_open} öppna ytor).")
                    self.viewport.update()
            else:
                self.status_label.setText("Shell avbröts.")
                self.viewport.update()

        dlg.finished.connect(on_finished)
        dlg.show()

    def prompt_move_body(self, target_body_id: str = ""):
        """Move / Rotate: Translates and rotates a 3D solid body parametrically with interactive 3D gizmo."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Move Body", "Inga kroppar hittades att flytta. Skapa en 3D-kropp först!")
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
                self.viewport.clear_extrude_handle()
                return

            body = self.doc.bodies[bid]
            center = get_body_center(body)
            moved_center = center + np.array([dx, dy, dz])

            active_ax = dlg.active_axis
            axis_map = {
                "X": ([1.0, 0.0, 0.0], (1.0, 0.25, 0.25)),
                "Y": ([0.0, 1.0, 0.0], (0.25, 0.9, 0.25)),
                "Z": ([0.0, 0.0, 1.0], (0.25, 0.6, 1.0)),
            }
            ax, col = axis_map.get(active_ax, ([1.0, 0.0, 0.0], (1.0, 0.25, 0.25)))
            arrow_len = max(25.0, min(80.0, self.viewport.distance * 0.18))
            self.viewport.set_extrude_handle(moved_center, ax, arrow_len, color=col)

        def refresh_preview():
            bid, dx, dy, dz, rx, ry, rz, pivot, _ = dlg.get_values()
            if not bid or bid not in self.doc.bodies:
                if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                    self.doc.bodies[current_hidden_id[0]].visible = True
                    current_hidden_id[0] = None
                self.viewport.set_preview(None)
                self.viewport.clear_extrude_handle()
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

        def on_handle_drag(val: float):
            active_ax = dlg.active_axis
            if not drag_state["dragging"]:
                drag_state["dragging"] = True
                drag_state["start_val"] = val
                cur_v = dlg.spn_dx.value() if active_ax == "X" else (dlg.spn_dy.value() if active_ax == "Y" else dlg.spn_dz.value())
                drag_state["start_axis_val"] = cur_v

            delta = val - drag_state["start_val"]
            new_val = round(drag_state["start_axis_val"] + delta, 2)
            dlg.set_active_axis_value(new_val)

        def on_drag_finished():
            drag_state["dragging"] = False
            update_handle()

        def on_axis_changed(_axis: str):
            drag_state["dragging"] = False
            update_handle()

        def on_face_picked(plane):
            if getattr(plane, "face", None) and hasattr(plane.face, "body_id"):
                dlg.select_body(plane.face.body_id)

        def cleanup():
            try:
                self.viewport.plane_picked.disconnect(on_face_picked)
            except Exception:
                pass
            try:
                self.viewport.extrude_handle_dragged.disconnect(on_handle_drag)
            except Exception:
                pass
            try:
                self.viewport.extrude_handle_drag_finished.disconnect(on_drag_finished)
            except Exception:
                pass
            self.viewport.end_plane_pick()
            self.viewport.clear_extrude_handle()
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
                    self.status_label.setText(f"Flyttade {b_name}: dx={dx:g}, dy={dy:g}, dz={dz:g} mm, rx={rx:g}°, ry={ry:g}°, rz={rz:g}°.")
                    self.viewport.update()
            else:
                self.status_label.setText("Flytt avbröts.")
                self.viewport.update()

        dlg.changed.connect(refresh_preview)
        dlg.axis_changed.connect(on_axis_changed)
        dlg.finished.connect(on_finished)
        self.viewport.extrude_handle_dragged.connect(on_handle_drag)
        self.viewport.extrude_handle_drag_finished.connect(on_drag_finished)
        self.viewport.plane_picked.connect(on_face_picked)
        self.viewport.begin_plane_pick("move_body")
        self.status_label.setText("Move: Dra i 3D-pilen eller ange mm/grader. Klicka på en annan kropp i 3D för att välja den.")

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
                self.status_label.setText(f"Infogade bildreferens: {data['name']} ({data['width_mm']:.1f} × {data['height_mm']:.1f} mm).")

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
        self.inspector.doc = doc
        doc.add_change_listener(self.inspector.refresh_info)
        doc.history_listeners.append(self._update_undo_actions)
        self._update_undo_actions()
        for panel, refresh in ((self.browser, "refresh_tree"), (self.timeline_bar, "refresh_timeline"),
                               (self.ribbon, "sync_active_tab")):
            panel.doc = doc
            doc.add_change_listener(getattr(panel, refresh))
        self.update_window_title()
        doc.notify_changed()

    def update_window_title(self):
        name = Path(self.current_path).name if getattr(self, "current_path", None) else "Untitled"
        from omacad import __version__
        self.setWindowTitle(f"{name} - Omacad {__version__}")

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

    def on_import_3mf(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import 3MF Model", "", "3MF Files (*.3mf)")
        if not filepath:
            return
        try:
            bodies = Exporter.import_3mf(filepath, self.doc)
            if bodies:
                self.viewport.zoom_fit()
                names = ", ".join(b.name for b in bodies)
                self.status_label.setText(f"Imported {len(bodies)} body(s) from {Path(filepath).name}: {names}")
            else:
                QMessageBox.warning(self, "Import 3MF", "No 3D meshes found in 3MF archive.")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not import {filepath}:\n{e}")

    def on_export_all_step(self):
        if not self.doc.bodies:
            QMessageBox.information(self, "Export STEP", "No bodies to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export All Bodies to STEP", "", "STEP Files (*.step *.stp)")
        if filepath:
            if not (filepath.endswith(".step") or filepath.endswith(".stp")):
                filepath += ".step"
            ok = Exporter.export_all_to_step(self.doc, filepath)
            if ok:
                QMessageBox.information(self, "Export STEP", f"Successfully exported STEP to:\n{filepath}")
                self.status_label.setText(f"Exported STEP to {filepath}")

    def export_single_body_step(self, body_id: str):
        body = self.doc.bodies.get(body_id)
        if not body:
            return

        filepath, _ = QFileDialog.getSaveFileName(self, f"Export {body.name} to STEP", f"{body.name}.step", "STEP Files (*.step *.stp)")
        if filepath:
            if not (filepath.endswith(".step") or filepath.endswith(".stp")):
                filepath += ".step"
            ok = Exporter.export_body_to_step(body, filepath)
            if ok:
                QMessageBox.information(self, "Export STEP", f"Successfully exported {body.name} to:\n{filepath}")
                self.status_label.setText(f"Exported {body.name} to {filepath}")

    # ------------------ Restart with a new version ------------------

    def start_restart_watch(self, interval_ms: int = 3000) -> None:
        """When the source tree gets a new commit (the agent finished a fix), save everything and restart on it."""
        from omacad import feedback, session
        self._code_root = feedback.repo_root()
        self._code_version = session.code_version(self._code_root)
        if self._code_version is None:
            return                                  # not a source checkout: nothing to watch
        self._restart_timer = QTimer(self)
        self._restart_timer.timeout.connect(self._check_code_version)
        self._restart_timer.start(interval_ms)

    def _check_code_version(self) -> None:
        from PySide6.QtWidgets import QApplication
        from omacad import session
        from omacad.ui.settings import get_settings
        if not get_settings().get("auto_restart", True) or QApplication.activeModalWidget() is not None:
            return                                  # never pull the app away under an open dialog
        version = session.code_version(self._code_root)
        if version and version != self._code_version:
            self._restart_timer.stop()
            self.status_label.setText("New version committed: saving your work and restarting ...")
            QTimer.singleShot(1500, self.restart_app)

    def restart_app(self) -> None:
        """Saves the session and starts a fresh process that resumes it, then closes this one."""
        import sys
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        from omacad import applog, session
        v = self.viewport
        camera = {"azimuth": v.azimuth, "elevation": v.elevation, "distance": v.distance,
                  "target": [float(x) for x in v.target]}
        try:
            session.save(self.doc, self.current_path, camera)
        except (OSError, TypeError, ValueError) as e:      # no restart if the work could not be saved
            applog.log("ERROR", f"restart cancelled, could not save the session: {e}")
            self.status_label.setText(f"Restart cancelled, could not save the session: {e}")
            self._restart_timer.start()
            return
        script = str(Path(self._code_root) / "app.py")
        if QProcess.startDetached(sys.executable, [script, session.RESUME_FLAG], str(self._code_root)):
            QApplication.quit()
        else:
            applog.log("ERROR", "restart cancelled, could not start the new process")
            self.status_label.setText("Restart cancelled, could not start the new process.")
            self._restart_timer.start()

    def restore_session(self) -> bool:
        """Puts back what restart_app saved (document, sketch being edited, camera). Returns whether there was one."""
        from omacad import session
        data = session.load()
        if not data:
            return False
        doc = Document()
        Exporter.apply_dict(doc, data["document"])
        self.attach_document(doc, data.get("path"))
        cam = data.get("camera") or {}
        v = self.viewport
        v.azimuth = cam.get("azimuth", v.azimuth)
        v.elevation = cam.get("elevation", v.elevation)
        v.distance = cam.get("distance", v.distance)
        if "target" in cam:
            v.target = np.array(cam["target"], dtype=np.float32)
        v.update()
        self.status_label.setText(f"Restarted on Omacad {__import__('omacad').__version__}; your work is back.")
        return True

    def on_report_problem(self):
        """Screenshot first (before any dialog covers the problem), then the note, then the report goes to the AI agent."""
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QPixmap
        from omacad import feedback
        from omacad.ui.feedback_dialog import FeedbackDialog

        def png(image):
            data, buf = QByteArray(), QBuffer()
            buf.setBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buf, "PNG")
            return bytes(data)

        window_shot = self.grab()
        view_shot = self.viewport.grabFramebuffer()
        dlg = FeedbackDialog(self, window_shot)
        if not dlg.exec():
            return
        v = self.viewport
        extra = {"camera": {"azimuth": v.azimuth, "elevation": v.elevation, "distance": v.distance,
                            "target": [float(x) for x in v.target]},
                 "sketch_tool": v.sketch_tool, "selected_sketch_entities": sorted(v.selected_entities),
                 "window_size": [self.width(), self.height()]}
        images = {"screenshot_window.png": png(window_shot.toImage()), "screenshot_view.png": png(view_shot)}
        marked = dlg.marked_image()
        if marked is not None:
            images["screenshot_marked.png"] = png(marked)   # the user's drawing on the window screenshot
        folder = feedback.build_bundle(self.doc, dlg.text(), images, extra)
        if dlg.fix_now() and feedback.launch_agent(folder):
            self.status_label.setText(f"Report sent to the AI agent (a terminal opened). Saved in {folder}")
        else:
            self.status_label.setText(f"Report saved in {folder}")

    def on_about(self):
        QMessageBox.about(
            self, "About Omacad",
            f"<h3>Omacad {__import__('omacad').__version__}</h3>"
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
            "<p><i>Vibecoded by Kindstrom</i></p>"
        )
