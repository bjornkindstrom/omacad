"""Japandi ribs: circular feature groups retain fillets and skip unchecked steps."""
import math

import manifold3d as m3d
import numpy as np
import pytest
from shapely.geometry import Polygon, box

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.pattern import PatternFeature
from omacad.model import quality


def bowl_with_rib(doc=None, extra_cut=False):
    doc = doc or Document()
    doc.add_cylinder(20, 20, wall_thickness=2)
    sk = doc.start_sketch("XY")
    sk.add_loop([(19,-1),(23,-1),(23,1),(19,1)], closed=True)
    doc.finish_sketch()
    index = next(i for i,p in enumerate(sk.profiles) if Polygon(p.exterior_pts).centroid.x > 20)
    doc.extrude_profile(sk.sketch_id, index, 20, operation="join")
    rib = doc.timeline.features[-1]
    if extra_cut:
        sk = doc.start_sketch("XY")
        sk.add_rect((-1,8),(1,10))
        doc.finish_sketch()
        index = next(i for i,p in enumerate(sk.profiles) if abs(Polygon(p.exterior_pts).area-4) < 1e-4)
        doc.extrude_profile(sk.sketch_id, index, 20, operation="cut")
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "line"
             and abs(e.p0[0]-23)<1e-4 and abs(e.p1[0]-23)<1e-4 and abs(e.p0[2]-e.p1[2])>19]
    assert len(edges) == 2
    fillet = doc.add_fillet([e.ref() for e in edges], .5)
    assert fillet.skipped == 0
    return doc, rib, fillet


def expected_volume(count, extra_cut=False):
    n = quality.circle_segments()
    factor = n/2*math.sin(2*math.pi/n)
    bowl = factor*(20**2*20 - 18**2*18)
    footprint = Polygon([(20*math.cos(2*math.pi*i/n), 20*math.sin(2*math.pi*i/n)) for i in range(n)])
    outside = box(19,-1,23,1).difference(footprint).area*20
    # Two vertical convex edge fillets, radius .5, each a 24-segment quarter circle.
    fillets = 2*20*.5**2*(1-24/2*math.sin(math.pi/48))
    return bowl + count*(outside-fillets) - (8 if extra_cut else 0)


@pytest.mark.parametrize("extra_cut", [False, True])
@pytest.mark.parametrize("picked", [False, True])
def test_pattern_copies_rounded_rib_and_only_selected_features(extra_cut, picked):
    doc, rib, fillet = bowl_with_rib(extra_cut=extra_cut)
    axis = {"rotation_axis": "picked", "axis_origin": [0,0,0], "axis_direction": [0,0,2]} if picked else {}
    pattern = doc.add_pattern([fillet.feature_id, rib.feature_id], "circular", count1=12, about="body", **axis)
    expected = expected_volume(12, extra_cut)
    assert pattern.copies == 11
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    saved = Exporter.document_to_dict(doc)
    copy = Document()
    Exporter.apply_dict(copy, saved)
    assert copy.timeline.features[-1].rotation_axis == ("picked" if picked else "z")
    assert next(iter(copy.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected_volume(1, extra_cut), rel=1e-6)
    doc.redo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    assert doc.edit_feature(len(doc.timeline.features)-1, count1=8)
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected_volume(8, extra_cut), rel=1e-6)


@pytest.mark.parametrize("axis,start,expected", [
    ("x", (0,10,0), (0,0,10)), ("y", (0,0,10), (10,0,0)), ("z", (10,0,0), (0,10,0)),
])
def test_selectable_world_rotation_axis(axis, start, expected):
    pattern = PatternFeature("p","P",[], "circular", count1=2, angle=90, rotation_axis=axis)
    transform = pattern._transforms(np.zeros(3), np.zeros(3), np.ones(3))[0]
    cube = m3d.Manifold.cube((1,1,1), center=True).translate(start)
    bounds = transform(cube).bounding_box()
    assert (np.array(bounds[:3])+bounds[3:])/2 == pytest.approx(expected)


def test_picked_axis_and_partial_negative_angle():
    pattern = PatternFeature("p","P",[], "circular", count1=3, angle=-180, rotation_axis="picked",
                             axis_origin=[5,7,9], axis_direction=[0,0,2])
    transforms = pattern._transforms(np.zeros(3), np.zeros(3), np.ones(3))
    cube = m3d.Manifold.cube((1,1,1), center=True).translate([15,7,9])
    centers=[]
    for transform in transforms:
        bounds=transform(cube).bounding_box()
        centers.append((np.array(bounds[:3])+bounds[3:])/2)
    assert np.array(centers) == pytest.approx(np.array([[5,-3,9],[-5,7,9]]))
    assert pattern.to_dict()["axis_origin"] == [5,7,9]


