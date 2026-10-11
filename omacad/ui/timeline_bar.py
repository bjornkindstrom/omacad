"""
Omacad - Parametric Timeline Bar
Horizontal history timeline at the bottom with playback controls and feature nodes.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QScrollArea, QFrame, QLabel, QSizePolicy, QMenu, QInputDialog
)
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.ui import feature_edit
from omacad.model.document import Document
from omacad.model.timeline import Feature


class FeatureNodeWidget(QFrame):
    """A single feature node chip in the parametric timeline."""

    clicked = Signal(int)
    double_clicked = Signal(int)
    context_requested = Signal(int, object)  # step index, global position

    FEATURE_ICONS = {
        "box": "📦",
        "cylinder": "🥫",
        "sphere": "⚽",
        "sketch": "✏️",
        "extrude": "⬆️",
        "revolve": "🔄",
        "combine": "🔗",
        "fillet": "🔘",
        "pattern": "🔁",
    }

    def __init__(self, index: int, feature: Feature, is_active: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        self.feature = feature
        self.is_active = is_active

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        icon_str = self.FEATURE_ICONS.get(feature.feature_type, "⚙️")
        lbl_icon = QLabel()
        lbl_icon.setPixmap(theme.emoji_icon(icon_str, 24).pixmap(24, 24))
        layout.addWidget(lbl_icon)

        lbl_name = QLabel(feature.name)
        if feature.suppressed:
            style(lbl_name, "font-size: 11px; font-weight: bold; color: #6B7280; text-decoration: line-through;")
        else:
            style(lbl_name, "font-size: 11px; font-weight: bold;")
        self.setToolTip(self._describe(feature) + "\n\nDouble-click to edit, right-click for more.")
        layout.addWidget(lbl_name)

        if is_active:
            style(self, """
                QFrame {
                    background-color: #2D333B;
                    border: 1px solid #E26D28;
                    border-radius: 4px;
                }
                QFrame:hover {
                    background-color: #353D47;
                }
            """)
        else:
            style(self, """
                QFrame {
                    background-color: #212428;
                    border: 1px solid #333842;
                    border-radius: 4px;
                }
                QFrame:hover {
                    background-color: #282C32;
                }
            """)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _describe(f) -> str:
        t = f.feature_type
        if t == "extrude":
            return f"{f.name}\nDistance {f.distance:g} mm, {f.direction.replace('_', ' ')}, {f.operation.replace('_', ' ')}"
        if t == "box":
            return f"{f.name}\n{f.length:g} x {f.width:g} x {f.height:g} mm"
        if t == "cylinder":
            return f"{f.name}\nRadius {f.radius:g}, height {f.height:g} mm"
        if t == "sphere":
            return f"{f.name}\nRadius {f.radius:g} mm"
        if t == "pattern":
            return f"{f.name}\n{f.kind} of {len(f.source_ids)} step(s), {f.copies} copies"
        if t == "fillet":
            return f"{f.name}\n{f.kind.title()} {f.size:g} mm on {len(f.edges)} edge(s)"
        return f.name + ("  (suppressed)" if f.suppressed else "")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self.index, event.globalPos())


class TimelineBar(QWidget):
    """Bottom Parametric Timeline bar with history playback."""

    edit_sketch_requested = Signal(str)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.refresh_timeline)

        self.setFixedHeight(48)
        style(self, """
            QWidget {
                background-color: #1A1C1E;
                border-top: 1px solid #2B2E33;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Timeline Label
        lbl_title = QLabel("TIMELINE")
        style(lbl_title, "font-weight: bold; font-size: 10px; color: #7B818C; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        # Playback Controls
        self.btn_rewind = QPushButton("⏮")
        self.btn_rewind.setToolTip("Rewind to Beginning")
        self.btn_rewind.setFixedSize(28, 28)
        self.btn_rewind.clicked.connect(self.on_rewind)
        layout.addWidget(self.btn_rewind)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("Step Backward")
        self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.clicked.connect(self.on_step_back)
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("Step Forward")
        self.btn_next.setFixedSize(28, 28)
        self.btn_next.clicked.connect(self.on_step_forward)
        layout.addWidget(self.btn_next)

        self.btn_ff = QPushButton("⏭")
        self.btn_ff.setToolTip("Fast Forward to End")
        self.btn_ff.setFixedSize(28, 28)
        self.btn_ff.clicked.connect(self.on_fast_forward)
        layout.addWidget(self.btn_ff)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        style(div, "color: #333842;")
        layout.addWidget(div)

        # Scroll Area for Feature Chips
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        style(self.scroll_area, "border: none; background: transparent;")

        self.nodes_container = QWidget()
        self.nodes_layout = QHBoxLayout(self.nodes_container)
        self.nodes_layout.setContentsMargins(4, 0, 4, 0)
        self.nodes_layout.setSpacing(6)
        self.nodes_layout.addStretch()

        self.scroll_area.setWidget(self.nodes_container)
        layout.addWidget(self.scroll_area)

        self.refresh_timeline()

    def refresh_timeline(self):
        """Re-renders feature nodes according to timeline state."""
        # Clear existing nodes
        while self.nodes_layout.count() > 1:
            item = self.nodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        features = self.doc.timeline.features
        marker = self.doc.timeline.marker_index

        for idx, feat in enumerate(features):
            is_active = (idx < marker)
            chip = FeatureNodeWidget(idx + 1, feat, is_active)
            chip.clicked.connect(self.on_node_clicked)
            chip.double_clicked.connect(self.on_node_edit)
            chip.context_requested.connect(self.on_node_menu)
            self.nodes_layout.insertWidget(idx, chip)

    def on_node_clicked(self, step_index: int):
        pass  # a single click only selects; roll back with the arrows or the right-click menu

    def on_node_edit(self, step_index: int):
        """Double-click: edit that step (a sketch opens in sketch mode)."""
        idx = step_index - 1
        feat = self.doc.timeline.features[idx]
        if feat.feature_type == "sketch":
            self.edit_sketch_requested.emit(feat.sketch.sketch_id)
        elif feature_edit.can_edit(feat):
            feature_edit.edit_feature(self.window(), self.doc, idx)

    def on_node_menu(self, step_index: int, pos):
        idx = step_index - 1
        feat = self.doc.timeline.features[idx]
        menu = QMenu(self)
        a_edit = theme.action_with_icon(menu, "✏️ Edit…") if feature_edit.can_edit(feat) else None
        a_rename = theme.action_with_icon(menu, "🏷️ Rename…")
        a_supp = theme.action_with_icon(menu, "▶️ Unsuppress" if feat.suppressed else "⏸️ Suppress")
        menu.addSeparator()
        a_back = theme.action_with_icon(menu, "⏮️ Roll back to here")
        a_end = theme.action_with_icon(menu, "⏭️ Roll forward to the end")
        menu.addSeparator()
        a_del = theme.action_with_icon(menu, "🗑️ Delete…")
        chosen = menu.exec(pos)
        if chosen is None:
            return
        if chosen is a_edit:
            self.on_node_edit(step_index)
        elif chosen is a_rename:
            name, ok = QInputDialog.getText(self.window(), "Rename step", "Name:", text=feat.name)
            if ok:
                self.doc.rename_feature(idx, name)
        elif chosen is a_supp:
            self.doc.toggle_suppress(idx)
        elif chosen is a_back:
            self.doc.timeline.step_to(step_index, self.doc)
            self.doc.notify_changed()
        elif chosen is a_end:
            self.on_fast_forward()
        elif chosen is a_del and feature_edit.confirm_delete(self.window(), self.doc, idx):
            self.doc.delete_feature(idx)

    def on_rewind(self):
        self.doc.timeline.rewind(self.doc)
        self.doc.notify_changed()

    def on_step_back(self):
        self.doc.timeline.step_backward(self.doc)
        self.doc.notify_changed()

    def on_step_forward(self):
        self.doc.timeline.step_forward(self.doc)
        self.doc.notify_changed()

    def on_fast_forward(self):
        self.doc.timeline.fast_forward(self.doc)
        self.doc.notify_changed()
