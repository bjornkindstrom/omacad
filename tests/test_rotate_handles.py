"""Björn #107: curved arrows beside the selected body (X red, Y green, Z blue) turn it about its centre, in 15° steps,
and the release is one Move step."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.doc.add_box(40, 20, 10)
    return w


def test_handles_only_on_one_selected_body_outside_a_sketch(win):
    rh = win.viewport.rotate_handles
    assert rh.handles() == {}
    win.doc.selected_body_ids = list(win.doc.bodies)
    assert set(rh.handles()) == {"X", "Y", "Z"}
    win.doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    assert rh.handles() == {}


def test_dragging_the_z_arrow_turns_the_body_in_steps_and_undo_takes_it_back(win):
    doc, vp = win.doc, win.viewport
    bid = next(iter(doc.bodies))
    doc.selected_body_ids = [bid]
    rh = vp.rotate_handles
    pos, tangent, _out = rh.handles()["Z"]
    assert rh.press(*pos)
    rh.move(*(pos + tangent * 120))
    angle = rh.drag["angle"]
    assert angle != 0 and angle % 15 == 0
    assert vp.display_override and bid in vp.display_override        # live preview of the turned body
    assert rh.release()
    assert not vp.display_override
    move = doc.timeline.features[-1]
    assert move.feature_type == "move" and (move.rx, move.ry, move.rz) == (0, 0, angle) and move.pivot == "center"
    lo, hi = np.array(doc.bodies[bid].manifold.bounding_box()).reshape(2, 3)
    a = np.radians(angle)
    assert hi[0] - lo[0] == pytest.approx(40 * abs(np.cos(a)) + 20 * abs(np.sin(a)), abs=1e-6)
    assert (lo + hi)[:2] / 2 == pytest.approx([20, 10], abs=1e-6)     # about its own centre
    assert doc.selected_body_ids == [bid]
    doc.undo()
    assert [f.feature_type for f in doc.timeline.features] == ["box"]


def test_escape_cancels_a_turn(win):
    doc, vp = win.doc, win.viewport
    doc.selected_body_ids = list(doc.bodies)
    rh = vp.rotate_handles
    pos, tangent, _out = rh.handles()["X"]
    rh.press(*pos)
    rh.move(*(pos + tangent * 120))
    assert rh.cancel() and not vp.display_override
    assert not rh.release()
    assert [f.feature_type for f in doc.timeline.features] == ["box"]
