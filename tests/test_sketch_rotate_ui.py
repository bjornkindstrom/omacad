"""Rotation transaction: preview, pivot changes, pick, cancellation, undo and persistence."""
import pytest
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchConstraint
from omacad.ui.viewport import Viewport3D


@pytest.fixture
def scene():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch()
    selected = sk.add_slot((2, 2), (8, 2), 1)
    untouched = sk.add_circle((20, 20), 2)
    viewport = Viewport3D(doc)
    viewport.selected_entities = {selected.entity_id}
    yield doc, sk, viewport, selected.entity_id, untouched.entity_id
    viewport.set_sketch_tool("NONE")
    viewport.close()
    viewport.deleteLater()
    app.processEvents()


def test_preview_pivot_changes_cancel_commit_undo_redo_and_save(scene):
    doc, sk, vp, eid, other = scene
    before = sk.to_dict()
    undo_count = len(doc.undo_stack)
    vp.set_sketch_tool("ROTATE")
    panel = vp.rotation_panel
    assert panel.pivot.currentData() == "area"
    assert vp._move["pivot"] == pytest.approx((5, 2))
    panel.angle.setValue(90)
    assert sk.get_entity(eid).center1 == pytest.approx((5, -1))
    panel.pivot.setCurrentIndex(panel.pivot.findData("origin"))
    assert sk.get_entity(eid).center1 == pytest.approx((-2, 2))
    assert sk.get_entity(other).to_dict() == before["entities"][1]
    assert len(doc.undo_stack) == undo_count
    panel.cancel.click()
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    panel.angle.setValue(90)
    panel.ok.click()
    after = sk.to_dict()
    assert len(doc.undo_stack) == undo_count + 1
    assert vp.sketch_tool == "NONE"
    doc.undo()
    assert sk.to_dict() == before
    doc.redo()
    assert sk.to_dict() == after
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert loaded.sketches[sk.sketch_id].get_entity(eid).to_dict() == sk.get_entity(eid).to_dict()


def test_custom_pivot_can_be_picked_and_escape_restores_everything(scene, monkeypatch):
    doc, sk, vp, eid, _ = scene
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(90)
    vp.sketch_palette.chk_snap_grid.setChecked(False)
    vp.sketch_palette.chk_snap_points.setChecked(False)
    vp.rotation_panel.pick.click()
    monkeypatch.setattr(vp, "get_sketch_plane_uv", lambda x, y: (1.0, 1.0))
    p = QPointF(10, 10)
    vp.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, p, Qt.MouseButton.LeftButton,
                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert vp._move["pivot"] == pytest.approx((1, 1))
    assert sk.get_entity(eid).center1 == pytest.approx((0, 2))
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert sk.to_dict() == before
    assert vp.sketch_tool == "NONE"


def test_fixed_and_projected_geometry_are_protected(scene):
    _, sk, vp, eid, _ = scene
    sk.constraints.append(SketchConstraint("fixed", "FIX", [eid]))
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(30)
    assert not vp.rotation_panel.ok.isEnabled()
    vp.rotation_panel.cancel.click()
    assert sk.to_dict() == before
    sk.get_entity(eid).projected = True
    vp.set_sketch_tool("ROTATE")
    assert vp.sketch_tool == "NONE"
    assert vp._move is None


def test_rectangle_rotation_restores_constraints_on_cancel_and_is_one_undo_step(scene):
    doc, sk, vp, _, _ = scene
    lines = sk.add_rect((0, 0), (6, 3))
    vp.selected_entities = {e.entity_id for e in lines}
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(45)
    assert any(c.ctype == "PERPENDICULAR" for c in sk.constraints)
    vp.set_sketch_tool("LINE")
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(45)
    vp.rotation_panel.ok.click()
    doc.undo()
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    undo_count = len(doc.undo_stack)
    vp.rotation_panel.ok.click()  # zero degrees makes no history entry
    assert len(doc.undo_stack) == undo_count


def test_rotation_rejects_incompatible_axis_distance(scene):
    _, sk, vp, _, other = scene
    line = sk.add_line((2, 2), (8, 2))
    vp.selected_entities = {line.entity_id}
    sk.add_dimension("HORIZ_DIST", line.entity_id, 18, refs=[other], pts=["p1", "center"])
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(90)
    assert not vp.rotation_panel.ok.isEnabled()
    vp.rotation_panel.cancel.click()
    assert sk.to_dict() == before


def test_text_rotates_about_picked_coordinates_and_path_text_is_protected(scene):
    from shapely import affinity
    _, sk, vp, _, _ = scene
    text = sk.add_text("L", (4, 3), height=5)
    expected = affinity.rotate(text.geometry(), 30, origin=(0, 0))
    vp.selected_entities = {text.entity_id}
    vp.set_sketch_tool("ROTATE")
    panel = vp.rotation_panel
    panel.pivot.setCurrentIndex(panel.pivot.findData("origin"))
    panel.angle.setValue(30)
    moved = sk.get_entity(text.entity_id)
    assert moved.geometry().symmetric_difference(expected).area < 1e-6
    assert moved.sketch is sk
    panel.ok.click()
    path = sk.add_circle((0, 0), 10, is_construction=True)
    text = sk.add_text("PATH", height=3, path_id=path.entity_id)
    before = sk.to_dict()
    vp.selected_entities = {text.entity_id}
    vp.set_sketch_tool("ROTATE")
    panel.angle.setValue(30)
    assert not panel.ok.isEnabled()
    panel.cancel.click()
    assert sk.to_dict() == before
