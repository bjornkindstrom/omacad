import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Tests never read or write the user's real settings (they also set the global curve smoothness)."""
    try:
        from omacad.ui import settings as settings_mod
    except Exception:   # CI installs only the modelling dependencies
        yield
        return
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "settings.json"))
    yield
    from omacad.model import quality
    quality.set_circle_segments(quality.DEFAULT_SEGMENTS)
