"""
TideBedPy Desktop — PySide6 PyInstaller Build Script
=====================================================

Usage:
    python tidebedpy/build_desktop_exe.py           # onedir (default)
    python tidebedpy/build_desktop_exe.py --onefile  # single exe
    python tidebedpy/build_desktop_exe.py --zip      # build + zip package

Output:
    dist/TideBedPy_Desktop/TideBedPy_Desktop.exe    (onedir)
    dist/TideBedPy_Desktop.exe                      (onefile)
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent          # TideBedPy/
PKG = ROOT / "tidebedpy"                               # tidebedpy/
SHARED = ROOT.parent.parent / "_shared"                # E:/Software/_shared/
ENTRY = PKG / "desktop" / "main.py"                    # entry point

APP_NAME = "TideBedPy_Desktop"
APP_VERSION = "v3.0"

# ── Resource bundles (--add-data) ──────────────────────────────────

SEP = ";"  # Windows path separator for PyInstaller

DATAS = [
    # Pretendard fonts
    (str(PKG / "fonts"), f"tidebedpy{os.sep}fonts"),
    # geoview_pyside6 shared library
    (str(SHARED / "geoview_pyside6"), "geoview_pyside6"),
    # geoview_common shared library
    (str(SHARED / "geoview_common"), "geoview_common"),
]

# ── Hidden imports ─────────────────────────────────────────────────

HIDDEN_IMPORTS = [
    # PySide6
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",

    # pyqtgraph (viewer panel charts)
    "pyqtgraph",

    # Scientific
    "numpy",
    "scipy",
    "scipy.interpolate",
    "scipy.spatial",

    # Data formats
    "netCDF4",
    "geographiclib",
    "geographiclib.geodesic",
    "chardet",

    # matplotlib (output/graph.py, output/map_view.py — Agg backend)
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.dates",
    "matplotlib.font_manager",
    "matplotlib.ticker",
    "matplotlib.patches",
    "matplotlib.patheffects",
    "matplotlib.colors",
    "matplotlib.collections",
    "matplotlib.backends.backend_agg",

    # pkg_resources runtime hook dependencies
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",

    # Shared libraries
    "geoview_pyside6",
    "geoview_pyside6.app_base",
    "geoview_pyside6.constants",
    "geoview_pyside6.themes",
    "geoview_pyside6.widgets",
    "geoview_pyside6.widgets.data_table",
    "geoview_pyside6.widgets.kpi_card",
    "geoview_pyside6.widgets.status_badge",
    "geoview_common",
    "geoview_common.styles",
    "geoview_common.styles.colors",
    "geoview_common.styles.fonts",
    "geoview_common.styles.themes",

    # tidebedpy package
    "tidebedpy",
    "tidebedpy.core",
    "tidebedpy.core.error_codes",
    "tidebedpy.core.geodesy",
    "tidebedpy.core.interpolation",
    "tidebedpy.core.tide_correction",
    "tidebedpy.data_io",
    "tidebedpy.data_io.csv_to_tops",
    "tidebedpy.data_io.khoa_api",
    "tidebedpy.data_io.navigation",
    "tidebedpy.data_io.tide_series",
    "tidebedpy.data_io.global_tide",
    "tidebedpy.data_io.station",
    "tidebedpy.data_io.cotidal",
    "tidebedpy.output",
    "tidebedpy.output.tid_writer",
    "tidebedpy.output.format_writers",
    "tidebedpy.output.report",
    "tidebedpy.output.summary",
    "tidebedpy.output.graph",
    "tidebedpy.output.map_view",
    "tidebedpy.utils",
    "tidebedpy.utils.encoding",
    "tidebedpy.utils.font_utils",
    "tidebedpy.utils.time_utils",
    "tidebedpy.desktop",
    "tidebedpy.desktop.main",
    "tidebedpy.desktop.app_controller",
    "tidebedpy.desktop.panels",
    "tidebedpy.desktop.panels.correction_panel",
    "tidebedpy.desktop.panels.tools_panel",
    "tidebedpy.desktop.panels.compare_panel",
    "tidebedpy.desktop.panels.viewer_panel",
    "tidebedpy.desktop.widgets",
    "tidebedpy.desktop.widgets.toast",
    "tidebedpy.desktop.widgets.path_row",
    "tidebedpy.desktop.widgets.log_viewer",
    "tidebedpy.desktop.widgets.progress_bar",
    "tidebedpy.desktop.widgets.station_select_dialog",
    "tidebedpy.desktop.widgets.tide_chart",
    "tidebedpy.desktop.widgets.weight_chart",
    "tidebedpy.desktop.services",
    "tidebedpy.desktop.services.correction_worker",
]

# ── Excludes (size optimization) ───────────────────────────────────

EXCLUDES = [
    # Tkinter (not needed for PySide6 build)
    "tkinter", "_tkinter", "Tkinter",
    # Other Qt bindings
    "PyQt5", "PyQt6", "PySide2",
    # Heavy ML/AI
    "torch", "torchvision", "torchaudio",
    "tensorflow", "keras",
    "sklearn", "scikit-learn",
    # Web frameworks
    "flask", "django", "fastapi", "uvicorn", "starlette",
    "streamlit", "plotly",
    # Data science (pandas not used)
    "pandas",
    # Dev tools
    "IPython", "jupyter", "notebook", "jupyterlab",
    "pytest", "sphinx", "setuptools",
    # Image/video
    "cv2", "PIL", "Pillow",
    # Heavy unused transitive deps
    "llvmlite", "numba",
    "pyarrow", "pyarrow.lib",
    "Cython",
    "h5py",
    "lxml",
    "cryptography",
    "Pythonwin", "win32com", "win32api",
    "openpyxl",
]


def build(onefile: bool = False):
    """Run PyInstaller build."""
    print(f"\n{'='*60}")
    print(f"  TideBedPy Desktop - PyInstaller Build")
    print(f"  Version: {APP_VERSION}")
    print(f"  Mode:    {'onefile' if onefile else 'onedir'}")
    print(f"{'='*60}\n")

    # Verify entry point
    if not ENTRY.exists():
        print(f"[ERROR] Entry point not found: {ENTRY}")
        return False

    # Verify shared libraries
    for name in ("geoview_pyside6", "geoview_common"):
        p = SHARED / name
        if not p.exists():
            print(f"[ERROR] Shared library not found: {p}")
            return False

    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile" if onefile else "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
    ]

    # Path extensions (so PyInstaller can find modules)
    cmd += ["--paths", str(ROOT)]
    cmd += ["--paths", str(SHARED)]

    # Data files
    for src, dest in DATAS:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src}{SEP}{dest}"]
            print(f"  [DATA] {src} -> {dest}")
        else:
            print(f"  [WARN] Data path not found: {src}")

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]

    # Collect submodules
    cmd += ["--collect-submodules", "scipy"]
    cmd += ["--collect-all", "matplotlib"]

    # Excludes
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]

    # Spec/dist/build directories
    cmd += ["--specpath", str(ROOT)]
    cmd += ["--distpath", str(ROOT / "dist")]
    cmd += ["--workpath", str(ROOT / "build")]

    # Entry point
    cmd.append(str(ENTRY))

    print(f"\n  Running PyInstaller...\n")

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\n[ERROR] PyInstaller failed with code {result.returncode}")
        return False

    # Verify output
    if onefile:
        exe = ROOT / "dist" / f"{APP_NAME}.exe"
    else:
        exe = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"

    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\n[OK] Build successful!")
        print(f"     EXE: {exe}")
        print(f"     Size: {size_mb:.1f} MB")

        if not onefile:
            dist_dir = ROOT / "dist" / APP_NAME
            total = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file())
            print(f"     Total dist: {total / (1024*1024):.1f} MB")

        return True
    else:
        print(f"\n[ERROR] EXE not found at {exe}")
        return False


def create_readme():
    """Create README.txt in dist directory."""
    dist_dir = ROOT / "dist" / APP_NAME
    if not dist_dir.exists():
        return

    readme = dist_dir / "README.txt"
    readme.write_text(f"""\
