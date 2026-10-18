"""Jar with Lid end to end: the Primitives menu entry opens the panel with -0.2 tolerance, sliders on the fields, OK
adds the jar and the lid as one undo step, and the panel remembers the sizes."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def test_jar_tool_adds_jar_and_lid_as_one_step(win):
    win.ribbon.jar_clicked.emit()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and dlg.windowTitle() == "Jar with Lid"
    assert dlg.spins["tolerance"].value() == pytest.approx(-0.2)
    assert all(isinstance(s.parentWidget(), NumericSlider) for s in dlg.spins.values())
    dlg.spins["diameter"].setValue(50.0)
    dlg.spins["neck_diameter"].setValue(40.0)
    dlg.accept()
    assert sorted(b.name for b in win.doc.bodies.values()) == ["Jar", "Lid"]
    assert len(win.doc.undo_stack) == 1
    win.doc.undo()
    assert not win.doc.bodies
    win.prompt_jar()                                         # remembers the last sizes
    again = win.inspector.current_tool_dlg
    assert again.spins["diameter"].value() == pytest.approx(50.0)
    again.reject()
    assert not win.doc.bodies


def test_impossible_jar_cannot_be_made(win):
    win.prompt_jar()
    dlg = win.inspector.current_tool_dlg
    dlg.spins["neck_diameter"].setValue(39.5)                # no lid wall left outside the thread
    QApplication.processEvents()
    from PySide6.QtTest import QTest
    QTest.qWait(400)
    assert not dlg.btn_ok.isEnabled() and "lid's wall" in dlg.lbl_info.text()
    dlg.reject()
