"""Section view cut faces are hatched like Fusion 360: diagonal lines clipped to the cut, with holes left open."""
import numpy as np
import pytest

from omacad.model.section_hatch import cut_shape, hatch_and_outline

SQUARE = [[(0, 0), (10, 0), (10, 10), (0, 10)]]                 # counter-clockwise: material
HOLE = [(3, 3), (3, 7), (7, 7), (7, 3)]                          # clockwise: a hole


def test_square_is_hatched_inside_and_outlined():
    hatch, outline = hatch_and_outline(SQUARE, 2.0)
    assert len(outline) == 4
    assert np.allclose(sorted(np.linalg.norm(outline[:, 1] - outline[:, 0], axis=1)), [10, 10, 10, 10])
    assert len(hatch) > 5
    assert hatch.min() >= -1e-9 and hatch.max() <= 10 + 1e-9               # nothing outside the cut
    d = hatch[:, 1] - hatch[:, 0]
    assert np.allclose(np.abs(d[:, 0]), np.abs(d[:, 1]))                    # 45 degrees


def test_spacing_sets_the_number_of_lines():
    few, _ = hatch_and_outline(SQUARE, 4.0)
    many, _ = hatch_and_outline(SQUARE, 1.0)
    assert len(many) > 2.5 * len(few)


def test_holes_are_not_hatched():
    hatch, outline = hatch_and_outline(SQUARE + [HOLE], 1.0)
    assert cut_shape(SQUARE + [HOLE]).area == pytest.approx(100 - 16)
    mids = (hatch[:, 0] + hatch[:, 1]) / 2
    inside = (mids[:, 0] > 3.01) & (mids[:, 0] < 6.99) & (mids[:, 1] > 3.01) & (mids[:, 1] < 6.99)
    assert not inside.any()
    assert len(outline) == 8                                                # outer ring + hole ring


def test_empty_and_bad_input():
    h, o = hatch_and_outline([], 2.0)
    assert len(h) == 0 and len(o) == 0
    h, o = hatch_and_outline(SQUARE, 0.0)
    assert len(h) == 0


def test_viewport_builds_world_hatch_for_a_section(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    from omacad.ui import settings as settings_mod
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    d = Document()
    d.add_box(20, 20, 20)
    v = Viewport3D(d)
    v.set_section((0, 0, 0), (0, 0, 1), 10.0)
    hatch, outline = v._section_hatch(v.section)
    assert len(hatch) and len(outline)
    assert np.allclose(hatch[:, 2], 10.0, atol=0.2) and np.allclose(outline[:, 2], 10.0, atol=0.2)   # on the cut plane
