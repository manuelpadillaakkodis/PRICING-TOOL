# -*- mode: python ; coding: utf-8 -*-
#
# app.spec  --  Compila la "Herramienta de Ajuste de Coeficientes"
#                        en un unico .exe (onefile) con consola visible.
#
# USO  (desde DENTRO de la carpeta AJUSTE):
#     pyinstaller --noconfirm app.spec
#
# Resultado:  AJUSTE\dist\app.exe
# ---------------------------------------------------------------------------

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# --- 1) Detectar el paquete automaticamente --------------------------------
PKG_DIR  = os.path.abspath(SPECPATH)                 # carpeta de este .spec
PKG_NAME = os.path.basename(PKG_DIR.rstrip("\\/"))   # p.ej. "AJUSTE"
PARENT   = os.path.dirname(PKG_DIR)                  # carpeta que CONTIENE el paquete

print("=" * 60)
print(f"[app.spec] Paquete detectado : {PKG_NAME}")
print(f"[app.spec] Carpeta paquete   : {PKG_DIR}")
print("=" * 60)

if not os.path.exists(os.path.join(PKG_DIR, "app.py")):
    raise SystemExit(
        f"[app.spec] No encuentro app.py en {PKG_DIR}. "
        f"Pon este .spec DENTRO de la carpeta del paquete y lanza "
        f"'pyinstaller app.spec' desde ahi."
    )

for _p in (PARENT, PKG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --- 2) Lanzador: importa el paquete por su nombre -------------------------
# Evita el bootstrap de app.py (que en onefile rompe los imports relativos).
LAUNCHER = os.path.join(PARENT, f"_run_{PKG_NAME}.py")
with open(LAUNCHER, "w", encoding="utf-8") as _f:
    _f.write(
        "# Lanzador autogenerado por app.spec (no editar)\n"
        f"from {PKG_NAME}.app import main\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
print(f"[app.spec] Lanzador generado : {LAUNCHER}")

# --- 3) Imports ocultos -----------------------------------------------------
_mods = [
    'app', 'carga_datos', 'procesamiento_xml', 'optimizacion', 'metricas',
    'ajuste_manual', 'funciones_legacy', 'funcionespesado',
    'metodosrecuento', 'metodosrecuento_legacy',
]
hiddenimports = [PKG_NAME] + [f'{PKG_NAME}.{m}' for m in _mods]

# openpyxl se usa como string (engine='openpyxl') -> el analisis no lo ve.
hiddenimports += ['openpyxl', 'et_xmlfile']
hiddenimports += collect_submodules('openpyxl')

# scipy (lsq_linear, SLSQP, rankdata)
hiddenimports += collect_submodules('scipy.optimize')
hiddenimports += collect_submodules('scipy.linalg')
hiddenimports += collect_submodules('scipy.sparse')
hiddenimports += ['scipy', 'scipy.special', 'scipy.stats', 'numpy', 'pandas']

# GUI
hiddenimports += [
    'tkinter', 'tkinter.filedialog', 'tkinter.messagebox',
    'tkinter.ttk', 'tkinter.simpledialog',
]

# --- 4) Datos ---------------------------------------------------------------
datas = collect_data_files('openpyxl')

# --- 5) Build (ONEFILE + consola) ------------------------------------------
a = Analysis(
    [LAUNCHER],
    pathex=[PARENT, PKG_DIR],
    binaries=[],
    datas=datas,
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
    name='app',                    # -> dist\app.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                  # consola negra detras de la GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
