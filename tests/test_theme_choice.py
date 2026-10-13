"""Theme choice: follow Omarchy live, or pick a bundled theme that Omarchy switches cannot change."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.ui import theme  # noqa: E402


@pytest.fixture(autouse=True)
def reset():
    yield
    theme.FIXED_THEME = None
    theme._palette = theme.load_palette()


def test_themes_are_bundled_for_machines_without_omarchy():
    names = theme.available_themes()
    assert "tokyo-night" in names and "catppuccin-latte" in names and len(names) >= 10


def test_a_fixed_theme_gives_its_own_palette_and_builtin_gives_the_default():
    theme.set_fixed_theme("catppuccin-latte")
    light = theme.palette().canvas_rgb01()
    theme.set_fixed_theme("tokyo-night")
    dark = theme.palette().canvas_rgb01()
    assert sum(light) > sum(dark)                      # a light theme and a dark theme
    theme.set_fixed_theme(theme.BUILTIN)
    assert theme.palette().canvas_rgb01() is not None


def test_omarchy_switches_are_ignored_while_a_theme_is_fixed(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    seen = []
    w = theme.ThemeWatcher()
    w.changed.connect(lambda: seen.append(1))
    theme.set_fixed_theme("nord")
    w._reload()
    assert seen == []                                   # fixed: nothing happens
    theme.set_fixed_theme(None)
    w._reload()
    assert seen == [1]                                  # following Omarchy again: the switch is applied


def test_saved_choice_is_read_at_start(tmp_path, monkeypatch):
    from omacad.ui import settings as st
    s = st.SettingsManager(tmp_path / "s.json")
    s.set("theme_mode", "fixed")
    s.set("theme_name", "gruvbox")
    monkeypatch.setattr(st, "get_settings", lambda: s)
    theme.apply_saved_choice()
    assert theme.FIXED_THEME == "gruvbox"
    s.set("theme_mode", "omarchy")
    theme.apply_saved_choice()
    assert theme.FIXED_THEME is None
