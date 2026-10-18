"""Sketch entity move and rotate drag operations."""

import copy
import math
import numpy as np
from PySide6.QtCore import Qt
from omacad.model.sketch import move_entity, rotate_entity, entity_key_points
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch_snap import SketchSnapper


class SketchMoveMixin:
    """Sketch move operation state and pointer handling."""

    def _toggle_pick(self, event, x, y) -> bool:
        """Mirror/Move picking: a click adds or removes the whole figure, Ctrl/Shift/Alt+click one element."""
        ent = self._pick_entity(x, y)
        if ent is None:
            return False
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
            self.selected_entities ^= {ent.entity_id}
        else:
            ids = self.doc.active_sketch.connected_entities(ent.entity_id)
            self.selected_entities = (self.selected_entities - ids) if ids <= self.selected_entities else (self.selected_entities | ids)
        self.selection_changed.emit()
        self.update()
        return True
    def _move_status(self):
        if self._move_phase == "pick":
            n = len(self.selected_entities)
            self.status_message.emit(f"Move: {n} element(s) picked. Click more (Ctrl+click = one element, click again removes), "
                                     "then Enter. Esc cancels.")
        else:
            self.status_message.emit("Move: click the base point (it snaps to points), then where it should go. "
                                     "Type X / Y for exact distances. The elements keep their angle. Esc cancels.")
    def _move_next(self):
        """Move: picking done, now the base point."""
        if not self.selected_entities:
            self.status_message.emit("Move: pick at least one sketch element first.")
            return
        self._move_phase = "base"
        self._move_status()
        self.update()
    def _begin_move(self, ids):
        sk = self.doc.active_sketch
        ids = {i for i in ids if not getattr(sk.get_entity(i), "projected", False)}
        orig_ents = {e.entity_id: copy.deepcopy(e) for e in sk.entities if e.entity_id in ids}
        # Compute bounding center as rotation pivot
        all_kps = [kp for ent in orig_ents.values() for kp in entity_key_points(ent)]
        if all_kps:
            center_u = sum(p[0] for p in all_kps) / len(all_kps)
            center_v = sum(p[1] for p in all_kps) / len(all_kps)
        else:
            center_u, center_v = 0.0, 0.0

        self._move = {
            "ids": set(ids),
            "orig": orig_ents,
            "before": sk.to_dict(),
            "delta": (0.0, 0.0),
            "angle": 0.0,
            "pivot": (center_u, center_v),
        }
    def _apply_move(self, du: float, dv: float, angle_deg: float = 0.0):
        """Positions the moving entities at original + (du, dv) rotated by angle_deg around pivot."""
        m = self._move
        if not m:
            return
        sk = self.doc.active_sketch
        pivot = m.get("pivot", (0.0, 0.0))
        for i, ent in enumerate(sk.entities):
            orig = m["orig"].get(ent.entity_id)
            if orig is not None:
                moved = copy.deepcopy(orig)
                if abs(angle_deg) > 1e-4:
                    rotate_entity(moved, angle_deg, pivot)
                if abs(du) > 1e-9 or abs(dv) > 1e-9:
                    move_entity(moved, du, dv)
                sk.entities[i] = moved
        sk._bind_texts()
        sk.solve_profiles()
        m["delta"] = (du, dv)
        m["angle"] = angle_deg
        self.update()
    def _end_move(self, commit: bool):
        m = self._move
        self._move = None
        self._drag = None
        self.active_snap = None
        if not m:
            return
        sk = self.doc.active_sketch
        if sk is None:
            return
        du, dv = m["delta"]
        ang = m.get("angle", 0.0)
        has_change = (abs(du) > 1e-9 or abs(dv) > 1e-9 or abs(ang) > 1e-4)
        if commit and has_change and (sk.constraints or sk.dimensions):
            res = solve_sketch(sk, fixed_ids=m["ids"])
            if not res.ok:
                sk.restore_from_dict(m["before"])
                self.status_message.emit(res.message + " - move cancelled.")
                self.doc.notify_changed()
                self.update()
                return
        if commit and has_change:
            self.doc.record_sketch_change(sk, m["before"])
            self.doc.timeline.recompute(self.doc)
            self.doc.notify_changed()
        else:
            sk.restore_from_dict(m["before"])
        self.update()
    def _snap_move_delta(self, du: float, dv: float):
        """Snaps the dragged elements' key points to geometry/edges, else the grid."""
        m = self._move
        sk = self.doc.active_sketch
        tol = max(0.3, min(8.0, self._entity_tolerance() * 1.25))

        class _Others:
            entities = [e for e in sk.entities if e.entity_id not in m["ids"]]

        refs = self._reference_segments()
        best = None
        kps = [kp for orig in m["orig"].values() for kp in entity_key_points(orig)][:32]
        for kp in kps:
            r = SketchSnapper.snap(raw_uv=(kp[0] + du, kp[1] + dv), sketch=_Others, snap_distance=tol,
                                   grid_step=0.0, enable_grid_snap=False, enable_geom_snap=True,
                                   reference_segments=refs)
            if r.snap_type in ("ORIGIN", "ENDPOINT", "MIDPOINT", "EDGE"):
                ddu, ddv = r.uv[0] - kp[0], r.uv[1] - kp[1]
                dist = math.hypot(ddu - du, ddv - dv)
                if best is None or dist < best[0]:
                    best = (dist, ddu, ddv, r)
        if best:
            self.active_snap = best[3]
            return best[1], best[2]
        self.active_snap = None
        if self.sketch_palette.chk_snap_grid.isChecked():
            return round(du / 5.0) * 5.0, round(dv / 5.0) * 5.0
        return du, dv
    def _drag_move(self, event):
        d = self._drag
        if not d["moved"]:
            if (event.position() - d["press_pos"]).manhattanLength() < 4:
                return
            d["moved"] = True
            self._begin_move(self.selected_entities)
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        if uv is None:
            return
        du, dv = self._snap_move_delta(uv[0] - d["press_uv"][0], uv[1] - d["press_uv"][1])
        self._apply_move(du, dv)
    def _drag_release(self, event):
        d = self._drag
        self._drag = None
        if d["moved"]:
            self._end_move(True)
        elif not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and len(self.selected_entities) > 1:
            self.selected_entities = {d["ent_id"]}  # plain click inside a multi-selection narrows it
            self.selection_changed.emit()
        self.update()
