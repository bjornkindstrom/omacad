"""The sketch Text tool end to end: dialog options, click to place, Text On Path by clicking a circle, edit later, one
undo step, cancel removes the text."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane, SketchText
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    return w


def _texts(w):
    return [e for e in w.doc.active_sketch.entities if isinstance(e, SketchText)]


def test_text_button_exists_and_starts_the_tool(win):
    assert win.ribbon.btn_text.text().strip() == "Text"
    win.ribbon.btn_text.click()
    assert win.viewport.sketch_tool == "TEXT" and win._text_session is not None
    assert win.inspector.current_tool_dlg is win._text_session.dlg
    assert win.viewport.text_draft is not None                       # the ghost that follows the cursor
    win._text_session.dlg.reject()


def test_click_places_the_text_and_ok_is_one_undo_step(win):
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.edt_text.setPlainText("OMACAD")
    dlg.spn_height.setValue(8.0)
    win.viewport.text_place_requested.emit((12.0, 5.0), None)
    t = _texts(win)[0]
    assert t.text == "OMACAD" and t.anchor == (12.0, 5.0) and t.height == 8.0
    dlg.edt_text.setPlainText("OMA")                                  # still editable live before OK
    dlg.cmb_h.setCurrentIndex(1)
    assert t.text == "OMA" and t.h_align == "center"
    assert len(win.doc.active_sketch.profiles) >= 3                  # the letters are profiles already
    dlg.accept()
    assert win._text_session is None and win.inspector.current_tool_dlg is None
    assert len(_texts(win)) == 1
    win.doc.undo()                                                   # placing + editing was one step
    assert _texts(win) == []


def test_cancel_removes_a_placed_text(win):
    win.prompt_text()
    win.viewport.text_place_requested.emit((0.0, 0.0), None)
    assert len(_texts(win)) == 1
    win._text_session.dlg.reject()
    assert _texts(win) == [] and win._text_session is None


def test_text_on_path_picks_a_circle(win):
    sk = win.doc.active_sketch
    circle = sk.add_circle((0.0, 0.0), 25.0)
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.cmb_type.setCurrentIndex(1)                                  # Text On Path
    assert win.viewport.text_wants_path
    win.viewport.text_place_requested.emit(None, None)               # a click that hit no curve does nothing
    assert _texts(win) == []
    dlg.edt_text.setPlainText("AROUND THE CIRCLE")
    win.viewport.text_place_requested.emit(None, circle.entity_id)
    t = _texts(win)[0]
    assert t.path_id == circle.entity_id and t.polygons()
    dlg.cmb_place.setCurrentIndex(1)                                 # Below
    assert t.placement == "below"
    dlg.accept()
    assert _texts(win)[0].path_id == circle.entity_id


def test_edit_existing_text_and_cancel_restores_it(win):
    sk = win.doc.active_sketch
    t = sk.add_text("Hello", (3.0, 4.0), height=6.0)
    win.prompt_text_edit(t.entity_id)
    dlg = win._text_session.dlg
    assert dlg.edt_text.toPlainText() == "Hello" and dlg.spn_height.value() == 6.0
    dlg.edt_text.setPlainText("Changed")
    dlg.spn_height.setValue(12.0)
    assert _texts(win)[0].text == "Changed"
    dlg.reject()
    again = _texts(win)[0]
    assert again.text == "Hello" and again.height == 6.0              # back to what it was


def test_edit_then_ok_is_one_undo_step(win):
    sk = win.doc.active_sketch
    t = sk.add_text("Hello", (3.0, 4.0), height=6.0)
    win.prompt_text_edit(t.entity_id)
    win._text_session.dlg.edt_text.setPlainText("World")
    win._text_session.dlg.accept()
    assert _texts(win)[0].text == "World"
    win.doc.undo()
    assert _texts(win)[0].text == "Hello"


def test_leaving_the_tool_before_placing_cancels(win):
    win.prompt_text()
    win.viewport.set_sketch_tool("LINE")
    assert win._text_session is None


def test_right_click_menu_offers_edit_text():
    import inspect
    from omacad.ui.viewport.viewport import Viewport3D
    src = inspect.getsource(Viewport3D._show_element_menu)
    assert "edit_text" in src and "Edit Text" in src


def test_dialog_shows_the_rows_that_fit_the_type():
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs import TextDialog
    dlg = TextDialog()
    dlg.show()
    assert dlg.cmb_v.isVisible() and dlg.flip_box.isVisible() and not dlg.cmb_place.isVisible()
    assert dlg.layout_label(dlg.flip_box).isVisible()
    dlg.cmb_type.setCurrentIndex(1)
    assert not dlg.cmb_v.isVisible() and not dlg.flip_box.isVisible() and dlg.cmb_place.isVisible() and dlg.chk_fit.isVisible()
    assert not dlg.layout_label(dlg.flip_box).isVisible()               # no "Flip:" label left behind


def test_the_font_list_is_themed_not_black(win):
    from omacad.ui.dialogs.text_dlg import ThemedFontComboBox
    win.prompt_text()
    dlg = win._text_session.dlg                                      # docked in the side panel, as in the app
    assert isinstance(dlg.cmb_font, ThemedFontComboBox)
    dlg.cmb_font.showPopup()
    css = dlg.cmb_font.view().styleSheet()
    dlg.cmb_font.hidePopup()
    assert "background-color" in css and "#000000" not in css.lower() and "rgb(0, 0, 0)" not in css
    dlg.reject()


def test_the_font_list_follows_a_light_theme_and_a_dark_one():
    from PySide6.QtGui import QColor
    from omacad.ui import theme
    from omacad.ui.dialogs.text_dlg import ThemedFontComboBox

    def background() -> float:
        value = theme.themeify(ThemedFontComboBox.POPUP_CSS).split("background-color:")[1].split(";")[0].strip()
        return QColor(value).lightnessF()                              # themeify gives #rrggbb or rgb(r, g, b)

    try:
        theme.set_fixed_theme("catppuccin-latte")
        light = background()
        theme.set_fixed_theme("tokyo-night")
        dark = background()
    finally:
        theme.set_fixed_theme(None)
        theme._palette = theme.load_palette()
    assert light > 0.7 and dark < 0.35                                 # a light theme gives a light list, a dark one a dark list
