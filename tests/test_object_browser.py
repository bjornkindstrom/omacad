"""Real in-tree editors and responsive browser layout."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QInputDialog
from PySide6.QtTest import QTest
from omacad.model.document import Document
from omacad.ui.browser import BrowserTree


@pytest.fixture
def browser():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    widget = BrowserTree(doc)
    widget.resize(500, 700)
    widget.show()
    widget.tree.expandAll()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def row(browser, key):
    return next(item for item, _ in browser._walk()
                if item.data(0, Qt.ItemDataRole.UserRole) == ('parameter', (browser.doc.timeline.features[0].feature_id, key)))


def test_value_edited_inside_tree_enter_commits_and_escape_cancels(browser, monkeypatch):
    def no_dialog(*args, **kwargs):
        pytest.fail('Numeric editing opened a modal dialog')
    monkeypatch.setattr(QInputDialog, 'getText', no_dialog)
    item = row(browser, 'height')
    browser.tree.scrollToItem(item)
    QApplication.processEvents()
    QTest.mouseClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=browser.tree.visualItemRect(item).center())
    QTest.mouseDClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=browser.tree.visualItemRect(item).center())
    editor = browser.tree.findChild(QLineEdit)
    assert editor is not None and editor.isVisible()
    editor.setText('2*8')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(20)
    assert browser.doc.timeline.features[0].height == 16
    assert browser.doc.timeline.features[0].exprs['height'] == '2*8'
    browser.on_item_double_clicked(row(browser, 'height'), 0)
    editor = next(e for e in browser.tree.findChildren(QLineEdit) if e.isVisible())
    editor.setText('99')
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.qWait(20)
    assert browser.doc.timeline.features[0].height == 16
    browser.doc.undo()
    assert browser.doc.timeline.features[0].height == 10


def test_invalid_expression_is_reported_in_browser_without_changing_model(browser):
    browser.tree.itemDelegate().apply_value('parameter',
        (browser.doc.timeline.features[0].feature_id, 'height'), 'missing_parameter')
    assert browser.doc.timeline.features[0].height == 10
    assert browser.parameter_error is not None
    assert 'missing_parameter' in row(browser, 'height').text(0)


def test_width_grows_with_expanded_text_and_respects_small_window(browser):
    width = browser.preferred_width(1600)
    item = row(browser, 'height')
    item.setText(0, 'Height: wall_thickness * 12 + base_height + top_clearance')
    larger = browser.preferred_width(1600)
    assert larger > width
    assert larger <= 1600 * .48
    assert browser.preferred_width(500) <= 280


def test_live_preview_does_not_modify_document_or_undo_stack(browser):
    delegate = browser.tree.itemDelegate()
    original = browser.doc.snapshot()
    undo_count = len(browser.doc.undo_stack)
    seen = []
    browser.preview_changed.connect(seen.append)
    delegate.preview_value = ('parameter', (browser.doc.timeline.features[0].feature_id, 'height'), '2 cm')
    delegate.update_preview()
    assert seen[-1] is not None
    assert next(iter(seen[-1].values())).volume() == pytest.approx(2000)
    assert browser.doc.snapshot() == original
    assert len(browser.doc.undo_stack) == undo_count
    delegate.clear_preview()
    assert seen[-1] is None


def test_value_editor_is_tall_enough_to_show_what_is_typed(browser):
    """Björn: the editor sat inside the stylesheet's item padding (17 px) and cut the text off."""
    item = row(browser, 'height')
    browser.on_item_double_clicked(item, 0)
    QApplication.processEvents()
    editor = next(e for e in browser.tree.findChildren(QLineEdit) if e.isVisible())
    assert editor.height() >= editor.sizeHint().height()
    assert editor.height() >= browser.tree.visualItemRect(item).height()
    QTest.keyClick(editor, Qt.Key.Key_Escape)


def test_jar_tool_objects_hang_under_their_combine_in_the_tree():
    from omacad.model.jar import JarSpec
    doc = Document()
    doc.add_jar(JarSpec())
    widget = BrowserTree(doc)
    objects = next(item for item, _ in widget._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ('group', 'objects'))
    trunk = [objects.child(i).text(0) for i in range(objects.childCount())]
    assert trunk == ['Jar', 'Lid']
    neck = next(item for item, _ in widget._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ('object', 'object_cylinder_2'))
    assert neck.parent().data(0, Qt.ItemDataRole.UserRole) == ('feature', 'combine_3')
    widget.deleteLater()
