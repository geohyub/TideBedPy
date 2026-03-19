"""
TideBedPy - 조석보정 Python CLI

KHOA TideBedLite의 Python 재구현.
해양 수로측량 Nav 데이터에 대해 Co-tidal 격자와 IDW 가중평균으로
조석보정값(Tc)을 산출한다.

Original: TideBedLite v1.05, Copyright (c) 2014, KHOA / GeoSR Inc.
Python:   Junhyub, 2025

사용법:
  python main.py --nav Navi/After --tide 실측조위 -o result.tid
  python main.py --ini setting/TideBedLite.ini -o result.tid
  python main.py --nav Navi/After --tide 실측조위 -o result.tid --validate ref.tid
"""

import sys
import os
import time
import argparse
import logging

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TideBedConfig
from data_io.station import load_stations
from data_io.tide_series import load_tide_folder, adjust_tide_year
from data_io.navigation import load_nav_directory
from data_io.cotidal import CoTidalGrid
from core.tide_correction import TideCorrectionEngine
from output.tid_writer import write_tid, write_detail, write_error
from output.report import validate_output, print_validation_report


def setup_logging(verbose: int = 0):
    """로깅 설정"""
    if verbose >= 2:
        level = logging.DEBUG
    elif verbose >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )


def create_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서 생성"""
    parser = argparse.ArgumentParser(
        description='TideBedPy - 조석보정 프로그램 (KHOA TideBedLite Python 재구현)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 최소 인자 (DB/기준항정보는 자동 탐색)
  python main.py --nav Navi/After --tide 실측조위 -o result.tid

  # INI 파일로 실행
  python main.py --ini setting/TideBedLite.ini -o result.tid

  # 모든 경로 직접 지정
  python main.py --nav Navi/After --tide 실측조위 --db 표준개정수DB \\
                 --stations 기준항정보.txt -o result.tid

  # 검증 모드
  python main.py --ini setting/TideBedLite.ini -o result.tid --validate ref.tid
        """
    )

    parser.add_argument('--ini', help='TideBedLite.ini 설정 파일 경로')
    parser.add_argument('--nav', help='항적 데이터 디렉토리')
    parser.add_argument('--tide', help='조위 시계열 폴더')
    parser.add_argument('--db', help='표준개정수DB 루트 디렉토리 (미지정 시 자동 탐색)')
    parser.add_argument('--stations', help='기준항정보.txt 경로 (미지정 시 자동 탐색)')
    parser.add_argument('-o', '--output', help='출력 .tid 파일 경로', required=True)
    parser.add_argument('--type', choices=['실측', '예측'], default=None,
                        help='조위 시계열 유형 (실측/예측)')
    parser.add_argument('--rank-limit', type=int, default=None,
                        help='최대 사용 기준항 수 (1-10, 기본 10)')
    parser.add_argument('--time-interval', type=int, default=None,
                        help='출력 시간 간격 (초, 0=모든 포인트)')
    parser.add_argument('--detail', action='store_true', default=None,
                        help='상세 출력 (.tid.detail) 생성')
    parser.add_argument('--no-detail', action='store_false', dest='detail',
                        help='상세 출력 비생성')
    parser.add_argument('--kst', action='store_true',
                        help='Nav 시간을 KST로 처리 (기본: GMT)')
    parser.add_argument('--validate', help='검증용 참조 .tid 파일 경로')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='상세 출력 (-v: INFO, -vv: DEBUG)')

    return parser


def progress_callback(current: int, total: int):
    """진행률 표시"""
    pct = current / total * 100
    bar_len = 40
    filled = int(bar_len * current / total)
    bar = '#' * filled + '-' * (bar_len - filled)
    print(f'\r  Processing: [{bar}] {pct:5.1f}% ({current}/{total})', end='', flush=True)


