"""Typing a parameter name: the letters stay in the field (no menu shortcut such as E = Extrude fires), a list of the
parameters starting with them opens under the field, Up/Down step and Enter picks without closing the panel; the
same in the 3D view and in the dimension fields while drawing. Values driven by parameters are marked."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from omacad.model.document import Parameter
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win(monkeypatch):
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    boxes = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: boxes.append(a))   # Extrude with no sketch
    w = MainWindow()
    w.boxes = boxes
    w.doc.parameters = [Parameter("depth", "12"), Parameter("diameter", "30"), Parameter("edge", "4")]
    w.doc.refresh_parameters()
    w.show()
    QTest.qWait(400)
    yield w
    w.viewport.set_sketch_tool("NONE")
    w.close()


def _type(widget, text):
    for ch in text:
        QTest.keyClick(QApplication.focusWidget() or widget, ch)
        QTest.qWait(10)


def test_field_lists_parameters_and_enter_picks_one(win):
    win.prompt_box()
    dlg = win.inspector.current_tool_dlg
    f = dlg.spn_length
    win.activateWindow()
    f.setFocus()
    f.lineEdit().selectAll()
    _type(f, "d")
    assert f.suggestions_visible() and f._list.count() == 2               # depth, diameter
    QTest.keyClick(f, Qt.Key.Key_Down)
    QTest.keyClick(f, Qt.Key.Key_Return)
    assert not f.suggestions_visible()
    assert win.inspector.current_tool_dlg is dlg                           # Enter chose the name, not OK
    assert f.expression() == "diameter" and f.value() == pytest.approx(30.0)
    assert f.property("formula")                                           # marked as parameter-driven
    dlg.reject()


def test_letters_typed_in_the_view_go_to_the_panel_not_to_shortcuts(win):
    win.prompt_box()
    dlg = win.inspector.current_tool_dlg
    win.activateWindow()
    win.viewport.setFocus()
    QTest.qWait(20)
    _type(win.viewport, "depth")
    assert not win.boxes and win.inspector.current_tool_dlg is dlg         # no Extrude at the 'e'
    assert dlg.primary_field().lineEdit().text().startswith("depth")
    dlg.reject()


def test_drawing_dimension_field_takes_a_parameter_name(win):
    vp = win.viewport
    win.doc.start_sketch("XY")
    vp.set_sketch_tool("RECT")
    vp.sketch_start_uv, vp.sketch_current_uv = (0.0, 0.0), (10.0, 5.0)
    win.activateWindow()
    vp.setFocus()
    QTest.keyClick(vp, Qt.Key.Key_Tab)
    _type(vp, "e")
    assert win.doc.active_sketch is not None and not win.boxes            # E did not start Extrude
    assert vp.dyn.texts[vp.dyn.focus] == "e"
    vp.repaint()
    vp._dyn_suggest()
    assert vp._dyn_list is not None and vp._dyn_list.isVisible()
    QTest.keyClick(vp, Qt.Key.Key_Return)
    assert vp.dyn.texts[vp.dyn.focus] == "edge" and not vp._dyn_list.isVisible()


def test_timeline_chip_marks_steps_with_formulas(win):
    from omacad.ui.timeline_bar import FeatureNodeWidget
    win.doc.add_box(10, 10, 10)
    feat = win.doc.timeline.features[0]
    feat.exprs = {"length": "depth"}
    chip = FeatureNodeWidget(1, feat, True)
    assert chip.lbl_name.text().endswith("ƒx") and "length = depth" in chip.toolTip()
