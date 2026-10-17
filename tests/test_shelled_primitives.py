"""Shelled primitive presets reuse parametric geometry and undo history."""
import math

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from omacad.model import quality
from omacad.ui.main_window import MainWindow
from omacad.ui.settings import get_settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind", ["box", "cylinder"])
def test_shelled_preset_thickness_volume_and_undo(app, kind):
    get_settings().set("primitive_shell_thickness", 3.0)
    w = MainWindow()
    getattr(w, "prompt_shelled_"+kind)()
    handles = w.viewport.primitive_handles
    dlg = handles.dialog
    assert dlg.windowTitle() == "Create Shelled "+kind.title()
    assert dlg.spn_wall.value() == 3
    assert w.viewport.preview_mesh is not None
    assert not w.doc.bodies
    dlg.spn_wall.setValue(4)
    dlg.accept()
    feat = w.doc.timeline.features[-1]
    assert feat.wall_thickness == 4
    body = next(iter(w.doc.bodies.values()))
    if kind == "box":
        expected = 50*50*25 - 42*42*21
    else:
        n = quality.circle_segments()
        expected = n/2 * math.sin(2*math.pi/n) * (20**2*40 - 16**2*36)
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    w.doc.undo()
    assert not w.doc.bodies
    w.doc.redo()
    assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    getattr(w, "prompt_"+kind)()
    assert w.viewport.primitive_handles.dialog.spn_wall.value() == 0
    w.viewport.primitive_handles.dialog.reject()
    w.close()


@pytest.mark.parametrize("grouped", [True, False])
def test_shelled_commands_in_both_ribbon_layouts(app, grouped):
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    if grouped:
        menu = next(menu for menu in w.ribbon.findChildren(QMenu)
                    if any(a.text() == "Shelled Box" for a in menu.actions()))
        command = next(a for a in menu.actions() if a.text() == "Shelled Cylinder")
        command.trigger()
    else:
        button = next(b for b in w.ribbon.findChildren(QToolButton) if b.text() == "Shelled Cylinder")
        button.click()
    assert w.viewport.primitive_handles.kind == "cylinder"
    assert w.viewport.primitive_handles.dialog.spn_wall.value() == 2
    w.viewport.primitive_handles.dialog.reject()
    w.close()
