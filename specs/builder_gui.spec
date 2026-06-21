# -*- mode: python ; coding: utf-8 -*-
import os
import customtkinter
root = os.path.join(SPECPATH, '..')
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    [os.path.join(root, 'builder_gui.py')],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, 'dist/installer_gui.exe'), '.'),
        (os.path.join(root, 'src/*.py'), 'src'),
        (os.path.join(ctk_path, 'assets'), 'customtkinter/assets'),
    ],
    hiddenimports=[
        'src',
        'src.builder',
        'src.installer',
        'src.utils',
        'customtkinter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='builder_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
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
