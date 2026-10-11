"""A QDoubleSpinBox that accepts arithmetic such as 10-1 or 2x(3+5) (see omacad.model.expr)."""

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox

from omacad.model import expr


class ExprDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setKeyboardTracking(True)  # live preview once the formula is complete
        self._expr = None  # the formula behind the current value, when it is not a plain number

    def focusInEvent(self, event):
        names = sorted(expr.get_variables())
        base = "Type a value, a formula (10-1, 2x(3+5)) or a parameter name."
        self.setToolTip(base + (f"\nParameters: {', '.join(names)}" if names else "\nNo parameters defined yet (Modify > Change Parameters)."))
        super().focusInEvent(event)

    def expression(self):
        """The formula/parameter expression the user entered (None for a plain number)."""
        if self._expr is None:
            return None
        try:
            return self._expr if abs(expr.evaluate(self._expr) - self.value()) < 1e-9 else None
        except ValueError:
            return None

    def set_expression(self, text):
        """Shows `text` (e.g. 'width/2') as the field's content and sets the value it evaluates to."""
        try:
            value = expr.evaluate(text)
        except ValueError:
            return
        self._expr = None if expr.is_plain_number(text) else text.strip()
        self.setValue(value)
        self.lineEdit().setText(self.textFromValue(value) + self.suffix())

    def textFromValue(self, value):
        e = self.expression() if self._expr is not None else None
        return e if e is not None else super().textFromValue(value)

    def _core(self, text: str) -> str:
        for affix in (self.suffix(), self.prefix()):
            if affix:
                text = text.replace(affix, "")
        return text.strip()

    def valueFromText(self, text):
        core = self._core(text)
        try:
            value = expr.evaluate(core)
        except ValueError:
            return self.value()
        self._expr = None if expr.is_plain_number(core) else core
        return value

    def validate(self, text, pos):
        core = self._core(text)
        if core == "" or not expr.is_expression_text(core):
            state = QValidator.State.Intermediate if core == "" else QValidator.State.Invalid
            return state, text, pos
        try:
            v = expr.evaluate(core)
        except ValueError:
            return QValidator.State.Intermediate, text, pos  # still being typed
        if self.minimum() <= v <= self.maximum():
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos
