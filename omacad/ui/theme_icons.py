"""Icon rendering and menu icon style helpers."""

from pathlib import Path
from typing import Optional
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QProxyStyle, QStyle

_icon_cache = {}

ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"

EMOJI_TO_TOOL = {
    "✏️": "sketch",
    "📐": "offset_plane",
    "🖼️": "canvas",
    "📏": "measure",
    "✂️": "trim",
    "⬆️": "extrude",
    "🔄": "revolve",
    "🔘": "fillet",
    "◢": "chamfer",
    "🔁": "pattern",
    "📦": "box",
    "🥫": "cylinder",
    "⬢": "hexagon",
    "⚽": "sphere",
    "🧮": "parameters",
    "🔩": "thread",
    "🔗": "combine",
    "🪚": "split_body",
    "🐚": "shell",
    "↔️": "move",
    "✥": "move",
    "🗑️": "delete",
    "⚙️": "settings",
    "⭕": "circle",
    "⬡": "polygon",
    "⌒": "arc",
    "💊": "slot",
    "🔤": "text",
    "🔖": "emboss",
    "╭": "fillet_sk",
    "🪞": "mirror",
    "⧉": "offset_sk",
    "🟣": "project",
    "⚡": "construct",
    "🔲": "rect",
    "⛶": "rect",
    "▢": "rect",
    "▣": "rect",
}

def clear_icon_cache():
    _icon_cache.clear()

def tool_icon(symbol_or_name: str, px: int = 24) -> QIcon:
    """Returns a themed SVG vector QIcon (solid, blueprint, semantic) or falls back to emoji_icon."""
    from omacad.ui.settings import get_settings
    icon_theme = get_settings().get("icon_theme", "solid")
    tool_key = EMOJI_TO_TOOL.get(symbol_or_name, symbol_or_name)
    svg_path = ICONS_DIR / icon_theme / f"{tool_key}.svg"

    if not svg_path.exists():
        return emoji_icon(symbol_or_name, px)

    # Color adaptation for current theme
    from omacad.ui import theme
    active_palette = theme.palette()
    is_light = (active_palette.mode == "light")
    cur_color = "#1D2939" if is_light else "#E0E3E7"
    accent_color = active_palette.map_hex("#E26D28")

    cache_key = (icon_theme, tool_key, px, is_light, cur_color, accent_color)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    try:
        svg_text = svg_path.read_text(encoding="utf-8")
        # Replace currentColor with theme text color
        svg_text = svg_text.replace("currentColor", cur_color)
        if icon_theme != "semantic":
            svg_text = svg_text.replace("#E26D28", accent_color)

        scale = 2
        pm = QPixmap(px * scale, px * scale)
        pm.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        pm.setDevicePixelRatio(scale)
        icon = QIcon(pm)
        _icon_cache[cache_key] = icon
        return icon
    except Exception:
        return emoji_icon(symbol_or_name, px)

def emoji_icon(ch: str, px: int = 24) -> QIcon:
    """The emoji drawn as a real QIcon of a chosen size (emoji in text would stay at the font size)."""
    key = ("emoji", ch, px)
    if key not in _icon_cache:
        scale = 2  # crisp on HiDPI
        pm = QPixmap(px * scale, px * scale)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        font = QFont("Noto Color Emoji")
        font.setPixelSize(int(px * scale * 0.78))
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, ch)
        painter.end()
        pm.setDevicePixelRatio(scale)
        _icon_cache[key] = QIcon(pm)
    return _icon_cache[key]

def split_emoji(text: str):
    """('📁', 'Name') for '📁 Name'; ('', text) if the text does not start with an emoji."""
    import unicodedata
    head = text[:1]
    if head and ord(head) > 0x2000 and unicodedata.category(head) in ("So", "Sk") and head != "•":
        i = 1
        while i < len(text) and (ord(text[i]) in (0xFE0F, 0x200D) or unicodedata.category(text[i]) in ("Mn", "Sk")):
            i += 1
        return text[:i], text[i:].lstrip()
    return "", text

class BigIconStyle(QProxyStyle):
    """Larger icons everywhere in menus, tree views and tool buttons."""

    _SIZES = {
        QStyle.PixelMetric.PM_SmallIconSize: 24,
        QStyle.PixelMetric.PM_ToolBarIconSize: 30,
        QStyle.PixelMetric.PM_LargeIconSize: 36,
    }

    def pixelMetric(self, metric, option=None, widget=None):
        # Called for every widget while painting: it must never raise (an error here re-enters the style
        # while the error box is drawn and floods the screen on some PySide versions / Windows).
        try:
            size = self._SIZES.get(metric)
            if size is not None:
                return size
            return self.baseStyle().pixelMetric(metric, option, widget)
        except Exception:
            return 16

_big_icon_style_instance: Optional[BigIconStyle] = None

def ensure_big_icon_style(app) -> None:
    """Install BigIconStyle once on QApplication and keep a module-level reference."""
    global _big_icon_style_instance
    if app is not None and _big_icon_style_instance is None:
        _big_icon_style_instance = BigIconStyle("Fusion")
        app.setStyle(_big_icon_style_instance)
