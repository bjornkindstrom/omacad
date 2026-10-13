"""Dialog for Move / Rotate Body feature with interactive axis dragging."""

from typing import Dict
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QHBoxLayout, QPushButton
)
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class MoveBodyDialog(BaseFeatureDialog):
    changed = Signal()
    axis_changed = Signal(str)

    def __init__(self, doc: Document, parent=None, preselected_body_id=None):
        super().__init__("Move / Rotate Body", parent)
        self.doc = doc
        self.active_axis = "X"
        form = QFormLayout()

        # Target body selection
        self.cmb_target = QComboBox()
        self.body_ids = []
        target_idx = 0
        for bid, b in doc.bodies.items():
            self.body_ids.append(bid)
            self.cmb_target.addItem(f"Body: {b.name}")
            if bid == preselected_body_id:
                target_idx = len(self.body_ids) - 1
        if self.body_ids:
            self.cmb_target.setCurrentIndex(target_idx)
        form.addRow("Target Body:", self.cmb_target)

        # Active Drag Axis buttons (X, Y, Z)
        axis_layout = QHBoxLayout()
        self.btn_axis_x = QPushButton("X")
        self.btn_axis_y = QPushButton("Y")
        self.btn_axis_z = QPushButton("Z")
        # the axis colours of the 3D arrows: red, green, blue. Checked = filled with the colour, white text.
        for b, colour, name in ((self.btn_axis_x, "#D8453B", "red"), (self.btn_axis_y, "#2E9E4F", "green"),
                                (self.btn_axis_z, "#2F7FE0", "blue")):
            b.setCheckable(True)
            b.setToolTip(f"Drag along the {name} arrow")
            b.setStyleSheet(
                f"QPushButton {{ padding: 6px 0px; font-weight: bold; border: 2px solid {colour}; border-radius: 4px; }}"
                f"QPushButton:checked {{ background-color: {colour}; color: #FFFFFF; }}")
            axis_layout.addWidget(b)
        self.btn_axis_x.setChecked(True)
        form.addRow("Drag 3D arrow:", axis_layout)

        # Translation
        self.spn_dx = ExprDoubleSpinBox()
        self.spn_dx.setRange(-10000.0, 10000.0)
        self.spn_dx.setDecimals(2)
        self.spn_dx.setSuffix(" mm")
        self.spn_dx.setValue(0.0)
        form.addRow("Move X (dx):", self.spn_dx)

        self.spn_dy = ExprDoubleSpinBox()
        self.spn_dy.setRange(-10000.0, 10000.0)
        self.spn_dy.setDecimals(2)
        self.spn_dy.setSuffix(" mm")
        self.spn_dy.setValue(0.0)
        form.addRow("Move Y (dy):", self.spn_dy)

        self.spn_dz = ExprDoubleSpinBox()
        self.spn_dz.setRange(-10000.0, 10000.0)
        self.spn_dz.setDecimals(2)
        self.spn_dz.setSuffix(" mm")
        self.spn_dz.setValue(0.0)
        form.addRow("Move Z (dz):", self.spn_dz)

        # Pivot point for rotation
        self.cmb_pivot = QComboBox()
        self.cmb_pivot.addItems(["Body Center (Kroppens mitt)", "World Origin (Origo 0,0,0)"])
        form.addRow("Rotations-pivot:", self.cmb_pivot)

        # Rotation
        self.spn_rx = ExprDoubleSpinBox()
        self.spn_rx.setRange(-3600.0, 3600.0)
        self.spn_rx.setDecimals(2)
        self.spn_rx.setSuffix(" °")
        self.spn_rx.setValue(0.0)
        form.addRow("Rotate X (rx):", self.spn_rx)

        self.spn_ry = ExprDoubleSpinBox()
        self.spn_ry.setRange(-3600.0, 3600.0)
        self.spn_ry.setDecimals(2)
        self.spn_ry.setSuffix(" °")
        self.spn_ry.setValue(0.0)
        form.addRow("Rotate Y (ry):", self.spn_ry)

        self.spn_rz = ExprDoubleSpinBox()
        self.spn_rz.setRange(-3600.0, 3600.0)
        self.spn_rz.setDecimals(2)
        self.spn_rz.setSuffix(" °")
        self.spn_rz.setValue(0.0)
        form.addRow("Rotate Z (rz):", self.spn_rz)

        # Lay a face flat: click a face of the body and the rotation and height below are filled in for you
        self.btn_lay = QPushButton("Lay a face on the ground…")
        self.btn_lay.setCheckable(True)
        self.btn_lay.setToolTip("Then click the face in the 3D view that should rest on the ground (XY plane). "
                                "The rotation and height are filled in below; adjust them or press OK.")
        form.addRow("Lay on plane:", self.btn_lay)

        self.main_layout.addLayout(form)
        self.add_buttons()

        def set_x():
            self.set_active_axis("X")
        def set_y():
            self.set_active_axis("Y")
        def set_z():
            self.set_active_axis("Z")

        self.btn_axis_x.clicked.connect(set_x)
        self.btn_axis_y.clicked.connect(set_y)
        self.btn_axis_z.clicked.connect(set_z)

        self.spn_dx.editingFinished.connect(set_x)
        self.spn_dy.editingFinished.connect(set_y)
        self.spn_dz.editingFinished.connect(set_z)

        for spn in (self.spn_dx, self.spn_dy, self.spn_dz, self.spn_rx, self.spn_ry, self.spn_rz):
            spn.valueChanged.connect(lambda *_: self.changed.emit())
        self.cmb_pivot.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.cmb_target.currentIndexChanged.connect(lambda *_: self.changed.emit())

    def set_active_axis(self, axis: str):
        self.active_axis = axis
        self.btn_axis_x.setChecked(axis == "X")
        self.btn_axis_y.setChecked(axis == "Y")
        self.btn_axis_z.setChecked(axis == "Z")
        self.axis_changed.emit(axis)

    def set_active_axis_value(self, val: float):
        if self.active_axis == "X":
            self.spn_dx.setValue(val)
        elif self.active_axis == "Y":
            self.spn_dy.setValue(val)
        elif self.active_axis == "Z":
            self.spn_dz.setValue(val)

    def select_body(self, body_id: str):
        if body_id in self.body_ids:
            idx = self.body_ids.index(body_id)
            self.cmb_target.setCurrentIndex(idx)

    def get_values(self):
        b_idx = self.cmb_target.currentIndex()
        if b_idx < 0 or b_idx >= len(self.body_ids):
            return None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "center", {}
        bid = self.body_ids[b_idx]
        pivot = "center" if self.cmb_pivot.currentIndex() == 0 else "origin"
        exprs = {}
        for k, spn in (("dx", self.spn_dx), ("dy", self.spn_dy), ("dz", self.spn_dz),
                       ("rx", self.spn_rx), ("ry", self.spn_ry), ("rz", self.spn_rz)):
            if spn.expression():
                exprs[k] = spn.expression()
        return (bid, self.spn_dx.value(), self.spn_dy.value(), self.spn_dz.value(),
                self.spn_rx.value(), self.spn_ry.value(), self.spn_rz.value(), pivot, exprs)

    def get_expressions(self) -> Dict[str, str]:
        exprs = {}
        for k, spn in (("dx", self.spn_dx), ("dy", self.spn_dy), ("dz", self.spn_dz),
                       ("rx", self.spn_rx), ("ry", self.spn_ry), ("rz", self.spn_rz)):
            if spn.expression():
                exprs[k] = spn.expression()
        return exprs
