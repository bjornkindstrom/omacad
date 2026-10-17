"""
Omacad - Top Ribbon Toolbar
Fusion 360 style ribbon with SOLID, SKETCH tabs and tool buttons.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabBar, QTabWidget, QToolButton, QLabel, QFrame, QSizePolicy, QScrollArea
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


def ribbon_labels() -> bool:
    """Whether ribbon buttons show their name under the icon (off = icon only, name in the tooltip)."""
    from omacad.ui.settings import get_settings
    return bool(get_settings().get("show_button_labels", False))


def ribbon_height(scale: float) -> int:
    """Height of the ribbon tab widget: tab bar + one row of buttons."""
    if ribbon_labels():
        return max(70, int(round(104 * scale)))
    return max(50, int(round(66 * scale)))


class RibbonButton(QToolButton):
    """Large Fusion 360 style ribbon tool button with vertical icon and label."""

    def __init__(self, text: str, icon_symbol: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.raw_text = text
        self.icon_symbol = icon_symbol
        self.setText(text)
        self.apply_scale()
        self.setToolTip("")

    def setToolTip(self, tip: str):
        """The tooltip always starts with the button's name, since the label may be hidden."""
        name = " ".join(self.raw_text.split())
        super().setToolTip(f"<b>{name}</b><br>{tip}" if tip and tip != name else f"<b>{name}</b>")

    def apply_scale(self):
        scale = ribbon_button_scale()
        icon_px = max(18, int(round(30 * scale)))
        font_px = max(8, int(round(10 * scale)))
        min_h = max(44, int(round(62 * scale)))
        labels = ribbon_labels()
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if labels
                                else Qt.ToolButtonStyle.ToolButtonIconOnly)
        if not labels:
            min_h = icon_px + max(6, int(round(8 * scale)))
        self.setIcon(theme.tool_icon(self.icon_symbol, icon_px))
        self.setIconSize(QSize(icon_px, icon_px))
        self.setMinimumHeight(min_h)
        style(self, f"""
            QToolButton {{
                background-color: rgba(45, 49, 54, 0.4);
                border: 1px solid #3E434B;
                border-radius: 4px;
                color: #D2D6DC;
                font-size: {font_px}px;
                font-weight: 500;
                text-align: center;
                padding: {max(1, int(round(2 * scale)))}px;
            }}
            QToolButton:hover {{
                background-color: #353A42;
                border: 1px solid #5A6270;
                color: #FFFFFF;
            }}
            QToolButton:pressed, QToolButton:checked {{
                background-color: #E26D28;
                border: 1px solid #FF7E36;
                color: #FFFFFF;
            }}
        """)
        self.ensurePolished()
        if not labels:
            self.setMinimumWidth(icon_px + max(8, int(round(10 * scale))))
            return
        fm = self.fontMetrics()
        widest = max(fm.horizontalAdvance(line) for line in self.text().split("\n"))
        base_w = max(40, int(round(54 * scale)))
        pad_w = max(8, int(round(12 * scale)))
        self.setMinimumWidth(max(base_w, widest + pad_w))


