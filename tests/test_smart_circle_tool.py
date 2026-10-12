"""The Smart Circle tool end to end in the viewport: numbers and Enter place a dimensioned circle."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.model.sketch import SketchCircle  # noqa: E402


@pytest.fixture
def view():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport import Viewport3D
    return Viewport3D(Document())


def key(view, k, text=""):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier, text))


def typ(view, s):
    from PySide6.QtCore import Qt
    for ch in s:
        key(view, getattr(Qt.Key, f"Key_{ch}") if ch.isdigit() else Qt.Key.Key_Period, ch)
    key(view, Qt.Key.Key_Return)


def test_numbers_and_enter_place_a_circle_and_dimension_it(view):
    sk = view.doc.start_sketch("XY")
    sk.add_rect((0, 0), (60, 40))
    view.set_sketch_tool("SMART_CIRCLE")
    view._raw_mouse_uv = view.smart.mouse = (50, 30)
    view.smart.segments = view._smart_segments()
    typ(view, "8")          # diameter
    view.smart.mouse = (48, 30)
    typ(view, "10")         # 10 from the right wall
    view.smart.mouse = (30, 38)
    typ(view, "6")          # 6 from the top wall
    circles = [e for e in sk.entities if isinstance(e, SketchCircle)]
    assert len(circles) == 1
    c = circles[0]
    assert c.radius == pytest.approx(4.0)
    assert tuple(c.center) == pytest.approx((50.0, 34.0))
    kinds = sorted(d.dim_type for d in sk.dimensions if d.target_entity_id == c.entity_id)
    assert kinds == ["DIAMETER", "PT_LINE_DIST", "PT_LINE_DIST"]
    assert view.smart.stage == 0   # ready for the next circle
