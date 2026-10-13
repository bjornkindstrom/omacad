"""The dialog behind 'Report problem': write what is wrong, zoom into the screenshot and draw where the problem is."""
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

MARK_COLOUR = QColor(255, 45, 45)
MARK_WIDTH = 5.0           # in screenshot pixels, so marks look the same at any zoom
Mark = Tuple[str, List[QPointF]]   # (tool, points in screenshot coordinates)


def draw_mark(painter: QPainter, mark: Mark, width: float = MARK_WIDTH) -> None:
    tool, pts = mark
    if not pts:
        return
    painter.setPen(QPen(MARK_COLOUR, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    a, b = pts[0], pts[-1]
    if tool == "pen":
        painter.drawPolyline(QPolygonF(pts) if len(pts) > 1 else QPolygonF([a, a + QPointF(0.1, 0.1)]))
    elif tool == "rect":
        painter.drawRect(QRectF(a, b).normalized())
    elif tool == "arrow":
        painter.drawLine(a, b)
        d = b - a
        n = math.hypot(d.x(), d.y())
        if n > 1e-6:
            ux, uy = d.x() / n, d.y() / n
            head = min(28.0, max(12.0, n * 0.3))
            for sgn in (1, -1):
                ang = math.radians(150) * sgn
                cs, sn = math.cos(ang), math.sin(ang)
                painter.drawLine(b, QPointF(b.x() + head * (ux * cs - uy * sn), b.y() + head * (ux * sn + uy * cs)))


class MarkableImage(QWidget):
    """A screenshot you can zoom (mouse wheel, around the pointer), pan (middle or right button, or Ctrl+drag)
    and draw on (pen, rectangle, arrow). Marks live in screenshot coordinates."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.marks: List[Mark] = []
        self.tool = "pen"
        self.scale = 1.0
        self.offset = QPointF(0, 0)
        self._current: Optional[Mark] = None
        self._pan_from: Optional[QPointF] = None
        self._fitted = False
        self.setMinimumSize(480, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(False)

    # ---- coordinates -------------------------------------------------------------
    def to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self.offset.x()) / self.scale, (p.y() - self.offset.y()) / self.scale)

    def fit(self) -> None:
        if self.pixmap.isNull() or self.width() < 2 or self.height() < 2:
            return
        self.scale = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        self.offset = QPointF((self.width() - self.pixmap.width() * self.scale) / 2,
                              (self.height() - self.pixmap.height() * self.scale) / 2)
        self._fitted = True
        self.update()

    def zoom_at(self, pos: QPointF, factor: float) -> None:
        """Zoom so that the screenshot point under `pos` stays under it."""
        anchor = self.to_image(pos)
        self.scale = max(0.05, min(40.0, self.scale * factor))
        self.offset = QPointF(pos.x() - anchor.x() * self.scale, pos.y() - anchor.y() * self.scale)
        self.update()

    # ---- marks --------------------------------------------------------------------
    def undo(self) -> None:
        if self.marks:
            self.marks.pop()
            self.update()

    def clear(self) -> None:
        self.marks.clear()
        self.update()

    def annotated_image(self) -> QImage:
        """The screenshot with the marks drawn on it."""
        img = self.pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for m in self.marks:
            draw_mark(p, m)
        p.end()
        return img

    # ---- events -------------------------------------------------------------------
    def resizeEvent(self, event):
        if not self._fitted or not self.marks:
            self.fit()
        super().resizeEvent(event)

    def wheelEvent(self, event):
        self.zoom_at(event.position(), 1.25 if event.angleDelta().y() > 0 else 0.8)

    def mouseDoubleClickEvent(self, event):
        self.fit()

    def mousePressEvent(self, event):
        pos = event.position()
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or \
                (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._pan_from = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._current = (self.tool, [self.to_image(pos)])

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._pan_from is not None:
            self.offset += pos - self._pan_from
            self._pan_from = pos
            self.update()
        elif self._current is not None:
            tool, pts = self._current
            if tool == "pen":
                pts.append(self.to_image(pos))
            else:
                self._current = (tool, [pts[0], self.to_image(pos)])
            self.update()

    def mouseReleaseEvent(self, event):
        if self._pan_from is not None:
            self._pan_from = None
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._current is not None:
            self.marks.append(self._current)
            self._current = None
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 32, 36))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.scale < 1.0)   # crisp pixels when zoomed in
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.offset)
        p.scale(self.scale, self.scale)
        p.drawPixmap(0, 0, self.pixmap)
        for m in self.marks + ([self._current] if self._current else []):
            draw_mark(p, m)


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, screenshot: QPixmap = None, mode: str = "report"):
        """mode "report": a problem, handed to the AI agent. mode "request": a wish for a change, sent to GitHub for review."""
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("Request a change" if mode == "request" else "Report problem")
        self.resize(1000, 760)
        lay = QVBoxLayout(self)
        if mode == "request":
            lay.addWidget(QLabel("What would you like to change or add? Describe it in a few sentences. The screenshot, the model "
                                 "and the log are sent along so it is easy to understand. Zoom with the mouse wheel and draw "
                                 "what you mean."))
        else:
            lay.addWidget(QLabel("What is wrong? A sentence is enough. The screenshot, the model and the log are sent along. "
                                 "Zoom with the mouse wheel and draw where the problem is."))
        self.image: Optional[MarkableImage] = None
        if screenshot is not None and not screenshot.isNull():
            tools = QHBoxLayout()
            group = QButtonGroup(self)
            self.image = MarkableImage(screenshot)
            for key, label in (("pen", "✏️ Pen"), ("rect", "▭ Rectangle"), ("arrow", "➚ Arrow")):
                b = QToolButton()
                b.setText(label)
                b.setCheckable(True)
                b.setChecked(key == "pen")
                b.clicked.connect(lambda _=False, k=key: setattr(self.image, "tool", k))
                group.addButton(b)
                tools.addWidget(b)
            for label, slot in (("Undo mark", lambda: self.image.undo()), ("Clear marks", lambda: self.image.clear()),
                                ("Fit", lambda: self.image.fit())):
                b = QPushButton(label)
                b.clicked.connect(slot)
                tools.addWidget(b)
            tools.addStretch()
            tools.addWidget(QLabel("Wheel = zoom · middle/right button or Ctrl+drag = move · double-click = fit"))
            lay.addLayout(tools)
            lay.addWidget(self.image, 1)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("e.g. I would like to be able to ..." if mode == "request"
                                     else "e.g. the corner of the offset is not rounded like the original")
        self.note.setFixedHeight(80)
        lay.addWidget(self.note)
        self.chk_fix = QCheckBox("Let the AI (Omarchy's default agent) fix it now")
        self.chk_fix.setChecked(True)
        self.chk_fix.setToolTip("Opens the default coding agent in a terminal with the report. Untick to only save the report.")
        self.edt_name = QLineEdit()
        if mode == "request":
            self.chk_fix.setVisible(False)
            from omacad.ui.settings import get_settings
            self.edt_name.setPlaceholderText("Your name (so the owner knows who asked)")
            self.edt_name.setText(str(get_settings().get("rfc_name") or ""))
            lay.addWidget(self.edt_name)
            lay.addWidget(QLabel("Sent to the owner of Omacad on GitHub: your text, the screenshot, the model and the log of this session."))
        else:
            lay.addWidget(self.chk_fix)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Send request" if mode == "request" else "Report")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.note.setFocus()

    def text(self) -> str:
        return self.note.toPlainText().strip()

    def name(self) -> str:
        return self.edt_name.text().strip()

    def fix_now(self) -> bool:
        return self.chk_fix.isChecked()

    def marked_image(self) -> Optional[QImage]:
        """The screenshot with the user's drawing, or None when nothing was drawn."""
        return self.image.annotated_image() if self.image is not None and self.image.marks else None
