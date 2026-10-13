"""Base modal dialog and docking runner for Omacad feature dialogs."""

from typing import Optional
from PySide6.QtCore import Qt, QEventLoop
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton
)
from omacad.ui.theme import style

# The main window's right-hand panel; every tool dialog is docked there so none covers the model.
SIDE_HOST = None


def run_docked(dlg) -> int:
    """Like dlg.exec(), but the dialog sits in the side panel and a local event loop waits for it."""
    if SIDE_HOST is None:
        return QDialog.exec(dlg)
    SIDE_HOST.dock(dlg)
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    loop.exec()
    return dlg.result()


class BaseFeatureDialog(QDialog):
    """Base modal dialog with Fusion 360 styling."""

    def __init__(self, title: str, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._embedded = embedded
        self._drag_offset = None
        self.user_moved = False
        if embedded:
            # a panel inside the 3D view instead of a separate window: it can be dragged out of the way
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setFixedWidth(290)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setFixedWidth(320)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        style(self, """
            QDialog {
                background-color: #25282C;
                border: 1px solid #3E444D;
                border-radius: 6px;
            }
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

    # ---- embedded panel: placement and dragging ------------------------------------
    def exec(self):
        return run_docked(self)

    def place(self, parent_size, left: bool = False):
        """Dock into the side panel (or, without one, the right side of the view until dragged)."""
        if SIDE_HOST is not None:
            SIDE_HOST.dock(self)
            return
        self.adjustSize()
        if not self.user_moved:
            x = 24 if left else max(0, parent_size.width() - self.width() - 24)
            self.move(x, 150)

    def mousePressEvent(self, event):
        if self._embedded and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._embedded and self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.mapToParent(event.position().toPoint() - self._drag_offset))
            self.user_moved = True
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def add_buttons(self):
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("PrimaryButton")
        self.btn_ok.setDefault(True)  # Enter confirms, as in Fusion
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        self.main_layout.addLayout(btn_layout)
