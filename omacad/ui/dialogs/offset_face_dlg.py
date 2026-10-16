"""Dialog for Offset Face: pick faces in the viewport, type how far they move."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog

HINT = ("Click flat faces, holes or pins in the viewport (click again to deselect). "
        "Plus moves the face out of the body (adds material, a hole gets smaller), minus moves it in.")


class OffsetFaceDialog(BaseFeatureDialog):
    """Offset Face: the faces are picked in the viewport, the distance is typed here."""

    changed = Signal()

    def __init__(self, parent=None, distance: float = 0.2, editing: bool = False, embedded: bool = False):
        super().__init__("Offset Face", parent, embedded)
        self.faces = []          # face references, see offset_face.plane_face_ref / cylinder_face_ref
        self.body_id = ""        # the body the faces belong to
        form = QFormLayout()
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-1000.0, 1000.0)
        self.spn_dist.setDecimals(3)
        self.spn_dist.setSingleStep(0.05)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.setValue(distance)
        self.spn_dist.setToolTip("Distance in mm. Formulas and parameter names work. Negative moves the face into the body.")
        form.addRow("Distance:", self.spn_dist)
        self.lbl_count = QLabel("" if editing else HINT)
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)
        self.main_layout.addLayout(form)
        if not editing:
            btn = QPushButton("Clear selection")
            btn.clicked.connect(self.clear)
            self.main_layout.addWidget(btn)
        self.add_buttons()
        self.spn_dist.valueChanged.connect(lambda *_: self.changed.emit())
        QTimer.singleShot(0, lambda: (self.spn_dist.setFocus(), self.spn_dist.selectAll()))

    @staticmethod
    def _same(a, b) -> bool:
        import numpy as np
        if a["kind"] != b["kind"]:
            return False
        keys = ("normal", "origin") if a["kind"] == "plane" else ("origin", "axis")
        return all(np.allclose(a[k], b[k], atol=1e-3) for k in keys)

    def toggle(self, ref: dict, body_id: str) -> bool:
        """Adds the face (or removes it when already picked). False when it belongs to another body."""
        if self.faces and body_id != self.body_id:
            return False
        for i, f in enumerate(self.faces):
            if self._same(f, ref):
                self.faces.pop(i)
                break
        else:
            self.faces.append(ref)
        self.body_id = body_id if self.faces else ""
        self._update_count()
        self.changed.emit()
        return True

    def clear(self):
        self.faces, self.body_id = [], ""
        self._update_count()
        self.changed.emit()

    def _update_count(self):
        n = len(self.faces)
        self.lbl_count.setText(f"{n} face{'s' if n != 1 else ''} selected. Click faces to add or remove them." if n else HINT)

    def distance(self) -> float:
        return self.spn_dist.value()

    def get_expressions(self) -> dict:
        e = self.spn_dist.expression()
        return {"distance": e} if e else {}
