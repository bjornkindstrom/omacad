"""A small, non-modal window that walks through a guide (pictures + short text) while the user keeps working."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from omacad.guide import Guide

WIDTH = 540          # the guide window
BIG_WIDTH = 900      # the enlarged window (the pictures are 900 px wide)
BOX_IMAGE = 330      # the small box in a tool panel


def _pixmap(path, width: int) -> QPixmap:
    pix = QPixmap(str(path)) if path else QPixmap()
    return pix if pix.isNull() else pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)


class GuideBox(QFrame):
    """A small guide inside a tool panel: one picture and a line or two, Back/Next, collapsible, and a button that
    opens the same guide in a bigger window (at the same step)."""

    def __init__(self, guide: Guide, parent=None):
        super().__init__(parent)
        self.guide = guide
        self.index = 0
        self.big = None
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.lbl_title = QLabel("Guide")
        self.lbl_title.setStyleSheet("font-weight: bold;")
        self.btn_fold = QPushButton("Hide")
        self.btn_fold.setToolTip("Hide or show the guide")
        self.btn_big = QPushButton("Bigger")
        self.btn_big.setToolTip("Open the guide in a bigger window")
        head.addWidget(self.lbl_title)
        head.addStretch()
        head.addWidget(self.btn_big)
        head.addWidget(self.btn_fold)
        layout.addLayout(head)
        self.body = QFrame()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text = QLabel()
        self.lbl_text.setWordWrap(True)
        bar = QHBoxLayout()
        self.btn_prev = QPushButton("Back")
        self.btn_next = QPushButton("Next")
        self.btn_prev.clicked.connect(lambda: self.go(self.index - 1))
        self.btn_next.clicked.connect(lambda: self.go(self.index + 1))
        self.lbl_step = QLabel()
        bar.addWidget(self.btn_prev)
        bar.addStretch()
        bar.addWidget(self.lbl_step)
        bar.addStretch()
        bar.addWidget(self.btn_next)
        for w in (self.lbl_image, self.lbl_text):
            body.addWidget(w)
        body.addLayout(bar)
        layout.addWidget(self.body)
        self.btn_fold.clicked.connect(self.toggle_fold)
        self.btn_big.clicked.connect(self.open_big)
        self.go(0)

    def toggle_fold(self) -> None:
        show = self.body.isHidden()
        self.body.setVisible(show)
        self.btn_fold.setText("Hide" if show else "Show")

    def go(self, i: int) -> None:
        self.index = max(0, min(i, len(self.guide.steps) - 1))
        step = self.guide.steps[self.index]
        pix = _pixmap(step.image, BOX_IMAGE)
        self.lbl_image.setVisible(not pix.isNull())
        if not pix.isNull():
            self.lbl_image.setPixmap(pix)
        self.lbl_text.setText(step.text)
        self.lbl_step.setText(f"{self.index + 1} / {len(self.guide.steps)}")
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < len(self.guide.steps) - 1)

    def open_big(self) -> None:
        if self.big is not None:
            self.big.close()
        self.big = GuideWindow(self.guide, self.window(), width=BIG_WIDTH, start=self.index)
        self.big.show()


class GuideWindow(QDialog):
    def __init__(self, guide: Guide, parent=None, width: int = WIDTH, start: int = 0):
        super().__init__(parent)
        self.guide = guide
        self.index = 0
        self.width_px = width
        self.setWindowTitle(guide.title)
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedWidth(width)
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
        self.btn_prev = QPushButton("Back")
        self.btn_next = QPushButton("Next")
        self.btn_prev.clicked.connect(lambda: self.go(self.index - 1))
        self.btn_next.clicked.connect(self._next)
        bar.addWidget(self.btn_prev)
        bar.addStretch()
        bar.addWidget(self.btn_next)
        for w in (self.lbl_step, self.lbl_image, self.lbl_text):
            layout.addWidget(w)
        layout.addLayout(bar)
        self.go(start)

    def _next(self):
        if self.index >= len(self.guide.steps) - 1:
            self.close()
        else:
            self.go(self.index + 1)

    def go(self, i: int) -> None:
        self.index = max(0, min(i, len(self.guide.steps) - 1))
        step = self.guide.steps[self.index]
        self.lbl_step.setText(f"Step {self.index + 1} of {len(self.guide.steps)}")
        pix = _pixmap(step.image, self.width_px - 24)
        self.lbl_image.setVisible(not pix.isNull())
        if not pix.isNull():
            self.lbl_image.setPixmap(pix)
        self.lbl_text.setText(step.text)
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setText("Done" if self.index == len(self.guide.steps) - 1 else "Next")
