"""
Omacad - Thread & Coil Dialog
3D-Print optimized parametric thread dialog, docked in the right side panel.
"""

from typing import Optional, Any
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QCheckBox, QLabel, QHBoxLayout, QPushButton, QGroupBox, QVBoxLayout
)
from PySide6.QtCore import Signal
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


# Standard 3D-printing friendly thread presets: (Name, Dia, Pitch)
THREAD_PRESETS = [
    ("Custom", 0.0, 0.0),
    ("M6  (Pitch 1.25 mm)", 6.0, 1.25),
    ("M8  (Pitch 1.50 mm)", 8.0, 1.50),
    ("M10 (Pitch 2.00 mm)", 10.0, 2.00),
    ("M12 (Pitch 2.00 mm)", 12.0, 2.00),
    ("M14 (Pitch 2.00 mm)", 14.0, 2.00),
    ("M16 (Pitch 2.50 mm)", 16.0, 2.50),
    ("M20 (Pitch 2.50 mm)", 20.0, 2.50),
    ("M24 (Pitch 3.00 mm)", 24.0, 3.00),
    ("M30 (Pitch 3.50 mm)", 30.0, 3.50),
]


class ThreadDialog(BaseFeatureDialog):
    """Dialog for creating 3D-printable or CAD threads and coils."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, doc: Document, parent=None, preselected_body_id: Optional[str] = None):
        super().__init__("Create Thread / Coil", parent)
        self.doc = doc
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        self.body_ids = list(doc.bodies.keys())
        body_names = [doc.bodies[bid].name for bid in self.body_ids]

        form = QFormLayout()

        # Thread Type (Male bolt or Female nut/hole)
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("Male (Yttergänga / Bult)", False)
        self.cmb_type.addItem("Female (Innergänga / Hål/Mutter)", True)
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Thread Type:", self.cmb_type)

        # Presets
        self.cmb_preset = QComboBox()
        for name, dia, p in THREAD_PRESETS:
            self.cmb_preset.addItem(name, (dia, p))
        self.cmb_preset.setCurrentIndex(3)  # default to M10
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self.cmb_preset)

        # Diameter
        self.spn_dia = ExprDoubleSpinBox()
        self.spn_dia.setRange(1.0, 500.0)
        self.spn_dia.setValue(10.0)
        self.spn_dia.setSuffix(" mm")
        self.spn_dia.valueChanged.connect(self._on_dim_changed)
        form.addRow("Diameter (D):", self.spn_dia)

        # Pitch
        self.spn_pitch = ExprDoubleSpinBox()
        self.spn_pitch.setRange(0.2, 50.0)
        self.spn_pitch.setValue(2.0)
        self.spn_pitch.setSuffix(" mm")
        self.spn_pitch.valueChanged.connect(self._on_dim_changed)
        form.addRow("Pitch (Stigning):", self.spn_pitch)

        # Length
        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(0.5, 2000.0)
        self.spn_length.setValue(25.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Length (Längd):", self.spn_length)

        # Target Body / Application Mode
        self.cmb_target = QComboBox()
        self.cmb_target.addItem("New Body (Ny fristående kropp)", None)
        for bid, bname in zip(self.body_ids, body_names):
            self.cmb_target.addItem(f"Apply to: {bname}", bid)
        if preselected_body_id and preselected_body_id in self.body_ids:
            idx = self.cmb_target.findData(preselected_body_id)
            if idx >= 0:
                self.cmb_target.setCurrentIndex(idx)
        self.cmb_target.currentIndexChanged.connect(self._on_target_changed)
        form.addRow("Target:", self.cmb_target)

        # 3D Printing Optimizations Group
        grp_3d = QGroupBox("3D Print Optimeringar")
        grp_lay = QVBoxLayout(grp_3d)

        self.chk_profile = QCheckBox("45° Trapezoidal (Printbar utan support)")
        self.chk_profile.setChecked(True)
        self.chk_profile.setToolTip("45° vinkel på gängflankerna eliminerar överhäng som säckar ihop i FDM-print.")
        self.chk_profile.toggled.connect(lambda _: self.changed.emit())
        grp_lay.addWidget(self.chk_profile)

        # Clearance row
        clr_layout = QHBoxLayout()
        clr_label = QLabel("Clearance (Tolerans):")
        self.spn_clearance = ExprDoubleSpinBox()
        self.spn_clearance.setRange(0.0, 2.0)
        self.spn_clearance.setSingleStep(0.05)
        self.spn_clearance.setValue(0.25)
        self.spn_clearance.setSuffix(" mm")
        self.spn_clearance.setToolTip("Standard 0.25 mm ger perfekt passning på en 0.4mm nozzle FDM-skrivare.")
        self.spn_clearance.valueChanged.connect(lambda _: self.changed.emit())
        clr_layout.addWidget(clr_label)
        clr_layout.addWidget(self.spn_clearance)
        grp_lay.addLayout(clr_layout)

        self.chk_taper = QCheckBox("Smooth Lead-in & Runout Taper")
        self.chk_taper.setChecked(True)
        self.chk_taper.setToolTip("Fasar in och ut gängans start och slut så bulten glider i muttern utan att skära snett.")
        self.chk_taper.toggled.connect(lambda _: self.changed.emit())
        grp_lay.addWidget(self.chk_taper)

        form.addRow(grp_3d)

        # Placement Face button & label
        self.btn_face = QPushButton("Välj yta (Start face…)")
        self.btn_face.setToolTip("Klicka på en yta eller plan i 3D-vyn där gängan ska börja.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        form.addRow("Start Face:", face_row)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def select_body(self, body_id: str):
        """Allows interactive clicking in 3D viewport to update selected body."""
        idx = self.cmb_target.findData(body_id)
        if idx >= 0:
            self.cmb_target.setCurrentIndex(idx)

    def _on_type_changed(self):
        is_female = self.cmb_type.currentData()
        # If female, automatically default operation suggestion to apply on existing body if available
        if is_female and self.cmb_target.currentIndex() == 0 and len(self.body_ids) > 0:
            self.cmb_target.setCurrentIndex(1)
        self.changed.emit()

    def _on_preset_changed(self):
        data = self.cmb_preset.currentData()
        if data and data[0] > 0.0:
            self.spn_dia.blockSignals(True)
            self.spn_pitch.blockSignals(True)
            self.spn_dia.setValue(data[0])
            self.spn_pitch.setValue(data[1])
            self.spn_dia.blockSignals(False)
            self.spn_pitch.blockSignals(False)
        self.changed.emit()

    def _on_dim_changed(self):
        # Switch preset combo to Custom if values don't match
        cur_dia = self.spn_dia.value()
        cur_pitch = self.spn_pitch.value()
        matched = False
        for idx in range(1, self.cmb_preset.count()):
            d, p = self.cmb_preset.itemData(idx)
            if abs(cur_dia - d) < 1e-3 and abs(cur_pitch - p) < 1e-3:
                self.cmb_preset.blockSignals(True)
                self.cmb_preset.setCurrentIndex(idx)
                self.cmb_preset.blockSignals(False)
                matched = True
                break
        if not matched:
            self.cmb_preset.blockSignals(True)
            self.cmb_preset.setCurrentIndex(0)  # Custom
            self.cmb_preset.blockSignals(False)
        self.changed.emit()

    def _on_target_changed(self):
        self.changed.emit()

    def set_plane(self, plane):
        if plane is None:
            self.plane_origin = None
            self.plane_normal = None
            self.plane_u = None
            self.plane_v = None
            self.lbl_face.setText("Default: XY ground plane")
            self.changed.emit()
            return

        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        self.lbl_face.setText(f"{p_name}")
        self.changed.emit()

    def get_values(self):
        is_female = bool(self.cmb_type.currentData())
        target_bid = self.cmb_target.currentData()
        profile_type = "trapezoidal_45" if self.chk_profile.isChecked() else "iso_60"
        op = "cut" if (target_bid and is_female) else ("join" if target_bid else "new_body")

        return {
            "diameter": self.spn_dia.value(),
            "pitch": self.spn_pitch.value(),
            "length": self.spn_length.value(),
            "is_female": is_female,
            "clearance": self.spn_clearance.value(),
            "profile": profile_type,
            "taper_lead_in": self.chk_taper.isChecked(),
            "taper_turns": 0.75,
            "target_body_id": target_bid,
            "operation": op,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
        }
