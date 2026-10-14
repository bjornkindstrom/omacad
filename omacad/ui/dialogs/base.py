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
    """Like dlg.exec(), but the dialog sits cleanly in the right-hand side panel."""
    if SIDE_HOST is None:
        return QDialog.exec(dlg)
    SIDE_HOST.dock(dlg)
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    loop.exec()
    return dlg.result()


class BaseFeatureDialog(QDialog):
    """Base modal dialog with Fusion 360 styling, docked in the right side panel."""

    def __init__(self, title: str, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._embedded = embedded
        self.setFixedWidth(338)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        style(self, """
            QDialog {
                background-color: #25282C;
                border: 1px solid #3E444D;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #33373E;
                color: #E0E3E7;
                border: 1px solid #4D535E;
                border-bottom: 2px solid #25282D;
                border-radius: 5px;
                padding: 7px 18px;
                font-weight: 600;
                font-size: 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #3E434C;
                border-color: #5C6370;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #E26D28;
                border: 1px solid #E26D28;
                border-top: 2px solid #B85317;
                color: #FFFFFF;
                padding-top: 8px;
            }
            QPushButton#PrimaryButton, QPushButton:default {
                background-color: #E26D28;
                border: 1px solid #FF7E36;
                border-bottom: 2px solid #B85317;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 22px;
            }
            QPushButton#PrimaryButton:hover, QPushButton:default:hover {
                background-color: #FF7E36;
                border-color: #FFA566;
                color: #FFFFFF;
            }
            QPushButton#PrimaryButton:pressed, QPushButton:default:pressed {
                background-color: #C45B1C;
                border: 1px solid #B85317;
                border-top: 2px solid #8C3A0A;
                color: #FFFFFF;
                padding-top: 8px;
            }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(12)

    def exec(self):
        return run_docked(self)

    def place(self, parent_size=None, left: bool = False):
        """Docks the dialog in the right-hand side panel."""
        if SIDE_HOST is not None:
            SIDE_HOST.dock(self)

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
