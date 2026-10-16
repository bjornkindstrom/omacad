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
