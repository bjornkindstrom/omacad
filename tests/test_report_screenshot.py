"""The report's window screenshot must contain the 3D view's painter overlay (dimensions etc.)."""
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui.main_window import MainWindow


class _Window(QWidget):
    grab_with_overlay = MainWindow.grab_with_overlay


def test_window_shot_includes_view_overlay():
    app = QApplication.instance() or QApplication([])
    win = _Window()
    win.resize(200, 100)
    win.viewport = QWidget(win)
    win.viewport.setGeometry(50, 20, 100, 60)
    win.show()
    view = QImage(100, 60, QImage.Format.Format_ARGB32)
    view.fill(QColor(255, 0, 0))
    shot = win.grab_with_overlay(view).toImage()
    assert QColor(shot.pixel(100, 50)).red() == 255 and QColor(shot.pixel(100, 50)).green() == 0
    assert QColor(shot.pixel(5, 5)) != QColor(255, 0, 0)
