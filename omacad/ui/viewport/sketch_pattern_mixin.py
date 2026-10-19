"""Sketch Pattern tool (Björn #75): live copies of the selection while the panel's numbers change; OK is one undo
step, Cancel / Esc / another tool puts the sketch back."""

from omacad.model.sketch_pattern import circular_copies, default_spacing, rectangular_copies, selection_centre
from omacad.model.sketch_rotate import sketch_face_pivot
from omacad.ui.sketch_pattern_panel import SketchPatternPanel


class SketchPatternMixin:
    def _init_sketch_pattern(self):
        self.pattern_panel = SketchPatternPanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.pattern_panel)
        self.pattern_panel.hide()
        self.pattern_panel.changed.connect(self._pattern_preview)
        self.pattern_panel.accepted.connect(lambda: self._pattern_finish(True))
        self.pattern_panel.cancelled.connect(lambda: self.set_sketch_tool("NONE"))
        self._pattern = None

    def _pattern_begin(self) -> bool:
        sk = self.doc.active_sketch
        ents = [e for e in sk.entities if e.entity_id in self.selected_entities and not getattr(e, "projected", False)]
        if not ents:
            self.status_message.emit("Pattern: select sketch elements first (click, Ctrl+click, or double-click a figure).")
            return False
        centres = {"selection": selection_centre(ents), "origin": (0.0, 0.0)}
        face = sketch_face_pivot(self.doc, sk)
        if face is not None:
            centres["face"] = tuple(face)
        self._pattern = {"before": sk.to_dict(), "ids": [e.entity_id for e in ents], "centres": centres}
        labels = {"selection": "Selection centre", "origin": "Sketch origin", "face": "Face centre"}
        self.pattern_panel.configure(default_spacing(ents), [(k, labels[k]) for k in centres])
        self.pattern_panel.show()
        self.sketch_palette.adjustSize()
        self._pattern_preview()
        return True

    def _pattern_preview(self):
        p = self._pattern
        if self.sketch_tool != "PATTERN" or not p:
            return
        sk = self.doc.active_sketch
        sk.restore_from_dict(p["before"])
        ents = [sk.get_entity(i) for i in p["ids"]]
        panel = self.pattern_panel
        if panel.kind.currentData() == "circular":
            copies = circular_copies(sk, ents, int(panel.count.value()), p["centres"][panel.centre.currentData()],
                                     panel.angle.value())
        else:
            copies = rectangular_copies(sk, ents, int(panel.count_x.value()), panel.spacing_x.value(),
                                        int(panel.count_y.value()), panel.spacing_y.value())
        sk._bind_texts()
        sk.solve_profiles()
        p["copies"] = [c.entity_id for c in copies]
        self.status_message.emit(f"Pattern: {len(copies)} new element(s). OK keeps them.")
        self.update()

    def _pattern_finish(self, commit: bool):
        p, self._pattern = self._pattern, None
        self.pattern_panel.hide()
        sk = self.doc.active_sketch
        if not p or sk is None:
            return
        if commit and p.get("copies"):
            self.doc.record_sketch_change(sk, p["before"])
            self.doc.timeline.recompute(self.doc)
            self.selected_entities = set(p["ids"]) | set(p["copies"])
            self.selection_changed.emit()
        else:
            sk.restore_from_dict(p["before"])
        self.doc.notify_changed()
        if commit and self.sketch_tool == "PATTERN":
            self.set_sketch_tool("NONE")
        self.update()
