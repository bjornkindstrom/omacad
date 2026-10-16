"""Test that SettingsDialog content is scrollable and stays accessible on smaller displays (e.g. Windows laptops)."""

from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
from omacad.ui.settings_dialog import SettingsDialog


def test_settings_dialog_fits_and_scrolls_on_small_screens():
    QApplication.instance() or QApplication([])
    dlg = SettingsDialog()
    # Check that tabs are embedded in QScrollArea
    assert isinstance(dlg.tabs.widget(0), QScrollArea)
    assert isinstance(dlg.tabs.widget(2), QScrollArea)

    # Simulate opening on a display with constrained vertical height (e.g. 500px)
    dlg.resize(550, 480)
    dlg.show()

    assert dlg.height() <= 480

    # Ensure Save and Cancel buttons are within dialog bounds and visible
    save_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Save")
    cancel_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel")

    assert save_btn.isVisible()
    assert cancel_btn.isVisible()

    save_y = save_btn.mapTo(dlg, save_btn.rect().topLeft()).y()
    assert 0 < save_y < dlg.height()
    dlg.close()
