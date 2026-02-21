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
        # bridge_worker.py must be bundled as a readable .py file (not compiled)
        # because the SDK's Python needs to execute it as a standalone script.
        (os.path.join('src', 'renpy_analyzer', 'bridge_worker.py'), '.'),
    ],
    hiddenimports=[
        'renpy_analyzer',
        'renpy_analyzer.app',
        'renpy_analyzer.settings',
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
        'renpy_analyzer.checks.flow',
        'renpy_analyzer.checks.screens',
        'renpy_analyzer.checks.transforms',
        'renpy_analyzer.checks.translations',
        'renpy_analyzer.checks.texttags',
        'renpy_analyzer.checks.callreturn',
        'renpy_analyzer.checks.callcycle',
        'renpy_analyzer.checks.emptylabels',
        'renpy_analyzer.checks.persistent',
        'renpy_analyzer.checks._label_body',
        'renpy_analyzer.log',
        'renpy_analyzer.analyzer',
        'renpy_analyzer.sdk_bridge',
        'renpy_analyzer.report',
        'renpy_analyzer.report.pdf',
        'platformdirs',
        'PIL',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.pdfbase',
        'reportlab.pdfbase.pdfmetrics',
        'reportlab.lib',
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
