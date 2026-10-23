"""Panel for Sweep, Loft and Pipe (Björn #46): profiles are clicked in the 3D view, the path is a sketch."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel

from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox

OPERATIONS = (("new_body", "New Body"), ("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect"))
TITLES = {"sweep": "Sweep", "loft": "Loft", "pipe": "Pipe"}
HELP = {
    "sweep": "Click the profile to sweep in the 3D view, then choose the sketch that holds the path (its lines and "
             "arcs in one chain, or a circle).",
    "loft": "Click the profiles in the order the loft passes through them (two or more, on different planes). "
            "Click a profile again to drop it.",
    "pipe": "Choose the sketch that holds the path (its lines and arcs in one chain, or a circle) and the diameter; "
            "a wall thickness makes it a tube.",
}


def path_entities(sketch) -> list:
    """The elements of a sketch that make a path: drawn lines, arcs and circles (not construction or face edges)."""
    from omacad.model.sketch_entities import SketchArc, SketchCircle, SketchLine
    return [e.entity_id for e in sketch.entities
            if isinstance(e, (SketchLine, SketchArc, SketchCircle))
            and not getattr(e, "is_construction", False) and not getattr(e, "projected", False)]


class SweepLoftDialog(BaseFeatureDialog):
    changed = Signal()

    def __init__(self, doc, mode: str, parent=None, embedded: bool = False):
        super().__init__(TITLES[mode], parent, embedded)
        self.doc, self.mode = doc, mode
        info = QLabel(HELP[mode])
        info.setWordWrap(True)
        self.main_layout.addWidget(info)
        form = QFormLayout()
        self.lbl_profiles = QLabel("")
        if mode != "pipe":
            form.addRow("Profile:" if mode == "sweep" else "Profiles:", self.lbl_profiles)
        self.cmb_path = QComboBox()
        if mode != "loft":
            for sid, sk in doc.sketches.items():
                if sk is not doc.active_sketch and path_entities(sk):
                    self.cmb_path.addItem(sk.name, sid)
            self.cmb_path.setCurrentIndex(self.cmb_path.count() - 1)      # the newest sketch: usually the path
            self.cmb_path.currentIndexChanged.connect(lambda *_: self.changed.emit())
            form.addRow("Path:", self.cmb_path)
        self.spn_diam = self._spin(5.0, 0.01, 10000.0, " mm", "Outside diameter of the pipe")
        self.spn_thick = self._spin(0.0, 0.0, 5000.0, " mm", "Wall thickness (0 = solid rod)")
        self.spn_twist = self._spin(0.0, -3600.0, 3600.0, " °", "Turn the profile this much from start to end")
        if mode == "pipe":
            form.addRow("Diameter:", self.spn_diam)
            form.addRow("Wall:", self.spn_thick)
        if mode == "sweep":
            form.addRow("Twist:", self.spn_twist)
        self.cmb_op = QComboBox()
        for _key, label in OPERATIONS:
            self.cmb_op.addItem(label)
        self.cmb_op.currentIndexChanged.connect(lambda *_: self.changed.emit())
        form.addRow("Operation:", self.cmb_op)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addLayout(form)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self.profiles = []                  # [(sketch id, profile index)] in pick order
        self.set_profiles([])
        if mode == "pipe":
            QTimer.singleShot(0, self, self.focus_primary)

    def _spin(self, value, lo, hi, suffix, tip):
        s = ExprDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSuffix(suffix)
        s.setValue(value)
        s.setToolTip(tip)
        s.valueChanged.connect(lambda *_: self.changed.emit())
        return s

    def set_profiles(self, profiles):
        self.profiles = list(profiles)
        names = [self.doc.sketches[s].name for s, _ in self.profiles if s in self.doc.sketches]
        if self.mode == "sweep":
            self.lbl_profiles.setText(names[0] if names else "click a profile")
        else:
            self.lbl_profiles.setText(" → ".join(names) if names else "click the first profile")
        self.changed.emit()

    def path(self):
        sid = self.cmb_path.currentData()
        if sid is None or sid not in self.doc.sketches:
            return None
        return (sid, path_entities(self.doc.sketches[sid]))

    def operation(self) -> str:
        return OPERATIONS[max(self.cmb_op.currentIndex(), 0)][0]

    def get_expressions(self) -> dict:
        out = {}
        for key, spin in (("diameter", self.spn_diam), ("thickness", self.spn_thick), ("twist", self.spn_twist)):
            e = spin.expression()
            if e:
                out[key] = e
        return out
