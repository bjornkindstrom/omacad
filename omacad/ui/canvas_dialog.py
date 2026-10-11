"""
Omacad - Canvas / Reference Image Editor & Calibration Dialog
Allows importing an image onto a sketch plane, pre-editing (brightness, contrast, crop, rotate, flip),
and calibrating with a virtual tape measure for tracing blueprints and sketches.
"""

import base64
import math
from io import BytesIO
from typing import Optional, Tuple
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QBrush,
    QFont, QTransform
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QSlider, QCheckBox, QComboBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QMessageBox, QWidget, QScrollArea, QSplitter
)
from omacad.model.document import Document
from omacad.ui.theme import style


class ImageCanvasWidget(QWidget):
    """Interactive canvas widget displaying the image with crop box and calibration tape measure."""

    point_picked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_image: Optional[QImage] = None
        self.processed_pixmap: Optional[QPixmap] = None
        self.crop_rect: Optional[QRectF] = None  # in normalized (0..1) coords

        # Calibration state
        self.calibrate_mode: bool = False
        self.calib_pt1: Optional[QPointF] = None  # in pixel coords
        self.calib_pt2: Optional[QPointF] = None

        # Crop drag state
        self.crop_mode: bool = False
        self.crop_start: Optional[QPointF] = None
        self.crop_current: Optional[QPointF] = None

        self.zoom: float = 1.0
        self.setMouseTracking(True)
        self.setMinimumSize(420, 420)
        style(self, "background-color: #1A1C1E; border: 1px solid #33373D; border-radius: 4px;")

    def set_pixmap(self, pix: QPixmap):
        self.processed_pixmap = pix
        self.update()

    def image_to_widget_rect(self) -> QRectF:
        if not self.processed_pixmap or self.processed_pixmap.isNull():
            return QRectF()
        pw, ph = self.processed_pixmap.width(), self.processed_pixmap.height()
        ww, wh = self.width() - 16, self.height() - 16
        scale = min(ww / max(pw, 1), wh / max(ph, 1))
        dw, dh = pw * scale, ph * scale
        dx = (self.width() - dw) / 2.0
        dy = (self.height() - dh) / 2.0
        return QRectF(dx, dy, dw, dh)

    def widget_to_image_coords(self, wx: float, wy: float) -> Optional[QPointF]:
        r = self.image_to_widget_rect()
        if r.isEmpty() or not r.contains(wx, wy):
            return None
        pw = self.processed_pixmap.width()
        ph = self.processed_pixmap.height()
        ix = (wx - r.x()) / r.width() * pw
        iy = (wy - r.y()) / r.height() * ph
        return QPointF(ix, iy)

    def image_to_widget_coords(self, ix: float, iy: float) -> QPointF:
        r = self.image_to_widget_rect()
        if r.isEmpty() or not self.processed_pixmap:
            return QPointF()
        pw = self.processed_pixmap.width()
        ph = self.processed_pixmap.height()
        wx = r.x() + (ix / pw) * r.width()
        wy = r.y() + (iy / ph) * r.height()
        return QPointF(wx, wy)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pt = self.widget_to_image_coords(event.position().x(), event.position().y())
            if not pt:
                return
            if self.calibrate_mode:
                if self.calib_pt1 is None or self.calib_pt2 is not None:
                    self.calib_pt1 = pt
                    self.calib_pt2 = None
                else:
                    self.calib_pt2 = pt
                self.update()
                if self.calib_pt1 and self.calib_pt2:
                    self.point_picked.emit(self.calib_pt1.x(), self.calib_pt1.y())
            elif self.crop_mode:
                self.crop_start = pt
                self.crop_current = pt
                self.update()

    def mouseMoveEvent(self, event):
        if self.crop_mode and self.crop_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pt = self.widget_to_image_coords(event.position().x(), event.position().y())
            if pt:
                self.crop_current = pt
                self.update()

    def mouseReleaseEvent(self, event):
        if self.crop_mode and self.crop_start and self.crop_current:
            x0 = min(self.crop_start.x(), self.crop_current.x())
            y0 = min(self.crop_start.y(), self.crop_current.y())
            x1 = max(self.crop_start.x(), self.crop_current.x())
            y1 = max(self.crop_start.y(), self.crop_current.y())
            if abs(x1 - x0) > 5 and abs(y1 - y0) > 5:
                self.crop_rect = QRectF(x0, y0, x1 - x0, y1 - y0)
            self.crop_start = None
            self.crop_current = None
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.processed_pixmap or self.processed_pixmap.isNull():
            p.setPen(QColor(140, 145, 155))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Ingen bild laddad.\nKlicka på 'Välj bild...' för att importera en ritning.")
            return

        img_rect = self.image_to_widget_rect()
        p.drawPixmap(img_rect.toRect(), self.processed_pixmap)

        # Draw Crop Box
        if self.crop_rect:
            p0 = self.image_to_widget_coords(self.crop_rect.x(), self.crop_rect.y())
            p1 = self.image_to_widget_coords(self.crop_rect.right(), self.crop_rect.bottom())
            r_crop = QRectF(p0, p1)
            p.setPen(QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(0, 180, 255, 30)))
            p.drawRect(r_crop)
        elif self.crop_start and self.crop_current:
            p0 = self.image_to_widget_coords(min(self.crop_start.x(), self.crop_current.x()), min(self.crop_start.y(), self.crop_current.y()))
            p1 = self.image_to_widget_coords(max(self.crop_start.x(), self.crop_current.x()), max(self.crop_start.y(), self.crop_current.y()))
            p.setPen(QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(p0, p1))

        # Draw Calibration Tape Measure
        if self.calib_pt1:
            w1 = self.image_to_widget_coords(self.calib_pt1.x(), self.calib_pt1.y())
            p.setPen(QPen(QColor(255, 200, 0), 2))
            p.setBrush(QBrush(QColor(255, 200, 0)))
            p.drawEllipse(w1, 5, 5)

            if self.calib_pt2:
                w2 = self.image_to_widget_coords(self.calib_pt2.x(), self.calib_pt2.y())
                p.drawEllipse(w2, 5, 5)
                # Tape measure line
                p.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.SolidLine))
                p.drawLine(w1, w2)
                # Cross ticks at ends
                dx, dy = w2.x() - w1.x(), w2.y() - w1.y()
                dist_px = math.hypot(dx, dy)
                if dist_px > 1e-3:
                    nx, ny = -dy / dist_px * 8, dx / dist_px * 8
                    p.drawLine(QPointF(w1.x() - nx, w1.y() - ny), QPointF(w1.x() + nx, w1.y() + ny))
                    p.drawLine(QPointF(w2.x() - nx, w2.y() - ny), QPointF(w2.x() + nx, w2.y() + ny))
                    mid = QPointF((w1.x() + w2.x()) / 2.0, (w1.y() + w2.y()) / 2.0 - 10)
                    raw_dist = math.hypot(self.calib_pt2.x() - self.calib_pt1.x(), self.calib_pt2.y() - self.calib_pt1.y())
                    p.setPen(QColor(255, 220, 50))
                    p.setFont(QFont("sans-serif", 10, QFont.Weight.Bold))
                    p.drawText(mid, f"📏 {raw_dist:.1f} px")


