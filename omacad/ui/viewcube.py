"""
Omacad - 3D ViewCube Navigation Widget
Renders an interactive orientation cube in the corner with clickable faces (TOP, FRONT, RIGHT, etc.).
"""

import math
from typing import Tuple, Optional, Callable
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont, QRegion
from omacad.ui.theme import qcolor


class ViewCube:
    """Renders a responsive 3D orientation cube overlay using QPainter."""

    FACES = [
        ("TOP", np.array([0, 0, 1]), [(0,0,1), (1,0,1), (1,1,1), (0,1,1)]),
        ("BOTTOM", np.array([0, 0, -1]), [(0,0,0), (0,1,0), (1,1,0), (1,0,0)]),
        ("FRONT", np.array([0, -1, 0]), [(0,0,0), (1,0,0), (1,0,1), (0,0,1)]),
        ("BACK", np.array([0, 1, 0]), [(0,1,0), (0,1,1), (1,1,1), (1,1,0)]),
        ("RIGHT", np.array([1, 0, 0]), [(1,0,0), (1,1,0), (1,1,1), (1,0,1)]),
        ("LEFT", np.array([-1, 0, 0]), [(0,0,0), (0,0,1), (0,1,1), (0,1,0)]),
    ]

    def __init__(self, size: int = 90, on_face_clicked: Optional[Callable[[str], None]] = None):
        self.size = size
        self.on_face_clicked = on_face_clicked
        self.hovered_face: Optional[str] = None
        self.cube_center = (0, 0)
        self.rendered_faces = []  # List of (face_name, QPolygonF, z_depth)
        self.home_hovered = False

    def handle_mouse_move(self, local_x: int, local_y: int, viewport_w: int) -> bool:
        """Updates hover states and returns True if cursor is over ViewCube."""
        cube_x = viewport_w - self.size - 25
        cube_y = 25
        rect = QRectF(cube_x - 15, cube_y - 15, self.size + 30, self.size + 30)

        # Check Home button
        home_rect = QRectF(cube_x - 12, cube_y - 10, 22, 22)
        old_home = self.home_hovered
        self.home_hovered = home_rect.contains(local_x, local_y)

        old_hover = self.hovered_face
        self.hovered_face = None

        if rect.contains(local_x, local_y) and not self.home_hovered:
            pt = QPointF(local_x, local_y)
            # Find closest visible face that contains point
            # rendered_faces is sorted by depth (front first)
            for face_name, poly, _ in sorted(self.rendered_faces, key=lambda x: x[2], reverse=True):
                if poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
                    self.hovered_face = face_name
                    break

        return (old_hover != self.hovered_face) or (old_home != self.home_hovered)

    def handle_mouse_press(self, local_x: int, local_y: int, viewport_w: int) -> bool:
        """Returns True if click was handled by ViewCube."""
        cube_x = viewport_w - self.size - 25
        cube_y = 25

        # Check Home button
        home_rect = QRectF(cube_x - 12, cube_y - 10, 22, 22)
        if home_rect.contains(local_x, local_y):
            if self.on_face_clicked:
                self.on_face_clicked("HOME")
            return True

        if self.hovered_face and self.on_face_clicked:
            self.on_face_clicked(self.hovered_face)
            return True

        return False

    def draw(self, painter: QPainter, viewport_w: int, viewport_h: int, azimuth: float, elevation: float):
        """Draws the 3D cube rotated according to camera azimuth and elevation."""
        cube_x = viewport_w - self.size - 25
        cube_y = 35
        center_x = cube_x + self.size / 2.0
        center_y = cube_y + self.size / 2.0
        self.cube_center = (center_x, center_y)

        # 1. Draw Home Button
        home_rect = QRectF(cube_x - 12, cube_y - 12, 22, 22)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(qcolor(60, 65, 75), 1))
        painter.setBrush(QBrush(qcolor(226, 109, 40) if self.home_hovered else qcolor(45, 50, 58, 220)))
        painter.drawRoundedRect(home_rect, 4, 4)

        # Draw home house icon
        painter.setPen(QPen(qcolor(255, 255, 255), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        hx, hy = home_rect.center().x(), home_rect.center().y()
        house_poly = QPolygonF([
            QPointF(hx, hy - 5),
            QPointF(hx - 5, hy),
            QPointF(hx - 5, hy + 5),
            QPointF(hx + 5, hy + 5),
            QPointF(hx + 5, hy),
        ])
        painter.drawPolyline(house_poly)

        # 2. Compute View Matrix for Cube
        rad_az = math.radians(azimuth)
        rad_el = math.radians(elevation)

        # Direction from center to eye
        eye = np.array([
            math.cos(rad_el) * math.sin(rad_az),
            -math.cos(rad_el) * math.cos(rad_az),
            math.sin(rad_el)
        ], dtype=float)

        # Up and right vectors
        up = np.array([0.0, 0.0, 1.0], dtype=float)
        right = np.cross(eye, up)
        norm_r = np.linalg.norm(right)
        if norm_r < 1e-4:
            right = np.array([1.0, 0.0, 0.0], dtype=float)
        else:
            right /= norm_r
        cam_up = np.cross(right, eye)

        # Project a unit cube centered at origin [-0.5..0.5]
        scale = self.size * 0.42

        def project(pt):
            # Center cube
            v = np.array(pt, dtype=float) - 0.5
            px = np.dot(v, right) * scale + center_x
            py = -np.dot(v, cam_up) * scale + center_y
            depth = -np.dot(v, eye)
            return px, py, depth

        # Collect faces and sort back-to-front
        faces_to_render = []
        for name, normal, corners in self.FACES:
            # Face normal dot eye gives visibility (positive means facing camera)
            vis = float(np.dot(normal, eye))
            if vis > 0.05:  # Facing camera (cull back faces)
                pts_2d = [project(c) for c in corners]
                avg_depth = sum(p[2] for p in pts_2d) / 4.0
                poly = QPolygonF([QPointF(p[0], p[1]) for p in pts_2d])
                faces_to_render.append((name, poly, avg_depth, vis))

        # Sort back to front (largest depth first)
        faces_to_render.sort(key=lambda x: x[2])
        self.rendered_faces = []

        font = QFont("sans-serif", 9, QFont.Weight.Bold)
        painter.setFont(font)

        for name, poly, depth, vis in faces_to_render:
            self.rendered_faces.append((name, poly, depth))

            is_hovered = (self.hovered_face == name)

            if is_hovered:
                fill_color = qcolor(226, 109, 40, 240)  # Fusion Orange
                text_color = qcolor(255, 255, 255)
            else:
                # Shading based on normal angle
                shade = int(55 + 40 * max(0.0, vis))
                fill_color = qcolor(shade, shade + 5, shade + 12, 235)
                text_color = qcolor(220, 225, 230)

            # Draw face
            painter.setPen(QPen(qcolor(85, 92, 102), 1.2))
            painter.setBrush(QBrush(fill_color))
            painter.drawPolygon(poly)

            # Draw label only if face is clearly oriented towards camera
            if vis >= 0.28:
                cx = sum(p.x() for p in poly) / 4.0
                cy = sum(p.y() for p in poly) / 4.0
                painter.setPen(QPen(text_color))
                label_rect = QRectF(cx - 30, cy - 12, 60, 24)
                painter.save()
                painter.setClipRegion(QRegion(poly.toPolygon()))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, name)
                painter.restore()
