"""
Omacad - Floating Sketch Palette
Fusion 360 style floating palette for sketch controls, snap toggles, and view orientation.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QFrame, QToolButton
)
from omacad.ui.theme import style


class SketchPalette(QFrame):
    """Floating toolbox overlay on the canvas during sketch mode."""

    finish_clicked = Signal()
    look_at_clicked = Signal()
    settings_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(200)
        style(self, """
            QFrame {
                background-color: rgba(30, 34, 40, 240);
                border: 1px solid #3E4550;
                border-radius: 6px;
            }
            QLabel {
                color: #D2D6DC;
                font-size: 11px;
            }
            QCheckBox {
                color: #D2D6DC;
                font-size: 11px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #4B5563;
                background-color: #1F242C;
            }
            QCheckBox::indicator:checked {
                background-color: #E26D28;
                border-color: #E26D28;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel("SKETCH PALETTE  ⠿")
        lbl_title.setToolTip("Drag to move")
        lbl_title.setCursor(Qt.CursorShape.SizeAllCursor)
        style(lbl_title, "font-weight: bold; font-size: 10px; color: #9AA0A6; letter-spacing: 0.5px;")
        header.addWidget(lbl_title)
        header.addStretch()

        self.btn_toggle = QToolButton()
        self.btn_toggle.setText("▼")
        self.btn_toggle.setFixedSize(16, 16)
        style(self.btn_toggle, "border: none; color: #8E95A0; font-size: 9px;")
        self.btn_toggle.clicked.connect(self.toggle_collapsed)
        header.addWidget(self.btn_toggle)
        layout.addLayout(header)

        # Content container
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(6)

        # Checkboxes
        self.chk_snap_grid = QCheckBox("Snap to Grid")
        self.chk_snap_grid.setChecked(True)
        self.chk_snap_grid.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_snap_grid)

        self.chk_snap_points = QCheckBox("Snap to Points")
        self.chk_snap_points.setChecked(True)
        self.chk_snap_points.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_snap_points)

        self.chk_auto_constraints = QCheckBox("Auto Constraints")
        self.chk_auto_constraints.setToolTip("Add Horizontal/Vertical/Coincident constraints automatically when drawing lines")
        self.chk_auto_constraints.setChecked(True)
        self.chk_auto_constraints.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_auto_constraints)

        self.chk_show_constraints = QCheckBox("Show All Constraints")
        self.chk_show_constraints.setToolTip("Normally constraint symbols are shown only for selected or hovered elements")
        self.chk_show_constraints.setChecked(False)
        self.chk_show_constraints.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_show_constraints)

        self.chk_show_dims = QCheckBox("Show Dimensions")
        self.chk_show_dims.setChecked(True)
        self.chk_show_dims.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_show_dims)

        self.chk_show_profiles = QCheckBox("Shaded Profiles")
        self.chk_show_profiles.setChecked(True)
        self.chk_show_profiles.stateChanged.connect(self.settings_changed)
        content_layout.addWidget(self.chk_show_profiles)

        content_layout.addSpacing(4)

        # Look At Button
        btn_look_at = QPushButton("🎯  Look at Plane")
        style(btn_look_at, """
            QPushButton {
                background-color: #2D333B;
                border: 1px solid #444C56;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                color: #E0E3E7;
            }
            QPushButton:hover {
                background-color: #373E47;
                border-color: #57606A;
            }
        """)
        btn_look_at.clicked.connect(self.look_at_clicked)
        content_layout.addWidget(btn_look_at)

        content_layout.addSpacing(6)

        # Finish Sketch Button
        btn_finish = QPushButton("✅  Finish Sketch")
        style(btn_finish, """
            QPushButton {
                background-color: #2E7D32;
                border: 1px solid #388E3C;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #1B5E20;
            }
        """)
        btn_finish.clicked.connect(self.finish_clicked)
        content_layout.addWidget(btn_finish)

        layout.addWidget(self.content_widget)

    # ---- Dragging: grab the palette anywhere that is not a control ----------
    def place_default(self, parent_size):
        """Top-right corner until the user has moved it; afterwards just keep it on screen."""
        if not getattr(self, "user_moved", False):
            self.move(parent_size.width() - self.width() - 24, 140)
        else:
            self._clamp(parent_size)

    def _clamp(self, parent_size):
        x = max(0, min(self.x(), parent_size.width() - self.width()))
        y = max(0, min(self.y(), parent_size.height() - 30))
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_offset", None) is not None and event.buttons() & Qt.MouseButton.LeftButton:
            top_left = self.mapToParent(event.position().toPoint() - self._drag_offset)
            self.move(top_left)
            self.user_moved = True
            if self.parentWidget():
                self._clamp(self.parentWidget().size())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def toggle_collapsed(self):
        is_visible = self.content_widget.isVisible()
        self.content_widget.setVisible(not is_visible)
        self.btn_toggle.setText("▶" if is_visible else "▼")
        self.adjustSize()
