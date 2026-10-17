"""The sketch Text tool in the view: a ghost of the text follows the cursor, a click places it; for Text On Path the
click picks the circle, arc or line the text runs along (it lights up while you hover it)."""
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt

from omacad.model.sketch import SketchArc, SketchCircle, SketchLine, SketchText


class TextToolMixin:
    PATH_KINDS = (SketchCircle, SketchArc, SketchLine)

    def set_text_draft(self, draft: Optional[SketchText]) -> None:
        """The text being placed (None: none). Its anchor follows the cursor; on a path it follows the hovered curve."""
        self.text_draft = draft
        self.update()

    def _text_path_pick(self, x: float, y: float):
        ent = self._pick_entity(x, y)
        return ent if isinstance(ent, self.PATH_KINDS) else None

    def _text_hover(self, x: float, y: float) -> None:
        draft = getattr(self, "text_draft", None)
        if draft is None:
            return
        if draft.path_id is not None or getattr(self, "text_wants_path", False):
            ent = self._text_path_pick(x, y)
            new_id = ent.entity_id if ent is not None else None
            if new_id != self.hover_entity_id:
                self.hover_entity_id = new_id
            draft.path_id = new_id
        elif self.sketch_current_uv is not None:
            draft.anchor = tuple(self.sketch_current_uv)
        self.update()

    def _text_press(self, event, x: float, y: float) -> bool:
        """Left click with the Text tool: place the draft, or edit the text under the cursor. True when handled."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        sk = self.doc.active_sketch
        under = self._pick_entity(x, y)
        draft = getattr(self, "text_draft", None)
        if isinstance(under, SketchText) and not getattr(self, "text_wants_path", False):
            self.text_edit_requested.emit(under.entity_id)
            return True
        if draft is None:
            return True
        if getattr(self, "text_wants_path", False):
            ent = self._text_path_pick(x, y)
            if ent is None:
                self.status_message.emit("Text On Path: click a circle, an arc or a line of this sketch.")
                return True
            self.text_place_requested.emit(None, ent.entity_id)
            return True
        uv = self.get_sketch_plane_uv(x, y)
        if self.sketch_current_uv is not None:
            uv = self.sketch_current_uv
        if uv is not None:
            self.text_place_requested.emit((float(uv[0]), float(uv[1])), None)
        return True

    def render_text_preview(self, mvp: np.ndarray) -> None:
        """The ghost of the text being placed, in the highlight colour."""
        draft = getattr(self, "text_draft", None)
        sk = self.doc.active_sketch
        if draft is None or sk is None or self.sketch_tool != "TEXT":
            return
        flat = []
        for p1, p2 in draft.to_lines():
            w1, w2 = sk.plane.uv_to_world(*p1), sk.plane.uv_to_world(*p2)
            flat.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
        if not flat:
            return
        from OpenGL import GL
        from omacad.ui import theme
        from omacad.ui.settings import get_settings
        col = get_settings().highlight_color_rgb01() or theme.palette().highlight01()
        GL.glDisable(GL.GL_DEPTH_TEST)
        self.draw_thick_lines(mvp, flat, (*col, 0.9), 2.0, halo=False)
        GL.glEnable(GL.GL_DEPTH_TEST)
