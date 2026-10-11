"""The rectangle ribbon button: one button with a dropdown, and a remembered default."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from omacad.model.document import Document
from omacad.ui import settings as settings_mod
from omacad.ui.ribbon import RECT_TOOLS


@pytest.fixture
def ribbon(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.ribbon import Ribbon
    return Ribbon(Document())


def test_default_is_remembered_and_drives_the_button(ribbon):
    chosen = []
    ribbon.sketch_tool_selected.connect(chosen.append)
    ribbon.set_rect_default("ROUNDED_RECT")
    ribbon.btn_rect.click()
    assert chosen == ["ROUNDED_RECT"]
    assert settings_mod.get_settings().get("rect_default_tool") == "ROUNDED_RECT"
    assert ribbon.btn_rect.text() == RECT_TOOLS["ROUNDED_RECT"][0]


def test_dropdown_lists_every_kind(ribbon):
    labels = [a.text() for a in ribbon.btn_rect.menu().actions() if a.text()]
    assert all(t.replace("\n", " ") in labels for t, _ in RECT_TOOLS.values())
