"""
Omacad - Application Settings & Preferences
Stores persistent user preferences (colors, sketch palette position, behavior) in ~/.config/omacad/settings.json.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

CONFIG_DIR = Path.home() / ".config" / "omacad"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Colors (hex strings like "#3498DB", or None for theme highlight default)
    "arrow_color": None,                # None = follow theme highlight
    "measure_color": "#FFAA3C",         # Accent orange
    "sketch_line_color": "#4CE0FF",     # Vibrant cyan
    "sketch_construction_color": "#FFCC4D", # Amber / gold
    "highlight_color": None,            # None = follow theme highlight
    # Palette & UI options
    "palette_position": "bottom_right", # "bottom_right", "top_left", "bottom_left", "top_right"
    "autohide_palette_on_measure": True,
    "invert_zoom": False,
    "grid_step": 5.0,
    "fillet_default_radius": 2.0,
}


def hex_to_rgb01(hex_str: Optional[str]) -> Optional[Tuple[float, float, float]]:
    if not hex_str:
        return None
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        return None
    try:
        r = int(hex_str[0:2], 16) / 255.0
        g = int(hex_str[2:4], 16) / 255.0
        b = int(hex_str[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return None


def rgb01_to_hex(r: float, g: float, b: float) -> str:
    ir = max(0, min(255, int(round(r * 255))))
    ig = max(0, min(255, int(round(g * 255))))
    ib = max(0, min(255, int(round(b * 255))))
    return f"#{ir:02X}{ig:02X}{ib:02X}"


class SettingsManager(QObject):
    changed = Signal()

    def __init__(self, config_file: Optional[Path] = None):
        super().__init__()
        self.config_file = config_file or SETTINGS_FILE
        self._data: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    self._data.update(saved)
            except Exception as e:
                print(f"[Settings] Failed to load {self.config_file}: {e}")

    def save(self):
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[Settings] Failed to save {self.config_file}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()
        self.changed.emit()

    def update(self, new_values: Dict[str, Any]):
        self._data.update(new_values)
        self.save()
        self.changed.emit()

    def reset_defaults(self):
        self._data = dict(DEFAULT_SETTINGS)
        self.save()
        self.changed.emit()

    # --- Convenience Color Getters ---
    def arrow_color_rgb01(self) -> Optional[Tuple[float, float, float]]:
        return hex_to_rgb01(self.get("arrow_color"))

    def measure_color_qcolor(self) -> QColor:
        hex_c = self.get("measure_color") or DEFAULT_SETTINGS["measure_color"]
        return QColor(hex_c)

    def sketch_line_color_rgb01(self) -> Tuple[float, float, float]:
        rgb = hex_to_rgb01(self.get("sketch_line_color"))
        return rgb if rgb is not None else (0.30, 0.88, 1.0)

    def sketch_construction_color_rgb01(self) -> Tuple[float, float, float]:
        rgb = hex_to_rgb01(self.get("sketch_construction_color"))
        return rgb if rgb is not None else (1.0, 0.80, 0.30)

    def highlight_color_rgb01(self) -> Optional[Tuple[float, float, float]]:
        return hex_to_rgb01(self.get("highlight_color"))


_instance: Optional[SettingsManager] = None


def get_settings() -> SettingsManager:
    global _instance
    if _instance is None:
        _instance = SettingsManager()
    return _instance
