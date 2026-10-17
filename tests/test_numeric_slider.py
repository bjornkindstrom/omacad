"""Tool sliders preserve numeric entry, expressions, signals and field limits."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox

from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.numeric_slider import NumericSlider, add_numeric_sliders
from omacad.ui.main_window import MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("cls", [QDoubleSpinBox, QSpinBox, ExprDoubleSpinBox])
def test_bidirectional_slider_and_typed_values(app, cls):
    dialog = QDialog()
    form = QFormLayout(dialog)
    field = cls()
    field.setRange(-10000, 10000)
    field.setValue(5)
    form.addRow("Distance", field)
    changed = []
    field.valueChanged.connect(changed.append)
    add_numeric_sliders(dialog)
    wrapper = field.parentWidget()
    assert isinstance(wrapper, NumericSlider)
    wrapper.slider.setValue(1000)
    assert field.value() == 20
    assert changed[-1] == 20
    field.setValue(5000)
    assert field.value() == 5000
    wrapper.slider.setValue(0)
    assert field.value() == -10000
    field.setEnabled(False)
    assert not wrapper.slider.isEnabled()
    field.setEnabled(True)
    assert wrapper.slider.isEnabled()
    add_numeric_sliders(dialog)
    assert len(dialog.findChildren(NumericSlider)) == 1
    dialog.close()


def test_formula_survives_sync_and_slider_can_replace_it(app):
    dialog = QDialog()
    form = QFormLayout(dialog)
    field = ExprDoubleSpinBox()
    field.setRange(.1, 10000)
    field.set_expression("2*(20+5)")
    form.addRow(field)
    add_numeric_sliders(dialog)
    wrapper = field.parentWidget()
    assert field.expression() == "2*(20+5)"
    wrapper.sync()
    assert field.expression() == "2*(20+5)"
    wrapper.slider.setValue(1000)
    assert field.value() == 100
    assert field.expression() is None
    dialog.close()


def test_primitive_sliders_follow_fields_handles_and_disabled_controls(app):
    w = MainWindow()
    w.prompt_box()
    dialog = w.viewport.primitive_handles.dialog
    assert len(dialog.findChildren(NumericSlider)) == len(dialog.findChildren(QDoubleSpinBox))
    length = dialog.spn_length
    wrapper = length.parentWidget()
    wrapper.slider.setValue(1000)
    assert length.value() == 100
    length.setValue(25)
    assert wrapper.slider.value() == 249  # 0.1..100 range, field remains exact
    assert not dialog.spn_inner_round.parentWidget().slider.isEnabled()
    dialog.spn_wall.setValue(2)
    assert dialog.spn_inner_round.parentWidget().slider.isEnabled()
    dialog.reject()
    assert not w.doc.bodies
    w.close()


def test_existing_section_slider_is_not_duplicated(app):
    from omacad.ui.dialogs.section_dlg import SectionDialog
    from PySide6.QtWidgets import QSlider
    dialog = SectionDialog("XY", 100)
    add_numeric_sliders(dialog)
    assert len(dialog.findChildren(QSlider)) == 1
    dialog.close()


def test_primitive_slider_obeys_drag_precision(app):
    from omacad.ui.settings import get_settings
    w = MainWindow()
    w.prompt_cylinder()
    field = w.viewport.primitive_handles.dialog.spn_radius
    slider = field.parentWidget().slider
    slider.setValue(557)
    assert field.value() == round(field.value())
    get_settings().set("primitive_drag_decimals", 2)
    slider.setValue(558)
    assert field.value() != round(field.value())
    w.viewport.primitive_handles.dialog.reject()
    w.close()
