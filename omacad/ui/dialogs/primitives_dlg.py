"""Dialogs for primitive 3D solid bodies: Box, Cylinder, Sphere."""

from typing import Optional, Tuple, Any
from PySide6.QtWidgets import QFormLayout, QComboBox, QPushButton, QHBoxLayout, QLabel
from PySide6.QtCore import Signal
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class BoxDialog(BaseFeatureDialog):
    """Dialog for creating a primitive box/block."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Create Box", parent, embedded)
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        form = QFormLayout()

        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(0.1, 10000.0)
        self.spn_length.setValue(50.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Length (X):", self.spn_length)

        self.spn_width = ExprDoubleSpinBox()
        self.spn_width.setRange(0.1, 10000.0)
        self.spn_width.setValue(50.0)
        self.spn_width.setSuffix(" mm")
        self.spn_width.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Width (Y):", self.spn_width)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(25.0)
        self.spn_height.setSuffix(" mm")
        self.spn_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Height (Z):", self.spn_height)

        # Placement mode
        self.cmb_placement = QComboBox()
        self.cmb_placement.addItem("Undersida i origo (Center XY, Z: 0..H)", "bottom_center")
        self.cmb_placement.addItem("Hörn i origo (X, Y, Z: 0..+)", "corner")
        self.cmb_placement.addItem("Helt centrerad i origo (±X, ±Y, ±Z)", "center")
        self.cmb_placement.addItem("På vald yta / plan (On face…)", "on_face")
        self.cmb_placement.currentIndexChanged.connect(self._on_placement_changed)
        form.addRow("Placement:", self.cmb_placement)

        # On face button & label
        self.btn_face = QPushButton("Välj yta (On face…)")
        self.btn_face.setToolTip("Klicka på en yta eller plan i 3D-vyn där boxen ska starta.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        self.face_row_widget = face_row
        form.addRow("Target Face:", face_row)

        self.main_layout.addLayout(form)
        self.add_buttons()
        self._update_face_row_visibility()

    def _on_placement_changed(self):
        self._update_face_row_visibility()
        if self.cmb_placement.currentData() == "on_face" and self.plane_normal is None:
            self.pick_face_requested.emit()
        self.changed.emit()

    def _update_face_row_visibility(self):
        is_on_face = self.cmb_placement.currentData() == "on_face"
        self.btn_face.setVisible(is_on_face)
        self.lbl_face.setVisible(is_on_face)

    def set_target_plane(self, plane):
        """Called when user picks a face or plane in 3D viewport."""
        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        n = self.plane_normal
        desc = "Horisontell" if abs(n[2]) > 0.8 else ("Vertikal" if abs(n[2]) < 0.2 else "Vinklad")
        self.lbl_face.setText(f"{p_name} ({desc})")
        if self.cmb_placement.currentData() != "on_face":
            idx = self.cmb_placement.findData("on_face")
            if idx >= 0:
                self.cmb_placement.blockSignals(True)
                self.cmb_placement.setCurrentIndex(idx)
                self.cmb_placement.blockSignals(False)
                self._update_face_row_visibility()
        self.changed.emit()

    def get_expressions(self) -> dict:
        out = {"length": self.spn_length.expression(), "width": self.spn_width.expression(), "height": self.spn_height.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        mode = self.cmb_placement.currentData()
        if mode == "center":
            center_val = True
        elif mode == "corner":
            center_val = False
        else:
            center_val = "bottom_center"

        use_plane = (mode == "on_face" and self.plane_origin is not None)
        return (
            self.spn_length.value(),
            self.spn_width.value(),
            self.spn_height.value(),
            center_val,
            self.plane_origin if use_plane else None,
            self.plane_normal if use_plane else None,
            self.plane_u if use_plane else None,
            self.plane_v if use_plane else None
        )


class CylinderDialog(BaseFeatureDialog):
    """Dialog for creating a primitive cylinder."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Create Cylinder", parent, embedded)
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        form = QFormLayout()

        self.spn_radius = ExprDoubleSpinBox()
        self.spn_radius.setRange(0.1, 10000.0)
        self.spn_radius.setValue(20.0)
        self.spn_radius.setSuffix(" mm")
        self.spn_radius.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Radius:", self.spn_radius)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(40.0)
        self.spn_height.setSuffix(" mm")
        self.spn_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Height:", self.spn_height)

        # Placement mode
        self.cmb_placement = QComboBox()
        self.cmb_placement.addItem("Undersida i origo (Center XY, Z: 0..H)", "bottom_center")
        self.cmb_placement.addItem("Helt centrerad i origo (±Z/2)", "center")
        self.cmb_placement.addItem("På vald yta / plan (On face…)", "on_face")
        self.cmb_placement.currentIndexChanged.connect(self._on_placement_changed)
        form.addRow("Placement:", self.cmb_placement)

        # On face button & label
        self.btn_face = QPushButton("Välj yta (On face…)")
        self.btn_face.setToolTip("Klicka på en yta eller plan i 3D-vyn där cylindern ska starta.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        self.face_row_widget = face_row
        form.addRow("Target Face:", face_row)

        self.main_layout.addLayout(form)
        self.add_buttons()
        self._update_face_row_visibility()

    def _on_placement_changed(self):
        self._update_face_row_visibility()
        if self.cmb_placement.currentData() == "on_face" and self.plane_normal is None:
            self.pick_face_requested.emit()
        self.changed.emit()

    def _update_face_row_visibility(self):
        is_on_face = self.cmb_placement.currentData() == "on_face"
        self.btn_face.setVisible(is_on_face)
        self.lbl_face.setVisible(is_on_face)

    def set_target_plane(self, plane):
        """Called when user picks a face or plane in 3D viewport."""
        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        n = self.plane_normal
        desc = "Horisontell" if abs(n[2]) > 0.8 else ("Vertikal" if abs(n[2]) < 0.2 else "Vinklad")
        self.lbl_face.setText(f"{p_name} ({desc})")
        if self.cmb_placement.currentData() != "on_face":
            idx = self.cmb_placement.findData("on_face")
            if idx >= 0:
                self.cmb_placement.blockSignals(True)
                self.cmb_placement.setCurrentIndex(idx)
                self.cmb_placement.blockSignals(False)
                self._update_face_row_visibility()
        self.changed.emit()

    def get_expressions(self) -> dict:
        out = {"radius": self.spn_radius.expression(), "height": self.spn_height.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        mode = self.cmb_placement.currentData()
        if mode == "center":
            center_val = True
        else:
            center_val = "bottom_center"

        use_plane = (mode == "on_face" and self.plane_origin is not None)
        return (
            self.spn_radius.value(),
            self.spn_height.value(),
            center_val,
            self.plane_origin if use_plane else None,
            self.plane_normal if use_plane else None,
            self.plane_u if use_plane else None,
            self.plane_v if use_plane else None
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