def test_circular_pattern_dialog_timeline_sliders_and_axis_pick():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QPointF, QEvent
    from PySide6.QtGui import QMouseEvent
    from omacad.ui.main_window import MainWindow
    from omacad.ui.numeric_slider import NumericSlider

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc, rib, fillet = bowl_with_rib(win.doc)
    before = len(doc.timeline.features)
    win.prompt_pattern("circular")
    dlg = win._pattern_dlg
    assert dlg.kind() == "circular" and dlg.spn_count1.value() == 12
    assert rib.feature_id in dlg.source_ids() and fillet.feature_id in dlg.source_ids()
    assert doc.timeline.features[0].feature_id not in dlg.source_ids()
    rib_step = doc.timeline.features.index(rib)+1
    win.timeline_bar.on_node_clicked(rib_step)
    assert rib.feature_id not in dlg.source_ids()
    win.timeline_bar.on_node_clicked(rib_step)
    assert rib.feature_id in dlg.source_ids()
    assert len(doc.timeline.features) == before

    for kind in ("linear", "circular", "mirror", "circular"):
        dlg.cmb_kind.setCurrentIndex(dlg.KINDS.index(kind))
    assert isinstance(dlg.spn_count1.parentWidget(), NumericSlider)
    assert isinstance(dlg.spn_angle.parentWidget(), NumericSlider)
    assert not dlg.spn_angle.isHidden()

    vp = win.viewport
    vp.resize(1000,800)
    vp.azimuth, vp.elevation, vp.distance = 0., 0., 90.
    vp.target = np.array([0.,0.,10.], dtype=np.float32)
    dlg.btn_axis.click()
    assert vp.plane_pick_purpose == "pattern_axis"
    point = vp.world_to_screen(np.array([0.,-20.,10.]))
    vp.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(*point), QPointF(*point),
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    vp.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(*point), QPointF(*point),
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert not vp.plane_pick_mode
    assert dlg.get_params()["rotation_axis"] == "picked"
    assert abs(np.array(dlg.picked_direction) @ [0,0,1]) > .999
    dlg.accept()
    assert win.timeline_bar.feature_pick_handler is None
    assert not vp.pick_step_mode
    assert win._pattern_dlg is None
    # Interactive tessellation: 30 degrees is not a whole number of facets, so the copies shave the
    # chords' sag (< 0.1 mm skin) off the round walls.
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected_volume(12), rel=1e-4)
    win.close()


def test_circular_pattern_cancel_preserves_document_and_clears_picking():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc, rib, fillet = bowl_with_rib(win.doc)
    before = doc.snapshot()
    win.prompt_pattern("circular")
    dlg = win._pattern_dlg
    dlg.btn_axis.click()
    dlg.reject()
    assert doc.snapshot() == before
    assert win.timeline_bar.feature_pick_handler is None
    assert not win.viewport.plane_pick_mode
    assert not win.viewport.pick_step_mode
    assert win.viewport.preview_mesh is None
    win.close()


def test_circular_pattern_of_wrapped_slot_leaves_no_skin_strips():
    """Report: 9 wrapped slots (deboss + floor fillet) around a 192-facet cylinder left paper-thin skin
    strips, because 40 degrees is not a whole number of facets. Every slice must be one clean loop with
    the area of the cylinder minus nine single-slot cuts."""
    doc = Exporter.load_project("tests/data/circular_pattern_wrapped_slot.omacad")
    before, after = doc.step_states[2]["body_cylinder_1"], doc.step_states[4]["body_cylinder_1"]
    body = doc.bodies["body_cylinder_1"].manifold

    def area(m, z):
        return sum(Polygon(p).area for p in m.slice(z).to_polygons())
    for z in np.linspace(0.5, 78.5, 40):
        assert len(body.slice(z).to_polygons()) == 1, z
    for z in (20.0, 37.5, 60.0):
        expected = area(before, z) - 9*(area(before, z) - area(after, z))
        assert area(body, z) == pytest.approx(expected, abs=0.25)


def test_circular_pattern_on_square_body_keeps_its_corners():
    """A body that is not round about the axis must not be cut down to what every rotation keeps."""
    doc = Document()
    doc.add_box(40, 40, 10)
    sk = doc.start_sketch("XY")
    sk.add_rect((34, 19), (36, 21))
    doc.finish_sketch()
    index = next(i for i, p in enumerate(sk.profiles) if abs(Polygon(p.exterior_pts).area-4) < 1e-4)
    doc.extrude_profile(sk.sketch_id, index, 10, operation="cut")
    cut = doc.timeline.features[-1]
    doc.add_pattern([cut.feature_id], kind="circular", count1=3, angle=360.0, rotation_axis="z")
    body = next(iter(doc.bodies.values())).manifold
    assert body.volume() == pytest.approx(40*40*10 - 3*4*10, abs=1e-3)
