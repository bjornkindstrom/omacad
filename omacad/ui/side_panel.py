"""
Omacad - Right-Hand Inspector & Tool Host Panel
Provides a persistent right-hand dock for tool dialogs (Extrude, Fillet, Shell, etc.)
and displays live properties for bodies, sketches, measurements, and document statistics,
eliminating intrusive floating windows that block the 3D model.
"""

from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QGroupBox, QFormLayout
)
from omacad.model.document import Document
from omacad.ui import theme
from omacad.ui.theme import style


class InspectorPanel(QWidget):
    """Right-hand side panel hosting active tool dialogs and live model/sketch properties."""

    tool_action_requested = Signal(str, object)  # e.g. ("extrude", body_id), ("fillet", None)

    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setFixedWidth(340)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header Bar
        self.header = QWidget()
        style(self.header, "background-color: #202225; border-bottom: 1px solid #33373D; padding: 6px 10px;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_title = QLabel("INSPECTOR")
        style(self.lbl_title, "font-weight: bold; font-size: 11px; color: #8E95A0; letter-spacing: 0.5px;")
        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch()
        main_layout.addWidget(self.header)

        # Scroll Area for Content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        style(self.scroll, "background-color: #24272C; border: none;")

        self.content_widget = QWidget()
        style(self.content_widget, "background-color: #24272C;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)

        # 1. Tool Dock Container (when a tool/dialog is active)
        self.tool_container = QWidget()
        self.tool_layout = QVBoxLayout(self.tool_container)
        self.tool_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_layout.setSpacing(6)
        self.tool_container.hide()
        self.content_layout.addWidget(self.tool_container)

        # 2. Properties & Info Container (when no tool is active or context info)
        self.info_container = QWidget()
        self.info_layout = QVBoxLayout(self.info_container)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(8)
        self.content_layout.addWidget(self.info_container)

        self.content_layout.addStretch()
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll)

        self.current_tool_dlg = None
        self.refresh_info()

    def dock_tool(self, dlg):
        """Docks a tool dialog into the side panel."""
        if self.current_tool_dlg is dlg:
            return

        if self.current_tool_dlg is not None:
            self.undock_tool(self.current_tool_dlg)

        self.current_tool_dlg = dlg
        dlg._embedded = False
        dlg.setParent(self.tool_container)
        dlg.setWindowFlags(Qt.WindowType.Widget)
        dlg.setMinimumWidth(0)
        dlg.setFixedWidth(318)
        dlg.unsetCursor()

        self.tool_layout.addWidget(dlg)
        self.tool_container.show()
        self.lbl_title.setText(f"🛠️ {dlg.windowTitle().upper()}")
        dlg.show()

        # Hide background info when tool is active for clean focused UI
        self.info_container.hide()

        def on_finished(*_):
            self.undock_tool(dlg)

        dlg.finished.connect(on_finished)

    def undock_tool(self, dlg=None):
        if dlg is None:
            dlg = self.current_tool_dlg
        if dlg is not None and self.current_tool_dlg is dlg:
            self.tool_layout.removeWidget(dlg)
            dlg.hide()
            self.current_tool_dlg = None
            self.tool_container.hide()
            self.lbl_title.setText("INSPECTOR")
            self.info_container.show()
            self.refresh_info()

    def _make_card(self, title: str, layout) -> QFrame:
        card = QFrame()
        style(card, "QFrame { background-color: #1E2126; border: 1px solid #333842; border-radius: 6px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(6)

        lbl_header = QLabel(title.upper())
        style(lbl_header, "font-size: 11px; font-weight: bold; color: #E26D28; letter-spacing: 0.5px; border: none; background: transparent;")
        card_layout.addWidget(lbl_header)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        style(div, "background-color: #2D323B; height: 1px; border: none;")
        card_layout.addWidget(div)

        card_layout.addLayout(layout)
        return card

    def refresh_info(self, selected_entities=None, measure_info=None):
        """Updates the context info based on document, selection, or sketch state."""
        # Clear existing info widgets
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # A. Measure active?
        if measure_info:
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)
            for line in measure_info:
                lbl = QLabel(line)
                style(lbl, "color: #FFC83B; font-weight: bold; font-size: 13px; border: none; background: transparent;")
                form.addRow(lbl)
            self.info_layout.addWidget(self._make_card("📏 Mätresultat (Measure)", form))
            return

        # B. Sketch mode active?
        sk = self.doc.active_sketch
        if sk is not None:
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)

            plane_name = sk.plane.name if hasattr(sk.plane, "name") else "Sketch Plane"
            form.addRow("Plan:", QLabel(plane_name))

            status_str = self.doc.sketch_status(sk)
            lbl_status = QLabel(status_str or "Under defined")
            if "Fully" in status_str:
                style(lbl_status, "color: #66BB6A; font-weight: bold; border: none; background: transparent;")
            else:
                style(lbl_status, "color: #FFA726; border: none; background: transparent;")
            form.addRow("Status:", lbl_status)

            form.addRow("Element:", QLabel(f"{len(sk.entities)} st"))
            form.addRow("Villkor:", QLabel(f"{len(sk.constraints)} st"))
            form.addRow("Mått:", QLabel(f"{len(sk.dimensions)} st"))
            form.addRow("Profiler:", QLabel(f"{len(sk.profiles)} st"))

            if selected_entities:
                n_sel = len(selected_entities)
                lbl_sel = QLabel(f"{n_sel} element markerade")
                style(lbl_sel, "color: #42A5F5; font-weight: bold; border: none; background: transparent;")
                form.addRow("Markering:", lbl_sel)

            self.info_layout.addWidget(self._make_card(f"✏️ Skiss: {sk.name}", form))
            return

        # C. Body selected?
        selected_bodies = [self.doc.bodies[bid] for bid in self.doc.selected_body_ids if bid in self.doc.bodies]
        if selected_bodies:
            body = selected_bodies[0]
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)

            vol = body.manifold.volume()
            area = body.manifold.surface_area()
            bbox = body.manifold.bounding_box()
            dx = bbox[3] - bbox[0]
            dy = bbox[4] - bbox[1]
            dz = bbox[5] - bbox[2]

            lbl_vol = QLabel(f"{vol:,.1f} mm³".replace(",", " "))
            style(lbl_vol, "color: #E0E0E0; font-weight: bold; border: none; background: transparent;")
            form.addRow("Volym:", lbl_vol)

            lbl_area = QLabel(f"{area:,.1f} mm²".replace(",", " "))
            form.addRow("Yta:", lbl_area)

            form.addRow("Storlek:", QLabel(f"{dx:.1f} × {dy:.1f} × {dz:.1f} mm"))
            form.addRow("Plana ytor:", QLabel(f"{len(body.faces)} st"))
            form.addRow("Kanter:", QLabel(f"{len(body.edges)} st"))

            self.info_layout.addWidget(self._make_card(f"📦 Kropp: {body.name}", form))
            return

        # D. Document Overview (Nothing specifically selected)
        form_doc = QFormLayout()
        form_doc.setContentsMargins(0, 4, 0, 0)
        form_doc.setSpacing(6)
        form_doc.addRow("Dokument:", QLabel(self.doc.name))
        form_doc.addRow("Bodies:", QLabel(f"{len(self.doc.bodies)} st"))
        form_doc.addRow("Skisser:", QLabel(f"{len(self.doc.sketches)} st"))
        form_doc.addRow("Features:", QLabel(f"{len(self.doc.timeline.features)} st"))
        form_doc.addRow("Offset-plan:", QLabel(f"{len(self.doc.construction_planes)} st"))
        if hasattr(self.doc, "canvases"):
            form_doc.addRow("Canvases:", QLabel(f"{len(self.doc.canvases)} st"))
        self.info_layout.addWidget(self._make_card("📋 Designöversikt", form_doc))

        # Quick tips
        v_tips = QVBoxLayout()
        v_tips.setContentsMargins(0, 4, 0, 0)
        v_tips.setSpacing(4)
        tips = [
            "E - Extrudera profil",
            "F - Fit View / Centrera",
            "I - Mätverktyg (Measure)",
            "Ctrl+P - Parametrar",
            "Högerklick yta - Skissa / Extrudera",
            "Högerklick plan - Splitta body / Skissa",
        ]
        for tip in tips:
            lbl = QLabel(tip)
            style(lbl, "color: #8E95A0; font-size: 11px; border: none; background: transparent;")
            v_tips.addWidget(lbl)
        self.info_layout.addWidget(self._make_card("⚡ Snabbkommandon", v_tips))
