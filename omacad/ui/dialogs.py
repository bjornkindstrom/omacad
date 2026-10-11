"""
Omacad - Feature Parameter Dialogs
Floating/docked dialogs for Extrude, Box, Cylinder, Sphere, Combine, and Sketch Planes.
"""

from typing import Optional, Dict
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QFormLayout, QGroupBox, QListWidget, QListWidgetItem, QSpinBox
)
from omacad.ui.theme import style

# The main window's right-hand panel; every tool dialog is docked there so none covers the model.
SIDE_HOST = None


def run_docked(dlg) -> int:
    """Like dlg.exec(), but the dialog sits in the side panel and a local event loop waits for it."""
    if SIDE_HOST is None:
        return QDialog.exec(dlg)
    from PySide6.QtCore import QEventLoop
    SIDE_HOST.dock(dlg)
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    loop.exec()
    return dlg.result()
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox


class BaseFeatureDialog(QDialog):
    """Base modal dialog with Fusion 360 styling."""

    def __init__(self, title: str, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._embedded = embedded
        self._drag_offset = None
        self.user_moved = False
        if embedded:
            # a panel inside the 3D view instead of a separate window: it can be dragged out of the way
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setFixedWidth(290)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setFixedWidth(320)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        style(self, """
            QDialog {
                background-color: #25282C;
                border: 1px solid #3E444D;
                border-radius: 6px;
            }
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

    # ---- embedded panel: placement and dragging ------------------------------------
    def exec(self):
        return run_docked(self)

    def place(self, parent_size, left: bool = False):
        """Dock into the side panel (or, without one, the right side of the view until dragged)."""
        if SIDE_HOST is not None:
            SIDE_HOST.dock(self)
            return
        self.adjustSize()
        if not self.user_moved:
            x = 24 if left else max(0, parent_size.width() - self.width() - 24)
            self.move(x, 150)

    def mousePressEvent(self, event):
        if self._embedded and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._embedded and self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.mapToParent(event.position().toPoint() - self._drag_offset))
            self.user_moved = True
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def add_buttons(self):
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("PrimaryButton")
        btn_ok.setDefault(True)  # Enter confirms, as in Fusion
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)

        self.main_layout.addLayout(btn_layout)


class SketchPlaneDialog(BaseFeatureDialog):
    """Dialog to choose which reference plane to sketch on."""

    def __init__(self, parent=None):
        super().__init__("Select Sketch Plane", parent)
        form = QFormLayout()

        self.cmb_plane = QComboBox()
        self.cmb_plane.addItems(["XY Plane (Top / Ground)", "XZ Plane (Front)", "YZ Plane (Right / Side)"])
        form.addRow("Plane:", self.cmb_plane)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_plane_name(self) -> str:
        idx = self.cmb_plane.currentIndex()
        return ["XY", "XZ", "YZ"][idx]


class ExtrudeDialog(BaseFeatureDialog):
    """Non-modal dialog for linear solid extrusion with live preview."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, doc: Document, parent=None, embedded: bool = False):
        super().__init__("Extrude", parent, embedded)
        self.doc = doc
        form = QFormLayout()

        # Profile selection
        self.cmb_profile = QComboBox()
        self.profile_keys = []
        for s_id, s in doc.sketches.items():
            for p_idx, p in enumerate(s.profiles):
                label = f"{s.name} - Profile {p_idx + 1} ({p.area:.1f} mm²)"
                self.cmb_profile.addItem(label)
                self.profile_keys.append((s_id, p_idx))

        if not self.profile_keys:
            self.cmb_profile.addItem("No closed sketch profiles found!")
            self.cmb_profile.setEnabled(False)

        form.addRow("Profile:", self.cmb_profile)

        # Distance
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-10000.0, 10000.0)
        self.spn_dist.setValue(25.0)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.setToolTip("Type a value or a formula, e.g. -10, 10-1 or 2x(3+5)")
        self.btn_face = QPushButton("To face…")
        self.btn_face.setToolTip("Click another face (or origin plane) in the viewport: the distance to it is filled in")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        dist_row = QHBoxLayout()
        dist_row.setContentsMargins(0, 0, 0, 0)
        dist_row.addWidget(self.spn_dist, 1)
        dist_row.addWidget(self.btn_face)
        form.addRow("Distance:", dist_row)

        # Direction
        self.cmb_dir = QComboBox()
        self.cmb_dir.addItems(["One Side", "Symmetric", "Two Sides"])
        self.cmb_dir.currentIndexChanged.connect(self._on_dir_changed)
        form.addRow("Direction:", self.cmb_dir)

        self.spn_dist2 = ExprDoubleSpinBox()
        self.spn_dist2.setRange(0.0, 10000.0)
        self.spn_dist2.setValue(10.0)
        self.spn_dist2.setSuffix(" mm")
        self.lbl_dist2 = QLabel("Distance 2:")
        form.addRow(self.lbl_dist2, self.spn_dist2)
        self._on_dir_changed(0)

        # Operation
        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Auto", "New Body", "Join", "Cut (Difference)", "Intersect"])
        self.cmb_op.setToolTip("Auto: cuts when the extrusion goes into a body, joins when it starts on a body's face and goes out, otherwise makes a new body.")
        form.addRow("Operation:", self.cmb_op)

        hint = QLabel("Click a profile to select it; Shift+click adds or removes more (a ring and the circle inside it are separate profiles). Distance accepts formulas (10-1, 2x(3+5)).")
        hint.setWordWrap(True)
        style(hint, "color: #8A929C;")
        self.main_layout.addWidget(hint)
        self.main_layout.addLayout(form)
        self.add_buttons()

        self.cmb_profile.setPlaceholderText("Click a profile in the view")
        if doc.selected_profile in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(doc.selected_profile))
        elif len(self.profile_keys) > 1:
            self.cmb_profile.setCurrentIndex(-1)   # nothing is picked for you when there is a choice
        QTimer.singleShot(0, self.focus_distance)
        for sig in (self.cmb_profile.currentIndexChanged, self.cmb_dir.currentIndexChanged,
                    self.cmb_op.currentIndexChanged, self.spn_dist.valueChanged, self.spn_dist2.valueChanged):
            sig.connect(lambda *_: self.changed.emit())

    def reload_profiles(self):
        """Rebuild the profile list (a face sketch may have been added while the dialog is open)."""
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        self.profile_keys = []
        for s_id, sk in self.doc.sketches.items():
            for p_idx, p in enumerate(sk.profiles):
                self.cmb_profile.addItem(f"{sk.name} - Profile {p_idx + 1} ({p.area:.1f} mm²)")
                self.profile_keys.append((s_id, p_idx))
        self.cmb_profile.setEnabled(bool(self.profile_keys))
        self.cmb_profile.blockSignals(False)

    def focus_distance(self):
        """Distance field active with its text selected: just type, e.g. -10, and press Enter."""
        self.spn_dist.setFocus()
        self.spn_dist.selectAll()

    def set_distance(self, value: float):
        """Used by 'To face': one-sided extrusion by the given (signed) distance."""
        self.cmb_dir.setCurrentIndex(0)
        self.spn_dist.setValue(round(value, 4))
        self.focus_distance()

    def select_profile(self, key):
        """Selects a (sketch_id, profile_idx) in the combo (e.g. picked in the viewport)."""
        if key in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(key))

    def get_operation(self) -> str:
        return {0: "auto", 1: "new_body", 2: "join", 3: "cut", 4: "intersect"}.get(self.cmb_op.currentIndex(), "auto")

    def set_auto_result(self, op: str):
        """Shows what 'Auto' currently resolves to, e.g. 'Auto (Cut)'."""
        names = {"new_body": "New Body", "join": "Join", "cut": "Cut", "intersect": "Intersect"}
        self.cmb_op.setItemText(0, f"Auto ({names.get(op, op)})")

    def _on_dir_changed(self, idx: int):
        two = idx == 2
        self.spn_dist2.setVisible(two)
        self.lbl_dist2.setVisible(two)
        # Symmetric/two-sided lengths are magnitudes
        self.spn_dist.setMinimum(0.1 if idx else -10000.0)

    def get_expressions(self) -> dict:
        """Formulas typed into the distance fields (None-valued entries dropped)."""
        out = {"distance": self.spn_dist.expression(), "distance2": self.spn_dist2.expression()}
        return {k: v for k, v in out.items() if v}

    def get_direction(self):
        return ["one_side", "symmetric", "two_sides"][self.cmb_dir.currentIndex()], self.spn_dist2.value()

    def get_values(self):
        idx = self.cmb_profile.currentIndex()
        if not self.profile_keys or idx < 0:
            return None, 0, 0.0, "new_body"

        s_id, p_idx = self.profile_keys[idx]
        dist = self.spn_dist.value()
        op = self.get_operation()
        return s_id, p_idx, dist, op


