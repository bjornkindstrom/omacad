"""#46 in the window: Cone panel, and the Sweep / Loft / Pipe panel building a body from clicked profiles."""
import math

import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def test_cone_panel_makes_a_pointed_cone(win):
    from omacad.ui.dialogs.primitives_dlg import ConeDialog
    win.prompt_cone()
    QApplication.processEvents()
    d = win.findChildren(ConeDialog)[-1]
    d.spn_radius.setValue(10.0)
    d.spn_height.setValue(30.0)
    d.spn_top.setValue(0.0)
    d.accept()
    QApplication.processEvents()
    feat = win.doc.timeline.features[-1]
    assert feat.feature_type == "cone"
    vol = next(iter(win.doc.bodies.values())).manifold.volume()
    assert abs(vol - math.pi * 100 * 30 / 3) < 0.01 * math.pi * 1000


def test_loft_and_pipe_panels(win):
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    a = doc.start_sketch("XY")
    a.add_circle((0, 0), 10)
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 20.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_circle((0, 0), 5)
    doc.finish_sketch()
    win.prompt_sweep_tool("loft")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    # clicks in the view: each adds a profile, though they lie on different planes (Shift+click used to drop the
    # second one, so a Loft never got two profiles)
    win.viewport.toggle_profile_in_selection((a.sketch_id, 0))
    win.viewport.toggle_profile_in_selection((b.sketch_id, 0))
    assert dlg.profiles == [(a.sketch_id, 0), (b.sketch_id, 0)]
    dlg.accept()
    QApplication.processEvents()
    assert doc.timeline.features[-1].feature_type == "loft"
    want = math.pi * 20 / 3 * (100 + 50 + 25)
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - want) < 0.01 * want

    path = doc.start_sketch("XZ")
    path.add_line((30, 0), (30, 40))
    doc.finish_sketch()
    win.prompt_sweep_tool("pipe")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    dlg.cmb_path.setCurrentIndex(dlg.cmb_path.findData(path.sketch_id))
    dlg.spn_diam.setValue(4.0)
    dlg.accept()
    QApplication.processEvents()
    pipe = doc.timeline.features[-1]
    assert pipe.feature_type == "pipe"
    assert abs(doc.bodies[f"body_{pipe.feature_id}"].manifold.volume() - math.pi * 4 * 40) < 0.01 * math.pi * 160
