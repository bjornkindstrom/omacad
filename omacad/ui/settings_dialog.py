"""
Omacad - Settings Dialog
GUI for configuring user preferences including custom colors, sketch palette placement, and navigation.
"""

from typing import Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QLineEdit, 
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QComboBox, QCheckBox, QDoubleSpinBox, QColorDialog,
    QFrame, QGridLayout
)

from omacad.ui import theme
from omacad.ui.settings import get_settings, rgb01_to_hex


class ColorRow(QWidget):
    changed = Signal()

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

        self.btn_pick = QPushButton("Choose colour…")
        self.btn_pick.clicked.connect(self.choose_color)
        lay.addWidget(self.btn_pick)

        self.btn_reset = QPushButton("Follow theme" if default_hex is None else "Reset")
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
            self.btn_swatch.setText("Theme")

    def choose_color(self):
        initial = QColor(self.current_hex) if self.current_hex else QColor(*[int(c * 255) for c in theme.palette().highlight01()])
        color = QColorDialog.getColor(initial, self, "Choose colour")
        if color.isValid():
            self.current_hex = color.name().upper()
            self.update_swatch()
            self.changed.emit()

    def reset_color(self):
        self.current_hex = self.default_hex
        self.update_swatch()
        self.changed.emit()


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        theme.style(self, theme._BASE_CSS)

        self.settings = get_settings()
        self._just_saved = ""

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(14)

        self.tabs = QTabWidget()
        main_lay.addWidget(self.tabs)

        # Tab 1: Colours
        tab_colors = QWidget()
        lay_colors = QVBoxLayout(tab_colors)
        lay_colors.setContentsMargins(12, 12, 12, 12)
        lay_colors.setSpacing(10)

        # Theme: follow Omarchy live, or keep a chosen one
        theme_row = QHBoxLayout()
        lbl_theme = QLabel("Theme:")
        lbl_theme.setMinimumWidth(200)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("Follow the Omarchy theme (live)", "omarchy")
        self.cmb_theme.addItem("Omacad default (dark)", theme.BUILTIN)
        for name in theme.available_themes():
            self.cmb_theme.addItem(name.replace("-", " ").title(), name)
        for name in theme.custom_themes():
            self.cmb_theme.addItem(f"★ {name}", theme.CUSTOM_PREFIX + name)
        cur = "omarchy" if self.settings.get("theme_mode") != "fixed" else self.settings.get("theme_name")
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(cur)))
        self.cmb_theme.setToolTip("Follow Omarchy: the app changes colours when you switch theme in Omarchy.\n"
                                  "Any other choice: the app keeps that theme, whatever Omarchy does.")
        theme_row.addWidget(lbl_theme)
        theme_row.addWidget(self.cmb_theme)
        theme_row.addStretch()
        lay_colors.addLayout(theme_row)

        info_lbl = QLabel("Customise colours for 3D arrows, highlights and tools in the view:")
        info_lbl.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        lay_colors.addWidget(info_lbl)

        self.row_arrow = ColorRow("Extrude arrow / dragger:", self.settings.get("arrow_color"), default_hex=None)
        lay_colors.addWidget(self.row_arrow)

        self.row_measure = ColorRow("Measure tool (overlay):", self.settings.get("measure_color"), default_hex="#FFAA3C")
        lay_colors.addWidget(self.row_measure)

        self.row_sketch = ColorRow("Active sketch lines:", self.settings.get("sketch_line_color"), default_hex="#4CE0FF")
        lay_colors.addWidget(self.row_sketch)

        self.row_construct = ColorRow("Construction lines:", self.settings.get("sketch_construction_color"), default_hex="#FFCC4D")
        lay_colors.addWidget(self.row_construct)

        self.row_highlight = ColorRow("Highlight:", self.settings.get("highlight_color"), default_hex=None)
        lay_colors.addWidget(self.row_highlight)

        lay_colors.addStretch()
        self.tabs.addTab(tab_colors, "🎨 Colours")

        # Tab: theme editor (every colour by hand, saved under a name)
        from omacad.ui.theme_editor import ThemeEditorTab
        self.editor = ThemeEditorTab()
        self.editor.saved.connect(self._theme_saved)
        self.tabs.addTab(self.editor, "🖌 Theme editor")

        # Tab 2: Sketch & View
        tab_sketch = QWidget()
        lay_sketch = QVBoxLayout(tab_sketch)
        lay_sketch.setContentsMargins(12, 12, 12, 12)
        lay_sketch.setSpacing(12)

        # Palette position
        pos_row = QHBoxLayout()
        lbl_pos = QLabel("Sketch palette position:")
        lbl_pos.setMinimumWidth(200)
        self.cmb_pos = QComboBox()
        self.cmb_pos.addItem("Bottom right (recommended)", "bottom_right")
        self.cmb_pos.addItem("Top left", "top_left")
        self.cmb_pos.addItem("Bottom left", "bottom_left")
        self.cmb_pos.addItem("Top right", "top_right")
        cur_pos = self.settings.get("palette_position", "bottom_right")
        idx = self.cmb_pos.findData(cur_pos)
        if idx >= 0:
            self.cmb_pos.setCurrentIndex(idx)
        pos_row.addWidget(lbl_pos)
        pos_row.addWidget(self.cmb_pos)
        pos_row.addStretch()
        lay_sketch.addLayout(pos_row)

        # Autohide on measure
        self.chk_autohide = QCheckBox("Hide the sketch palette automatically while measuring (M)")
        self.chk_autohide.setToolTip("Stops the palette from covering lines or dimensions while you measure.")
        self.chk_autohide.setChecked(bool(self.settings.get("autohide_palette_on_measure", True)))
        lay_sketch.addWidget(self.chk_autohide)

        # Invert zoom
        self.chk_invert_zoom = QCheckBox("Reverse the mouse wheel zoom direction")
        self.chk_invert_zoom.setChecked(bool(self.settings.get("invert_zoom", False)))
        lay_sketch.addWidget(self.chk_invert_zoom)

        # Grid step
        grid_row = QHBoxLayout()
        lbl_grid = QLabel("Grid step (mm):")
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
        lbl_fillet = QLabel("Default radius for Sketch Fillet:")
        lbl_fillet.setMinimumWidth(200)
        self.spn_fillet = QDoubleSpinBox()
        self.spn_fillet.setRange(0.1, 1000.0)
        self.spn_fillet.setValue(float(self.settings.get("fillet_default_radius", 2.0)))
        self.spn_fillet.setSuffix(" mm")
        fillet_row.addWidget(lbl_fillet)
        fillet_row.addWidget(self.spn_fillet)
        fillet_row.addStretch()
        lay_sketch.addLayout(fillet_row)

        # The extrude arrow
        arrow_row = QHBoxLayout()
        lbl_arrow = QLabel("Arrow size:")
        lbl_arrow.setMinimumWidth(200)
        self.spn_arrow_size = QDoubleSpinBox()
        self.spn_arrow_size.setRange(0.3, 4.0)
        self.spn_arrow_size.setSingleStep(0.1)
        self.spn_arrow_size.setDecimals(1)
        self.spn_arrow_size.setSuffix(" ×")
        self.spn_arrow_size.setValue(float(self.settings.get("arrow_size", 1.0)))
        arrow_row.addWidget(lbl_arrow)
        arrow_row.addWidget(self.spn_arrow_size)
        arrow_row.addStretch()
        lay_sketch.addLayout(arrow_row)

        gap_row = QHBoxLayout()
        lbl_gap = QLabel("Arrow distance from the surface:")
        lbl_gap.setMinimumWidth(200)
        self.spn_arrow_gap = QDoubleSpinBox()
        self.spn_arrow_gap.setRange(0.0, 20.0)
        self.spn_arrow_gap.setSingleStep(0.5)
        self.spn_arrow_gap.setDecimals(1)
        self.spn_arrow_gap.setSuffix(" mm")
        self.spn_arrow_gap.setValue(float(self.settings.get("arrow_gap", 2.0)))
        self.spn_arrow_gap.setToolTip("The arrow is drawn this far off the surface, in the direction it points, so it never starts inside the material.")
        gap_row.addWidget(lbl_gap)
        gap_row.addWidget(self.spn_arrow_gap)
        gap_row.addStretch()
        lay_sketch.addLayout(gap_row)

        # Toolbar button size
        btn_size_row = QHBoxLayout()
        lbl_btn_size = QLabel("Toolbar button size:")
        lbl_btn_size.setMinimumWidth(200)
        self.cmb_btn_size = QComboBox()
        self.cmb_btn_size.addItem("Compact (75%)", 0.75)
        self.cmb_btn_size.addItem("Medium (default, 100%)", 1.0)
        self.cmb_btn_size.addItem("Large (125%)", 1.25)
        self.cmb_btn_size.addItem("Extra large (150%)", 1.5)
        cur_scale = float(self.settings.get("button_scale", 1.0))
        idx_scale = self.cmb_btn_size.findData(cur_scale)
        if idx_scale < 0:
            self.cmb_btn_size.addItem(f"Custom ({int(round(cur_scale * 100))}%)", cur_scale)
            idx_scale = self.cmb_btn_size.count() - 1
        self.cmb_btn_size.setCurrentIndex(max(0, idx_scale))
        self.cmb_btn_size.setToolTip("Adjusts the height and icon sizes of buttons in the top toolbar ribbon.")
        btn_size_row.addWidget(lbl_btn_size)
        btn_size_row.addWidget(self.cmb_btn_size)
        btn_size_row.addStretch()
        lay_sketch.addLayout(btn_size_row)

        # Request for change
        rfc_row = QHBoxLayout()
        lbl_rfc = QLabel("Your name on change requests:")
        lbl_rfc.setMinimumWidth(200)
        self.edt_rfc_name = QLineEdit(str(self.settings.get("rfc_name") or ""))
        self.edt_rfc_name.setPlaceholderText("Help > Request a change (F8)")
        rfc_row.addWidget(lbl_rfc)
        rfc_row.addWidget(self.edt_rfc_name)
        lay_sketch.addLayout(rfc_row)
        tok_row = QHBoxLayout()
        lbl_tok = QLabel("GitHub token for requests (optional):")
        lbl_tok.setMinimumWidth(200)
        self.edt_rfc_token = QLineEdit(str(self.settings.get("rfc_token") or ""))
        self.edt_rfc_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_rfc_token.setPlaceholderText("empty = use the one built into the app")
        tok_row.addWidget(lbl_tok)
        tok_row.addWidget(self.edt_rfc_token)
        lay_sketch.addLayout(tok_row)

        # Smoothness of round shapes
        q_row = QHBoxLayout()
        lbl_q = QLabel("Curve smoothness:")
        lbl_q.setMinimumWidth(200)
        self.cmb_curves = QComboBox()
        for label, n in (("Light (32), fastest", 32), ("Normal (64)", 64), ("Smooth (96), default", 96),
                         ("Extra smooth (192)", 192), ("Seamless (360), heavy", 360)):
            self.cmb_curves.addItem(label, n)
        cur = int(self.settings.get("curve_segments", 96))
        idx = self.cmb_curves.findData(cur)
        if idx < 0:
            self.cmb_curves.addItem(f"Egen ({cur})", cur)
            idx = self.cmb_curves.count() - 1
        self.cmb_curves.setCurrentIndex(idx)
        self.cmb_curves.setToolTip("How many flat pieces a circle is cut into. More = smoother round surfaces but heavier for the computer. Applies to the whole model, which is rebuilt.")
        q_row.addWidget(lbl_q)
        q_row.addWidget(self.cmb_curves)
        q_row.addStretch()
        lay_sketch.addLayout(q_row)

        # Camera: projection type and perspective field of view
        proj_row = QHBoxLayout()
        lbl_proj = QLabel("Camera type (3D view):")
        lbl_proj.setMinimumWidth(200)
        self.cmb_projection = QComboBox()
        self.cmb_projection.addItem("Perspective", "perspective")
        self.cmb_projection.addItem("Orthographic (no perspective)", "orthographic")
        self.cmb_projection.setCurrentIndex(max(0, self.cmb_projection.findData(self.settings.get("view_projection", "perspective"))))
        proj_row.addWidget(lbl_proj)
        proj_row.addWidget(self.cmb_projection)
        proj_row.addStretch()
        lay_sketch.addLayout(proj_row)

        fov_row = QHBoxLayout()
        lbl_fov = QLabel("Perspective (field of view):")
        lbl_fov.setMinimumWidth(200)
        self.spn_fov = QDoubleSpinBox()
        self.spn_fov.setRange(10.0, 60.0)
        self.spn_fov.setDecimals(0)
        self.spn_fov.setSuffix("°")
        self.spn_fov.setValue(float(self.settings.get("view_fov", 30.0)))
        self.spn_fov.setToolTip("Lower = flatter image and less distortion. The zoom does not change.")
        fov_row.addWidget(lbl_fov)
        fov_row.addWidget(self.spn_fov)
        fov_row.addWidget(QLabel("lower = flatter, less skewed"))
        fov_row.addStretch()
        lay_sketch.addLayout(fov_row)

        # Restart on a new version
        self.chk_auto_restart = QCheckBox("Restart automatically when a new version has been committed (your work is saved and restored)")
        self.chk_auto_restart.setChecked(bool(self.settings.get("auto_restart", True)))
        lay_sketch.addWidget(self.chk_auto_restart)

        lay_sketch.addStretch()
        self.tabs.addTab(tab_sketch, "📐 Sketch & View")

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_reset_all = QPushButton("Reset to defaults")
        btn_reset_all.clicked.connect(self.reset_all)
        btn_row.addWidget(btn_reset_all)
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.save_and_close)
        btn_row.addWidget(btn_save)

        main_lay.addLayout(btn_row)

    def _theme_saved(self, key: str):
        """A theme was saved (or deleted) in the editor: update the list and pick it."""
        self._just_saved = key
        cur = self.cmb_theme.currentData()
        for i in reversed(range(self.cmb_theme.count())):
            if str(self.cmb_theme.itemData(i)).startswith(theme.CUSTOM_PREFIX):
                self.cmb_theme.removeItem(i)
        for name in theme.custom_themes():
            self.cmb_theme.addItem(f"★ {name}", theme.CUSTOM_PREFIX + name)
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(key or cur)))

    def reject(self):
        theme.set_preview(None)
        super().reject()

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
        self.cmb_theme.setCurrentIndex(0)
        self.cmb_curves.setCurrentIndex(max(0, self.cmb_curves.findData(96)))
        self.spn_arrow_size.setValue(1.0)
        self.spn_arrow_gap.setValue(2.0)
        self.cmb_btn_size.setCurrentIndex(max(0, self.cmb_btn_size.findData(1.0)))

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
            "arrow_size": self.spn_arrow_size.value(),
            "arrow_gap": self.spn_arrow_gap.value(),
            "button_scale": float(self.cmb_btn_size.currentData() or 1.0),
            "curve_segments": self.cmb_curves.currentData(),
            "view_projection": self.cmb_projection.currentData(),
            "view_fov": self.spn_fov.value(),
            "auto_restart": self.chk_auto_restart.isChecked(),
            "rfc_name": self.edt_rfc_name.text().strip(),
            "rfc_token": self.edt_rfc_token.text().strip(),
            "theme_mode": "omarchy" if self.cmb_theme.currentData() == "omarchy" else "fixed",
            "theme_name": self.settings.get("theme_name") if self.cmb_theme.currentData() == "omarchy" else self.cmb_theme.currentData(),
        }
        key = new_data["theme_name"] if new_data["theme_mode"] == "fixed" else ""
        if key.startswith(theme.CUSTOM_PREFIX):
            # a saved theme carries its tool colours
            tdata = theme.load_theme_data(key) or {}
            from omacad.ui.theme_editor import TOOL_ROLES
            for tkey, setting, _label in TOOL_ROLES:
                if tkey in tdata and (key != self.settings.get("theme_name") or key == self._just_saved):
                    new_data[setting] = tdata.get(tkey)
        theme.PREVIEW = None
        self.settings.update(new_data)
        theme.set_fixed_theme(new_data["theme_name"] if new_data["theme_mode"] == "fixed" else None)
        super().accept()