class BoxDialog(BaseFeatureDialog):
    """Dialog for creating a primitive box/block."""

    def __init__(self, parent=None):
        super().__init__("Create Box", parent)
        form = QFormLayout()

        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(0.1, 10000.0)
        self.spn_length.setValue(50.0)
        self.spn_length.setSuffix(" mm")
        form.addRow("Length (X):", self.spn_length)

        self.spn_width = ExprDoubleSpinBox()
        self.spn_width.setRange(0.1, 10000.0)
        self.spn_width.setValue(50.0)
        self.spn_width.setSuffix(" mm")
        form.addRow("Width (Y):", self.spn_width)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(25.0)
        self.spn_height.setSuffix(" mm")
        form.addRow("Height (Z):", self.spn_height)

        self.chk_center = QCheckBox("Center on Origin")
        self.chk_center.setChecked(False)
        form.addRow("", self.chk_center)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_expressions(self) -> dict:
        out = {"length": self.spn_length.expression(), "width": self.spn_width.expression(), "height": self.spn_height.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        return (
            self.spn_length.value(),
            self.spn_width.value(),
            self.spn_height.value(),
            self.chk_center.isChecked()
        )


class CylinderDialog(BaseFeatureDialog):
    """Dialog for creating a primitive cylinder."""

    def __init__(self, parent=None):
        super().__init__("Create Cylinder", parent)
        form = QFormLayout()

        self.spn_radius = ExprDoubleSpinBox()
        self.spn_radius.setRange(0.1, 10000.0)
        self.spn_radius.setValue(20.0)
        self.spn_radius.setSuffix(" mm")
        form.addRow("Radius:", self.spn_radius)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(40.0)
        self.spn_height.setSuffix(" mm")
        form.addRow("Height:", self.spn_height)

        self.chk_center = QCheckBox("Center on Origin")
        self.chk_center.setChecked(False)
        form.addRow("", self.chk_center)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_expressions(self) -> dict:
        out = {"radius": self.spn_radius.expression(), "height": self.spn_height.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        return (
            self.spn_radius.value(),
            self.spn_height.value(),
            self.chk_center.isChecked()
        )


class SphereDialog(BaseFeatureDialog):
    """Dialog for creating a primitive sphere."""

    def __init__(self, parent=None):
        super().__init__("Create Sphere", parent)
        form = QFormLayout()

        self.spn_radius = ExprDoubleSpinBox()
        self.spn_radius.setRange(0.1, 10000.0)
        self.spn_radius.setValue(25.0)
        self.spn_radius.setSuffix(" mm")
        form.addRow("Radius:", self.spn_radius)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_expressions(self) -> dict:
        out = {"radius": self.spn_radius.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        return self.spn_radius.value()


class OffsetPlaneDialog(BaseFeatureDialog):
    """Offset plane: a plane parallel to the chosen plane or face, at a distance or up to any surface."""
    changed = Signal()
    surface_requested = Signal()

    def __init__(self, base_name: str, parent=None, embedded=False):
        super().__init__("Offset Plane", parent, embedded)
        info = QLabel(f"From: {base_name}\nType a distance (formulas and parameters work) or press 'To surface…' "
                      "and click a face, a cylinder or a sphere: the plane then touches it.")
        info.setWordWrap(True)
        self.main_layout.addWidget(info)
        form = QFormLayout()
        row = QHBoxLayout()
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-10000.0, 10000.0)
        self.spn_dist.setDecimals(3)
        self.spn_dist.setValue(10.0)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.valueChanged.connect(lambda *_: self.changed.emit())
        row.addWidget(self.spn_dist, 1)
        self.btn_surface = QPushButton("To surface…")
        self.btn_surface.setAutoDefault(False)
        self.btn_surface.setToolTip("Click a flat or curved surface; the plane is placed tangent to it")
        self.btn_surface.clicked.connect(self.surface_requested.emit)
        row.addWidget(self.btn_surface)
        form.addRow("Distance:", row)
        self.main_layout.addLayout(form)
        self.add_buttons()

    def focus_distance(self):
        self.spn_dist.setFocus()
        self.spn_dist.selectAll()

    def get_expressions(self) -> dict:
        e = self.spn_dist.expression()
        return {"distance": e} if e else {}


class CombineDialog(BaseFeatureDialog):
    """Dialog for boolean combine operations (Join, Cut, Intersect)."""

    def __init__(self, doc: Document, parent=None):
        super().__init__("Combine Bodies", parent)
        self.doc = doc
        form = QFormLayout()

        self.body_ids = list(doc.bodies.keys())
        names = [doc.bodies[bid].name for bid in self.body_ids]

        self.cmb_target = QComboBox()
        self.cmb_target.addItems(names)
        form.addRow("Target Body:", self.cmb_target)

        self.cmb_tool = QComboBox()
        self.cmb_tool.addItems(names)
        if len(names) > 1:
            self.cmb_tool.setCurrentIndex(1)
        form.addRow("Tool Body:", self.cmb_tool)

        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Join (Union)", "Cut (Difference)", "Intersect"])
        form.addRow("Operation:", self.cmb_op)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_values(self):
        t_idx = self.cmb_target.currentIndex()
        tool_idx = self.cmb_tool.currentIndex()
        if not self.body_ids or t_idx < 0 or tool_idx < 0 or t_idx == tool_idx:
            return None, None, "join"

        target_id = self.body_ids[t_idx]
        tool_id = self.body_ids[tool_idx]
        op_map = {0: "join", 1: "cut", 2: "intersect"}
        op = op_map.get(self.cmb_op.currentIndex(), "join")
        return target_id, tool_id, op


class RoundEdgesDialog(BaseFeatureDialog):
    """Fillet / Chamfer: choose the size while the edges are selected in the viewport."""

    changed = Signal()

    def __init__(self, parent=None, kind: str = "fillet", size: float = 2.0, editing: bool = False, embedded: bool = False):
        super().__init__("Fillet / Chamfer", parent, embedded)
        form = QFormLayout()
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["Fillet (round)", "Chamfer (bevel)"])
        self.cmb_kind.setCurrentIndex(1 if kind == "chamfer" else 0)
        form.addRow("Type:", self.cmb_kind)
        self.spn_size = ExprDoubleSpinBox()
        self.spn_size.setRange(0.01, 10000.0)
        self.spn_size.setDecimals(3)
        self.spn_size.setSuffix(" mm")
        self.spn_size.setValue(size)
        self.spn_size.setToolTip("Radius (fillet) or distance (chamfer). Formulas and parameter names work.")
        form.addRow("Size:", self.spn_size)
        self.lbl_count = QLabel("" if editing else "Click edges in the viewport to select them (click again to deselect).")
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)
        self.main_layout.addLayout(form)
        self.add_buttons()
        self.cmb_kind.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.spn_size.valueChanged.connect(lambda *_: self.changed.emit())
        QTimer.singleShot(0, lambda: (self.spn_size.setFocus(), self.spn_size.selectAll()))

    def kind(self) -> str:
        return "chamfer" if self.cmb_kind.currentIndex() == 1 else "fillet"

    def set_count(self, n: int):
        self.lbl_count.setText(f"{n} edge{'s' if n != 1 else ''} selected. Click edges in the viewport to add or remove them."
                               if n else "Click edges in the viewport to select them (click again to deselect).")

    def get_expressions(self) -> dict:
        e = self.spn_size.expression()
        return {"size": e} if e else {}


