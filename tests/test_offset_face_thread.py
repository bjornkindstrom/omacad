"""Offset Face on a thread surface edits the thread (its `grow`) instead of deforming the finished mesh: exact, no
folds, and the Move that came after the thread is followed."""
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.features.thread import ThreadFeature

DOC = str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad")


def _doc():
    doc = Exporter.load_project(DOC)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    return doc, last


def test_surface_of_the_coil_is_recognised_and_signed():
    doc, last = _doc()
    thread, sign = doc._thread_offset(last.faces)
    assert isinstance(thread, ThreadFeature) and sign == -1      # the groove in the jar faces into the coil


def test_offset_edits_thread_and_undoes():
    doc, last = _doc()
    burk = lambda: doc.bodies["body_split_2"].manifold
    v0 = burk().volume()
    n_offsets = len([f for f in doc.timeline.features if f.feature_type == "offset_face"])
    feat = doc.add_offset_face("body_split_2", last.faces, -0.2)
    assert isinstance(feat, ThreadFeature) and abs(feat.grow - 0.2) < 1e-9
    assert burk().status().name == "NoError" and burk().volume() < v0 - 40      # a wider groove removes material
    assert len([f for f in doc.timeline.features if f.feature_type == "offset_face"]) == n_offsets   # none added
    doc.undo()
    assert doc.timeline.features[4].grow == 0.0
    assert abs(burk().volume() - v0) < 1e-6


def test_grow_widens_every_profile():
    from omacad.model.kernel import CadKernel
    for prof in ("round", "trapezoidal_45", "iso_60"):
        a = CadKernel.create_thread(20, 2.5, 10, profile=prof, include_core=False, attached_to_cylinder=True)
        b = CadKernel.create_thread(20, 2.5, 10, profile=prof, include_core=False, attached_to_cylinder=True, grow=0.2)
        assert b.volume() > a.volume()


def test_dialog_explains_what_ok_does_for_a_thread():
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    doc, last = _doc()
    w = MainWindow()
    w.attach_document(doc)
    w.prompt_offset_face()
    dlg = w.inspector.current_tool_dlg
    dlg.spn_dist.setValue(-0.2)
    dlg.toggle(last.faces[0], "body_split_2")
    QTest.qWait(400)
    assert "coil of Thread 1" in dlg.lbl_note.text() and "0.2 mm thicker" in dlg.lbl_note.text()
    dlg.reject()


def test_preview_equals_result_and_leaves_document_alone():
    doc, last = _doc()
    v0 = doc.bodies["body_split_2"].manifold.volume()
    preview = doc.thread_offset_result(last.faces, -0.2, "body_split_2")
    assert doc.timeline.features[4].grow == 0.0
    assert abs(doc.bodies["body_split_2"].manifold.volume() - v0) < 1e-9
    doc.add_offset_face("body_split_2", last.faces, -0.2)
    assert abs(preview.volume() - doc.bodies["body_split_2"].manifold.volume()) < 1e-6
