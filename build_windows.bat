@echo off
echo ==============================================
echo  Bygger Omacad fristående Windows-app (.exe)
echo ==============================================

python -m pip install --upgrade pip
pip install PySide6 numpy manifold3d trimesh PyOpenGL Pillow shapely pyinstaller

pyinstaller omacad.spec

echo.
echo ==============================================
echo  Klart! Applikationen finns i: dist\Omacad\Omacad.exe
echo ==============================================
pause
