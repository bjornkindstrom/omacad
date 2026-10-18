"""Jar with Lid: a threaded jar and its screw lid as editable history steps, with a thread tolerance."""
import math

import manifold3d as m3d
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.jar import JarSpec, thread_tooth

THREAD_BAND = m3d.Manifold.cube((100, 100, 9)).translate((-50, -50, 40.5))   # the neck, above the shoulder


def _jar(**kw):
    doc = Document()
    ids = doc.add_jar(JarSpec(**kw))
    return doc, doc.bodies[ids["jar"]].manifold, doc.bodies[ids["lid"]].manifold


def test_one_undo_step_with_editable_steps():
    doc, _, _ = _jar()
    assert len(doc.undo_stack) == 1
    types = [f.feature_type for f in doc.timeline.features]
    assert types == ["cylinder", "cylinder", "combine", "shell", "thread", "cylinder", "combine", "cylinder", "combine",
                     "offset_face", "move"]
    doc.undo()
    assert not doc.bodies and not doc.timeline.features


def test_jar_is_a_hollow_cup_with_the_given_wall():
    _, jar, _ = _jar(lid_beside=False, tolerance=0.0)
    above = m3d.Manifold.cube((100, 100, 100)).translate((-50, -50, 50))
    assert (jar ^ above).volume() < 1e-6                     # nothing above the neck
    body = m3d.Manifold.cube((100, 100, 36)).translate((-50, -50, 2))      # 2 mm bottom .. just below the shoulder
    ring = math.pi * (20 ** 2 - 18 ** 2) * 36
    assert (jar ^ body).volume() == pytest.approx(ring, rel=0.02)          # faceting aside


@pytest.mark.parametrize("tol, at_least", [(-0.2, 0.15), (-0.4, 0.3)])
def test_lid_screws_on_with_room_in_the_thread(tol, at_least):
    _, jar, lid = _jar(lid_beside=False, tolerance=tol)
    assert (jar ^ lid).volume() < 1e-6
    assert len(lid.decompose()) == 1
    assert jar.min_gap(lid ^ THREAD_BAND, 2.0) >= at_least


def test_without_tolerance_the_threads_touch_and_no_plug_is_left():
    _, jar, lid = _jar(lid_beside=False, tolerance=0.0)
    assert (jar ^ lid).volume() < 1e-6
    assert jar.min_gap(lid ^ THREAD_BAND, 2.0) < 1e-3
    bore = m3d.Manifold.cylinder(10, 13.5, 13.5, 64).translate((0, 0, 40))     # inside the neck's bore (r 14)
    assert (lid ^ bore).volume() < 1e-9


def test_lid_beside_is_upside_down_on_the_bed():
    _, jar, lid = _jar()
    bb = lid.bounding_box()
    assert bb[2] == pytest.approx(0.0, abs=1e-6) and bb[5] == pytest.approx(12.0, abs=1e-6)
    assert bb[0] == pytest.approx(30.0, abs=1e-6)          # 10 mm beside the jar
    bed = m3d.Manifold.cube((100, 100, 2)).translate((0, -50, 0))
    assert (lid ^ bed).volume() == pytest.approx(math.pi * 20 ** 2 * 2, rel=0.01)   # the closed top lies on the bed


def test_problems_and_save_load(tmp_path):
    assert JarSpec(neck_diameter=38).problems(thread_tooth(JarSpec(neck_diameter=38)))
    assert not JarSpec().problems(thread_tooth(JarSpec()))
    doc, jar, lid = _jar()
    path = tmp_path / "jar.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    vols = sorted(b.manifold.volume() for b in again.bodies.values())
    assert vols == pytest.approx(sorted([jar.volume(), lid.volume()]), rel=1e-6)
