"""
Omacad - Change Parameters
A table of named values. Any number field (dimensions, extrude distance, box sizes ...) accepts a
parameter name or a formula using them, e.g. width/2 + 3. Change a parameter here and everything
that uses it is rebuilt.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from omacad.model.document import Document, Parameter

COL_NAME, COL_EXPR, COL_VALUE, COL_COMMENT = range(4)


class ParametersDialog(QDialog):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("Change Parameters")
        self.resize(620, 420)
        lay = QVBoxLayout(self)

        hint = QLabel("Name a value, then type its name (or a formula such as width/2 + 3) in any number field. "
                      "Change it here and the drawing and all steps follow.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Expression", "Value", "Comment"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_EXPR, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_COMMENT, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(COL_NAME, 150)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay.addWidget(self.table, 1)

        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        lay.addWidget(self.lbl_problem)

        row = QHBoxLayout()
        btn_add = QPushButton("＋ Add parameter")
        btn_add.setAutoDefault(False)
        btn_add.clicked.connect(self.add_row)
        btn_del = QPushButton("🗑 Remove")
        btn_del.setAutoDefault(False)
        btn_del.clicked.connect(self.remove_selected)
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.apply_and_close)
        row.addWidget(btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

        for q in doc.parameters:
            self._append(q.name, q.expr, q.comment)
        self.table.cellChanged.connect(self.recalculate)
        self.recalculate()

    # ---- rows ------------------------------------------------------------------------
    def _append(self, name: str, expr: str, comment: str = ""):
        self.table.blockSignals(True)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, COL_NAME, QTableWidgetItem(name))
        self.table.setItem(r, COL_EXPR, QTableWidgetItem(expr))
        val = QTableWidgetItem("")
        val.setFlags(val.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, COL_VALUE, val)
        self.table.setItem(r, COL_COMMENT, QTableWidgetItem(comment))
        self.table.blockSignals(False)

    def add_row(self):
        existing = {self.table.item(r, COL_NAME).text() for r in range(self.table.rowCount())}
        n = 1
        while f"param{n}" in existing:
            n += 1
        self._append(f"param{n}", "10")
        self.recalculate()
        self.table.setCurrentCell(self.table.rowCount() - 1, COL_NAME)
        self.table.editItem(self.table.item(self.table.rowCount() - 1, COL_NAME))

    def remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
        self.recalculate()

    def collect(self):
        return [Parameter(self.table.item(r, COL_NAME).text().strip(), self.table.item(r, COL_EXPR).text().strip(),
                          self.table.item(r, COL_COMMENT).text())
                for r in range(self.table.rowCount())]

    # ---- live evaluation ---------------------------------------------------------------
    def recalculate(self, *_):
        params = self.collect()
        values, errors = self.doc.evaluate_parameters(params)
        problems = self.doc.validate_parameters(params)
        bad_names = {q.name for q in params if q.name and not self._name_ok(q.name, params)}
        self.table.blockSignals(True)
        for r, q in enumerate(params):
            item = self.table.item(r, COL_VALUE)
            if q.name in values:
                item.setText(f"{values[q.name]:.6g}")
                item.setForeground(QBrush())
            else:
                item.setText(errors.get(q.name, "?"))
                item.setForeground(QBrush(QColor(220, 90, 70)))
            name_item = self.table.item(r, COL_NAME)
            name_item.setForeground(QBrush(QColor(220, 90, 70)) if q.name in bad_names else QBrush())
        self.table.blockSignals(False)
        self.lbl_problem.setText("\n".join(problems[:3]))
        self.lbl_problem.setStyleSheet("color: rgb(220, 90, 70);")
        self.btn_ok.setEnabled(not problems)

    def _name_ok(self, name, params) -> bool:
        from omacad.model import expr
        return expr.is_valid_name(name) and sum(1 for q in params if q.name == name) == 1

    def apply_and_close(self):
        problems = self.doc.set_parameters(self.collect())
        if problems:
            QMessageBox.warning(self, "Parameters", "\n".join(problems))
            return
        self.accept()