class CanvasEditorDialog(QDialog):
    """Full-featured editor dialog for importing, pre-processing, and calibrating reference canvases."""

    def __init__(self, doc: Document, parent=None, initial_image_path: Optional[str] = None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("Insert Canvas (Reference Image)")
        self.resize(880, 620)
        style(self, "background-color: #22252A; color: #D0D5DD;")

        self.original_image: Optional[QImage] = None
        self.current_image: Optional[QImage] = None
        self.px_per_mm: float = 1.0  # calibration scale
        self.rotation_quarter: int = 0  # 0, 1, 2, 3 (90-deg steps)
        self.flip_h: bool = False
        self.flip_v: bool = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Left / Center: Interactive Image Viewer
        self.canvas_view = ImageCanvasWidget(self)
        layout.addWidget(self.canvas_view, stretch=3)

        # Right: Tool Panel
        tools_widget = QWidget()
        tools_widget.setFixedWidth(340)
        tools_layout = QVBoxLayout(tools_widget)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(10)

        # 1. File Group
        grp_file = QGroupBox("Bildfil")
        form_file = QVBoxLayout(grp_file)
        self.btn_load = QPushButton("📁 Välj bild...")
        self.btn_load.clicked.connect(self.choose_image)
        form_file.addWidget(self.btn_load)
        self.lbl_file_info = QLabel("Ingen fil vald")
        self.lbl_file_info.setWordWrap(True)
        form_file.addWidget(self.lbl_file_info)
        tools_layout.addWidget(grp_file)

        # 2. Calibration Group (Måttband)
        grp_calib = QGroupBox("Kalibrera med måttband")
        form_calib = QFormLayout(grp_calib)
        self.btn_calib = QPushButton("📏 Starta kalibrering")
        self.btn_calib.setCheckable(True)
        self.btn_calib.clicked.connect(self.toggle_calibrate)
        form_calib.addRow(self.btn_calib)

        self.spn_calib_dist = QDoubleSpinBox()
        self.spn_calib_dist.setRange(0.1, 100000.0)
        self.spn_calib_dist.setValue(100.0)
        self.spn_calib_dist.setSuffix(" mm")
        self.spn_calib_dist.setDecimals(2)
        self.spn_calib_dist.valueChanged.connect(self.apply_calibration)
        form_calib.addRow("Verklig längd:", self.spn_calib_dist)

        self.lbl_calib_status = QLabel("Klicka på 2 punkter på bilden vars avstånd du känner till.")
        self.lbl_calib_status.setWordWrap(True)
        style(self.lbl_calib_status, "color: #9AA2B0; font-size: 11px;")
        form_calib.addRow(self.lbl_calib_status)
        tools_layout.addWidget(grp_calib)

        # 3. Light & Color Adjustments (Ljus & Färg)
        grp_adj = QGroupBox("Ljus, Färg & Beskärning")
        form_adj = QFormLayout(grp_adj)

        self.sld_bright = QSlider(Qt.Orientation.Horizontal)
        self.sld_bright.setRange(-100, 100); self.sld_bright.setValue(0)
        self.sld_bright.valueChanged.connect(self.refresh_image_processing)
        form_adj.addRow("Ljusstyrka:", self.sld_bright)

        self.sld_contrast = QSlider(Qt.Orientation.Horizontal)
        self.sld_contrast.setRange(-100, 100); self.sld_contrast.setValue(0)
        self.sld_contrast.valueChanged.connect(self.refresh_image_processing)
        form_adj.addRow("Kontrast:", self.sld_contrast)

        self.chk_gray = QCheckBox("Svartvitt (Gråskala)")
        self.chk_gray.toggled.connect(self.refresh_image_processing)
        form_adj.addRow(self.chk_gray)

        self.chk_invert = QCheckBox("Invertera färger (Negativ)")
        self.chk_invert.toggled.connect(self.refresh_image_processing)
        form_adj.addRow(self.chk_invert)

        # Rotate & Flip buttons
        h_rot = QHBoxLayout()
        btn_rot = QPushButton("🔄 Rotera 90°")
        btn_rot.clicked.connect(self.rotate_image)
        btn_fliph = QPushButton("↔ Spegla H")
        btn_fliph.clicked.connect(self.flip_horizontal)
        h_rot.addWidget(btn_rot)
        h_rot.addWidget(btn_fliph)
        form_adj.addRow(h_rot)

        # Crop tool
        h_crop = QHBoxLayout()
        self.btn_crop_tool = QPushButton("✂ Markera beskärning")
        self.btn_crop_tool.setCheckable(True)
        self.btn_crop_tool.clicked.connect(self.toggle_crop)
        self.btn_apply_crop = QPushButton("Beskär nu")
        self.btn_apply_crop.clicked.connect(self.apply_crop)
        h_crop.addWidget(self.btn_crop_tool)
        h_crop.addWidget(self.btn_apply_crop)
        form_adj.addRow(h_crop)

        tools_layout.addWidget(grp_adj)

        # 4. Placement & Opacity Group
        grp_place = QGroupBox("Placering & Opacitet")
        form_place = QFormLayout(grp_place)

        self.cmb_plane = QComboBox()
        # Add origin planes
        for p in ("XY", "XZ", "YZ"):
            self.cmb_plane.addItem(f"🌐 {p} Plane", p)
        # Add construction planes
        for pid, cp in doc.construction_planes.items():
            self.cmb_plane.addItem(f"📐 {cp['name']}", pid)
        form_place.addRow("Plan:", self.cmb_plane)

        self.sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sld_opacity.setRange(5, 100); self.sld_opacity.setValue(50)
        form_place.addRow("Opacitet:", self.sld_opacity)

        self.lbl_dims = QLabel("Mått: - x - mm")
        form_place.addRow(self.lbl_dims)
        tools_layout.addWidget(grp_place)

        tools_layout.addStretch()

        # OK / Cancel
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Avbryt")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_ok = QPushButton("Infoga Canvas")
        self.btn_ok.setObjectName("PrimaryButton")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_ok)
        tools_layout.addLayout(btn_box)

        layout.addWidget(tools_widget)

        self.canvas_view.point_picked.connect(self.on_points_picked)

        if initial_image_path:
            self.load_image_file(initial_image_path)

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj referensbild", "", "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.load_image_file(path)

    def load_image_file(self, path: str):
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Fel", f"Kunde inte ladda bilden:\n{path}")
            return
        self.original_image = img
        self.current_image = img.copy()
        import os
        self.lbl_file_info.setText(f"{os.path.basename(path)} ({img.width()}x{img.height()} px)")
        self.rotation_quarter = 0
        self.flip_h = False
        self.flip_v = False
        self.px_per_mm = 1.0  # default 1 px = 1 mm until calibrated
        self.btn_ok.setEnabled(True)
        self.refresh_image_processing()

    def toggle_calibrate(self, checked: bool):
        self.canvas_view.calibrate_mode = checked
        if checked:
            self.canvas_view.crop_mode = False
            self.btn_crop_tool.setChecked(False)
            self.lbl_calib_status.setText("Klicka på punkt 1 och punkt 2 på bilden.")
        else:
            self.lbl_calib_status.setText("Kalibrering avslutad.")

    def on_points_picked(self, x, y):
        p1 = self.canvas_view.calib_pt1
        p2 = self.canvas_view.calib_pt2
        if p1 and p2:
            dist_px = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            self.lbl_calib_status.setText(f"Mätt: {dist_px:.1f} pixlar. Ange verklig längd i fältet ovan.")
            self.apply_calibration()

    def apply_calibration(self):
        p1 = self.canvas_view.calib_pt1
        p2 = self.canvas_view.calib_pt2
        if p1 and p2:
            dist_px = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            mm = self.spn_calib_dist.value()
            if dist_px > 1.0 and mm > 0.01:
                self.px_per_mm = dist_px / mm
                self.update_dimension_labels()

    def update_dimension_labels(self):
        if not self.current_image:
            return
        w_mm = self.current_image.width() / max(self.px_per_mm, 1e-4)
        h_mm = self.current_image.height() / max(self.px_per_mm, 1e-4)
        self.lbl_dims.setText(f"Mått: {w_mm:.1f} x {h_mm:.1f} mm\n({self.px_per_mm:.2f} px/mm)")

    def rotate_image(self):
        self.rotation_quarter = (self.rotation_quarter + 1) % 4
        self.refresh_image_processing()

    def flip_horizontal(self):
        self.flip_h = not self.flip_h
        self.refresh_image_processing()

    def toggle_crop(self, checked: bool):
        self.canvas_view.crop_mode = checked
        if checked:
            self.canvas_view.calibrate_mode = False
            self.btn_calib.setChecked(False)

    def apply_crop(self):
        if not self.canvas_view.crop_rect or not self.current_image:
            return
        cr = self.canvas_view.crop_rect
        ix, iy, iw, ih = int(cr.x()), int(cr.y()), int(cr.width()), int(cr.height())
        ix = max(0, min(self.current_image.width() - 1, ix))
        iy = max(0, min(self.current_image.height() - 1, iy))
        iw = max(1, min(self.current_image.width() - ix, iw))
        ih = max(1, min(self.current_image.height() - iy, ih))

        self.current_image = self.current_image.copy(ix, iy, iw, ih)
        self.original_image = self.current_image.copy()
        self.canvas_view.crop_rect = None
        self.btn_crop_tool.setChecked(False)
        self.canvas_view.crop_mode = False
        self.refresh_image_processing()

    def refresh_image_processing(self):
        if not self.original_image:
            return

        # 1. Start with copy
        img = self.original_image.copy()

        # 2. Rotation & Flip
        if self.rotation_quarter != 0 or self.flip_h:
            t = QTransform()
            if self.rotation_quarter:
                t.rotate(self.rotation_quarter * 90)
            if self.flip_h:
                t.scale(-1, 1)
            img = img.transformed(t)

        # 3. Grayscale
        if self.chk_gray.isChecked():
            img = img.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(QImage.Format.Format_ARGB32)
        else:
            img = img.convertToFormat(QImage.Format.Format_ARGB32)

        # 4. Brightness & Contrast adjustment
        bright = self.sld_bright.value()
        contrast = self.sld_contrast.value()
        invert = self.chk_invert.isChecked()

        if bright != 0 or contrast != 0 or invert:
            # Contrast factor: -100..100 -> 0.0..3.0
            cf = (contrast + 100.0) / 100.0 if contrast >= 0 else (100.0 + contrast) / 100.0
            cf = cf * cf if contrast >= 0 else cf
            b_offset = bright * 2.55

            # LUT for speed
            lut = bytearray(256)
            for i in range(256):
                val = i
                if invert:
                    val = 255 - val
                val = (val - 128) * cf + 128 + b_offset
                lut[i] = max(0, min(255, int(val)))

            # Apply LUT to image pixels
            bits = img.bits()
            # Fast in-place byte manipulation
            import numpy as np
            arr = np.frombuffer(bits, dtype=np.uint8).reshape((img.height(), img.bytesPerLine()))
            # ARGB: bytes 0,1,2 are B,G,R
            lut_arr = np.array(lut, dtype=np.uint8)
            arr[:, 0:img.width()*4:4] = lut_arr[arr[:, 0:img.width()*4:4]]
            arr[:, 1:img.width()*4:4] = lut_arr[arr[:, 1:img.width()*4:4]]
            arr[:, 2:img.width()*4:4] = lut_arr[arr[:, 2:img.width()*4:4]]

        self.current_image = img
        pix = QPixmap.fromImage(img)
        self.canvas_view.set_pixmap(pix)
        self.update_dimension_labels()

    def get_canvas_data(self) -> dict:
        """Returns the finalized canvas properties to be added to Document."""
        if not self.current_image:
            return {}

        w_mm = self.current_image.width() / max(self.px_per_mm, 1e-4)
        h_mm = self.current_image.height() / max(self.px_per_mm, 1e-4)
        plane_id = self.cmb_plane.currentData()

        # Convert image to Base64 PNG
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.current_image.save(buffer, "PNG")
        b64 = ba.toBase64().data().decode("ascii")

        return {
            "name": f"Canvas ({plane_id})",
            "plane_id": plane_id,
            "image_data": b64,
            "width_mm": float(w_mm),
            "height_mm": float(h_mm),
            "origin_uv": [-w_mm / 2.0, -h_mm / 2.0],  # centered at plane origin
            "rotation_deg": 0.0,
            "opacity": self.sld_opacity.value() / 100.0,
            "visible": True,
        }
