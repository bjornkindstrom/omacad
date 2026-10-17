"""
Omacad - Left Browser Tree
Hierarchy tree for Document Settings, Origin geometry, Bodies, and Sketches.
"""

from typing import Optional, Dict
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QMenu, QHeaderView, QLabel, QHBoxLayout,
    QAbstractItemView
)
from PySide6.QtGui import QIcon, QAction, QBrush, QColor, QFont, QKeySequence, QShortcut
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.model.document import Document
from omacad.ui.theme import qcolor


class BrowserTree(QWidget):
    """Fusion 360 style left hierarchy browser."""

    body_selected = Signal(str)
    sketch_selected = Signal(str)
    start_sketch_on_plane = Signal(str)
    start_sketch_on_cplane = Signal(str)
    edit_section_requested = Signal(str)
    export_body_stl = Signal(str)
    export_body_step = Signal(str)
    edit_sketch_requested = Signal(str)
    edit_sketch_text_requested = Signal(str, str)     # sketch_id, entity_id
    split_body_requested = Signal(str, str)
    insert_canvas_requested = Signal(str)
    edit_canvas_requested = Signal(str)
    shell_body_requested = Signal(str)
    move_body_requested = Signal(str)
    named_view_requested = Signal(str)
    extrude_sketch_requested = Signal(str)
    offset_plane_requested = Signal()
    find_in_window_requested = Signal(str, str)      # kind ("body"/"sketch"), id
    find_in_timeline_requested = Signal(str, str)
    delete_sketch_requested = Signal(str)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.refresh_tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header Bar (Fusion 360 floating card-style header)
        self.header = QWidget()
        style(self.header, "background-color: rgba(32, 34, 37, 0.75); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 3px 6px;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(6, 2, 4, 2)
        self.lbl_title = QLabel("BROWSER")
        style(self.lbl_title, "font-weight: bold; font-size: 11px; color: #8E95A0; letter-spacing: 0.8px; background: transparent;")
        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch()

        layout.addWidget(self.header)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setIndentation(18)
        self.tree.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        style(self.tree, """
            QTreeWidget {
                background: transparent;
                border: none;
                color: #D8DCE2;
                outline: none;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 5px 6px;
                border-radius: 4px;
                background: transparent;
            }
            QTreeWidget::item:hover {
                background-color: rgba(60, 68, 79, 0.4);
            }
            QTreeWidget::item:selected {
                background-color: rgba(6, 150, 215, 0.45);
                color: #FFFFFF;
            }
        """)
        # Column 0 = name, column 1 = clickable visibility eye
        self.tree.setColumnCount(2)
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, 40)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        # F2 or a slow second click on a selected sketch/body renames it in place
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.SelectedClicked)
        self.tree.itemChanged.connect(self.on_item_renamed)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.tree)
        # V shows/hides what is selected, as in Fusion
        sc = QShortcut(QKeySequence("V"), self.tree)
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(self.toggle_selected_visibility)

        self.setObjectName("BrowserWidget")
        style(self, "QWidget#BrowserWidget { background: transparent; border: none; }")
        self.refresh_tree()

    def refresh_tree(self):
        """Rebuilds the tree nodes based on the Document model."""
        self.tree.blockSignals(True)  # rebuilding must not look like a rename
        expanded = self._expanded_keys()
        scroll = self.tree.verticalScrollBar().value()
        try:
            self._rebuild_tree()
            self._restore_expanded(expanded)
            self.tree.verticalScrollBar().setValue(scroll)
        finally:
            self.tree.blockSignals(False)

    @staticmethod
    def _item_key(item: QTreeWidgetItem):
        """Identity of a node across rebuilds: the item's own data (kind, id) or, for groups, its text."""
        return item.data(0, Qt.ItemDataRole.UserRole) or item.text(0)

    def _walk(self):
        stack = [(self.tree.topLevelItem(i), ()) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item, path = stack.pop()
            key = path + (self._item_key(item),)
            yield item, key
            stack += [(item.child(i), key) for i in range(item.childCount())]

    def _expanded_keys(self) -> dict:
        """key -> expanded? for every node, so a rebuild (e.g. after hiding a plane) keeps the tree as it was."""
        return {key: item.isExpanded() for item, key in self._walk()}

    def _restore_expanded(self, state: dict):
        for item, key in self._walk():
            if key in state:
                item.setExpanded(state[key])

    def _iconify(self, item: QTreeWidgetItem):
        """Leading emoji of an item's text becomes a real icon (so it can be larger than the font)."""
        emoji, rest = theme.split_emoji(item.text(0))
        if emoji:
            item.setText(0, rest)
            item.setIcon(0, theme.emoji_icon(emoji, 22))
        for i in range(item.childCount()):
            self._iconify(item.child(i))

    def _rebuild_tree(self):
        self._rebuild_items()
        for i in range(self.tree.topLevelItemCount()):
            self._iconify(self.tree.topLevelItem(i))

    def _rebuild_items(self):
        self.tree.clear()

        # Root: the document, as in Fusion 360 ("(Unsaved)" until it has been saved)
        name = self.doc.name or ""
        unsaved = (not name) or name.lower().startswith("omacad - untitled") or name.lower() == "untitled"
        root = QTreeWidgetItem(self.tree, ["📁 " + ("(Unsaved)" if unsaved else name), ""])
        root.setExpanded(True)

        # Document Settings
        settings_item = QTreeWidgetItem(root, ["⚙️ Document Settings", ""])
        settings_item.setExpanded(True)
        for text in (f"📏 Units: {self.doc.units}, g", "🧱 Parametric Design"):
            it = QTreeWidgetItem(settings_item, [text, ""])
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        # Named Views
        views_item = QTreeWidgetItem(root, ["🎥 Named Views", ""])
        for view in ("Home", "Top", "Front", "Right", "Back", "Left", "Bottom"):
            it = QTreeWidgetItem(views_item, [f"🎥 {view}", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("view", view.upper()))

        # Origin
        origin_item = QTreeWidgetItem(root, ["🌐 Origin", ""])
        origin_item.setExpanded(False)
        origin_item.setData(0, Qt.ItemDataRole.UserRole, ("origin", "all"))
        self._style_eye(origin_item, self.doc.origin_visible("all"))
        origin_item.setToolTip(1, "Show or hide the whole origin (axes and planes)")
        for axis, label in (("X", "• X Axis (Red)"), ("Y", "• Y Axis (Green)"), ("Z", "• Z Axis (Blue)")):
            it = QTreeWidgetItem(origin_item, [label, ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("axis", axis))
            self._style_eye(it, self.doc.origin_visible("axis", axis))
        for name_ in ("XY", "XZ", "YZ"):
            it = QTreeWidgetItem(origin_item, [f"📄 {name_} Plane", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("plane", name_))
            self._style_eye(it, self.doc.origin_visible("plane", name_))
        for pid, c in self.doc.construction_planes.items():
            pi = QTreeWidgetItem(origin_item, ["📄 " + c["name"], ""])
            pi.setData(0, Qt.ItemDataRole.UserRole, ("cplane", pid))
            pi.setFlags(pi.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(pi, bool(c.get("visible", True)))
        if self.doc.construction_planes:
            origin_item.setExpanded(True)

        # Analysis (section views live here, as in Fusion)
        analysis = QTreeWidgetItem(root, ["🔍 Analysis", ""])
        for sid, sec in self.doc.sections.items():
            it = QTreeWidgetItem(analysis, ["✂️ " + sec["name"], ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("section", sid))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(it, bool(sec.get("active")))
            it.setToolTip(1, "Click to turn the section off" if sec.get("active") else "Click to turn the section on")
        if self.doc.sections:
            analysis.setExpanded(True)

        def group(label: str, key: str, visible: bool):
            g = QTreeWidgetItem(root, [label, ""])
            g.setData(0, Qt.ItemDataRole.UserRole, ("group", key))
            g.setExpanded(True)
            self._style_eye(g, visible)
            return g

        # Bodies
        bodies_group = group("🧊 Bodies", "bodies", any(b.visible for b in self.doc.bodies.values()) or not self.doc.bodies)
        for b_id, body in self.doc.bodies.items():
            b_item = QTreeWidgetItem(bodies_group, [body.name, ""])
            b_item.setData(0, Qt.ItemDataRole.UserRole, ("body", b_id))
            b_item.setFlags(b_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(b_item, body.visible)
            if body.selected:
                b_item.setSelected(True)

        # Canvases
        if getattr(self.doc, "canvases", None):
            canv_group = group("🖼️ Canvases", "canvases", any(c.get("visible", True) for c in self.doc.canvases.values()))
            for cid, c in self.doc.canvases.items():
                it = QTreeWidgetItem(canv_group, [c["name"], ""])
                it.setData(0, Qt.ItemDataRole.UserRole, ("canvas", cid))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                self._style_eye(it, bool(c.get("visible", True)))
                it.setToolTip(1, "Click to hide canvas" if c.get("visible", True) else "Click to show canvas")

        # Sketches (all of them, also those drawn on a body face)
        from omacad.model.sketch import SketchText
        sketches_group = group("✏️ Sketches", "sketches", any(sk.visible for sk in self.doc.sketches.values()) or not self.doc.sketches)
        for s_id, sketch in self.doc.sketches.items():
            s_item = QTreeWidgetItem(sketches_group, ["✏️ " + sketch.name, ""])
            s_item.setData(0, Qt.ItemDataRole.UserRole, ("sketch", s_id))
            s_item.setFlags(s_item.flags() | Qt.ItemFlag.ItemIsEditable)
            if sketch == self.doc.active_sketch:
                font = QFont(s_item.font(0))
                font.setBold(True)
                s_item.setFont(0, font)
                s_item.setToolTip(0, "Active sketch")
            self._style_eye(s_item, sketch.visible)
            texts = [e for e in sketch.entities if isinstance(e, SketchText)]
            for t_ent in texts:
                preview = t_ent.text.replace("\n", " ↵ ")
                if len(preview) > 24:
                    preview = preview[:23] + "…"
                t_item = QTreeWidgetItem(s_item, [f'🔤 "{preview}"', ""])
                t_item.setData(0, Qt.ItemDataRole.UserRole, ("sketch_text", f"{s_id}:{t_ent.entity_id}"))
                t_item.setToolTip(0, "Double-click to edit text")
            if texts and sketch == self.doc.active_sketch:
                s_item.setExpanded(True)

    @staticmethod
    def _style_eye(item: QTreeWidgetItem, visible: bool):
        """Eye icon in column 1; hidden items are greyed out."""
        item.setText(1, "")
        item.setIcon(1, theme.emoji_icon("👁" if visible else "🚫", 22))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(1, "Click to hide" if visible else "Click to show")
        grey = QBrush(qcolor(110, 116, 125))
        item.setForeground(0, QBrush() if visible else grey)

    def on_item_renamed(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if column != 0 or not data or data[0] not in ("sketch", "body", "section", "canvas"):
            return
        kind, item_id = data
        if kind == "canvas":
            self.doc.update_canvas(item_id, name=item.text(0))
            return
        if not self.doc.rename_item(kind, item_id, item.text(0)):
            self.refresh_tree()  # empty or invalid name: put the old one back

    def toggle_visibility(self, item_type: str, item_id: str) -> bool:
        """Show/hide whatever the tree item stands for (eye click, V, right-click menu). False: nothing to toggle."""
        doc = self.doc
        if item_type == "canvas":
            doc.toggle_canvas_visibility(item_id)
        elif item_type == "section":
            doc.set_section_active(item_id, not doc.sections[item_id].get("active"))
        elif item_type == "body":
            doc.toggle_body_visibility(item_id)
        elif item_type == "sketch":
            doc.toggle_sketch_visibility(item_id)
        elif item_type == "cplane":
            doc.toggle_construction_plane(item_id)
        elif item_type in ("origin", "axis", "plane"):
            kind, name = ("all", "") if item_type == "origin" else (item_type, item_id)
            doc.set_origin_visibility(kind, name, not doc.origin_visible(kind, name))
        elif item_type == "group":
            shown = {"bodies": any(b.visible for b in doc.bodies.values()),
                     "sketches": any(sk.visible for sk in doc.sketches.values()),
                     "canvases": any(c.get("visible", True) for c in doc.canvases.values())}.get(item_id, False)
            doc.set_group_visibility(item_id, not shown)
        else:
            return False
        return True

    def toggle_selected_visibility(self):
        for it in self.tree.selectedItems():
            data = it.data(0, Qt.ItemDataRole.UserRole)
            if data:
                self.toggle_visibility(*data)

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        if item_type == "view":
            self.named_view_requested.emit(item_id)
            return
        if column == 1 and item_type in ("origin", "axis", "plane", "body", "sketch", "section", "canvas", "cplane", "group"):
            self.toggle_visibility(item_type, item_id)
            return
        if item_type == "body":
            self.doc.select_body(item_id)
            self.body_selected.emit(item_id)
        elif item_type == "sketch":
            self.sketch_selected.emit(item_id)

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        if item_type == "plane":
            self.start_sketch_on_plane.emit(item_id)
        elif item_type == "cplane":
            self.start_sketch_on_cplane.emit(item_id)
        elif item_type == "body":
            self.doc.toggle_body_visibility(item_id)
        elif item_type == "sketch":
            self.edit_sketch_requested.emit(item_id)
        elif item_type == "sketch_text":
            s_id, ent_id = item_id.split(":", 1)
            self.edit_sketch_text_requested.emit(s_id, ent_id)
        elif item_type == "canvas":
            self.edit_canvas_requested.emit(item_id)
        elif item_type == "section":
            self.doc.set_section_active(item_id, not self.doc.sections[item_id].get("active"))

    def show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        menu = QMenu(self)
        theme.style_menu(menu)
        add = lambda text, slot: theme.action_with_icon(menu, text).triggered.connect(slot)
        rename = lambda: add("🏷️ Rename\tF2", lambda: self.tree.editItem(item, 0))
        show_hide = lambda: add("👁️ Show/Hide\tV", lambda: self.toggle_visibility(item_type, item_id))
        find = lambda kind: (menu.addSeparator(),
                             add("🔎 Find in Window", lambda: self.find_in_window_requested.emit(kind, item_id)),
                             add("🧭 Find in Timeline", lambda: self.find_in_timeline_requested.emit(kind, item_id)))

        if item_type == "plane":
            add(f"✏️ Create Sketch on {item_id} Plane", lambda: self.start_sketch_on_plane.emit(item_id))
            add("📐 Offset Plane", self.offset_plane_requested.emit)
            add(f"🖼️ Insert Canvas on {item_id} Plane…", lambda: self.insert_canvas_requested.emit(item_id))
            add(f"🪚 Split Body with {item_id} Plane…", lambda: self.split_body_requested.emit("", item_id))
            menu.addSeparator()
            show_hide()

        elif item_type == "cplane":
            add("✏️ Create Sketch on this Plane", lambda: self.start_sketch_on_cplane.emit(item_id))
            add("📐 Offset Plane", self.offset_plane_requested.emit)
            add("🖼️ Insert Canvas on this Plane…", lambda: self.insert_canvas_requested.emit(item_id))
            add("🪚 Split Body with this Plane…", lambda: self.split_body_requested.emit("", item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_construction_plane(item_id))

        elif item_type == "body":
            add("↔️ Move Body…", lambda: self.move_body_requested.emit(item_id))
            add("🐚 Shell…", lambda: self.shell_body_requested.emit(item_id))
            add("🪚 Split Body…", lambda: self.split_body_requested.emit(item_id, ""))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            find("body")
            menu.addSeparator()
            add("💾 Export as STL...", lambda: self.export_body_stl.emit(item_id))
            add("💾 Export as STEP...", lambda: self.export_body_step.emit(item_id))
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_body(item_id))

        elif item_type == "canvas":
            add("✏️ Edit Canvas (Calibrate / Set Origin)…", lambda: self.edit_canvas_requested.emit(item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_canvas(item_id))

        elif item_type == "section":
            on = bool(self.doc.sections[item_id].get("active"))
            add("🚫 Turn off" if on else "👁️ Turn on", lambda: self.doc.set_section_active(item_id, not on))
            add("✂️ Change the cut…", lambda: self.edit_section_requested.emit(item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_section(item_id))

        elif item_type == "sketch":
            add("⬆️ Extrude\tE", lambda: self.extrude_sketch_requested.emit(item_id))
            add("📐 Offset Plane", self.offset_plane_requested.emit)
            add("✏️ Edit Sketch", lambda: self.edit_sketch_requested.emit(item_id))
            sk = self.doc.sketches.get(item_id)
            if sk is not None:
                from omacad.model.sketch import SketchText
                first_txt = next((e for e in sk.entities if isinstance(e, SketchText)), None)
                if first_txt is not None:
                    add("🔤 Edit Text…", lambda eid=first_txt.entity_id: self.edit_sketch_text_requested.emit(item_id, eid))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            find("sketch")
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.delete_sketch_requested.emit(item_id))

        elif item_type == "sketch_text":
            s_id, ent_id = item_id.split(":", 1)
            add("🔤 Edit Text…", lambda: self.edit_sketch_text_requested.emit(s_id, ent_id))
            add("✏️ Edit Sketch", lambda: self.edit_sketch_requested.emit(s_id))

        elif item_type in ("origin", "axis", "group"):
            show_hide()

        elif item_type == "view":
            add("🎥 Apply this view", lambda: self.named_view_requested.emit(item_id))

        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(pos))
