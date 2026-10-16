"""A small, non-modal window that walks through a guide (pictures + short text) while the user keeps working."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from omacad.guide import Guide

WIDTH = 540


class GuideWindow(QDialog):
    def __init__(self, guide: Guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.index = 0
        self.setWindowTitle(guide.title)
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedWidth(WIDTH)
        layout = QVBoxLayout(self)
        self.lbl_step = QLabel()
        self.lbl_step.setStyleSheet("font-weight: bold;")
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text = QLabel()
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setMinimumHeight(110)
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Back")
        self.btn_next = QPushButton("Next ▶")
        self.btn_prev.clicked.connect(lambda: self.go(self.index - 1))
        self.btn_next.clicked.connect(self._next)
        bar.addWidget(self.btn_prev)
        bar.addStretch()
        bar.addWidget(self.btn_next)
        for w in (self.lbl_step, self.lbl_image, self.lbl_text):
            layout.addWidget(w)
        layout.addLayout(bar)
        self.go(0)

    def _next(self):
        if self.index >= len(self.guide.steps) - 1:
            self.close()
        else:
            self.go(self.index + 1)

    def go(self, i: int) -> None:
        self.index = max(0, min(i, len(self.guide.steps) - 1))
        step = self.guide.steps[self.index]
        self.lbl_step.setText(f"Step {self.index + 1} of {len(self.guide.steps)}")
        pix = QPixmap(str(step.image)) if step.image else QPixmap()
        self.lbl_image.setVisible(not pix.isNull())
        if not pix.isNull():
            self.lbl_image.setPixmap(pix.scaledToWidth(WIDTH - 24, Qt.TransformationMode.SmoothTransformation))
        self.lbl_text.setText(step.text)
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setText("Done" if self.index == len(self.guide.steps) - 1 else "Next ▶")
