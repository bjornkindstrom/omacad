"""
Omacad - Settings Dialog
GUI for configuring user preferences including custom colors, sketch palette placement, and navigation.
"""

from typing import Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QComboBox, QCheckBox, QDoubleSpinBox, QColorDialog,
    QFrame, QGridLayout
)

from omacad.ui import theme
from omacad.ui.settings import get_settings, rgb01_to_hex


class ColorRow(QWidget):
    def __init__(self, label: str, current_hex: Optional[str], default_hex: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_hex = current_hex
        self.default_hex = default_hex

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)

        self.lbl = QLabel(label)
        self.lbl.setMinimumWidth(180)
        lay.addWidget(self.lbl)

        self.btn_swatch = QPushButton()
        self.btn_swatch.setFixedSize(50, 24)
        self.btn_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swatch.clicked.connect(self.choose_color)
        lay.addWidget(self.btn_swatch)

        self.btn_pick = QPushButton("Välj färg…")
        self.btn_pick.clicked.connect(self.choose_color)
        lay.addWidget(self.btn_pick)

        self.btn_reset = QPushButton("Följ tema" if default_hex is None else "Återställ")
        self.btn_reset.clicked.connect(self.reset_color)
        lay.addWidget(self.btn_reset)
        lay.addStretch()

        self.update_swatch()

    def update_swatch(self):
        if self.current_hex:
            self.btn_swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.current_hex};
                    border: 1px solid #5A6270;
                    border-radius: 4px;
                }}
            """)
            self.btn_swatch.setText("")
        else:
            # Theme default highlight
            th_col = theme.palette().highlight01()
            hex_th = rgb01_to_hex(*th_col)
            self.btn_swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_th};
                    border: 1px dashed #7A8290;
                    border-radius: 4px;
                    color: #FFFFFF;
                    font-size: 10px;
                }}
            """)
            self.btn_swatch.setText("Tema")

    def choose_color(self):
        initial = QColor(self.current_hex) if self.current_hex else QColor(*[int(c * 255) for c in theme.palette().highlight01()])
        color = QColorDialog.getColor(initial, self, "Välj färg")
        if color.isValid():
            self.current_hex = color.name().upper()
            self.update_swatch()

    def reset_color(self):
        self.current_hex = self.default_hex
        self.update_swatch()


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Inställningar (Settings)")
        self.setMinimumWidth(520)
        theme.style(self, theme._BASE_CSS)

        self.settings = get_settings()

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(14)

        self.tabs = QTabWidget()
        main_lay.addWidget(self.tabs)

        # Tab 1: Färger
        tab_colors = QWidget()
        lay_colors = QVBoxLayout(tab_colors)
        lay_colors.setContentsMargins(12, 12, 12, 12)
        lay_colors.setSpacing(10)

        info_lbl = QLabel("Anpassa färger för 3D-pilar, markeringar och verktyg i vyn:")
        info_lbl.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        lay_colors.addWidget(info_lbl)

        self.row_arrow = ColorRow("Extrude-pil / Dragger:", self.settings.get("arrow_color"), default_hex=None)
        lay_colors.addWidget(self.row_arrow)

        self.row_measure = ColorRow("Mätverktyg (Measure overlay):", self.settings.get("measure_color"), default_hex="#FFAA3C")
        lay_colors.addWidget(self.row_measure)

        self.row_sketch = ColorRow("Aktiva sketchlinjer:", self.settings.get("sketch_line_color"), default_hex="#4CE0FF")
        lay_colors.addWidget(self.row_sketch)

        self.row_construct = ColorRow("Konstruktionslinjer:", self.settings.get("sketch_construction_color"), default_hex="#FFCC4D")
        lay_colors.addWidget(self.row_construct)

        self.row_highlight = ColorRow("Markering / Highlight:", self.settings.get("highlight_color"), default_hex=None)
        lay_colors.addWidget(self.row_highlight)

        lay_colors.addStretch()
        self.tabs.addTab(tab_colors, "🎨 Färger")

        # Tab 2: Sketch & Visning
        tab_sketch = QWidget()
        lay_sketch = QVBoxLayout(tab_sketch)
        lay_sketch.setContentsMargins(12, 12, 12, 12)
        lay_sketch.setSpacing(12)

        # Palette position
        pos_row = QHBoxLayout()
        lbl_pos = QLabel("Sketch-palett placering:")
        lbl_pos.setMinimumWidth(200)
        self.cmb_pos = QComboBox()
        self.cmb_pos.addItem("Nere till höger (rekommenderas)", "bottom_right")
        self.cmb_pos.addItem("Uppe till vänster", "top_left")
        self.cmb_pos.addItem("Nere till vänster", "bottom_left")
        self.cmb_pos.addItem("Uppe till höger", "top_right")
        cur_pos = self.settings.get("palette_position", "bottom_right")
        idx = self.cmb_pos.findData(cur_pos)
        if idx >= 0:
            self.cmb_pos.setCurrentIndex(idx)
        pos_row.addWidget(lbl_pos)
        pos_row.addWidget(self.cmb_pos)
        pos_row.addStretch()
        lay_sketch.addLayout(pos_row)

        # Autohide on measure
        self.chk_autohide = QCheckBox("Dölj sketch-paletten automatiskt under mätning (M)")
        self.chk_autohide.setToolTip("Gör att paletten inte skymmer linjer eller mått när du mäter.")
        self.chk_autohide.setChecked(bool(self.settings.get("autohide_palette_on_measure", True)))
        lay_sketch.addWidget(self.chk_autohide)

        # Invert zoom
        self.chk_invert_zoom = QCheckBox("Omvänd zoomriktning på mushjul")
        self.chk_invert_zoom.setChecked(bool(self.settings.get("invert_zoom", False)))
        lay_sketch.addWidget(self.chk_invert_zoom)

        # Grid step
        grid_row = QHBoxLayout()
        lbl_grid = QLabel("Rutnätssteg (Grid step, mm):")
        lbl_grid.setMinimumWidth(200)
        self.spn_grid = QDoubleSpinBox()
        self.spn_grid.setRange(0.5, 100.0)
        self.spn_grid.setValue(float(self.settings.get("grid_step", 5.0)))
        self.spn_grid.setSuffix(" mm")
        grid_row.addWidget(lbl_grid)
        grid_row.addWidget(self.spn_grid)
        grid_row.addStretch()
        lay_sketch.addLayout(grid_row)

        # Default fillet radius
        fillet_row = QHBoxLayout()
        lbl_fillet = QLabel("Förvald radie för Sketch Fillet:")
        lbl_fillet.setMinimumWidth(200)
        self.spn_fillet = QDoubleSpinBox()
        self.spn_fillet.setRange(0.1, 1000.0)
        self.spn_fillet.setValue(float(self.settings.get("fillet_default_radius", 2.0)))
        self.spn_fillet.setSuffix(" mm")
        fillet_row.addWidget(lbl_fillet)
        fillet_row.addWidget(self.spn_fillet)
        fillet_row.addStretch()
        lay_sketch.addLayout(fillet_row)

        # Smoothness of round shapes
        q_row = QHBoxLayout()
        lbl_q = QLabel("Rundhet (Curve smoothness):")
        lbl_q.setMinimumWidth(200)
        self.cmb_curves = QComboBox()
        for label, n in (("Lätt (32), snabbast", 32), ("Normal (64)", 64), ("Mjuk (96), standard", 96),
                         ("Extra mjuk (192)", 192), ("Sömlös (360), tung", 360)):
            self.cmb_curves.addItem(label, n)
        cur = int(self.settings.get("curve_segments", 96))
        idx = self.cmb_curves.findData(cur)
        if idx < 0:
            self.cmb_curves.addItem(f"Egen ({cur})", cur)
            idx = self.cmb_curves.count() - 1
        self.cmb_curves.setCurrentIndex(idx)
        self.cmb_curves.setToolTip("Hur många plana bitar en cirkel delas i. Fler = mjukare runda ytor men tyngre för datorn. Gäller hela modellen, som räknas om.")
        q_row.addWidget(lbl_q)
        q_row.addWidget(self.cmb_curves)
        q_row.addStretch()
        lay_sketch.addLayout(q_row)

        # Camera: projection type and perspective field of view
        proj_row = QHBoxLayout()
        lbl_proj = QLabel("Kameratyp (3D-vy):")
        lbl_proj.setMinimumWidth(200)
        self.cmb_projection = QComboBox()
        self.cmb_projection.addItem("Perspektiv", "perspective")
        self.cmb_projection.addItem("Ortografisk (inget perspektiv)", "orthographic")
        self.cmb_projection.setCurrentIndex(max(0, self.cmb_projection.findData(self.settings.get("view_projection", "perspective"))))
        proj_row.addWidget(lbl_proj)
        proj_row.addWidget(self.cmb_projection)
        proj_row.addStretch()
        lay_sketch.addLayout(proj_row)

        fov_row = QHBoxLayout()
        lbl_fov = QLabel("Perspektiv (synfält):")
        lbl_fov.setMinimumWidth(200)
        self.spn_fov = QDoubleSpinBox()
        self.spn_fov.setRange(10.0, 60.0)
        self.spn_fov.setDecimals(0)
        self.spn_fov.setSuffix("°")
        self.spn_fov.setValue(float(self.settings.get("view_fov", 30.0)))
        self.spn_fov.setToolTip("Lägre = plattare bild och mindre förvrängning. Zoomen ändras inte.")
        fov_row.addWidget(lbl_fov)
        fov_row.addWidget(self.spn_fov)
        fov_row.addWidget(QLabel("lägre = plattare, mindre skevt"))
        fov_row.addStretch()
        lay_sketch.addLayout(fov_row)

        # Restart on a new version
        self.chk_auto_restart = QCheckBox("Starta om automatiskt när en ny version har committats (arbetet sparas och återställs)")
        self.chk_auto_restart.setChecked(bool(self.settings.get("auto_restart", True)))
        lay_sketch.addWidget(self.chk_auto_restart)

        lay_sketch.addStretch()
        self.tabs.addTab(tab_sketch, "📐 Sketch & Visning")

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_reset_all = QPushButton("Återställ standard")
        btn_reset_all.clicked.connect(self.reset_all)
        btn_row.addWidget(btn_reset_all)
        btn_row.addStretch()

        btn_cancel = QPushButton("Avbryt")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Spara")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.save_and_close)
        btn_row.addWidget(btn_save)

        main_lay.addLayout(btn_row)

    def reset_all(self):
        self.row_arrow.reset_color()
        self.row_measure.reset_color()
        self.row_sketch.reset_color()
        self.row_construct.reset_color()
        self.row_highlight.reset_color()
        idx = self.cmb_pos.findData("bottom_right")
        if idx >= 0:
            self.cmb_pos.setCurrentIndex(idx)
        self.chk_autohide.setChecked(True)
        self.chk_invert_zoom.setChecked(False)
        self.spn_grid.setValue(5.0)
        self.spn_fillet.setValue(2.0)
        self.chk_auto_restart.setChecked(True)
        self.cmb_curves.setCurrentIndex(max(0, self.cmb_curves.findData(96)))

    def accept(self):
        self.save_and_close()

    def save_and_close(self):
        new_data = {
            "arrow_color": self.row_arrow.current_hex,
            "measure_color": self.row_measure.current_hex,
            "sketch_line_color": self.row_sketch.current_hex,
            "sketch_construction_color": self.row_construct.current_hex,
            "highlight_color": self.row_highlight.current_hex,
            "palette_position": self.cmb_pos.currentData(),
            "autohide_palette_on_measure": self.chk_autohide.isChecked(),
            "invert_zoom": self.chk_invert_zoom.isChecked(),
            "grid_step": self.spn_grid.value(),
            "fillet_default_radius": self.spn_fillet.value(),
            "curve_segments": self.cmb_curves.currentData(),
            "view_projection": self.cmb_projection.currentData(),
            "view_fov": self.spn_fov.value(),
            "auto_restart": self.chk_auto_restart.isChecked(),
        }
        self.settings.update(new_data)
        super().accept()
