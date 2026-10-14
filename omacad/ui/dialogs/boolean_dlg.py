"""Dialogs for Boolean operations: Combine (Join, Cut, Intersect) and Split Body."""

from typing import Optional
import numpy as np
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel
from omacad.model.document import Document
from omacad.ui.dialogs.base import BaseFeatureDialog


class CombineDialog(BaseFeatureDialog):
    """Dialog for boolean combine operations (Join, Cut, Intersect)."""

    def __init__(self, doc: Document, parent=None, preselected_target_id: Optional[str] = None):
        super().__init__("Combine Bodies", parent)
        self.doc = doc
        form = QFormLayout()

        self.body_ids = list(doc.bodies.keys())
        names = [doc.bodies[bid].name for bid in self.body_ids]

        self.cmb_target = QComboBox()
        self.cmb_target.addItems(names)
        if preselected_target_id and preselected_target_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(preselected_target_id))
        elif doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(doc.selected_body_ids[0]))
        form.addRow("Target Body:", self.cmb_target)

        self.cmb_tool = QComboBox()
        self.cmb_tool.addItems(names)
        t_idx = self.cmb_target.currentIndex()
        if len(names) > 1:
            tool_idx = 1 if t_idx == 0 else 0
            self.cmb_tool.setCurrentIndex(tool_idx)
        form.addRow("Tool Body:", self.cmb_tool)

        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Join (Union)", "Cut (Difference)", "Intersect"])
        form.addRow("Operation:", self.cmb_op)

        # Keep Tool Bodies checkbox (Fusion 360 style)
        from PySide6.QtWidgets import QCheckBox
        self.chk_keep_tool = QCheckBox("Keep tool bodies (Behåll verktygskropp)")
        self.chk_keep_tool.setChecked(False)
        form.addRow("", self.chk_keep_tool)

        self.main_layout.addLayout(form)
        self.add_buttons()

        self._active_field = "tool"  # clicking 3D body updates tool unless user focused target

    def select_body(self, body_id: str):
        if body_id not in self.body_ids:
            return
        # If clicked body is target, set target; otherwise set tool
        cur_target = self.body_ids[self.cmb_target.currentIndex()] if self.body_ids else None
        if cur_target == body_id:
            # User clicked target again or wants to change target
            pass
        elif self._active_field == "target":
            self.cmb_target.setCurrentIndex(self.body_ids.index(body_id))
            self._active_field = "tool"
        else:
            self.cmb_tool.setCurrentIndex(self.body_ids.index(body_id))

    def get_values(self):
        t_idx = self.cmb_target.currentIndex()
        tool_idx = self.cmb_tool.currentIndex()
        if not self.body_ids or t_idx < 0 or tool_idx < 0 or t_idx == tool_idx:
            return None, None, "join", False

        target_id = self.body_ids[t_idx]
        tool_id = self.body_ids[tool_idx]
        op_map = {0: "join", 1: "cut", 2: "intersect"}
        op = op_map.get(self.cmb_op.currentIndex(), "join")
        keep = self.chk_keep_tool.isChecked()
        return target_id, tool_id, op, keep


class SplitBodyDialog(BaseFeatureDialog):
    """Dialog to split a body using an offset (construction) plane or origin plane into two bodies."""

    def __init__(self, doc: Document, parent=None, preselected_body_id: Optional[str] = None, preselected_plane_id: Optional[str] = None):
        super().__init__("Split Body", parent)
        self.doc = doc
        form = QFormLayout()

        # Target Body
        self.body_ids = list(doc.bodies.keys())
        body_names = [doc.bodies[bid].name for bid in self.body_ids]
        self.cmb_target = QComboBox()
        self.cmb_target.addItems(body_names)
        if preselected_body_id and preselected_body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(preselected_body_id))
        elif doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(doc.selected_body_ids[0]))
        form.addRow("Target Body:", self.cmb_target)

        # Splitting Plane
        self.plane_keys = []
        plane_labels = []
        # Construction planes (offset planes) first
        for pid, cp in doc.construction_planes.items():
            self.plane_keys.append(pid)
            plane_labels.append(f"📐 {cp['name']}")
        # Origin planes
        for op in ("XY", "XZ", "YZ"):
            self.plane_keys.append(op)
            plane_labels.append(f"🌐 {op} Plane")

        self.cmb_plane = QComboBox()
        self.cmb_plane.addItems(plane_labels)
        if preselected_plane_id and preselected_plane_id in self.plane_keys:
            self.cmb_plane.setCurrentIndex(self.plane_keys.index(preselected_plane_id))
        form.addRow("Splitting Plane:", self.cmb_plane)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        form.addRow(self.lbl_status)

        self.main_layout.addLayout(form)
        self.add_buttons()

        self.cmb_target.currentIndexChanged.connect(self._update_status)
        self.cmb_plane.currentIndexChanged.connect(self._update_status)
        self._update_status()

    def _update_status(self):
        body_id, plane_id = self.get_values()
        if not body_id or not plane_id:
            self.lbl_status.setText("Select a body and a plane to split.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        body = self.doc.bodies.get(body_id)
        if not body:
            self.lbl_status.setText("Body not found.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        origin, normal = None, None
        if plane_id in self.doc.construction_planes:
            cp = self.doc.construction_planes[plane_id]
            origin = np.array(cp["origin"], dtype=float)
            normal = np.array(cp["normal"], dtype=float)
        elif plane_id in self.doc.origin_planes:
            op = self.doc.origin_planes[plane_id]
            origin = np.array(op.origin, dtype=float)
            normal = np.array(op.normal, dtype=float)

        if origin is None or normal is None:
            self.lbl_status.setText("Plane not found.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return
        normal = normal / norm
        d = float(np.dot(normal, origin))

        # Check cut
        p1 = body.manifold.trim_by_plane(normal, d)
        p2 = body.manifold.trim_by_plane(-normal, -d)
        if p1.is_empty() or p2.is_empty() or p1.volume() < 1e-6 or p2.volume() < 1e-6:
            self.lbl_status.setText("⚠️ Warning: Plane does not cut through the body.")
            self.lbl_status.setStyleSheet("color: #E57373;")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
        else:
            self.lbl_status.setText(f"✓ Split produces 2 bodies ({p1.volume():.1f} mm³ + {p2.volume():.1f} mm³).")
            self.lbl_status.setStyleSheet("color: #81C784;")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(True)

    def select_body(self, body_id: str):
        if body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(body_id))
            if hasattr(self, "update_preview"):
                self.update_preview()

    def get_values(self):
        b_idx = self.cmb_target.currentIndex()
        p_idx = self.cmb_plane.currentIndex()
        if b_idx < 0 or b_idx >= len(self.body_ids) or p_idx < 0 or p_idx >= len(self.plane_keys):
            return None, None
        return self.body_ids[b_idx], self.plane_keys[p_idx]
