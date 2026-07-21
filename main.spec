# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# pandas carga openpyxl de forma perezosa (engine="openpyxl" en exportacion.py),
# así que PyInstaller NO lo detecta solo. Sin esto, la exportación a Excel
# falla en el .exe con "Missing optional dependency 'openpyxl'".
hiddenimports = collect_submodules('openpyxl')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],              # Si quieres distribuir un coeficients.csv por defecto:
                           #   datas=[('coeficients.csv', '.')]
    hiddenimports=hiddenimports,
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
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX puede corromper DLLs de pandas/tk y dispara antivirus.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # GUI sin ventana de consola. Pon True solo para depurar.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,             # Ruta a un .ico si quieres icono propio.
)
