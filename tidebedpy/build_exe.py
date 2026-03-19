"""
build_exe.py - PyInstaller EXE 빌드 스크립트

TideBedPy를 독립 실행형 EXE로 빌드한다.
번들 리소스: Pretendard 폰트, 아이콘, 설정

사용법:
  python build_exe.py          # GUI 모드 빌드
  python build_exe.py --cli    # CLI 모드 빌드
  python build_exe.py --both   # 둘 다 빌드

Original: TideBedLite v1.05 (c) 2014 KHOA / GeoSR
Python:   Junhyub, 2025
"""

import os
import sys
import subprocess
import shutil

# 프로젝트 디렉토리
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DIST_DIR = os.path.join(PROJECT_ROOT, 'dist')
BUILD_DIR = os.path.join(PROJECT_ROOT, 'build')

# 번들 리소스
FONTS_DIR = os.path.join(SCRIPT_DIR, 'fonts')


def check_pyinstaller():
    """PyInstaller 설치 확인."""
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} detected")
        return True
    except ImportError:
        print("  [!] PyInstaller not installed. Installing...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
        return True


def build_gui():
    """GUI 모드 EXE 빌드."""
    print("\n" + "=" * 60)
    print("  Building TideBedPy GUI  (EXE)")
    print("=" * 60)

    # 데이터 파일 목록
    datas = []

    # 폰트 번들
    if os.path.isdir(FONTS_DIR):
        datas.append(f'--add-data={FONTS_DIR}{os.pathsep}fonts')
        print(f"  [+] Bundling fonts: {FONTS_DIR}")

    # hidden imports
    hidden = [
        '--hidden-import=numpy',
        '--hidden-import=scipy',
        '--hidden-import=scipy.interpolate',
        '--hidden-import=netCDF4',
        '--hidden-import=geographiclib',
        '--hidden-import=geographiclib.geodesic',
        '--hidden-import=chardet',
        '--hidden-import=matplotlib',
        '--hidden-import=matplotlib.pyplot',
        '--hidden-import=matplotlib.backends.backend_agg',
        '--hidden-import=matplotlib.font_manager',
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.font',
    ]

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--onedir',
        '--windowed',
        '--name=TideBedPy',
        f'--distpath={DIST_DIR}',
        f'--workpath={BUILD_DIR}',
        '--clean',
        # Qt 바인딩 충돌 방지 (tkinter 사용이므로 Qt 불필요)
        '--exclude-module=PyQt5',
        '--exclude-module=PyQt6',
        '--exclude-module=PySide2',
        '--exclude-module=PySide6',
        # 불필요한 대형 패키지 제외 (빌드 크기 최적화)
        '--exclude-module=torch',
        '--exclude-module=torchvision',
        '--exclude-module=torchaudio',
        '--exclude-module=tensorflow',
        '--exclude-module=keras',
        '--exclude-module=cv2',
        '--exclude-module=opencv',
        '--exclude-module=pandas',
        '--exclude-module=pyarrow',
        '--exclude-module=IPython',
        '--exclude-module=jupyter',
        '--exclude-module=notebook',
        '--exclude-module=sqlalchemy',
        '--exclude-module=flask',
        '--exclude-module=django',
        '--exclude-module=sklearn',
        '--exclude-module=skimage',
        '--exclude-module=sympy',
        '--exclude-module=dask',
        '--exclude-module=bokeh',
        '--exclude-module=plotly',
        '--exclude-module=seaborn',
        '--exclude-module=h5py',
        '--exclude-module=zmq',
        '--exclude-module=tornado',
        '--exclude-module=jinja2',
        '--exclude-module=pygments',
        '--exclude-module=sphinx',
        '--exclude-module=pytest',
        '--exclude-module=win32com',
    ]

    cmd.extend(datas)
    cmd.extend(hidden)

    # collect-all for matplotlib (폰트 등)
    cmd.extend([
        '--collect-all=matplotlib',
        '--collect-submodules=scipy',
    ])

    # 메인 스크립트
    cmd.append(os.path.join(SCRIPT_DIR, 'gui.py'))

    print(f"\n  Command: {' '.join(cmd[:5])}...")
    print("  Building... (this may take a few minutes)")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        exe_path = os.path.join(DIST_DIR, 'TideBedPy', 'TideBedPy.exe')
        if os.path.isfile(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"\n  [OK] GUI EXE built: {exe_path}")
            print(f"       Size: {size_mb:.1f} MB")
        else:
            print(f"\n  [OK] Build completed. Check: {DIST_DIR}")
    else:
        print(f"\n  [FAILED] Build failed with code {result.returncode}")

    return result.returncode == 0


