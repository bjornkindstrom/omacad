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
from PySide6.QtGui import QIcon, QAction, QBrush, QColor, QFont
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
    split_body_requested = Signal(str, str)
    insert_canvas_requested = Signal(str)
    shell_body_requested = Signal(str)
    move_body_requested = Signal(str)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.refresh_tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setIndentation(18)
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

        self.refresh_tree()

    def refresh_tree(self):
        """Rebuilds the tree nodes based on the Document model."""
        self.tree.blockSignals(True)  # rebuilding must not look like a rename
        try:
            self._rebuild_tree()
        finally:
            self.tree.blockSignals(False)

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

        # Root Document Node
        root = QTreeWidgetItem(self.tree, ["📁 " + self.doc.name])
        root.setExpanded(True)

        # Units Node
        units_item = QTreeWidgetItem(root, [f"📏 Units: {self.doc.units}"])
        units_item.setFlags(units_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        # Origin Node
        origin_item = QTreeWidgetItem(root, ["🌐 Origin"])
        origin_item.setExpanded(False)
        QTreeWidgetItem(origin_item, ["• Origin (0, 0, 0)"])
        QTreeWidgetItem(origin_item, ["• X Axis (Red)"])
        QTreeWidgetItem(origin_item, ["• Y Axis (Green)"])
        QTreeWidgetItem(origin_item, ["• Z Axis (Blue)"])
        xy_item = QTreeWidgetItem(origin_item, ["📄 XY Plane"])
        xy_item.setData(0, Qt.ItemDataRole.UserRole, ("plane", "XY"))
        xz_item = QTreeWidgetItem(origin_item, ["📄 XZ Plane"])
        xz_item.setData(0, Qt.ItemDataRole.UserRole, ("plane", "XZ"))
        yz_item = QTreeWidgetItem(origin_item, ["📄 YZ Plane"])
        yz_item.setData(0, Qt.ItemDataRole.UserRole, ("plane", "YZ"))

        for pid, c in self.doc.construction_planes.items():
            pi = QTreeWidgetItem(origin_item, ["📄 " + c["name"] + ("" if c.get("visible", True) else " (hidden)")])
            pi.setData(0, Qt.ItemDataRole.UserRole, ("cplane", pid))
        if self.doc.construction_planes:
            origin_item.setExpanded(True)

        # Bodies Group Node
        bodies_group = QTreeWidgetItem(root, [f"🧊 Bodies ({len(self.doc.bodies)})"])
        bodies_group.setExpanded(True)
        for b_id, body in self.doc.bodies.items():
            b_item = QTreeWidgetItem(bodies_group, [body.name, ""])
            b_item.setData(0, Qt.ItemDataRole.UserRole, ("body", b_id))
            b_item.setFlags(b_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(b_item, body.visible)
            if body.selected:
                b_item.setSelected(True)

        # Sketches Group Node
        sketches_group = QTreeWidgetItem(root, [f"✏️ Sketches ({len(self.doc.sketches)})"])
        sketches_group.setExpanded(True)
        for s_id, sketch in self.doc.sketches.items():
            s_item = QTreeWidgetItem(sketches_group, [sketch.name, ""])
            s_item.setData(0, Qt.ItemDataRole.UserRole, ("sketch", s_id))
            s_item.setFlags(s_item.flags() | Qt.ItemFlag.ItemIsEditable)
            if sketch == self.doc.active_sketch:  # shown in bold (the name itself stays editable text)
                font = QFont(s_item.font(0))
                font.setBold(True)
                s_item.setFont(0, font)
                s_item.setToolTip(0, "Active sketch")
            self._style_eye(s_item, sketch.visible)

        if self.doc.sections:
            sec_group = QTreeWidgetItem(root, [f"✂️ Section Views ({len(self.doc.sections)})"])
            sec_group.setExpanded(True)
            for sid, sec in self.doc.sections.items():
                it = QTreeWidgetItem(sec_group, [sec["name"], ""])
                it.setData(0, Qt.ItemDataRole.UserRole, ("section", sid))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                self._style_eye(it, bool(sec.get("active")))
                it.setToolTip(1, "Click to turn the section off" if sec.get("active") else "Click to turn the section on")

        if hasattr(self.doc, "canvases") and self.doc.canvases:
            canv_group = QTreeWidgetItem(root, [f"🖼️ Canvases ({len(self.doc.canvases)})"])
            canv_group.setExpanded(True)
            for cid, c in self.doc.canvases.items():
                it = QTreeWidgetItem(canv_group, [c["name"], ""])
                it.setData(0, Qt.ItemDataRole.UserRole, ("canvas", cid))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                self._style_eye(it, bool(c.get("visible", True)))
                it.setToolTip(1, "Click to hide canvas" if c.get("visible", True) else "Click to show canvas")

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

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        if column == 1 and item_type in ("body", "sketch", "section", "canvas"):
            if item_type == "canvas":
                self.doc.toggle_canvas_visibility(item_id)
            elif item_type == "section":
                self.doc.set_section_active(item_id, not self.doc.sections[item_id].get("active"))
            elif item_type == "body":
                self.doc.toggle_body_visibility(item_id)
            else:
                self.doc.toggle_sketch_visibility(item_id)
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

        if item_type == "plane":
            act = theme.action_with_icon(menu, f"✏️ Create Sketch on {item_id} Plane")
            act.triggered.connect(lambda: self.start_sketch_on_plane.emit(item_id))
            act_canv = theme.action_with_icon(menu, f"🖼️ Insert Canvas on {item_id} Plane…")
            act_canv.triggered.connect(lambda: self.insert_canvas_requested.emit(item_id))
            act_split = theme.action_with_icon(menu, f"🪚 Split Body with {item_id} Plane…")
            act_split.triggered.connect(lambda: self.split_body_requested.emit("", item_id))

        elif item_type == "cplane":
            act = theme.action_with_icon(menu, "✏️ Create Sketch on this Plane")
            act.triggered.connect(lambda: self.start_sketch_on_cplane.emit(item_id))
            act_canv = theme.action_with_icon(menu, "🖼️ Insert Canvas on this Plane…")
            act_canv.triggered.connect(lambda: self.insert_canvas_requested.emit(item_id))
            act_split = theme.action_with_icon(menu, "🪚 Split Body with this Plane…")
            act_split.triggered.connect(lambda: self.split_body_requested.emit("", item_id))
            act_vis = theme.action_with_icon(menu, "👁️ Show / Hide")
            act_vis.triggered.connect(lambda: self.doc.toggle_construction_plane(item_id))
            menu.addSeparator()
            act_del = theme.action_with_icon(menu, "🗑️ Delete Plane")
            act_del.triggered.connect(lambda: self.doc.delete_construction_plane(item_id))

        elif item_type == "body":
            act_rename = theme.action_with_icon(menu, "🏷️ Rename (F2)")
            act_rename.triggered.connect(lambda: self.tree.editItem(item, 0))

            act_shell = theme.action_with_icon(menu, "🐚 Shell Body…")
            act_shell.triggered.connect(lambda: self.shell_body_requested.emit(item_id))

            act_move = theme.action_with_icon(menu, "↔️ Move Body…")
            act_move.triggered.connect(lambda: self.move_body_requested.emit(item_id))

            act_split = theme.action_with_icon(menu, "🪚 Split Body…")
            act_split.triggered.connect(lambda: self.split_body_requested.emit(item_id, ""))

            act_vis = theme.action_with_icon(menu, "👁️ Toggle Visibility")
            act_vis.triggered.connect(lambda: self.doc.toggle_body_visibility(item_id))

            act_export = theme.action_with_icon(menu, "💾 Export as STL...")
            act_export.triggered.connect(lambda: self.export_body_stl.emit(item_id))

            act_export_step = theme.action_with_icon(menu, "💾 Export as STEP...")
            act_export_step.triggered.connect(lambda: self.export_body_step.emit(item_id))

            menu.addSeparator()
            act_del = theme.action_with_icon(menu, "🗑️ Delete Body")
            act_del.triggered.connect(lambda: self.doc.delete_body(item_id))

        elif item_type == "canvas":
            act_vis = theme.action_with_icon(menu, "👁️ Show / Hide")
            act_vis.triggered.connect(lambda: self.doc.toggle_canvas_visibility(item_id))
            menu.addSeparator()
            act_del = theme.action_with_icon(menu, "🗑️ Delete Canvas")
            act_del.triggered.connect(lambda: self.doc.delete_canvas(item_id))

        elif item_type == "section":
            on = bool(self.doc.sections[item_id].get("active"))
            act = theme.action_with_icon(menu, "🚫 Turn off" if on else "👁️ Turn on")
            act.triggered.connect(lambda: self.doc.set_section_active(item_id, not on))
            act_edit = theme.action_with_icon(menu, "✂️ Change the cut…")
            act_edit.triggered.connect(lambda: self.edit_section_requested.emit(item_id))
            act_rename = theme.action_with_icon(menu, "🏷️ Rename (F2)")
            act_rename.triggered.connect(lambda: self.tree.editItem(item, 0))
            menu.addSeparator()
            act_del = theme.action_with_icon(menu, "🗑️ Delete Section")
            act_del.triggered.connect(lambda: self.doc.delete_section(item_id))

        elif item_type == "sketch":
            act_edit = theme.action_with_icon(menu, "✏️ Edit Sketch")
            act_edit.triggered.connect(lambda: self.edit_sketch_requested.emit(item_id))

            act_rename = theme.action_with_icon(menu, "🏷️ Rename (F2)")
            act_rename.triggered.connect(lambda: self.tree.editItem(item, 0))

            act_vis = theme.action_with_icon(menu, "👁️ Toggle Visibility")
            act_vis.triggered.connect(lambda: self.doc.toggle_sketch_visibility(item_id))

        menu.exec(self.tree.viewport().mapToGlobal(pos))