def main():
    parser = create_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger('tidebedpy')

    start_time = time.time()
    print("\n  TideBedPy - Tidal Correction Program  v2.2.0")
    print("  Original: TideBedLite v1.05 (c) 2014 KHOA / GeoSR")
    print("  Python:   Junhyub, 2025")
    print("  " + "=" * 50)

    # -- 1. 설정 로드 --
    print("  [1/7] Loading configuration...", end=' ')
    if args.ini and os.path.isfile(args.ini):
        config = TideBedConfig.from_ini(args.ini)
    else:
        config = TideBedConfig()

    config.merge_args(args)

    # 자동 경로 탐색 (DB, 기준항정보)
    discovered = config.auto_discover()
    if discovered:
        print("OK (auto-discovered)")
        for msg in discovered:
            print(msg)
    else:
        # 검증
        errors = config.validate()
        if errors:
            print("FAILED!")
            for err in errors:
                print(f"    [X] {err}")
            sys.exit(1)
        print("OK")

    # 자동 탐색 후 재검증
    errors = config.validate()
    if errors:
        print("  Config validation FAILED!")
        for err in errors:
            print(f"    [X] {err}")
        sys.exit(1)

    # 설정 요약 출력
    print(f"  {'':>4}Nav:      {config.nav_directory}")
    print(f"  {'':>4}Tide:     {config.tts_folder}")
    print(f"  {'':>4}DB:       {config.db_root}")
    print(f"  {'':>4}Stations: {config.ref_st_info_path}")
    print(f"  {'':>4}Output:   {config.output_path}")
    print(f"  {'':>4}Options:  type={config.tide_series_type}, "
          f"rank={config.rank_limit}, "
          f"interval={config.time_interval_sec}s, "
          f"tz={'KST' if config.is_kst else 'GMT'}")

    # -- 2. 기준항 정보 로드 --
    print("  [2/7] Loading station info...", end=' ')
    stations = load_stations(config.ref_st_info_path)
    if not stations:
        print("FAILED! (no stations)")
        sys.exit(1)
    print(f"{len(stations)} stations")

    # -- 3. 조위 시계열 로드 + Akima 보간 --
    print("  [3/7] Loading tide series + interpolation...", end=' ')
    series_type_label = config.tide_series_type
    if series_type_label == '예측':
        folder = config.tts_p_folder if config.tts_p_folder else config.tts_folder
        matched = load_tide_folder(folder, stations, 'PRED')
    else:
        matched = load_tide_folder(config.tts_folder, stations, 'OBS')

    if matched == 0:
        print("WARNING! (no matched stations)")
        logger.warning("No tide series matched to any station")
    else:
        print(f"{matched} matched")

    # -- 4. Co-tidal 격자 로드 --
    print("  [4/7] Loading Co-tidal grids...", end=' ')
    cotidal = CoTidalGrid(config.db_root)
    if not cotidal.load_catalog():
        print("FAILED!")
        sys.exit(1)
    opened = cotidal.open_netcdfs()
    print(f"{opened} NC files")

    # -- 5. Nav 데이터 로드 --
    print("  [5/7] Loading Nav data...", end=' ')
    nav_points = load_nav_directory(config.nav_directory)
    if not nav_points:
        print("FAILED! (no Nav points)")
        cotidal.close_netcdfs()
        sys.exit(1)
    print(f"{len(nav_points)} points")
    print(f"  {'':>4}Time range: {nav_points[0].t} ~ {nav_points[-1].t}")

    # -- 5.5 조위 시계열 연도 조정 --
    if nav_points:
        nav_year = nav_points[0].t.year
        adj_count = adjust_tide_year(stations, nav_year)
        if adj_count > 0:
            print(f"  [*] Tide year adjusted to {nav_year} ({adj_count} series)")

    # -- 6. 조석보정 처리 --
    print(f"  [6/7] Processing tide correction (RankLimit={config.rank_limit})...")
    engine = TideCorrectionEngine(config, stations, cotidal)
    processed, all_corrections = engine.process_all(
        nav_points, progress_callback=progress_callback
    )
    print()  # 진행률 바 줄바꿈

    # 에러 통계
    error_count = sum(1 for nav in processed if nav.tc <= -999.0)
    valid_count = len(processed) - error_count
    print(f"  {'':>4}Results: {valid_count} valid, {error_count} errors "
          f"(total {len(processed)} points)")

    # -- 7. 출력 --
    print("  [7/7] Writing output...", end=' ')
    write_tid(config.output_path, processed, config,
              db_version=cotidal.version or '1101')

    if config.write_detail:
        write_detail(config.output_path, processed, all_corrections)

    # 에러 포인트 수집
    error_points = []
    for nav in processed:
        if nav.tc <= -999.0:
            error_points.append({
                'lon': nav.x,
                'lat': nav.y,
                'time': nav.t.strftime('%Y/%m/%d %H:%M:%S'),
            })
    write_error(config.output_path, error_points)

    output_files = [config.output_path]
    if config.write_detail:
        output_files.append(config.output_path + '.detail')
    output_files.append(config.output_path + '.err')
    print("OK")

    # NetCDF 닫기
    cotidal.close_netcdfs()

    elapsed = time.time() - start_time
    print(f"\n  Elapsed: {elapsed:.1f}s")
    print(f"  Output files:")
    for fp in output_files:
        if os.path.isfile(fp):
            size_kb = os.path.getsize(fp) / 1024
            print(f"    {fp} ({size_kb:.1f} KB)")

    # -- 검증 --
    if config.validate_path and os.path.isfile(config.validate_path):
        result = validate_output(config.output_path, config.validate_path)
        print_validation_report(result)

    print()


if __name__ == '__main__':
    main()
