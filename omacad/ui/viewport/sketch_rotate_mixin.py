"""Sketch rotation preview and pivot picking, using the viewport's move transaction."""

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QColor
from omacad.model.sketch_rotate import selection_pivots, sketch_face_pivot, rotate_axis_constraints, validate_axis_dimensions
from omacad.ui.sketch_rotation import SketchRotationPanel


class SketchRotateMixin:
    def _init_sketch_rotation(self):
        self.rotation_panel = SketchRotationPanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.rotation_panel)
        self.rotation_panel.hide()
        self.rotation_panel.changed.connect(self._rotate_preview)
        self.rotation_panel.pick_requested.connect(self._rotate_begin_pick)
        self.rotation_panel.accepted.connect(lambda: self._rotate_finish(True))
        self.rotation_panel.cancelled.connect(lambda: self.set_sketch_tool("NONE"))
        self._rotate_pick = False

    def _rotate_begin(self):
        self._begin_move(self.selected_entities)
        if not self._move["orig"]:
            self._end_move(False)
            self.status_message.emit("Rotate: select editable sketch elements first. Projected edges cannot be rotated.")
            return False
        self.selected_entities = set(self._move["ids"])
        self.selection_changed.emit()
        self._rotate_pivots = selection_pivots(self._move["orig"].values())
        self._rotate_pivots["origin"] = (0.0, 0.0)
        face = sketch_face_pivot(self.doc, self.doc.active_sketch)
        if face is not None:
            self._rotate_pivots["face"] = face
        self.rotation_panel.configure(self._rotate_pivots)
        self.rotation_panel.set_coordinates(self._move["pivot"], True)
        self.rotation_panel.show()
        self.sketch_palette.adjustSize()
        self._rotate_preview()
        QTimer.singleShot(0, self.rotation_panel.angle.setFocus)
        self.rotation_panel.angle.selectAll()
        return True

    def _rotate_preview(self):
        if self.sketch_tool != "ROTATE" or not self._move:
            return
        panel = self.rotation_panel
        key = panel.pivot.currentData()
        pivot = (panel.x.value(), panel.y.value()) if key == "custom" else self._rotate_pivots[key]
        panel.set_coordinates(pivot, key == "custom")
        self._rotate_pick = False
        self._move["pivot"] = pivot
        sk = self.doc.active_sketch
        # Every preview starts at the transaction snapshot; changing the pivot never
        # compounds a previous rotation or progressively removes constraints.
        sk.constraints = self._rotate_original_constraints()
        angle = panel.angle.value()
        self._apply_move(0, 0, angle)
        try:
            rotate_axis_constraints(sk, self._move["ids"], angle)
            validate_axis_dimensions(sk, self._move["ids"])
        except ValueError as exc:
            panel.info.setText(str(exc))
            panel.ok.setEnabled(False)
        else:
            panel.info.setText("Preview: type an angle. OK applies; Esc cancels. Axis relations follow the rotation.")
            panel.ok.setEnabled(True)
        self.update()

    def _rotate_original_constraints(self):
        from omacad.model.sketch import SketchConstraint
        return [SketchConstraint.from_dict(c) for c in self._move["before"]["constraints"]]

    def _rotate_begin_pick(self):
        if self.sketch_tool != "ROTATE":
            return
        self._rotate_pick = True
        self.status_message.emit("Rotate: click the pivot point in the sketch. Geometry and grid snapping are available.")
        self.setFocus()

    def _rotate_click(self, x, y):
        if self._rotate_pick:
            uv = self.get_sketch_plane_uv(x, y)
            if uv is None:
                return
            from omacad.model.sketch_snap import SketchSnapper
            snap = SketchSnapper.snap(
                raw_uv=uv, sketch=self.doc.active_sketch,
                snap_distance=max(0.3, min(8.0, self._entity_tolerance() * 1.25)),
                reference_segments=self._reference_segments(), grid_step=5.0,
                enable_grid_snap=self.sketch_palette.chk_snap_grid.isChecked(),
                enable_geom_snap=self.sketch_palette.chk_snap_points.isChecked())
            panel = self.rotation_panel
            panel.pivot.blockSignals(True)
            panel.pivot.setCurrentIndex(panel.pivot.findData("custom"))
            panel.pivot.blockSignals(False)
            panel.set_coordinates(snap.uv, True)
            self._rotate_preview()
            self.status_message.emit("Rotate: pivot set. Enter an angle, then OK to apply.")

    def _rotate_finish(self, commit):
        if self.sketch_tool != "ROTATE" or not self._move:
            return
        if commit and not self.rotation_panel.ok.isEnabled():
            return
        self._end_move(commit)
        self.set_sketch_tool("NONE")

    def _draw_rotation_pivot(self, painter):
        if self.sketch_tool != "ROTATE" or not self._move or not self.doc.active_sketch:
            return
        point = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*self._move["pivot"]))
        if point is None:
            return
        painter.save()
        painter.setPen(QPen(QColor(255, 125, 40), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x, y = point[:2]
        painter.drawEllipse(QPointF(x, y), 8, 8)
        painter.drawLine(QPointF(x - 13, y), QPointF(x + 13, y))
        painter.drawLine(QPointF(x, y - 13), QPointF(x, y + 13))
        painter.drawText(QPointF(x + 15, y - 12), "Pivot")
        painter.restore()
