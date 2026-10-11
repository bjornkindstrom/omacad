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
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.model.document import Document


class RibbonButton(QToolButton):
    """Large Fusion 360 style ribbon tool button with vertical icon and label."""

    def __init__(self, text: str, icon_symbol: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setText(text)
        self.setIcon(theme.emoji_icon(icon_symbol, 30))
        self.setIconSize(QSize(30, 30))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setMinimumHeight(76)
        style(self, """
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #D2D6DC;
                font-size: 10px;
                font-weight: 500;
                text-align: center;
                padding: 4px;
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
        """)
        # Width follows the font the stylesheet actually gives the button, so long labels
        # never overlap their neighbours (the Omarchy font is wider than a proportional one)
        self.ensurePolished()
        fm = self.fontMetrics()
        widest = max(fm.horizontalAdvance(line) for line in self.text().split("\n"))
        self.setMinimumWidth(max(68, widest + 22))


class Ribbon(QWidget):
    """Top command ribbon for CAD workspaces."""

    # Action Signals
    create_sketch_clicked = Signal()
    extrude_clicked = Signal()
    revolve_clicked = Signal()
    fillet_clicked = Signal()
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
        self.tabs.setFixedHeight(122)
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

        self.btn_rect = RibbonButton("2-Point\nRect (R)", "🔲")
        self.btn_rect.setCheckable(True)
        self.btn_rect.clicked.connect(lambda: self.select_sketch_tool("RECT"))
        h_layout.addWidget(self.btn_rect)

        self.btn_crect = RibbonButton("Center\nRect", "⛶")
        self.btn_crect.setCheckable(True)
        self.btn_crect.clicked.connect(lambda: self.select_sketch_tool("CENTER_RECT"))
        h_layout.addWidget(self.btn_crect)

        self.btn_circle = RibbonButton("Center\nCircle (C)", "⭕")
        self.btn_circle.setCheckable(True)
        self.btn_circle.clicked.connect(lambda: self.select_sketch_tool("CIRCLE"))
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
        btn_finish = QToolButton()
        btn_finish.setText("✅  Finish Sketch")
        btn_finish.setMinimumSize(140, 48)
        style(btn_finish, """
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
        btn_finish.clicked.connect(self.finish_sketch_clicked)
        h_layout.addWidget(btn_finish)

    def select_sketch_tool(self, tool_name: str):
        self.btn_line.setChecked(tool_name == "LINE")
        self.btn_rect.setChecked(tool_name == "RECT")
        self.btn_crect.setChecked(tool_name == "CENTER_RECT")
        self.btn_circle.setChecked(tool_name == "CIRCLE")
        self.btn_polygon.setChecked(tool_name == "POLYGON")
        self.btn_arc.setChecked(tool_name == "ARC")
        self.btn_slot.setChecked(tool_name == "SLOT")
        if hasattr(self, "btn_fillet_sk"):
            self.btn_fillet_sk.setChecked(tool_name == "FILLET")
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
            self.btn_crect.setChecked(False)
            self.btn_circle.setChecked(False)
            self.btn_arc.setChecked(False)
            self.btn_slot.setChecked(False)
            self.btn_dim.setChecked(False)
            self.btn_construct.setChecked(False)
