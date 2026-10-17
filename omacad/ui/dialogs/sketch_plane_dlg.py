"""Dialogs for selecting sketch planes and offset construction planes."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel, QHBoxLayout, QPushButton
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox


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

    def get_distance(self) -> float:
        return self.spn_dist.value()

    def get_expressions(self) -> dict:
        e = self.spn_dist.expression()
        return {"distance": e} if e else {}
