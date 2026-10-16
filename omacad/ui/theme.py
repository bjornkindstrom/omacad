"""
Omacad - Theme
Follows the active Omarchy theme (~/.local/state/omarchy/current/theme/colors.toml) and its
font, and re-applies itself live when the theme is switched.

The widgets' stylesheets were written with a fixed dark palette. Instead of rewriting every
colour, `themeify` maps them onto the Omarchy palette:
  * neutral greys/blues are placed on the line from the theme's darkest background to its
    foreground by lightness (so light themes invert correctly),
  * the orange accent family becomes the theme accent (chrome) or the theme's most vivid
    colour (the 3D highlight),
  * saturated semantic colours (greens, snap-marker blues ...) are left alone.
"""

import colorsys
import re
import subprocess
import sys
import tomllib
import weakref
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QByteArray, QFileSystemWatcher, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QProxyStyle, QStyle

STATE_DIR = Path.home() / ".local/state/omarchy/current"
COLORS_FILE = STATE_DIR / "theme/colors.toml"
NAME_FILE = STATE_DIR / "theme.name"

# Bundled themes (the Omarchy ones, copied into assets/themes so they also exist where Omarchy does not, e.g. Windows).
THEMES_DIR = Path(__file__).resolve().parents[2] / "assets" / "themes"
BUILTIN = "builtin"          # the original Omacad dark palette
CUSTOM_DIR = Path.home() / ".config" / "omacad" / "themes"   # themes made in the Settings theme editor
CUSTOM_PREFIX = "user:"      # FIXED_THEME / theme_name of a custom theme: "user:<name>"
PREVIEW: Optional[dict] = None   # unsaved colours from the theme editor, shown live
FIXED_THEME: Optional[str] = None   # None = follow the Omarchy theme live; otherwise the name of a bundled theme (or BUILTIN)

RGB = Tuple[float, float, float]


def _rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(c: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in c))


def _lum(c: RGB) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


def _sat(c: RGB) -> float:
    mx, mn = max(c), min(c)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _chroma(c: RGB) -> float:
    return (max(c) - min(c)) / 255.0


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))  # type: ignore[return-value]


ORANGE_BASE = _rgb("#E26D28")   # the accent every stylesheet was written with
NEUTRAL_MAX_CHROMA = 0.25  # (max-min)/255; HSV saturation would misjudge very dark navy greys


class Palette:
    """Omarchy colours plus the derived roles the app needs. Without a theme file the app
    keeps its original look (identity mapping)."""

    def __init__(self, data: Optional[dict]):
        self.loaded = bool(data)
        d = data or {}

        def col(key: str, default: str) -> RGB:
            return _rgb(d.get(key, default))

        self.mode = d.get("mode", "dark")
        self.background = col("background", "#1E2022")
        self.darker = col("darker_background", "#1A1C1E")
        self.foreground = col("foreground", "#E0E3E7")
        self.accent = col("accent", "#E26D28")
        self.muted = col("muted", "#8E95A0")
        # most vivid colour of the theme: used for 3D selection/hover highlights
        vivid = [col(k, "#000000") for k in (
            "accent", "red", "yellow", "green", "cyan", "blue", "magenta",
            "bright_red", "bright_yellow", "bright_green", "bright_cyan", "bright_blue", "bright_magenta",
        ) if k in d]
        best = max(vivid, key=lambda c: _sat(c) * (0.4 + _lum(c)), default=ORANGE_BASE)
        self.highlight = best if (self.loaded and _sat(best) >= 0.3) else ORANGE_BASE
        if not self.loaded:
            self.highlight = ORANGE_BASE
        # explicit overrides from the theme editor
        self.canvas = _rgb(d["canvas"]) if "canvas" in d else None
        self.grid = _rgb(d["grid"]) if "grid" in d else None
        if "highlight" in d:
            self.highlight = _rgb(d["highlight"])

    # -- mapping -----------------------------------------------------------
    def _neutral(self, c: RGB) -> RGB:
        t = max(0.0, min(1.0, (_lum(c) - 0.10) / 0.80))
        return _mix(self.darker, self.foreground, t)

    def _accentish(self, c: RGB, target: RGB) -> RGB:
        ratio = max(c) / max(ORANGE_BASE)
        return tuple(min(255.0, v * ratio) for v in target)  # type: ignore[return-value]

    def map_rgb(self, c: RGB, orange: str = "accent") -> RGB:
        if not self.loaded:
            return c
        if _lum(c) > 0.97 and _sat(c) < 0.05:
            return c  # pure white text stays white
        if _chroma(c) < NEUTRAL_MAX_CHROMA:
            return self._neutral(c)
        h, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
        if 0.03 <= h <= 0.12 and s > 0.5:  # the orange family
            return self._accentish(c, self.accent if orange == "accent" else self.highlight)
        return c

    def map_hex(self, h: str) -> str:
        return _hex(self.map_rgb(_rgb(h)))

    # -- roles used directly by the viewport ----------------------------------
    def canvas_rgb01(self) -> Tuple[float, float, float]:
        if self.canvas is not None:
            return tuple(v / 255.0 for v in self.canvas)  # type: ignore[return-value]
        c = _mix(self.darker, self.background, 0.5) if self.loaded else (41, 43, 48)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]

    def grid_rgb01(self) -> Tuple[float, float, float]:
        if self.grid is not None:
            return tuple(v / 255.0 for v in self.grid)  # type: ignore[return-value]
        c = _mix(tuple(v * 255 for v in self.canvas_rgb01()), self.foreground, 0.16)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]

    def highlight01(self, lighten: float = 0.0) -> Tuple[float, float, float]:
        c = _mix(self.highlight, (255, 255, 255), lighten)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]


