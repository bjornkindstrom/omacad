"""File handling mixin for MainWindow: "unsaved changes?" questions and the Open Recent list.

A document counts as changed when its saved form differs from the form it had when it was opened or last saved
(`_clean_state`), so view-only things like selection or camera never trigger the question.
"""

import json
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from omacad.io.exporter import Exporter
from omacad.model.document import Document

RECENT_LIMIT = 10


class FileSessionMixin:

    # ---- unsaved changes ----------------------------------------------------

    @staticmethod
    def _state_of(doc: Document) -> str:
        return json.dumps(Exporter.document_to_dict(doc), sort_keys=True, default=str)

    def mark_clean(self, baseline: str = None) -> None:
        """The current document is what is on disk (or `baseline` says what the clean state looks like)."""
        self._clean_state = baseline if baseline is not None else self._state_of(self.doc)

    def is_dirty(self) -> bool:
        clean = getattr(self, "_clean_state", None)
        if clean is None:                   # nothing opened or saved yet: clean means an empty design
            clean = self._state_of(Document())
        return self._state_of(self.doc) != clean

    def _ask_save_changes(self, name: str) -> str:
        """'save', 'discard' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Do you want to save the changes to {name}?")
        box.setInformativeText("If you don't save, your changes will be lost.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard else "cancel"

    def confirm_discard_changes(self) -> bool:
        """True when it is fine to replace the current document: nothing changed, saved now, or discarded on purpose."""
        if not self.is_dirty():
            return True
        name = Path(self.current_path).name if self.current_path else (self.doc.name or "Untitled")
        answer = self._ask_save_changes(name)
        if answer == "cancel":
            return False
        if answer == "save":
            self.on_file_save()
            return not self.is_dirty()      # a cancelled Save As or a failed write keeps everything as it was
        return True

    def closeEvent(self, event):
        if self.confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    # ---- recent files -------------------------------------------------------

    def recent_files(self) -> list:
        from omacad.ui.settings import get_settings
        return [p for p in get_settings().get("recent_files", []) if isinstance(p, str)]

    def add_recent_file(self, path: str) -> None:
        from omacad.ui.settings import get_settings
        path = str(Path(path).resolve())
        files = [path] + [p for p in self.recent_files() if p != path]
        get_settings().set("recent_files", files[:RECENT_LIMIT])
        self.rebuild_recent_menu()

    def forget_recent_file(self, path: str) -> None:
        from omacad.ui.settings import get_settings
        get_settings().set("recent_files", [p for p in self.recent_files() if p != path])
        self.rebuild_recent_menu()

    def clear_recent_files(self) -> None:
        from omacad.ui.settings import get_settings
        get_settings().set("recent_files", [])
        self.rebuild_recent_menu()

    def rebuild_recent_menu(self) -> None:
        menu = getattr(self, "menu_recent", None)
        if menu is None:
            return
        menu.clear()
        files = self.recent_files()
        for path in files:
            act = menu.addAction(f"{Path(path).name}    ({Path(path).parent})")
            act.setToolTip(path)
            act.triggered.connect(lambda _=False, p=path: self.open_recent(p))
        if not files:
            menu.addAction("(no recent files)").setEnabled(False)
        menu.addSeparator()
        clear = menu.addAction("Clear Recent Files")
        clear.setEnabled(bool(files))
        clear.triggered.connect(self.clear_recent_files)

    def open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(self, "Open Recent", f"{path}\n\nThe file no longer exists and is removed from the list.")
            self.forget_recent_file(path)
            return
        self.open_path(path)
