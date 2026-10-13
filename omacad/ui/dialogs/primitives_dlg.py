"""Dialogs for primitive 3D solid bodies: Box, Cylinder, Sphere."""

from PySide6.QtWidgets import QFormLayout, QCheckBox
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


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