def available_themes() -> List[str]:
    """Names of the bundled themes, for the settings list."""
    try:
        return sorted(p.stem for p in THEMES_DIR.glob("*.toml"))
    except OSError:
        return []


def custom_themes() -> List[str]:
    """Names of the themes saved from the theme editor."""
    try:
        return sorted(p.stem for p in CUSTOM_DIR.glob("*.toml"))
    except OSError:
        return []


def load_theme_data(key: str) -> Optional[dict]:
    """Raw colours of a theme key: BUILTIN (editor defaults), "user:<name>" or a bundled theme name."""
    try:
        if key == BUILTIN:
            return None
        base = CUSTOM_DIR / f"{key[len(CUSTOM_PREFIX):]}.toml" if key.startswith(CUSTOM_PREFIX) else THEMES_DIR / f"{key}.toml"
        with open(base, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def safe_theme_name(name: str) -> str:
    return re.sub(r"[^\w\- ]", "", name).strip()


def save_custom_theme(name: str, data: dict) -> str:
    """Writes ~/.config/omacad/themes/<name>.toml and returns its theme key."""
    name = safe_theme_name(name)
    if not name:
        raise ValueError("Give the theme a name")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v!r}" for k, v in data.items() if v is not None]
    (CUSTOM_DIR / f"{name}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CUSTOM_PREFIX + name


def delete_custom_theme(name: str) -> None:
    try:
        (CUSTOM_DIR / f"{safe_theme_name(name)}.toml").unlink()
    except OSError:
        pass


def set_preview(data: Optional[dict]) -> None:
    """Show unsaved editor colours live (None = back to the chosen theme)."""
    global PREVIEW
    PREVIEW = data
    refresh()


def set_fixed_theme(name: Optional[str]) -> None:
    """Pick a theme by hand (the app then ignores Omarchy theme switches), or None to follow Omarchy again."""
    global FIXED_THEME
    FIXED_THEME = name or None
    refresh()


def apply_saved_choice() -> None:
    """Read the theme choice from the settings; called at start-up before any widget is built."""
    global FIXED_THEME, _palette
    try:
        from omacad.ui.settings import get_settings
        st = get_settings()
        mode = st.get("theme_mode", "omarchy")
        if mode == "omarchy":
            FIXED_THEME = None
        elif mode == "light":
            FIXED_THEME = "catppuccin-latte"
        elif mode == "dark":
            dark_name = st.get("dark_theme_name", "tokyo-night")
            FIXED_THEME = dark_name if dark_name in ("tokyo-night", "nord") else "tokyo-night"
        elif mode == "fixed":
            FIXED_THEME = st.get("theme_name") or "tokyo-night"
        else:
            FIXED_THEME = None
    except Exception:
        FIXED_THEME = None
    _palette = load_palette()


def load_palette() -> Palette:
    if PREVIEW:
        return Palette(PREVIEW)
    if FIXED_THEME:
        if FIXED_THEME == BUILTIN:
            return Palette(None)
        return Palette(load_theme_data(FIXED_THEME))
    try:
        with open(COLORS_FILE, "rb") as f:
            return Palette(tomllib.load(f))
    except (OSError, tomllib.TOMLDecodeError):
        return Palette(None)


def current_font() -> str:
    """The Omarchy UI font (monospace by default in Omarchy)."""
    try:
        out = subprocess.run(["omarchy-font-current"], capture_output=True, text=True, timeout=2).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


_palette = load_palette()
_font = current_font()
_styled: List[Tuple["weakref.ref", str]] = []

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")
_FONT = re.compile(r"font-family:[^;]*;")


def font_family() -> str:
    return _font or ("Segoe UI" if sys.platform == "win32" else "Sans")


# ---- Icons --------------------------------------------------------------------
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
    is_light = (_palette.mode == "light")
    cur_color = "#1D2939" if is_light else "#E0E3E7"
    accent_color = _palette.map_hex("#E26D28")

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


def action_with_icon(menu, text: str, px: int = 22):
    """menu.addAction for a label that starts with an emoji: the emoji becomes the icon."""
    emoji, rest = split_emoji(text)
    if emoji:
        return menu.addAction(emoji_icon(emoji, px), rest)
    return menu.addAction(text)


def palette() -> Palette:
    return _palette


_ARROW_DIR = Path.home() / ".cache/omacad/arrows"


def _arrow_png(direction: str) -> str:
    """Path of a small up/down arrow image in the theme's text colour (for spin box buttons)."""
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    colour = _palette.map_hex("#E0E3E7")
    path = _ARROW_DIR / f"{direction}_{colour.lstrip('#')}.png"
    if not path.exists():
        _ARROW_DIR.mkdir(parents=True, exist_ok=True)
        pm = QPixmap(18, 18)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colour))
        pts = [(3, 12), (15, 12), (9, 5)] if direction == "up" else [(3, 6), (15, 6), (9, 13)]
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        p.end()
        pm.save(str(path))
    return str(path)


