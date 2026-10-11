"""The small dialog behind 'Report problem': write what is wrong, see the screenshot that will be sent."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, screenshot: QPixmap = None):
        super().__init__(parent)
        self.setWindowTitle("Report problem")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("What is wrong? A sentence is enough. The screenshot, the model and the log are sent along."))
        if screenshot is not None and not screenshot.isNull():
            thumb = QLabel()
            thumb.setPixmap(screenshot.scaledToWidth(480, Qt.TransformationMode.SmoothTransformation))
            lay.addWidget(thumb)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("e.g. the corner of the offset is not rounded like the original")
        self.note.setFixedHeight(90)
        lay.addWidget(self.note)
        self.chk_fix = QCheckBox("Let the AI (Omarchy's default agent) fix it now")
        self.chk_fix.setChecked(True)
        self.chk_fix.setToolTip("Opens the default coding agent in a terminal with the report. Untick to only save the report.")
        lay.addWidget(self.chk_fix)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Report")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.note.setFocus()

    def text(self) -> str:
        return self.note.toPlainText().strip()

    def fix_now(self) -> bool:
        return self.chk_fix.isChecked()
