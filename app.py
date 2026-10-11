#!/usr/bin/env python3
"""
Omacad - Native CAD for Omarchy
Entrypoint script.
"""

import sys
import os

# Ensure current directory is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat, QIcon
from PySide6.QtCore import Qt

from omacad.ui.main_window import MainWindow


def main():
    # Set default OpenGL surface format with 4x MSAA anti-aliasing
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    from omacad import applog
    applog.install()   # what the app prints and any error end up in problem reports

    # Initialize Qt Application
    app = QApplication(sys.argv)
    from omacad.ui.theme import BigIconStyle
    app.setStyle(BigIconStyle("Fusion"))  # larger menu/tree/tool icons
    app.setApplicationName("Omacad")
    app.setOrganizationName("Omarchy")
    app.setDesktopFileName("omacad")

    # Create & Show Main Window
    window = MainWindow()
    
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