def themeify(css: str) -> str:
    """Maps the colours (and font) of a stylesheet onto the active Omarchy theme."""
    if "@ARROW_UP@" in css:
        css = css.replace("@ARROW_UP@", _arrow_png("up").replace("\\", "/"))
    if "@ARROW_DOWN@" in css:
        css = css.replace("@ARROW_DOWN@", _arrow_png("down").replace("\\", "/"))
    css = _HEX.sub(lambda m: _palette.map_hex(m.group(0)), css)

    def rgba(m):
        r, g, b = _palette.map_rgb((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        a = m.group(4)
        return f"rgba({round(r)}, {round(g)}, {round(b)}, {a})" if a is not None else f"rgb({round(r)}, {round(g)}, {round(b)})"
    css = _RGBA.sub(rgba, css)
    if _font:
        css = _FONT.sub(f'font-family: "{_font}", monospace;', css)
    return css


def style(widget, css: str) -> None:
    """setStyleSheet that follows the theme, including later theme switches."""
    widget.setStyleSheet(themeify(css))
    _styled.append((weakref.ref(widget), css))


def qcolor(r: int, g: int, b: int, a: int = 255) -> QColor:
    """Themed QColor for painter code (orange becomes the 3D highlight colour)."""
    nr, ng, nb = _palette.map_rgb((r, g, b), orange="highlight")
    return QColor(round(nr), round(ng), round(nb), a)


def apply_qt_palette() -> None:
    """Gives Qt's own palette the theme colours too: widgets without a stylesheet (the inside of scroll
    areas, the ribbon behind the buttons) otherwise stay Fusion dark whatever the theme is."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None or not _palette.loaded:
        return
    m = lambda h: QColor(_palette.map_hex(h))
    pal = QPalette()
    for role, h in ((QPalette.ColorRole.Window, "#1E2022"), (QPalette.ColorRole.Base, "#25282C"),
                    (QPalette.ColorRole.AlternateBase, "#2D3136"), (QPalette.ColorRole.Button, "#2D3136"),
                    (QPalette.ColorRole.ToolTipBase, "#25282C"), (QPalette.ColorRole.Text, "#E0E3E7"),
                    (QPalette.ColorRole.WindowText, "#E0E3E7"), (QPalette.ColorRole.ButtonText, "#E0E3E7"),
                    (QPalette.ColorRole.ToolTipText, "#E0E3E7")):
        pal.setColor(role, m(h))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(*(round(v) for v in _palette.accent)))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(*(round(v) for v in _palette.darker)))
    app.setPalette(pal)


def refresh() -> None:
    global _palette, _font
    _palette = load_palette()
    _font = current_font()
    apply_qt_palette()
    alive = []
    for ref, css in _styled:
        w = ref()
        if w is not None:
            try:
                w.setStyleSheet(themeify(css))
                alive.append((ref, css))
            except RuntimeError:
                pass  # widget already deleted
    _styled[:] = alive


class ThemeWatcher(QObject):
    """Emits `changed` after the Omarchy theme (or its colours) changed on disk."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fs = QFileSystemWatcher(self)
        self._fs.fileChanged.connect(self._poke)
        self._fs.directoryChanged.connect(self._poke)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)  # a theme switch rewrites many files
        self._timer.timeout.connect(self._reload)
        self._watch()

    def _watch(self):
        paths = [str(p) for p in (STATE_DIR, STATE_DIR / "theme", NAME_FILE, COLORS_FILE) if p.exists()]
        missing = [p for p in paths if p not in self._fs.files() + self._fs.directories()]
        if missing:
            self._fs.addPaths(missing)

    def _poke(self, *_):
        self._timer.start()

    def _reload(self):
        self._watch()  # replaced files fall out of the watch list
        if FIXED_THEME or PREVIEW:
            return     # a theme was picked by hand: Omarchy theme switches are ignored
        refresh()
        self.changed.emit()



_BASE_CSS = """
QMainWindow {
    background-color: #1E2022;
    color: #E0E3E7;
}

QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Cantarell", sans-serif;
    font-size: 13px;
    color: #E0E3E7;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #333842;
    border-radius: 6px;
    margin-top: 22px;
    padding: 10px 8px 8px 8px;
    background-color: #202226;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #E26D28;
}

/* Menu Bar */
QMenuBar {
    background-color: #1E2022;
    color: #C5CBD3;
    border-bottom: 1px solid #33373E;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background-color: #2D3136;
    color: #FFFFFF;
}

QMenu {
    background-color: #25282C;
    border: 1px solid #3D424A;
    border-radius: 4px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 24px 6px 16px;
}
QMenu::item:selected {
    background-color: #E26D28;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #383D45;
    margin: 4px 8px;
}

/* ToolBar & Ribbon */
QToolBar {
    background-color: #25282C;
    border-bottom: 1px solid #353940;
    padding: 4px 6px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #D2D6DC;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #353A42;
    border: 1px solid #484F5A;
    color: #FFFFFF;
}
QToolButton:pressed, QToolButton:checked {
    background-color: #E26D28;
    border: 1px solid #E26D28;
    color: #FFFFFF;
}

/* Tab Bar (Ribbon workspaces) */
QTabWidget::pane {
    border-top: 1px solid #353940;
    background: #25282C;
}
QTabBar::tab {
    background: #1E2022;
    color: #9AA0A6;
    padding: 6px 16px;
    border: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-weight: bold;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #25282C;
    color: #FFFFFF;
    border-bottom: 2px solid #E26D28;
}
QTabBar::tab:hover:!selected {
    background: #272A2E;
    color: #D2D6DC;
}

/* Dock Widgets & Panels */
QDockWidget {
    background: transparent;
    color: #E0E3E7;
    titlebar-close-icon: url();
    titlebar-normal-icon: url();
}
QDockWidget::title {
    background: transparent;
    padding: 6px 10px;
    border-bottom: 1px solid #33373D;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: #8E95A0;
}

/* Tree Views (Browser Panel) */
QTreeView, QTreeWidget {
    background: transparent;
    border: none;
    color: #D8DCE2;
    outline: none;
    padding: 4px;
}
QTreeView::item {
    padding: 5px 4px;
    border-radius: 3px;
}
QTreeView::item:hover {
    background-color: #2B2F35;
}
QTreeView::item:selected {
    background-color: #383E47;
    color: #FFFFFF;
}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none;
}

/* Buttons */
QPushButton {
    background-color: #33373E;
    color: #E0E3E7;
    border: 1px solid #4D535E;
    border-bottom: 2px solid #25282D;
    border-radius: 5px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #3E434C;
    border-color: #5C6370;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #E26D28;
    border: 1px solid #E26D28;
    border-top: 2px solid #B85317;
    color: #FFFFFF;
    padding-top: 8px;
}
QPushButton#PrimaryButton, QPushButton:default {
    background-color: #E26D28;
    border: 1px solid #FF7E36;
    border-bottom: 2px solid #B85317;
    color: #FFFFFF;
    font-weight: bold;
    padding: 7px 22px;
}
QPushButton#PrimaryButton:hover, QPushButton:default:hover {
    background-color: #FF7E36;
    border-color: #FFA566;
    color: #FFFFFF;
}
QPushButton#PrimaryButton:pressed, QPushButton:default:pressed {
    background-color: #C45B1C;
    border: 1px solid #B85317;
    border-top: 2px solid #8C3A0A;
    color: #FFFFFF;
    padding-top: 8px;
}

QPushButton#SuccessButton {
    background-color: #2E7D32;
    border: 1px solid #388E3C;
    border-bottom: 2px solid #1B5E20;
    color: #FFFFFF;
    font-weight: bold;
    padding: 7px 18px;
}
QPushButton#SuccessButton:hover {
    background-color: #388E3C;
    border-color: #4CAF50;
}
QPushButton#SuccessButton:pressed {
    background-color: #1B5E20;
    border: 1px solid #1B5E20;
    padding-top: 8px;
}

/* Input Fields & Spinners */
QLineEdit, QDoubleSpinBox, QSpinBox {
    background-color: #1A1C1E;
    border: 1px solid #4D535E;
    border-radius: 4px;
    color: #E0E3E7;
    padding: 5px 8px;
    selection-background-color: #E26D28;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #E26D28;
}
QSpinBox, QDoubleSpinBox {
    padding-right: 22px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: #33373E;
    border-left: 1px solid #555C68;
    border-bottom: 1px solid #555C68;
    border-top-right-radius: 4px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: #33373E;
    border-left: 1px solid #555C68;
    border-bottom-right-radius: 4px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #555C68;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: #E26D28;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(@ARROW_UP@);
    width: 9px;
    height: 9px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(@ARROW_DOWN@);
    width: 9px;
    height: 9px;
}

/* Dropdown ComboBox: distinct button box with drop-down arrow */
QComboBox {
    background-color: #2D3138;
    border: 1px solid #555C68;
    border-bottom: 2px solid #20242A;
    border-radius: 5px;
    color: #E0E3E7;
    padding: 5px 28px 5px 10px;
    font-weight: 500;
    min-height: 20px;
}
QComboBox:hover {
    background-color: #383D46;
    border-color: #6C7482;
    color: #FFFFFF;
}
QComboBox:focus, QComboBox:on {
    border: 1px solid #E26D28;
    border-bottom: 2px solid #B85317;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #4D535E;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background-color: #282C32;
}
QComboBox::drop-down:hover {
    background-color: #3E434C;
}
QComboBox::down-arrow {
    image: url(@ARROW_DOWN@);
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background-color: #25282D;
    border: 1px solid #4D535E;
    border-radius: 4px;
    color: #E0E3E7;
    selection-background-color: #E26D28;
    selection-color: #FFFFFF;
    padding: 4px;
}

/* Sliders */
QSlider::groove:horizontal {
    border: 1px solid #33373E;
    height: 4px;
    background: #1A1C1E;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #E26D28;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #E0E3E7;
    border: 1px solid #33373E;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #FFFFFF;
    border-color: #E26D28;
}

/* Status Bar */
QStatusBar {
    background-color: #1A1C1E;
    color: #8E95A0;
    border-top: 1px solid #2B2E33;
    font-size: 12px;
    padding: 2px 10px;
}
"""


def indicator_stylesheet() -> str:
    """Tick boxes (also inside lists and trees) drawn from two small SVGs in the theme's colours: a visible empty box
    and a filled box with a white tick. (QSS borders are not painted for item-view indicators, so images are used.)"""
    import tempfile
    accent = _palette.map_hex("#E26D28")
    border, fill = _palette.map_hex("#6B7280"), _palette.map_hex("#2A2F37")
    folder = Path(tempfile.gettempdir()) / "omacad-ui"
    folder.mkdir(parents=True, exist_ok=True)
    off, on = folder / "check_off.svg", folder / "check_on.svg"
    off.write_text(f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="14" height="14" rx="3" '
                   f'fill="{fill}" stroke="{border}" stroke-width="1.4"/></svg>', encoding="utf-8")
    on.write_text(f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="14" height="14" rx="3" '
                  f'fill="{accent}" stroke="{accent}" stroke-width="1.4"/><polyline points="4,8.5 7,11.5 12,5" fill="none" '
                  f'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
    views = "QListView::indicator, QTreeView::indicator, QCheckBox::indicator"
    return (f"{views} {{ width: 16px; height: 16px; }}\n"
            + ", ".join(f"{v}:unchecked" for v in views.split(", ")) + f" {{ image: url({off.as_posix()}); }}\n"
            + ", ".join(f"{v}:checked" for v in views.split(", ")) + f" {{ image: url({on.as_posix()}); }}\n")


def base_stylesheet() -> str:
    return themeify(_BASE_CSS)
