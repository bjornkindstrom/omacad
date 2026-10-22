"""Origin plane markers are centred on the origin, small on an empty model and large enough to cover the bodies."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    v = Viewport3D(Document())
    v.resize(800, 600)
    return v


def test_marker_size_is_small_and_grows_with_the_model(view):
    assert view._origin_quadrant_size() == pytest.approx(20.0)
    view.doc.add_box(100, 100, 100)
    assert view._origin_quadrant_size() == pytest.approx(75.0)


def test_origin_plane_is_picked_on_all_sides_of_the_origin_but_not_far_away(view):
    view.begin_plane_pick("sketch")
    view.azimuth, view.elevation = 0.0, 89.9
    plane = view.doc.origin_planes["XY"]
    at = lambda u, v: view.world_to_screen(plane.uv_to_world(u, v))
    assert view._pick_plane_target(*at(8, 8)) == ("origin", "XY")
    assert view._pick_plane_target(*at(-8, -8)) == ("origin", "XY")
    assert view._pick_plane_target(*at(35, 8)) is None


def test_origin_plane_grows_to_cover_a_body_beside_the_origin(view):
    view.doc.add_box(40, 40, 10)
    view.begin_plane_pick("sketch")
    view.azimuth, view.elevation = 0.0, 89.9
    plane = view.doc.origin_planes["XY"]
    mesh = next(iter(view.doc.bodies.values())).render_mesh
    far = max(abs(float(mesh.bounds_min[0])), abs(float(mesh.bounds_max[0])))
    assert view._plane_half_size(plane) >= far
