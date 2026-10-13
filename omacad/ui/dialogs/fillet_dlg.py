"""Dialog for RoundEdges (Fillet and Chamfer)."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


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
        self.lbl_count = QLabel("" if editing else "Click edges in the viewport to select them (click again to deselect). X = see-through for hidden edges, double-click = whole loop, Shift+double-click = loop on the other face, Backspace = undo last, Ctrl+Backspace = clear.")
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
                               if n else "Click edges in the viewport to select them (click again to deselect). X = see-through for hidden edges, double-click = whole loop, Shift+double-click = loop on the other face, Backspace = undo last, Ctrl+Backspace = clear.")

    def get_expressions(self) -> dict:
        e = self.spn_size.expression()
        return {"size": e} if e else {}