TideBedPy Desktop {APP_VERSION}
{'='*40}

Tidal Correction Desktop Application
Copyright (c) 2025 GeoView Data QC Team

Built: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Usage
-----
  TideBedPy_Desktop.exe

Features
--------
  - KHOA API tidal data collection
  - Co-tidal chart IDW interpolation
  - Multi-station weighted correction
  - Batch Nav file processing
  - Interactive tide/weight visualization
  - Result comparison & verification

System Requirements
-------------------
  - Windows 10/11 (64-bit)
  - No additional installation required

Notes
-----
  - Settings are saved in user AppData
  - API key can be configured in the app
""", encoding="utf-8")
    print(f"[OK] README.txt created")


def create_zip():
    """Create distribution zip."""
    dist_dir = ROOT / "dist" / APP_NAME
    if not dist_dir.exists():
        print("[ERROR] dist directory not found. Run build first.")
        return False

    zip_name = f"{APP_NAME}_{APP_VERSION}_win64.zip"
    zip_path = ROOT / "dist" / zip_name

    print(f"\n  Creating {zip_name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in dist_dir.rglob("*"):
            if file.is_file():
                arcname = f"{APP_NAME}/{file.relative_to(dist_dir)}"
                zf.write(file, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[OK] ZIP created: {zip_path}")
    print(f"     Size: {size_mb:.1f} MB")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TideBedPy Desktop Build")
    parser.add_argument("--onefile", action="store_true", help="Single EXE mode")
    parser.add_argument("--zip", action="store_true", help="Create zip after build")
    parser.add_argument("--zip-only", action="store_true", help="Create zip without rebuilding")
    args = parser.parse_args()

    if args.zip_only:
        create_readme()
        create_zip()
        return

    success = build(onefile=args.onefile)
    if not success:
        sys.exit(1)

    if not args.onefile:
        create_readme()

    if args.zip:
        create_zip()

    print(f"\n{'='*60}")
    print(f"  Build complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
