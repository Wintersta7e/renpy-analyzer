# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Find customtkinter package path
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['launcher.py'],
    pathex=[os.path.join('.', 'src')],
    binaries=[],
    datas=[
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'renpy_analyzer',
        'renpy_analyzer.app',
        'renpy_analyzer.parser',
        'renpy_analyzer.project',
        'renpy_analyzer.models',
        'renpy_analyzer.checks',
        'renpy_analyzer.checks.labels',
        'renpy_analyzer.checks.variables',
        'renpy_analyzer.checks.logic',
        'renpy_analyzer.checks.menus',
        'renpy_analyzer.checks.assets',
        'renpy_analyzer.checks.characters',
        'renpy_analyzer.report',
        'renpy_analyzer.report.pdf',
        'PIL',
        'fitz',
        'pymupdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RenpyAnalyzer',
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
