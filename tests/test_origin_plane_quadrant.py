"""Origin plane markers cover only the first quadrant (positive u and v) and stay small."""
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


def test_only_first_quadrant_can_be_picked(view):
    view.begin_plane_pick("sketch")
    view.azimuth, view.elevation = 0.0, 89.9
    plane = view.doc.origin_planes["XY"]
    at = lambda u, v: view.world_to_screen(plane.uv_to_world(u, v))
    inside, outside_neg, outside_far = at(8, 8), at(-8, -8), at(35, 8)
    assert view._pick_plane_target(*inside) == ("origin", "XY")
    assert view._pick_plane_target(*outside_neg) is None
    assert view._pick_plane_target(*outside_far) is None
