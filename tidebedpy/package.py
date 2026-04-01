"""
package.py - TideBedPy 독립 패키지 생성 스크립트

TideBedLite와 분리된 독립 실행 패키지를 생성한다.
DB, 기준항정보, 프로그램 소스를 모두 하나의 폴더로 복사한다.

사용법:
  python package.py [--output 출력경로]
"""

import os
import sys
import shutil
import argparse
from datetime import datetime


def create_package(output_dir: str = None):
    """독립 패키지를 생성한다."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(project_root),
            f'TideBedPy_v2.1.0_{datetime.now().strftime("%Y%m%d")}'
        )

    print(f"\n  TideBedPy 독립 패키지 생성")
    print(f"  {'='*50}")
    print(f"  소스: {project_root}")
    print(f"  출력: {output_dir}")
    print()

    # 출력 디렉토리 생성 (안전 검사 포함)
    if os.path.exists(output_dir):
        # 보호: 시스템/사용자 데이터 경로 삭제 방지
        real_path = os.path.realpath(output_dir)
        _forbidden = [
            os.path.expanduser("~"),
            os.path.dirname(project_root),  # 소스 부모
            project_root,                    # 소스 자체
        ]
        # 드라이브 루트 금지
        if os.path.splitdrive(real_path)[1] in ('/', '\\', ''):
            raise ValueError(f"드라이브 루트 삭제 금지: {real_path}")
        for forbidden in _forbidden:
            if os.path.realpath(forbidden) == real_path:
                raise ValueError(f"보호된 경로 삭제 금지: {real_path}")
        # 이름에 'TideBedPy' 포함 확인 (패키지 출력 폴더만 삭제)
        basename = os.path.basename(real_path)
        if 'TideBedPy' not in basename:
            raise ValueError(
                f"패키지 출력 폴더가 아닌 것 같습니다 (이름에 'TideBedPy' 미포함): {basename}"
            )
        print(f"  [!] 기존 폴더 삭제: {output_dir}")
        shutil.rmtree(output_dir)

    os.makedirs(output_dir)

    # 1. 프로그램 소스 복사
    print("  [1/5] 프로그램 소스 복사...")
    src_dir = os.path.join(output_dir, 'tidebedpy')
    source_tidebedpy = os.path.join(project_root, 'tidebedpy')

    # 핵심 파일만 복사 (pycache 제외)
    for root, dirs, files in os.walk(source_tidebedpy):
        # __pycache__ 제외
        dirs[:] = [d for d in dirs if d != '__pycache__' and d != 'presets']

        rel_path = os.path.relpath(root, source_tidebedpy)
        dst_root = os.path.join(src_dir, rel_path)
        os.makedirs(dst_root, exist_ok=True)

        for fname in files:
            if fname.endswith('.pyc') or fname.endswith('.pyo'):
                continue
            src_file = os.path.join(root, fname)
            dst_file = os.path.join(dst_root, fname)
            shutil.copy2(src_file, dst_file)

    file_count = sum(1 for _, _, files in os.walk(src_dir) for _ in files)
    print(f"    -> {file_count}개 파일 복사")

    # 2. info 디렉토리 구조 생성
    print("  [2/5] 데이터베이스 + 기준항정보 복사...")
    info_dir = os.path.join(output_dir, 'info')
    os.makedirs(info_dir)

    # CoTidalDB (표준개정수DB) 복사
    source_db = os.path.join(project_root, 'info', 'CoTidalDB')
    if os.path.isdir(source_db):
        dst_db = os.path.join(info_dir, 'CoTidalDB')
        shutil.copytree(source_db, dst_db)
        db_size = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, files in os.walk(dst_db) for f in files
        ) / (1024 * 1024)
        print(f"    -> CoTidalDB: {db_size:.1f} MB")
    else:
        # 대안: 표준개정수DB
        alt_db = os.path.join(project_root, 'info', '표준개정수DB')
        if os.path.isdir(alt_db):
            dst_db = os.path.join(info_dir, '표준개정수DB')
            shutil.copytree(alt_db, dst_db)
            print(f"    -> 표준개정수DB 복사 완료")

    # 기준항정보 복사
    source_station = os.path.join(project_root, 'info', '기준항정보')
    if os.path.isdir(source_station):
        dst_station = os.path.join(info_dir, '기준항정보')
        shutil.copytree(source_station, dst_station)
        print(f"    -> 기준항정보 폴더 복사 완료")

    # 3. setting 디렉토리 생성
    print("  [3/5] 설정 파일 복사...")
    source_setting = os.path.join(project_root, 'setting')
    if os.path.isdir(source_setting):
        dst_setting = os.path.join(output_dir, 'setting')
        shutil.copytree(source_setting, dst_setting)
        print(f"    -> setting 폴더 복사 완료")

    # 4. 실행 배치 파일 생성
    print("  [4/5] 실행 파일 생성...")

    # GUI 실행 배치
    gui_bat = os.path.join(output_dir, 'TideBedPy_GUI.bat')
    with open(gui_bat, 'w', encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write('chcp 65001 >nul 2>&1\n')
        f.write('set SCRIPT_DIR=%~dp0\n')
        f.write('cd /d "%SCRIPT_DIR%"\n')
        f.write('echo.\n')
        f.write('echo   TideBedPy - GUI 모드 시작\n')
        f.write('echo.\n')
        f.write('python tidebedpy\\gui.py\n')
        f.write('if errorlevel 1 (\n')
        f.write('    echo.\n')
        f.write('    echo   [오류] Python 또는 필요 패키지가 설치되지 않았습니다.\n')
        f.write('    echo   아래 명령으로 필요 패키지를 설치하세요:\n')
        f.write('    echo     pip install -r tidebedpy\\requirements.txt\n')
        f.write('    echo.\n')
        f.write('    pause\n')
        f.write(')\n')

    # CLI 실행 배치
    cli_bat = os.path.join(output_dir, 'TideBedPy_CLI.bat')
    with open(cli_bat, 'w', encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write('chcp 65001 >nul 2>&1\n')
        f.write('set SCRIPT_DIR=%~dp0\n')
        f.write('cd /d "%SCRIPT_DIR%"\n')
        f.write('echo.\n')
        f.write('echo   TideBedPy - CLI 모드\n')
        f.write('echo   사용법: python tidebedpy\\main.py --help\n')
        f.write('echo.\n')
        f.write('python tidebedpy\\main.py %*\n')
        f.write('pause\n')

    # 설치 스크립트
    install_bat = os.path.join(output_dir, 'install_dependencies.bat')
    with open(install_bat, 'w', encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write('chcp 65001 >nul 2>&1\n')
        f.write('echo.\n')
        f.write('echo   TideBedPy 의존성 패키지 설치\n')
        f.write('echo   ==============================\n')
        f.write('echo.\n')
        f.write('pip install -r tidebedpy\\requirements.txt\n')
        f.write('echo.\n')
        f.write('echo   설치 완료!\n')
        f.write('pause\n')

    print(f"    -> TideBedPy_GUI.bat")
    print(f"    -> TideBedPy_CLI.bat")
    print(f"    -> install_dependencies.bat")

    # 5. requirements.txt 생성
    print("  [5/5] requirements.txt 생성...")
    req_path = os.path.join(src_dir, 'requirements.txt')
    with open(req_path, 'w') as f:
        f.write("# TideBedPy 의존성 패키지\n")
        f.write("geographiclib>=2.0\n")
        f.write("netCDF4>=1.6.0\n")
        f.write("numpy>=1.24.0\n")
        f.write("scipy>=1.10.0\n")
        f.write("chardet>=5.0.0\n")
        f.write("matplotlib>=3.7.0\n")

    # 패키지 크기 계산
    total_size = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(output_dir) for f in files
    ) / (1024 * 1024)

    print(f"\n  {'='*50}")
    print(f"  패키지 생성 완료!")
    print(f"  경로: {output_dir}")
    print(f"  크기: {total_size:.1f} MB")
    print(f"  {'='*50}")
    print()

    return output_dir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TideBedPy 독립 패키지 생성')
    parser.add_argument('--output', '-o', help='출력 디렉토리 경로')
    args = parser.parse_args()
    create_package(args.output)