class PatternDialog(BaseFeatureDialog):
    """Pattern / Mirror: copy what some steps did (e.g. a hole and its chamfers)."""

    changed = Signal()

    KINDS = ["linear", "mirror", "circular"]
    AXES = ["x", "y", "z"]
    MIRROR_MODES = ["auto", "x", "y", "xy", "diameter"]

    def __init__(self, doc: Document, parent=None, feature=None):
        super().__init__("Pattern / Mirror", parent)
        self.setFixedWidth(380)
        self.doc = doc
        form = QFormLayout()

        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["Evenly spaced copies (linear)", "Mirror around the body", "Around an axis (circular)"])
        form.addRow("Type:", self.cmb_kind)

        self.lst = QListWidget()
        self.lst.setFixedHeight(120)
        feats = doc.timeline.features
        last_sketch = max((i for i, f in enumerate(feats) if f.feature_type == "sketch"), default=0)
        for i, f in enumerate(feats):
            if f.feature_type == "pattern":
                continue
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, f.feature_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i >= last_sketch else Qt.CheckState.Unchecked)
            self.lst.addItem(item)
        form.addRow("Copy these steps:", self.lst)

        # linear
        self.cmb_axis1 = QComboBox(); self.cmb_axis1.addItems(["X", "Y", "Z"])
        self.spn_count1 = QSpinBox(); self.spn_count1.setRange(2, 500); self.spn_count1.setValue(3)
        self.spn_space1 = ExprDoubleSpinBox(); self.spn_space1.setRange(0.01, 100000); self.spn_space1.setSuffix(" mm"); self.spn_space1.setValue(20.0)
        self.chk_second = QCheckBox("Second direction (grid)")
        self.cmb_axis2 = QComboBox(); self.cmb_axis2.addItems(["X", "Y", "Z"]); self.cmb_axis2.setCurrentIndex(1)
        self.spn_count2 = QSpinBox(); self.spn_count2.setRange(1, 500); self.spn_count2.setValue(2)
        self.spn_space2 = ExprDoubleSpinBox(); self.spn_space2.setRange(0.01, 100000); self.spn_space2.setSuffix(" mm"); self.spn_space2.setValue(20.0)
        # mirror
        self.cmb_mirror = QComboBox()
        self.cmb_mirror.addItems(["Auto (round body: along the diameter)", "Mirror left-right (X)", "Mirror front-back (Y)", "All four corners (X and Y)", "Along the diameter (opposite side)"])
        # circular
        self.spn_angle = ExprDoubleSpinBox(); self.spn_angle.setRange(1, 360); self.spn_angle.setSuffix(" °"); self.spn_angle.setValue(360)
        self.cmb_about = QComboBox(); self.cmb_about.addItems(["Centre of the body", "Origin"])

        self.rows = {
            "linear": [("Direction:", self.cmb_axis1), ("Copies:", self.spn_count1), ("Spacing:", self.spn_space1),
                       ("", self.chk_second), ("Direction 2:", self.cmb_axis2), ("Copies 2:", self.spn_count2), ("Spacing 2:", self.spn_space2)],
            "mirror": [("Mirror:", self.cmb_mirror), ("About:", self.cmb_about)],
            "circular": [("Copies:", self.spn_count1), ("Angle:", self.spn_angle), ("About:", self.cmb_about)],
        }
        self._kind_form = QFormLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addLayout(form)
        self.main_layout.addLayout(self._kind_form)
        self.main_layout.addWidget(self.lbl_info)
        self.add_buttons()
        self.cmb_kind.currentIndexChanged.connect(self._show_kind)
        for w_ in (self.cmb_kind, self.cmb_axis1, self.cmb_axis2, self.cmb_mirror, self.cmb_about):
            w_.currentIndexChanged.connect(lambda *_: self.changed.emit())
        for w_ in (self.spn_count1, self.spn_count2, self.spn_space1, self.spn_space2, self.spn_angle):
            w_.valueChanged.connect(lambda *_: self.changed.emit())
        self.chk_second.toggled.connect(lambda *_: (self._show_kind(), self.changed.emit()))
        self.lst.itemChanged.connect(lambda *_: self.changed.emit())
        self._show_kind()
        if feature is not None:
            self.load(feature)

    def _show_kind(self, *_):
        """Show only the fields that belong to the chosen type."""
        for w_ in [x for rows in self.rows.values() for _, x in rows]:
            w_.setVisible(False)
        while self._kind_form.rowCount():
            row = self._kind_form.takeRow(0)
            if row.labelItem is not None and row.labelItem.widget() is not None:
                lbl = row.labelItem.widget()
                lbl.hide()          # gone at once (deleteLater alone leaves it painted for a moment)
                lbl.setParent(None)
                lbl.deleteLater()
        kind = self.KINDS[self.cmb_kind.currentIndex()]
        for text, widget in self.rows[kind]:
            if kind == "linear" and widget in (self.cmb_axis2, self.spn_count2, self.spn_space2) and not self.chk_second.isChecked():
                continue
            self._kind_form.addRow(QLabel(text), widget)
            widget.setVisible(True)

    def load(self, f):
        """Fill the dialog from an existing step (editing)."""
        self.cmb_kind.setCurrentIndex(self.KINDS.index(f.kind))
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in f.source_ids else Qt.CheckState.Unchecked)
        self.cmb_axis1.setCurrentIndex(self.AXES.index(f.axis1)); self.spn_count1.setValue(int(round(f.count1)))
        self.spn_space1.setValue(f.spacing1)
        self.chk_second.setChecked(int(round(f.count2)) > 1)
        self.cmb_axis2.setCurrentIndex(self.AXES.index(f.axis2)); self.spn_count2.setValue(max(1, int(round(f.count2))))
        self.spn_space2.setValue(f.spacing2)
        self.cmb_mirror.setCurrentIndex(self.MIRROR_MODES.index(f.mirror_mode))
        self.cmb_about.setCurrentIndex(0 if f.about == "body" else 1)
        self.spn_angle.setValue(f.angle)
        for key, spin in (("spacing1", self.spn_space1), ("spacing2", self.spn_space2), ("angle", self.spn_angle)):
            if f.exprs.get(key):
                spin.set_expression(f.exprs[key])
        self._show_kind()

    def source_ids(self):
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.CheckState.Checked]

    def kind(self) -> str:
        return self.KINDS[self.cmb_kind.currentIndex()]

    def get_params(self) -> dict:
        second = self.chk_second.isChecked()
        return {
            "axis1": self.AXES[self.cmb_axis1.currentIndex()], "count1": self.spn_count1.value(), "spacing1": self.spn_space1.value(),
            "axis2": self.AXES[self.cmb_axis2.currentIndex()], "count2": self.spn_count2.value() if second else 1,
            "spacing2": self.spn_space2.value(), "mirror_mode": self.MIRROR_MODES[self.cmb_mirror.currentIndex()],
            "about": "body" if self.cmb_about.currentIndex() == 0 else "origin", "angle": self.spn_angle.value(),
        }

    def get_expressions(self) -> dict:
        out = {"spacing1": self.spn_space1.expression(), "spacing2": self.spn_space2.expression() if self.chk_second.isChecked() else None,
               "angle": self.spn_angle.expression()}
        return {k: v for k, v in out.items() if v}