def build_cli():
    """CLI 모드 EXE 빌드."""
    print("\n" + "=" * 60)
    print("  Building TideBedPy CLI  (EXE)")
    print("=" * 60)

    datas = []
    if os.path.isdir(FONTS_DIR):
        datas.append(f'--add-data={FONTS_DIR}{os.pathsep}fonts')

    hidden = [
        '--hidden-import=numpy',
        '--hidden-import=scipy',
        '--hidden-import=scipy.interpolate',
        '--hidden-import=netCDF4',
        '--hidden-import=geographiclib',
        '--hidden-import=geographiclib.geodesic',
        '--hidden-import=chardet',
    ]

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--onedir',
        '--console',
        '--name=TideBedPy_CLI',
        f'--distpath={DIST_DIR}',
        f'--workpath={BUILD_DIR}',
        '--clean',
        # Qt 바인딩 충돌 방지 + 불필요 대형 패키지 제외
        '--exclude-module=PyQt5',
        '--exclude-module=PyQt6',
        '--exclude-module=PySide2',
        '--exclude-module=PySide6',
        '--exclude-module=torch',
        '--exclude-module=torchvision',
        '--exclude-module=torchaudio',
        '--exclude-module=tensorflow',
        '--exclude-module=keras',
        '--exclude-module=cv2',
        '--exclude-module=pandas',
        '--exclude-module=pyarrow',
        '--exclude-module=sklearn',
        '--exclude-module=dask',
        '--exclude-module=h5py',
        '--exclude-module=zmq',
        '--exclude-module=win32com',
    ]

    cmd.extend(datas)
    cmd.extend(hidden)
    cmd.extend([
        '--collect-submodules=scipy',
    ])

    cmd.append(os.path.join(SCRIPT_DIR, 'main.py'))

    print("  Building...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"\n  [OK] CLI EXE built in: {DIST_DIR}")
    else:
        print(f"\n  [FAILED] Build failed with code {result.returncode}")

    return result.returncode == 0


def copy_data_files():
    """필수 데이터 파일을 dist 폴더에 복사."""
    print("\n  Copying data files to dist...")

    gui_dist = os.path.join(DIST_DIR, 'TideBedPy')
    if not os.path.isdir(gui_dist):
        return

    # info 디렉토리 복사 (CoTidalDB + 기준항정보)
    info_src = os.path.join(PROJECT_ROOT, 'info')
    if os.path.isdir(info_src):
        info_dst = os.path.join(gui_dist, 'info')
        if not os.path.isdir(info_dst):
            shutil.copytree(info_src, info_dst)
            print(f"  [+] info/ -> {info_dst}")

    # setting 디렉토리 복사
    setting_src = os.path.join(PROJECT_ROOT, 'setting')
    if os.path.isdir(setting_src):
        setting_dst = os.path.join(gui_dist, 'setting')
        if not os.path.isdir(setting_dst):
            shutil.copytree(setting_src, setting_dst)
            print(f"  [+] setting/ -> {setting_dst}")

    # manual 디렉토리 복사
    manual_src = os.path.join(SCRIPT_DIR, 'manual')
    if os.path.isdir(manual_src):
        manual_dst = os.path.join(gui_dist, 'manual')
        if os.path.isdir(manual_dst):
            shutil.rmtree(manual_dst)
        shutil.copytree(manual_src, manual_dst)
        print(f"  [+] manual/ -> {manual_dst}")

    # README 생성
    readme_path = os.path.join(gui_dist, 'README.txt')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write("TideBedPy v2.3.0 - 조석보정 프로그램\n")
        f.write("=" * 50 + "\n\n")
        f.write("Original: TideBedLite v1.05 (c) 2014 KHOA / GeoSR Inc.\n")
        f.write("Python:   Junhyub, 2025\n\n")
        f.write("실행 방법:\n")
        f.write("  TideBedPy.exe    (GUI 모드)\n\n")
        f.write("필요 데이터:\n")
        f.write("  info/  - 표준개정수DB + 기준항정보\n")
        f.write("  setting/  - TideBedLite.ini 설정 파일 (선택)\n\n")
        f.write("조위 데이터 출처:\n")
        f.write("  KHOA 바다누리 해양정보서비스\n")
        f.write("  https://www.khoa.go.kr/oceangrid/gis/category/observe/observeSearch.do\n\n")
        f.write("항적 데이터:\n")
        f.write("  CARIS HIPS에서 Navigation Export (Before/After)\n")

    print(f"  [+] README.txt created")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='TideBedPy EXE Builder')
    parser.add_argument('--cli', action='store_true', help='CLI 모드만 빌드')
    parser.add_argument('--gui', action='store_true', help='GUI 모드만 빌드')
    parser.add_argument('--both', action='store_true', help='GUI + CLI 모두 빌드')
    args = parser.parse_args()

    print("\n  TideBedPy - EXE Builder")
    print("  " + "=" * 50)

    if not check_pyinstaller():
        sys.exit(1)

    # 기본: GUI 빌드
    build_gui_flag = True
    build_cli_flag = False

    if args.cli:
        build_gui_flag = False
        build_cli_flag = True
    elif args.both:
        build_gui_flag = True
        build_cli_flag = True
    elif args.gui:
        build_gui_flag = True
        build_cli_flag = False

    success = True

    if build_gui_flag:
        if not build_gui():
            success = False
        else:
            copy_data_files()

    if build_cli_flag:
        if not build_cli():
            success = False

    if success:
        print(f"\n  All builds completed!")
        print(f"  Output: {DIST_DIR}")
    else:
        print(f"\n  Some builds failed!")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
