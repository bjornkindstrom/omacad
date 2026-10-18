"""Picking a point on a body in the 3D view (Move / Rotate from a point, point to point).

While picking, the snap points of the bodies near the cursor show as dots: green for the end of a straight
edge, orange for the sharp corner a rounding hides, with dashed guide lines from the rounding to that
corner. The world origin can be picked too. A click emits `point_picked` with {"body", "kind", "xyz"}."""

import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen

from omacad.model.body_points import body_points

SNAP_PX = 12.0       # the cursor catches a point this close
SHOW_PX = 90.0       # points (and hidden corners' guide lines) this close are shown


class PointPickMixin:
    def begin_point_pick(self):
        self.point_pick = True
        self.hover_point = None
        self._near_points = []
        self.setFocus()
        self.update()

    def end_point_pick(self):
        self.point_pick = False
        self.hover_point = None
        self._near_points = []
        self.update()

    def _snap_points(self, body):
        """A body's snap points, worked out once per rebuild of the body (its edge list is replaced then)."""
        cache = self.__dict__.setdefault("_snap_point_cache", {})
        hit = cache.get(body.body_id)
        if hit is None or hit[0] is not body.edges:
            hit = cache[body.body_id] = (body.edges, body_points(body))
        return hit[1]

    def _candidate_points(self):
        """(body_id or None, kind, xyz, guides) of everything that can be picked: body points and the origin."""
        out = [(None, "fixed", np.zeros(3), ())]
        for body in self.doc.bodies.values():
            if body.visible or body.body_id == getattr(self, "point_pick_hidden_ok", None):
                out += [(body.body_id, p.kind, p.xyz, p.guides) for p in self._snap_points(body)]
        return out

    def _point_pick_hover(self, x: float, y: float) -> None:
        cands = self._candidate_points()
        screen, front = self.project_points(np.array([c[2] for c in cands]))
        dist = np.hypot(screen[:, 0] - x, screen[:, 1] - y)
        dist[~front] = np.inf
        self._near_points = [(cands[i], screen[i]) for i in np.flatnonzero(dist < SHOW_PX)]
        i = int(np.argmin(dist))
        hover = cands[i] if dist[i] < SNAP_PX else None
        if (hover is None) != (self.hover_point is None) or (hover is not None and hover[2] is not self.hover_point[2]):
            self.hover_point = hover
            if hover is not None:
                what = {"end": "end of an edge", "corner": "hidden corner",
                        "top_center": "centre of top face", "bottom_center": "centre of bottom face",
                        "fixed": "origin"}[hover[1]]
                self.status_message.emit(f"Point: {what} at ({hover[2][0]:.2f}, {hover[2][1]:.2f}, {hover[2][2]:.2f}). Click to pick it.")
        self.update()

    def _point_pick_press(self) -> bool:
        if self.hover_point is None:
            return False
        body_id, kind, xyz, _ = self.hover_point
        self.point_picked.emit({"body": body_id, "kind": kind, "xyz": [float(c) for c in xyz]})
        return True

    def _draw_point_pick(self, painter) -> None:
        if not getattr(self, "point_pick", False):
            return
        painter.save()
        colours = {"end": QColor(80, 220, 120), "corner": QColor(255, 150, 40),
                   "top_center": QColor(80, 190, 255), "bottom_center": QColor(80, 190, 255),
                   "fixed": QColor(120, 180, 255)}
        for (body_id, kind, xyz, guides), scr in self._near_points:
            colour = colours[kind]
            if kind == "corner":
                ends = self.project_points(np.array(guides))
                pen = QPen(colour, 1.5, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                for g, ok in zip(*ends):
                    if ok:
                        painter.drawLine(QPointF(*g), QPointF(*scr))
            hovered = self.hover_point is not None and self.hover_point[2] is xyz
            painter.setPen(QPen(QColor(255, 255, 255), 2 if hovered else 1))
            painter.setBrush(colour if hovered else QColor(colour.red(), colour.green(), colour.blue(), 110))
            painter.drawEllipse(QPointF(*scr), 7.0 if hovered else 4.0, 7.0 if hovered else 4.0)
        painter.restore()
