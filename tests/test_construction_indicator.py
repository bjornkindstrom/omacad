"""The construction button mirrors the viewport's construction mode and the mode resets when a sketch ends."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def test_button_follows_mode_and_resets_after_sketch(win):
    win.doc.start_sketch("XY")
    win.viewport.toggle_construction_mode()
    assert win.ribbon.btn_construct.isChecked() and win.viewport.construction_mode
    win.doc.finish_sketch()
    assert not win.viewport.construction_mode
    assert not win.ribbon.btn_construct.isChecked()
