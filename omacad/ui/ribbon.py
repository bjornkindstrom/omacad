"""
Omacad - Top Ribbon Toolbar
Fusion 360 style ribbon with SOLID, SKETCH tabs and tool buttons.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QToolButton, QLabel, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtGui import QFont, QFontMetrics
from omacad.ui.sketch_tools import RECT_TOOLS

CIRCLE_TOOLS = ('CIRCLE', 'SMART_CIRCLE')
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.model.document import Document



def ribbon_button_scale() -> float:
    from omacad.ui.settings import get_settings
    try:
        return float(get_settings().get("button_scale", 1.0))
    except Exception:
        return 1.0


class RibbonButton(QToolButton):
    """Large Fusion 360 style ribbon tool button with vertical icon and label."""

    def __init__(self, text: str, icon_symbol: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.raw_text = text
        self.icon_symbol = icon_symbol
        self.setText(text)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.apply_scale()

    def apply_scale(self):
        scale = ribbon_button_scale()
        icon_px = max(18, int(round(30 * scale)))
        font_px = max(8, int(round(10 * scale)))
        min_h = max(50, int(round(76 * scale)))
        self.setIcon(theme.emoji_icon(self.icon_symbol, icon_px))
        self.setIconSize(QSize(icon_px, icon_px))
        self.setMinimumHeight(min_h)
        style(self, f"""
            QToolButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #D2D6DC;
                font-size: {font_px}px;
                font-weight: 500;
                text-align: center;
                padding: {max(2, int(round(4 * scale)))}px;
            }}
            QToolButton:hover {{
                background-color: #353A42;
                border: 1px solid #484F5A;
                color: #FFFFFF;
            }}
            QToolButton:pressed, QToolButton:checked {{
                background-color: #E26D28;
                border: 1px solid #E26D28;
                color: #FFFFFF;
            }}
        """)
        self.ensurePolished()
        fm = self.fontMetrics()
        widest = max(fm.horizontalAdvance(line) for line in self.text().split("\n"))
        base_w = max(48, int(round(68 * scale)))
        pad_w = max(14, int(round(22 * scale)))
        self.setMinimumWidth(max(base_w, widest + pad_w))


class Ribbon(QWidget):
    """Top command ribbon for CAD workspaces."""

    # Action Signals
    create_sketch_clicked = Signal()
    extrude_clicked = Signal()
    revolve_clicked = Signal()
    fillet_clicked = Signal()
    project_clicked = Signal()
    chamfer_clicked = Signal()
    pattern_clicked = Signal()
    offset_plane_clicked = Signal()
    section_clicked = Signal()
    measure_clicked = Signal()
    parameters_clicked = Signal()
    box_clicked = Signal()
    cylinder_clicked = Signal()
    sphere_clicked = Signal()
    combine_clicked = Signal()
    delete_clicked = Signal()
    split_body_clicked = Signal()
    shell_clicked = Signal()
    move_clicked = Signal()
    canvas_clicked = Signal()
    inspect_clicked = Signal()
    settings_clicked = Signal()

    # Sketch Tools
    constraint_clicked = Signal(str)  # HORIZONTAL, VERTICAL, PARALLEL, ...
    sketch_tool_selected = Signal(str)  # "LINE", "RECT", "CENTER_RECT", "CIRCLE", "ARC", "SLOT", "FILLET", "DIMENSION"
    finish_sketch_clicked = Signal()
    toggle_construction_clicked = Signal()

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.sync_active_tab)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab Widget
        self.tabs = QTabWidget()
        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(max(80, int(round(122 * scale))))
        layout.addWidget(self.tabs)

        # 1. SOLID Tab
        self.solid_tab = QWidget()
        self.setup_solid_tab()
        self.tabs.addTab(self._scrollable(self.solid_tab), "SOLID")

        # 2. SKETCH Tab
        self.sketch_tab = QWidget()
        self.setup_sketch_tab()
        self.tabs.addTab(self._scrollable(self.sketch_tab), "SKETCH")

        # Hide sketch tab by default until sketch is started
        self.tabs.setTabVisible(1, False)

    def update_button_scale(self):
        """Update heights, icons and fonts for all ribbon buttons when button_scale setting changes."""
        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(max(80, int(round(122 * scale))))
        for btn in self.findChildren(RibbonButton):
            btn.apply_scale()
        if hasattr(self, "btn_finish") and self.btn_finish:
            self.btn_finish.setMinimumSize(max(100, int(round(140 * scale))), max(34, int(round(48 * scale))))

    @staticmethod
    def _scrollable(content: QWidget) -> QScrollArea:
        """A ribbon page scrolls sideways instead of squashing its buttons when the window is narrow
        (e.g. tiled to half the screen)."""
        area = QScrollArea()
        area.setWidget(content)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        style(area, """
            QScrollArea { background: transparent; }
            QScrollBar:horizontal { height: 6px; background: transparent; margin: 0; }
            QScrollBar::handle:horizontal { background: #484F5A; border-radius: 3px; min-width: 30px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)
        return area

    def setup_solid_tab(self):
        h_layout = QHBoxLayout(self.solid_tab)
        h_layout.setContentsMargins(8, 4, 8, 4)
        h_layout.setSpacing(6)

        # CREATE Group
        btn_sketch = RibbonButton("Create\nSketch", "✏️")
        btn_sketch.clicked.connect(self.create_sketch_clicked)
        h_layout.addWidget(btn_sketch)

        btn_plane = RibbonButton("Offset\nPlane", "📐")
        btn_plane.setToolTip("A new plane at a distance from a plane or face, or touching any surface (even a cylinder)")
        btn_plane.clicked.connect(self.offset_plane_clicked)
        h_layout.addWidget(btn_plane)

        btn_canvas = RibbonButton("Canvas\n(Bild)", "🖼️")
        btn_canvas.setToolTip("Insert a reference image on a plane, calibrate with tape measure and trace over it")
        btn_canvas.clicked.connect(self.canvas_clicked)
        h_layout.addWidget(btn_canvas)

        btn_measure = RibbonButton("Measure\n(I)", "📏")
        btn_measure.setToolTip("Click a line, circle or edge for its size; click a second one for the distance or angle between them")
        btn_measure.clicked.connect(self.measure_clicked)
        h_layout.addWidget(btn_measure)

        btn_section = RibbonButton("Section\nView", "✂️")
        btn_section.setToolTip("Cut through the model at a plane or face and slide the cut until you see what you want")
        btn_section.clicked.connect(self.section_clicked)
        h_layout.addWidget(btn_section)

        btn_extrude = RibbonButton("Extrude\n(E)", "⬆️")
        btn_extrude.clicked.connect(self.extrude_clicked)
        h_layout.addWidget(btn_extrude)

        btn_revolve = RibbonButton("Revolve", "🔄")
        btn_revolve.clicked.connect(self.revolve_clicked)
        h_layout.addWidget(btn_revolve)

        btn_fillet = RibbonButton("Fillet", "🔘")
        btn_fillet.setToolTip("Round edges (outside and inside corners): select edges, type a radius")
        btn_fillet.clicked.connect(self.fillet_clicked)
        h_layout.addWidget(btn_fillet)

        btn_chamfer = RibbonButton("Chamfer", "◢")
        btn_chamfer.setToolTip("Bevel edges (outside and inside corners): select edges, type a size")
        btn_chamfer.clicked.connect(self.chamfer_clicked)
        h_layout.addWidget(btn_chamfer)

        btn_pattern = RibbonButton("Pattern\nMirror", "🔁")
        btn_pattern.setToolTip("Copy a hole (and its chamfers) with even spacing, mirrored to all corners, or around an axis")
        btn_pattern.clicked.connect(self.pattern_clicked)
        h_layout.addWidget(btn_pattern)

        btn_box = RibbonButton("Box", "📦")
        btn_box.clicked.connect(self.box_clicked)
        h_layout.addWidget(btn_box)

        btn_cyl = RibbonButton("Cylinder", "🥫")
        btn_cyl.clicked.connect(self.cylinder_clicked)
        h_layout.addWidget(btn_cyl)

        btn_sph = RibbonButton("Sphere", "⚽")
        btn_sph.clicked.connect(self.sphere_clicked)
        h_layout.addWidget(btn_sph)

        btn_params = RibbonButton("Parameters", "🧮")
        btn_params.setToolTip("Named values usable in any number field (Ctrl+P)")
        btn_params.clicked.connect(self.parameters_clicked)
        h_layout.addWidget(btn_params)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        style(sep1, "color: #353940;")
        h_layout.addWidget(sep1)

        # MODIFY Group
        btn_combine = RibbonButton("Combine", "🔗")
        btn_combine.clicked.connect(self.combine_clicked)
        h_layout.addWidget(btn_combine)

        btn_split = RibbonButton("Split\nBody", "🪚")
        btn_split.setToolTip("Split a solid body into two using an offset plane or origin plane")
        btn_split.clicked.connect(self.split_body_clicked)
        h_layout.addWidget(btn_split)

        btn_shell = RibbonButton("Shell", "🐚")
        btn_shell.setToolTip("Hollow out a solid body with a specified wall thickness, opening selected faces")
        btn_shell.clicked.connect(self.shell_clicked)
        h_layout.addWidget(btn_shell)

        btn_move = RibbonButton("Move\n(M)", "↔️")
        btn_move.setToolTip("Translate or rotate a 3D solid body parametrically")
        btn_move.clicked.connect(self.move_clicked)
        h_layout.addWidget(btn_move)

        btn_del = RibbonButton("Delete", "🗑️")
        btn_del.clicked.connect(self.delete_clicked)
        h_layout.addWidget(btn_del)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        style(sep2, "color: #353940;")
        h_layout.addWidget(sep2)

        # INSPECT Group
        btn_inspect = RibbonButton("Measure", "📏")
        btn_inspect.clicked.connect(self.inspect_clicked)
        h_layout.addWidget(btn_inspect)

        # SETTINGS
        btn_settings = RibbonButton("Settings", "⚙️")
        btn_settings.setToolTip("Colors and app preferences (Ctrl+,)")
        btn_settings.clicked.connect(self.settings_clicked)
        h_layout.addWidget(btn_settings)

        h_layout.addStretch()

    def setup_sketch_tab(self):
        h_layout = QHBoxLayout(self.sketch_tab)
        h_layout.setContentsMargins(8, 4, 8, 4)
        h_layout.setSpacing(8)

        # Sketch Creation Tools
        self.btn_line = RibbonButton("Line\n(L)", "✏️")
        self.btn_line.setCheckable(True)
        self.btn_line.clicked.connect(lambda: self.select_sketch_tool("LINE"))
        h_layout.addWidget(self.btn_line)

        self._build_rect_button()
        h_layout.addWidget(self.btn_rect)

        self.btn_circle = RibbonButton("Center\nCircle (C)", "⭕")
        self.btn_circle.setCheckable(True)
        self.btn_circle.clicked.connect(lambda: self.select_sketch_tool("CIRCLE"))
        from PySide6.QtWidgets import QMenu, QToolButton
        self.btn_circle.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        circle_menu = QMenu(self.btn_circle)
        for tool, label in (("CIRCLE", "Center Circle  (C)"), ("SMART_CIRCLE", "Smart Circle  (Shift+C)")):
            circle_menu.addAction(label).triggered.connect(lambda _=False, t=tool: self.select_sketch_tool(t))
        self.btn_circle.setMenu(circle_menu)
        h_layout.addWidget(self.btn_circle)

        self.btn_polygon = RibbonButton("Polygon\n(P)", "⬡")
        self.btn_polygon.setCheckable(True)
        self.btn_polygon.setToolTip("Regular polygon: click the centre, move out, Tab to type the side length and the number of sides")
        self.btn_polygon.clicked.connect(lambda: self.select_sketch_tool("POLYGON"))
        h_layout.addWidget(self.btn_polygon)

        self.btn_arc = RibbonButton("3-Point\nArc (A)", "⌒")
        self.btn_arc.setCheckable(True)
        self.btn_arc.clicked.connect(lambda: self.select_sketch_tool("ARC"))
        h_layout.addWidget(self.btn_arc)

        self.btn_slot = RibbonButton("Center\nSlot", "💊")
        self.btn_slot.setCheckable(True)
        self.btn_slot.clicked.connect(lambda: self.select_sketch_tool("SLOT"))
        h_layout.addWidget(self.btn_slot)

        self.btn_fillet_sk = RibbonButton("Fillet\n(F)", "╭")
        self.btn_fillet_sk.setCheckable(True)
        self.btn_fillet_sk.setToolTip("Fillet (F): Round corners between two lines (click a corner or select lines)")
        self.btn_fillet_sk.clicked.connect(lambda: self.select_sketch_tool("FILLET"))
        h_layout.addWidget(self.btn_fillet_sk)

        self.btn_trim_sk = RibbonButton("Trim\n(T)", "✂️")
        self.btn_trim_sk.setCheckable(True)
        self.btn_trim_sk.setToolTip("Trim (T): remove the piece of a line, circle or arc up to the nearest crossings, or dangling stubs")
        self.btn_trim_sk.clicked.connect(lambda: self.select_sketch_tool("TRIM"))
        h_layout.addWidget(self.btn_trim_sk)

        self.btn_mirror_sk = RibbonButton("Mirror\n(Shift+M)", "🪞")
        self.btn_mirror_sk.setCheckable(True)
        self.btn_mirror_sk.setToolTip("Mirror (Shift+M): select elements first, then click a line or an origin axis to mirror across")
        self.btn_mirror_sk.clicked.connect(lambda: self.select_sketch_tool("MIRROR"))
        h_layout.addWidget(self.btn_mirror_sk)

        self.btn_offset_sk = RibbonButton("Offset\n(O)", "⧉")
        self.btn_offset_sk.setCheckable(True)
        self.btn_offset_sk.setToolTip("Offset (O): click curves (a click takes the whole connected chain, click more to add), then Enter and type the distance")
        self.btn_offset_sk.clicked.connect(lambda: self.select_sketch_tool("OFFSET"))
        h_layout.addWidget(self.btn_offset_sk)

        self.btn_project_sk = RibbonButton("Project\n(edges)", "🟣")
        self.btn_project_sk.setToolTip("Include / Project: turn the body edges lying in this sketch plane into sketch lines")
        self.btn_project_sk.clicked.connect(self.project_clicked)
        h_layout.addWidget(self.btn_project_sk)

        # Separator
        sep_dim = QFrame()
        sep_dim.setFrameShape(QFrame.Shape.VLine)
        style(sep_dim, "color: #353940;")
        h_layout.addWidget(sep_dim)

        btn_measure_s = RibbonButton("Measure\n(I)", "📏")
        btn_measure_s.setToolTip("Click a line or circle for its size; click a second one for the distance or angle between them")
        btn_measure_s.clicked.connect(self.measure_clicked)
        h_layout.addWidget(btn_measure_s)

        # Construction Toggle & Dimension Tool
        self.btn_construct = RibbonButton("Construct\n(X)", "⚡")
        self.btn_construct.setCheckable(True)
        self.btn_construct.setToolTip("Toggle Construction Geometry (X)")
        self.btn_construct.clicked.connect(self.toggle_construction_clicked)
        h_layout.addWidget(self.btn_construct)

        self.btn_dim = RibbonButton("Dimension\n(D)", "📏")
        self.btn_dim.setCheckable(True)
        self.btn_dim.clicked.connect(lambda: self.select_sketch_tool("DIMENSION"))
        h_layout.addWidget(self.btn_dim)

        self.btn_move = RibbonButton("Move\n(M)", "✥")
        self.btn_move.setCheckable(True)
        self.btn_move.setToolTip("Move selected sketch elements (M). Drag elements with the mouse to move them directly.")
        self.btn_move.clicked.connect(lambda: self.select_sketch_tool("MOVE"))
        h_layout.addWidget(self.btn_move)

        sep_con = QFrame()
        sep_con.setFrameShape(QFrame.Shape.VLine)
        style(sep_con, "color: #353940;")
        h_layout.addWidget(sep_con)

        # Constraints act on the selected sketch elements
        for ctype, label, icon, tip in (
            ("HORIZONTAL", "Horizontal", "━", "Make selected lines horizontal"),
            ("VERTICAL", "Vertical", "┃", "Make selected lines vertical"),
            ("COINCIDENT", "Coincident", "•", "Join the nearest end points of two selected lines"),
            ("PARALLEL", "Parallel", "∥", "Make selected lines parallel"),
            ("PERPENDICULAR", "Perpendic.", "⟂", "Make selected lines perpendicular"),
            ("EQUAL", "Equal", "＝", "Equal length (lines) or radius (circles)"),
            ("TANGENT", "Tangent", "◠", "Tangent: line + circle, or two circles"),
            ("CONCENTRIC", "Concentric", "◎", "Same centre for two circles"),
            ("FIX", "Fix", "🔒", "Lock selected lines/circles in place"),
        ):
            btn = RibbonButton(label, icon)
            btn.setToolTip(tip + "  (select elements first)")
            btn.clicked.connect(lambda _=False, c=ctype: self.constraint_clicked.emit(c))
            h_layout.addWidget(btn)

        h_layout.addStretch()

        # Big Green Finish Sketch Button (Fusion 360 hallmark)
        scale = ribbon_button_scale()
        self.btn_finish = QToolButton()
        self.btn_finish.setText("✅  Finish Sketch")
        self.btn_finish.setMinimumSize(max(100, int(round(140 * scale))), max(34, int(round(48 * scale))))
        style(self.btn_finish, """
            QToolButton {
                background-color: #2E7D32;
                border: 1px solid #388E3C;
                border-radius: 4px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background-color: #388E3C;
            }
            QToolButton:pressed {
                background-color: #1B5E20;
            }
        """)
        self.btn_finish.clicked.connect(self.finish_sketch_clicked)
        h_layout.addWidget(self.btn_finish)

    def _build_rect_button(self):
        """One rectangle button with a dropdown: the button itself draws the default rectangle,
        the arrow lists all kinds and lets you pick which one is the default (remembered)."""
        from PySide6.QtGui import QAction, QActionGroup
        from PySide6.QtWidgets import QMenu, QToolButton
        from omacad.ui.settings import get_settings
        self.btn_rect = RibbonButton("Rounded\nRect", "▢")      # widest label sets the width
        self.btn_rect.setCheckable(True)
        self.btn_rect.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu = QMenu(self.btn_rect)
        for tool, (label, _icon) in RECT_TOOLS.items():
            act = menu.addAction(label.replace("\n", " "))
            act.triggered.connect(lambda _=False, t=tool: self.select_sketch_tool(t))
        menu.addSeparator()
        default_menu = menu.addMenu("Button default")
        group = QActionGroup(default_menu)
        self._rect_default_actions = {}
        for tool, (label, _icon) in RECT_TOOLS.items():
            act = default_menu.addAction(label.replace("\n", " "))
            act.setCheckable(True)
            act.setActionGroup(group)
            act.triggered.connect(lambda _=False, t=tool: self.set_rect_default(t))
            self._rect_default_actions[tool] = act
        self.btn_rect.setMenu(menu)
        self.btn_rect.clicked.connect(lambda: self.select_sketch_tool(self.rect_default))
        self.set_rect_default(get_settings().get("rect_default_tool", "RECT"), save=False)

    def set_rect_default(self, tool: str, save: bool = True):
        """The rectangle kind the button draws when clicked; shown on the button and remembered."""
        from omacad.ui.settings import get_settings
        if tool not in RECT_TOOLS:
            tool = "RECT"
        self.rect_default = tool
        label, icon = RECT_TOOLS[tool]
        self.btn_rect.setText(label)
        self.btn_rect.setIcon(theme.emoji_icon(icon, 30))
        self._rect_default_actions[tool].setChecked(True)
        if save:
            get_settings().set("rect_default_tool", tool)

    def select_sketch_tool(self, tool_name: str):
        self.btn_line.setChecked(tool_name == "LINE")
        self.btn_rect.setChecked(tool_name in RECT_TOOLS)
        self.btn_circle.setChecked(tool_name in CIRCLE_TOOLS)
        self.btn_polygon.setChecked(tool_name == "POLYGON")
        self.btn_arc.setChecked(tool_name == "ARC")
        self.btn_slot.setChecked(tool_name == "SLOT")
        if hasattr(self, "btn_fillet_sk"):
            self.btn_fillet_sk.setChecked(tool_name == "FILLET")
        if hasattr(self, "btn_offset_sk"):
            self.btn_offset_sk.setChecked(tool_name == "OFFSET")
        if hasattr(self, "btn_mirror_sk"):
            self.btn_mirror_sk.setChecked(tool_name == "MIRROR")
        if hasattr(self, "btn_trim_sk"):
            self.btn_trim_sk.setChecked(tool_name == "TRIM")
        self.btn_dim.setChecked(tool_name == "DIMENSION")
        self.btn_move.setChecked(tool_name == "MOVE")
        self.sketch_tool_selected.emit(tool_name)

    def sync_active_tab(self):
        """Shows/hides SKETCH tab when sketch is active."""
        is_sketching = (self.doc.active_sketch is not None)
        self.tabs.setTabVisible(1, is_sketching)
        if is_sketching:
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)
            self.btn_line.setChecked(False)
            self.btn_rect.setChecked(False)
            self.btn_circle.setChecked(False)
            self.btn_arc.setChecked(False)
            self.btn_slot.setChecked(False)
            self.btn_dim.setChecked(False)
            self.btn_construct.setChecked(False)
