# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ('assets', 'assets'),
]

hiddenimports = [
    'manifold3d',
    'trimesh',
    'OpenGL',
    'OpenGL.GL',
    'OpenGL.GL.shaders',
    'OpenGL.arrays.ctypesarrays',
    'shapely',
    'python_solvespace',
    'tomllib',
]

excludes = [
    'tkinter',
    'matplotlib',
    'scipy',
    'pandas',
    'unittest',
    'test',
    'distutils',
    'pydoc',
    'sqlite3',
    'email',
    'html',
    'http',
    'xmlrpc',
    'curses',
    'IPython',
    'jedi',
    'docutils',
    'setuptools',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Omacad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
