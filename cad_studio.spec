# -*- mode: python ; coding: utf-8 -*-
"""
Spécification PyInstaller pour CAD Studio (radiant-darwin).
Compile un exécutable autonome (.exe) distribuable sans installation de Python.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collecte des fichiers de données et sous-modules
datas = [
    ('docs', 'docs'),
    ('src', 'src'),
]

hidden_imports = [
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'OpenGL',
    'OpenGL.GL',
    'OpenGL.GLU',
    'manifold3d',
    'trimesh',
    'scipy',
    'numpy',
    'networkx',
    'src.io',
    'src.catalog',
    'src.system',
    'src.viewport',
    'src.core',
    'src.cam',
    'src.fea',
    'src.sheetmetal',
    'src.drawing',
    'src.ai',
]

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'IPython', 'jupyter', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CADStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CADStudio',
)