class Ribbon(QWidget):
    """Top command ribbon for CAD workspaces."""

    # Action Signals
    create_sketch_clicked = Signal()
    extrude_clicked = Signal()
    revolve_clicked = Signal()
    emboss_clicked = Signal()
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
    shelled_box_clicked = Signal()
    shelled_cylinder_clicked = Signal()
    sphere_clicked = Signal()
    combine_clicked = Signal()
    delete_clicked = Signal()
    split_body_clicked = Signal()
    shell_clicked = Signal()
    offset_face_clicked = Signal()
    move_clicked = Signal()
    thread_clicked = Signal()
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
        self.tabs.setFixedHeight(ribbon_height(scale))
        layout.addWidget(self.tabs)

        # 1. SOLID Tab
        self.solid_tab = QWidget()
        self.setup_solid_tab()
        self.tabs.addTab(self._scrollable(self.solid_tab), "SOLID")

        # 2. SKETCH Tab
        self.sketch_tab = QWidget()
        self.setup_sketch_tab()
        self.tabs.addTab(self._scrollable(self.sketch_tab), "SKETCH")

        # The SOLID / SKETCH selector is not part of the ribbon: it is a small bar the main window puts in the 3D view,
        # above the Browser. The QTabWidget keeps the pages; its own tab bar is hidden and this one drives it.
        self.tabs.tabBar().hide()
        self.workspace_bar = QTabBar()
        self.workspace_bar.setDrawBase(False)
        self.workspace_bar.setExpanding(False)
        self.workspace_bar.setUsesScrollButtons(False)       # it is tiny; never scroll its two tabs
        self.workspace_bar.addTab("SOLID")
        self.workspace_bar.addTab("SKETCH")
        self.workspace_bar.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.workspace_bar.setCurrentIndex)
        # Hide sketch tab by default until sketch is started
        self.tabs.setTabVisible(1, False)
        self.workspace_bar.setTabVisible(1, False)
        self.equalize_buttons()
        self.fit_height()

    def equalize_buttons(self):
        """Every ribbon button gets the same size (in both tabs): with names, the widest plain button sets the width
        and the tallest the height; icon-only, icon plus a small margin. Buttons sized after their own text looked
        uneven. (Dropdown buttons draw their arrow inside the same size.)"""
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)       # buttons of a rebuilt tab are gone first
        buttons = self.findChildren(RibbonButton)
        if not buttons:
            return
        for b in buttons:
            b.setMinimumSize(0, 0)
            b.setMaximumSize(16777215, 16777215)
        scale = ribbon_button_scale()
        icon_px = max(18, int(round(30 * scale)))
        if ribbon_labels():
            plain = [b for b in buttons if not b.menu()] or buttons
            w = max(b.sizeHint().width() for b in plain)
            h = max(b.sizeHint().height() for b in buttons)
        else:
            w = icon_px + max(8, int(round(10 * scale)))
            h = icon_px + max(6, int(round(8 * scale)))
        for b in buttons:
            b.setFixedSize(w, h)

    def fit_height(self):
        """The ribbon is as high as its tab bar plus the tallest page (the sketch page has two rows of constraint
        buttons). A fixed number clipped the buttons on Windows, where the tab bar and fonts are taller."""
        pages = max(self.solid_tab.sizeHint().height(), self.sketch_tab.sizeHint().height())
        need = pages + 10      # + the sideways scrollbar (the tab selector is not in the ribbon)
        self.tabs.setFixedHeight(max(ribbon_height(ribbon_button_scale()), need))

    def update_button_scale(self):
        """Update heights, icons and fonts for all ribbon buttons when button_scale setting changes."""
        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(ribbon_height(scale))
        for btn in self.findChildren(RibbonButton):
            btn.apply_scale()
        self.equalize_buttons()
        self.fit_height()
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

    def rebuild_ribbon(self):
        """Reconstruct both tabs to reflect updated button scale, grouping, or tool preferences."""
        # Clean up existing children in solid_tab and sketch_tab
        for tab in (self.solid_tab, self.sketch_tab):
            layout = tab.layout()
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
                QWidget().setLayout(layout)

        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(ribbon_height(scale))
        self.setup_solid_tab()
        self.setup_sketch_tab()
        self.equalize_buttons()
        self.fit_height()
        self.sync_active_tab()

    def setup_solid_tab(self):
        from omacad.ui.settings import get_settings
        from PySide6.QtWidgets import QMenu
        settings = get_settings()
        group_primitives = bool(settings.get("group_primitives", True))
        group_modify = bool(settings.get("group_modify", False))
        group_inspect = bool(settings.get("group_inspect", True))

        h_layout = QHBoxLayout(self.solid_tab)
        h_layout.setContentsMargins(4, 1, 4, 1)
        h_layout.setSpacing(2)

        # CREATE Group
        btn_sketch = RibbonButton("Create\nSketch", "✏️")
        btn_sketch.setToolTip("Create a new sketch on a plane or face (L, C, R)")
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

        btn_extrude = RibbonButton("Extrude\n(E)", "⬆️")
        btn_extrude.setToolTip("Extrude closed sketch profiles or faces into 3D bodies or cuts (E)")
        btn_extrude.clicked.connect(self.extrude_clicked)
        h_layout.addWidget(btn_extrude)

        btn_revolve = RibbonButton("Revolve", "🔄")
        btn_revolve.setToolTip("Revolve a sketch profile around an axis or edge to create a solid body")
        btn_revolve.clicked.connect(self.revolve_clicked)
        h_layout.addWidget(btn_revolve)

        btn_emboss = RibbonButton("Emboss", "🔖")
        btn_emboss.setToolTip("Emboss or deboss text (any sketch profile) on a face, as in Fusion: a positive depth raises it, "
                              "a negative depth presses it in")
        btn_emboss.clicked.connect(self.emboss_clicked)
        h_layout.addWidget(btn_emboss)

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

        # Primitives: Box, Cylinder, Sphere, Thread/Coil
        if group_primitives:
            btn_primitives = RibbonButton("Primitives\n▾", "📦")
            btn_primitives.setToolTip("Create Box, Cylinder, Shelled Box, Shelled Cylinder, Sphere, Thread & Coil")
            btn_primitives.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            prim_menu = QMenu(btn_primitives)
            theme.style_menu(prim_menu)
            act_box = prim_menu.addAction(theme.tool_icon("📦", 18), "Box")
            act_box.triggered.connect(self.box_clicked)
            act_cyl = prim_menu.addAction(theme.tool_icon("🥫", 18), "Cylinder")
            act_cyl.triggered.connect(self.cylinder_clicked)
            act_shell_box = prim_menu.addAction(theme.tool_icon("📦", 18), "Shelled Box")
            act_shell_box.triggered.connect(self.shelled_box_clicked)
            act_shell_cyl = prim_menu.addAction(theme.tool_icon("🥫", 18), "Shelled Cylinder")
            act_shell_cyl.triggered.connect(self.shelled_cylinder_clicked)
            act_sph = prim_menu.addAction(theme.tool_icon("⚽", 18), "Sphere")
            act_sph.triggered.connect(self.sphere_clicked)
            act_thr = prim_menu.addAction(theme.tool_icon("🔩", 18), "Thread / Coil")
            act_thr.triggered.connect(self.thread_clicked)
            btn_primitives.setMenu(prim_menu)
            h_layout.addWidget(btn_primitives)
        else:
            btn_box = RibbonButton("Box", "📦")
            btn_box.setToolTip("Create a rectangular 3D box solid")
            btn_box.clicked.connect(self.box_clicked)
            h_layout.addWidget(btn_box)

            btn_cyl = RibbonButton("Cylinder", "🥫")
            btn_cyl.setToolTip("Create a 3D cylinder solid")
            btn_cyl.clicked.connect(self.cylinder_clicked)
            h_layout.addWidget(btn_cyl)

            for label, icon, signal in [
                ("Shelled Box", "📦", self.shelled_box_clicked),
                ("Shelled Cylinder", "🥫", self.shelled_cylinder_clicked),
            ]:
                button = RibbonButton(label, icon)
                button.setToolTip("Create an open-top hollow primitive with adjustable wall thickness")
                button.clicked.connect(signal)
                h_layout.addWidget(button)

            btn_sph = RibbonButton("Sphere", "⚽")
            btn_sph.setToolTip("Create a spherical 3D solid")
            btn_sph.clicked.connect(self.sphere_clicked)
            h_layout.addWidget(btn_sph)

            btn_thread = RibbonButton("Thread\nCoil", "🔩")
            btn_thread.setToolTip("3D-printable threads and helical coils (trapezoidal 45°, clearance, lead-in taper)")
            btn_thread.clicked.connect(self.thread_clicked)
            h_layout.addWidget(btn_thread)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        style(sep1, "color: #353940;")
        h_layout.addWidget(sep1)

        # MODIFY Group
        if group_modify:
            btn_mod = RibbonButton("Modify\n▾", "🔗")
            btn_mod.setToolTip("Solid modifications: Combine, Split Body, Shell, Offset Face, Move, Delete")
            btn_mod.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            mod_menu = QMenu(btn_mod)
            theme.style_menu(mod_menu)
            act_comb = mod_menu.addAction(theme.tool_icon("🔗", 18), "Combine (Boolean Join/Cut/Intersect)")
            act_comb.triggered.connect(self.combine_clicked)
            act_split = mod_menu.addAction(theme.tool_icon("🪚", 18), "Split Body (Split with plane)")
            act_split.triggered.connect(self.split_body_clicked)
            act_shell = mod_menu.addAction(theme.tool_icon("🐚", 18), "Shell (Hollow body)")
            act_shell.triggered.connect(self.shell_clicked)
            act_offset = mod_menu.addAction(theme.tool_icon("↔️", 18), "Offset Face (tolerance)")
            act_offset.triggered.connect(self.offset_face_clicked)
            act_move = mod_menu.addAction(theme.tool_icon("↔️", 18), "Move Body (M)")
            act_move.triggered.connect(self.move_clicked)
            act_del = mod_menu.addAction(theme.tool_icon("🗑️", 18), "Delete Selected (Del)")
            act_del.triggered.connect(self.delete_clicked)
            btn_mod.setMenu(mod_menu)
            h_layout.addWidget(btn_mod)
        else:
            btn_combine = RibbonButton("Combine", "🔗")
            btn_combine.setToolTip("Join, cut, or intersect solid bodies (Boolean operations)")
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

            btn_offset_face = RibbonButton("Offset\nFace", "↔️")
            btn_offset_face.setToolTip("Move flat faces or adjust hole/pin/thread tolerances")
            btn_offset_face.clicked.connect(self.offset_face_clicked)
            h_layout.addWidget(btn_offset_face)

            btn_move = RibbonButton("Move\n(M)", "↔️")
            btn_move.setToolTip("Translate or rotate a 3D solid body parametrically (M)")
            btn_move.clicked.connect(self.move_clicked)
            h_layout.addWidget(btn_move)

            btn_del = RibbonButton("Delete", "🗑️")
            btn_del.setToolTip("Delete selected bodies or features (Del)")
            btn_del.clicked.connect(self.delete_clicked)
            h_layout.addWidget(btn_del)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        style(sep2, "color: #353940;")
        h_layout.addWidget(sep2)

        # INSPECT & UTILS Group
        if group_inspect:
            btn_insp = RibbonButton("Inspect\n▾", "📏")
            btn_insp.setToolTip("Inspection and parameters: Measure, Section View, Parameters")
            btn_insp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            insp_menu = QMenu(btn_insp)
            theme.style_menu(insp_menu)
            act_meas = insp_menu.addAction(theme.tool_icon("📏", 18), "Measure (I)")
            act_meas.triggered.connect(self.measure_clicked)
            act_sec = insp_menu.addAction(theme.tool_icon("✂️", 18), "Section View")
            act_sec.triggered.connect(self.section_clicked)
            act_par = insp_menu.addAction(theme.tool_icon("🧮", 18), "Parameters (Ctrl+P)")
            act_par.triggered.connect(self.parameters_clicked)
            btn_insp.setMenu(insp_menu)
            h_layout.addWidget(btn_insp)
        else:
            btn_measure = RibbonButton("Measure\n(I)", "📏")
            btn_measure.setToolTip("Click a line, circle or edge for its size; click a second one for distance/angle (I)")
            btn_measure.clicked.connect(self.measure_clicked)
            h_layout.addWidget(btn_measure)

            btn_section = RibbonButton("Section\nView", "✂️")
            btn_section.setToolTip("Cut through the model at a plane or face and slide the cut until you see what you want")
            btn_section.clicked.connect(self.section_clicked)
            h_layout.addWidget(btn_section)

            btn_params = RibbonButton("Parameters", "🧮")
            btn_params.setToolTip("Named values usable in any number field (Ctrl+P)")
            btn_params.clicked.connect(self.parameters_clicked)
            h_layout.addWidget(btn_params)

        # SETTINGS
        btn_settings = RibbonButton("Settings", "⚙️")
        btn_settings.setToolTip("Colors, ribbon layout and app preferences (Ctrl+,)")
        btn_settings.clicked.connect(self.settings_clicked)
        h_layout.addWidget(btn_settings)

        h_layout.addStretch()

    def setup_sketch_tab(self):
        from omacad.ui.settings import get_settings
        settings = get_settings()
        group_constraints = bool(settings.get("group_constraints", True))

        h_layout = QHBoxLayout(self.sketch_tab)
        h_layout.setContentsMargins(4, 1, 4, 1)
        h_layout.setSpacing(2)

        # Sketch Creation Tools
        self.btn_line = RibbonButton("Line\n(L)", "✏️")
        self.btn_line.setCheckable(True)
        self.btn_line.setToolTip("Draw connected straight lines (L)")
        self.btn_line.clicked.connect(lambda: self.select_sketch_tool("LINE"))
        h_layout.addWidget(self.btn_line)

        self._build_rect_button()
        self.btn_rect.setToolTip("Draw rectangles: 2-Point, Center, or 3-Point (R)")
        h_layout.addWidget(self.btn_rect)

        self.btn_circle = RibbonButton("Center\nCircle (C)", "⭕")
        self.btn_circle.setCheckable(True)
        self.btn_circle.setToolTip("Center Circle (C) / Smart Circle (Shift+C)")
        self.btn_circle.clicked.connect(lambda: self.select_sketch_tool("CIRCLE"))
        from PySide6.QtWidgets import QMenu, QToolButton
        self.btn_circle.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        circle_menu = QMenu(self.btn_circle)
        theme.style_menu(circle_menu)
        for tool, label in (("CIRCLE", "Center Circle  (C)"), ("SMART_CIRCLE", "Smart Circle  (Shift+C)")):
            circle_menu.addAction(label).triggered.connect(lambda _=False, t=tool: self.select_sketch_tool(t))
        self.btn_circle.setMenu(circle_menu)
        h_layout.addWidget(self.btn_circle)

        self.btn_polygon = RibbonButton("Polygon\n(P)", "⬡")
        self.btn_polygon.setCheckable(True)
        self.btn_polygon.setToolTip("Regular polygon: click centre, move out, Tab to type side length & number of sides (P)")
        self.btn_polygon.clicked.connect(lambda: self.select_sketch_tool("POLYGON"))
        h_layout.addWidget(self.btn_polygon)

        self.btn_arc = RibbonButton("3-Point\nArc (A)", "⌒")
        self.btn_arc.setCheckable(True)
        self.btn_arc.setToolTip("Create a 3-point circular arc (A)")
        self.btn_arc.clicked.connect(lambda: self.select_sketch_tool("ARC"))
        h_layout.addWidget(self.btn_arc)

        self.btn_slot = RibbonButton("Center\nSlot", "💊")
        self.btn_slot.setCheckable(True)
        self.btn_slot.setToolTip("Create a slot shape defined by center-to-center line and diameter")
        self.btn_slot.clicked.connect(lambda: self.select_sketch_tool("SLOT"))
        h_layout.addWidget(self.btn_slot)

        self.btn_text = RibbonButton("Text", "🔤")
        self.btn_text.setCheckable(True)
        self.btn_text.setToolTip("Add text to the sketch (as in Fusion): letters in a frame, or along a circle, arc or line. "
                                 "The letters can be extruded or embossed")
        self.btn_text.clicked.connect(lambda: self.select_sketch_tool("TEXT"))
        h_layout.addWidget(self.btn_text)

        self.btn_fillet_sk = RibbonButton("Fillet\n(F)", "╭")
        self.btn_fillet_sk.setCheckable(True)
        self.btn_fillet_sk.setToolTip("Fillet (F): Round corners between two lines (click a corner or select lines)")
        self.btn_fillet_sk.clicked.connect(lambda: self.select_sketch_tool("FILLET"))
        h_layout.addWidget(self.btn_fillet_sk)

        self.btn_trim_sk = RibbonButton("Trim\n(T)", "✂️")
        self.btn_trim_sk.setCheckable(True)
        self.btn_trim_sk.setToolTip("Trim (T): remove the piece of a curve up to nearest crossings, or dangling stubs")
        self.btn_trim_sk.clicked.connect(lambda: self.select_sketch_tool("TRIM"))
        h_layout.addWidget(self.btn_trim_sk)

        self.btn_mirror_sk = RibbonButton("Mirror\n(Shift+M)", "🪞")
        self.btn_mirror_sk.setCheckable(True)
        self.btn_mirror_sk.setToolTip("Mirror (Shift+M): select curves to mirror, then pick mirror line/axis")
        self.btn_mirror_sk.clicked.connect(lambda: self.select_sketch_tool("MIRROR"))
        h_layout.addWidget(self.btn_mirror_sk)

        self.btn_offset_sk = RibbonButton("Offset\n(O)", "⧉")
        self.btn_offset_sk.setCheckable(True)
        self.btn_offset_sk.setToolTip("Offset (O): click curves to offset (Shift/Ctrl+click toggles individual curves), Enter distance")
        self.btn_offset_sk.clicked.connect(lambda: self.select_sketch_tool("OFFSET"))
        h_layout.addWidget(self.btn_offset_sk)

        self.btn_project_sk = RibbonButton("Project\n(edges)", "🟣")
        self.btn_project_sk.setToolTip("Project: turn solid body edges lying in sketch plane into sketch geometry")
        self.btn_project_sk.clicked.connect(self.project_clicked)
        h_layout.addWidget(self.btn_project_sk)

        # Separator
        sep_dim = QFrame()
        sep_dim.setFrameShape(QFrame.Shape.VLine)
        style(sep_dim, "color: #353940;")
        h_layout.addWidget(sep_dim)

        btn_measure_s = RibbonButton("Measure\n(I)", "📏")
        btn_measure_s.setToolTip("Click a line or circle for its size; click a second one for distance/angle (I)")
        btn_measure_s.clicked.connect(self.measure_clicked)
        h_layout.addWidget(btn_measure_s)

        # Construction Toggle & Dimension Tool & Move
        self.btn_construct = RibbonButton("Guide\nLine (X)", "┄")
        self.btn_construct.setCheckable(True)
        self.btn_construct.setToolTip("Construction / Guide Geometry (X): draw dashed helper lines or toggle selected curves to construction lines (ignored by Extrude, used as Revolve/Mirror axes)")
        self.btn_construct.clicked.connect(self.toggle_construction_clicked)
        h_layout.addWidget(self.btn_construct)

        self.btn_dim = RibbonButton("Dimension\n(D)", "dimension")
        self.btn_dim.setCheckable(True)
        self.btn_dim.setToolTip("Add dimension constraint or drive geometry length/angle/radius (D)")
        self.btn_dim.clicked.connect(lambda: self.select_sketch_tool("DIMENSION"))
        h_layout.addWidget(self.btn_dim)

        self.btn_move = RibbonButton("Move\n(M)", "✥")
        self.btn_move.setCheckable(True)
        self.btn_move.setToolTip("Move selected sketch elements (M). Drag elements with mouse to move directly.")
        self.btn_move.clicked.connect(lambda: self.select_sketch_tool("MOVE"))
        h_layout.addWidget(self.btn_move)

        self.btn_rotate_sk = RibbonButton("Rotate\n(Shift+R)", "↻")
        self.btn_rotate_sk.setCheckable(True)
        self.btn_rotate_sk.setToolTip("Rotate selected sketch elements about an area center, face center, origin or picked pivot (Shift+R)")
        self.btn_rotate_sk.clicked.connect(lambda: self.select_sketch_tool("ROTATE"))
        h_layout.addWidget(self.btn_rotate_sk)

        sep_con = QFrame()
        sep_con.setFrameShape(QFrame.Shape.VLine)
        style(sep_con, "color: #353940;")
        h_layout.addWidget(sep_con)

        # Constraints
        constraints_def = (
            ("HORIZONTAL", "Horizontal", "━", "Make selected lines horizontal"),
            ("VERTICAL", "Vertical", "┃", "Make selected lines vertical"),
            ("COINCIDENT", "Coincident", "•", "Join nearest end points of two selected curves"),
            ("PARALLEL", "Parallel", "∥", "Make selected lines parallel"),
            ("PERPENDICULAR", "Perpendic.", "⟂", "Make selected lines perpendicular"),
            ("EQUAL", "Equal", "＝", "Equal length (lines) or radius (circles)"),
            ("TANGENT", "Tangent", "◠", "Tangent constraint between line and circle, or two curves"),
            ("CONCENTRIC", "Concentric", "◎", "Share same centre point for two circles/arcs"),
            ("FIX", "Fix", "🔒", "Lock selected lines/circles/points in place"),
        )

        scale = ribbon_button_scale()
        if group_constraints:
            from PySide6.QtWidgets import QGridLayout
            grid_widget = QWidget()
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(max(2, int(round(3 * scale))))
            
            c_btn_size = max(24, int(round(34 * scale)))
            c_icon_size = max(14, int(round(18 * scale)))
            c_font_size = max(8, int(round(10 * scale)))

            for i, (ctype, label, icon, tip) in enumerate(constraints_def):
                row = i % 2
                col = i // 2
                c_btn = QToolButton()
                c_btn.setFixedSize(c_btn_size, c_btn_size)
                c_btn.setIcon(theme.tool_icon(icon, c_icon_size))
                c_btn.setIconSize(QSize(c_icon_size, c_icon_size))
                c_btn.setToolTip(f"{label}: {tip} (select elements first)")
                style(c_btn, f"""
                    QToolButton {{
                        background-color: rgba(45, 49, 54, 0.4);
                        border: 1px solid #3E434B;
                        border-radius: 3px;
                        color: #D2D6DC;
                        font-size: {c_font_size}px;
                        padding: 1px;
                    }}
                    QToolButton:hover {{
                        background-color: #353A42;
                        border: 1px solid #5A6270;
                        color: #FFFFFF;
                    }}
                    QToolButton:pressed {{
                        background-color: #E26D28;
                        border: 1px solid #FF7E36;
                        color: #FFFFFF;
                    }}
                """)
                c_btn.clicked.connect(lambda _=False, c=ctype: self.constraint_clicked.emit(c))
                grid_layout.addWidget(c_btn, row, col)

            h_layout.addWidget(grid_widget)
        else:
            for ctype, label, icon, tip in constraints_def:
                btn = RibbonButton(label, icon)
                btn.setToolTip(tip + "  (select elements first)")
                btn.clicked.connect(lambda _=False, c=ctype: self.constraint_clicked.emit(c))
                h_layout.addWidget(btn)

        h_layout.addStretch()

        # Big Green Finish Sketch Button (Fusion 360 hallmark)
        self.btn_finish = QToolButton()
        self.btn_finish.setText("✅  Finish Sketch")
        self.btn_finish.setToolTip("Finish editing sketch and return to 3D solid modeling mode")
        self.btn_finish.setMinimumSize(max(100, int(round(140 * scale))), max(34, int(round(48 * scale))))
        style(self.btn_finish, """
            QToolButton {{
                background-color: #2E7D32;
                border: 1px solid #388E3C;
                border-radius: 4px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                padding: 4px 8px;
            }}
            QToolButton:hover {{
                background-color: #388E3C;
            }}
            QToolButton:pressed {{
                background-color: #1B5E20;
            }}
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
        theme.style_menu(menu)
        for tool, (label, _icon) in RECT_TOOLS.items():
            act = menu.addAction(label.replace("\n", " "))
            act.triggered.connect(lambda _=False, t=tool: self.select_sketch_tool(t))
        menu.addSeparator()
        default_menu = menu.addMenu("Button default")
        theme.style_menu(default_menu)
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
        self.btn_text.setChecked(tool_name == "TEXT")
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
        self.btn_rotate_sk.setChecked(tool_name == "ROTATE")
        self.sketch_tool_selected.emit(tool_name)

    def sync_active_tab(self):
        """Shows/hides SKETCH tab when sketch is active."""
        is_sketching = (self.doc.active_sketch is not None)
        self.tabs.setTabVisible(1, is_sketching)
        self.workspace_bar.setTabVisible(1, is_sketching)
        self.workspace_bar.resize(self.workspace_bar.sizeHint())      # grows with the SKETCH tab
        if is_sketching:
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)
            for btn in (
                self.btn_line, self.btn_rect, self.btn_circle, self.btn_arc,
                self.btn_slot, self.btn_polygon, self.btn_text, self.btn_fillet_sk,
                self.btn_trim_sk, self.btn_mirror_sk, self.btn_offset_sk,
                self.btn_dim, self.btn_move, self.btn_rotate_sk, self.btn_construct,
            ):
                btn.setChecked(False)

