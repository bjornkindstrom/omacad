"""In-app guides: they load, every step has its picture, and the pictures stay small (see tools/guide_image.py) so the
repo and the packaged app do not grow with every guide we add."""
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from omacad.guide import find_guide, guides_root, list_guides
from omacad.ui.guide_dialog import GuideWindow

MAX_W, MAX_BYTES, MAX_TOTAL = 900, 120_000, 2_500_000


def test_guides_load_with_their_pictures():
    guides = list_guides()
    assert find_guide("offset_face_thread") in guides
    for g in guides:
        assert g.title and g.steps
        for s in g.steps:
            assert s.text and (s.image is None or s.image.is_file())


def test_pictures_stay_inside_the_size_budget():
    total = 0
    for img in guides_root().glob("*/*"):
        if img.suffix.lower() in (".jpg", ".jpeg", ".png"):
            assert img.suffix.lower() in (".jpg", ".jpeg"), f"{img}: use JPEG (tools/guide_image.py)"
            assert img.stat().st_size <= MAX_BYTES, f"{img}: {img.stat().st_size} bytes, run tools/guide_image.py"
            assert QImage(str(img)).width() <= MAX_W, f"{img}: wider than {MAX_W}px"
            total += img.stat().st_size
    assert total <= MAX_TOTAL, f"guides take {total} bytes"


def test_guide_window_steps_through():
    QApplication.instance() or QApplication([])
    g = find_guide("offset_face_thread")
    if g is None:
        return
    w = GuideWindow(g)
    assert w.index == 0 and not w.btn_prev.isEnabled()
    for _ in range(len(g.steps) - 1):
        w.btn_next.click()
    assert w.index == len(g.steps) - 1 and w.btn_next.text() == "Done"
    w.btn_prev.click()
    assert w.index == len(g.steps) - 2

