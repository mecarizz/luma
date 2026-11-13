# PyInstaller build configuration for the Luma desktop application.
from pathlib import Path

project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / "ui_main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "release_defaults" / "products.json"), "."),
        (str(project_root / "release_defaults" / "outsourced_products.txt"), "."),
    ],
    hiddenimports=[
        "trendyol_labels",
        "trendyol_watcher",
        "reportlab.graphics.barcode.code128",
        "reportlab.graphics.barcode.code93",
        "reportlab.pdfbase.ttfonts",
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
    name="Luma",
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
