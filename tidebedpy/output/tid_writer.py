"""
tid_writer.py - .tid / .tid.detail / .tid.err 파일 출력

원본 TideBedLite TOPS 호환 형식으로 출력한다.
참조: frmMain.cs Calib4File (output writing sections)
"""

import logging
from datetime import datetime
from typing import List

from utils.time_utils import format_tid_time
from data_io.navigation import NavPoint

logger = logging.getLogger(__name__)


def write_tid(output_path: str, nav_points: List[NavPoint],
              config, db_version: str = '1101') -> None:
    """
    .tid 파일 출력.

    참조: frmMain.cs (lines 5440-5518)

    헤더: TOPS 호환 형식 (25줄)
    데이터: YYYY/MM/DD HH:MM:SS  Tc_m  0.0

    Args:
        output_path: 출력 경로
        nav_points: 처리 완료된 NavPoint 리스트
        config: TideBedConfig
        db_version: DB 버전 (기본 1101)
    """
    if not nav_points:
        logger.warning("출력할 Nav 포인트가 없습니다")
        return

    valid_points = [p for p in nav_points if p.tc > -999.0]
    if not valid_points:
        logger.warning("유효한 조석보정값이 없습니다")
        valid_points = nav_points

    start_time = nav_points[0].t
    end_time = nav_points[-1].t
    now = datetime.now()

    # 시간대 문자열 (UTC 오프셋 지원)
    utc_offset = getattr(config, 'utc_offset', 0.0)
    if config.is_kst or utc_offset == 9.0:
        tz_str = "KST ( 9.0)"
    elif utc_offset == 0.0:
        tz_str = "GMT ( 0.0)"
    else:
        # 유연한 UTC 오프셋
        sign = '+' if utc_offset >= 0 else ''
        tz_str = f"UTC{sign}{utc_offset:.1f} ({utc_offset:5.1f})"

    pg_version = "1.0.0"

    with open(output_path, 'w', encoding='utf-8') as f:
        # 헤더 (25줄)
        f.write(f"-------------------- TideBed DB Ver.{db_version}--PG Ver.{pg_version}-----------------\n")
        f.write("-------------------- TEMPORARY STATION ---------------------\n")
        f.write(f"------------------ Time Zone:  {tz_str} ------------------\n")
        f.write("                                                            \n")
        f.write("--------------------- Invariant Fields ---------------------\n")
        f.write("Name             Type Size    Units Value                   \n")
        f.write("------------------------------------------------------------\n")
        f.write("station_id       CHAR    5          Unknown                 \n")
        f.write("station_name     CHAR   16          Unknown                 \n")
        f.write("data_product     CHAR    3          Unknown                 \n")
        f.write(f"start_time       INTG    4  seconds {format_tid_time(start_time)}\n")
        f.write(f"end_time         INTG    4  seconds {format_tid_time(end_time)}\n")
        f.write(f"file_date        INTG    4  seconds {format_tid_time(now)}\n")
        f.write("max_water_level  REAL    4   metres    XXXX                 \n")
        f.write("min_water_level  REAL    4   metres    XXXX                 \n")
        f.write("------------------------------------------------------------\n")
        f.write("                                                            \n")
        f.write("---------------------- Variant Fields ----------------------\n")
        f.write("Name             Type Size    Units                         \n")
        f.write("---------------------- Variant Fields ----------------------\n")
        f.write("time             INTG    4  seconds                         \n")
        f.write("water_level      REAL    4   metres                         \n")
        f.write("std_dev          REAL    4   metres                         \n")
        f.write("------------------------------------------------------------\n")
        f.write("\n")

        # 데이터
        for nav in nav_points:
            tc_m = nav.tc / 100.0 if nav.tc > -999.0 else -9.99
            time_str = format_tid_time(nav.t)
            f.write(f"{time_str}  {tc_m:.2f}  0.0\n")

    logger.info(f".tid 출력 완료: {len(nav_points)}개 레코드 → {output_path}")


def write_detail(output_path: str, nav_points: List[NavPoint],
                 all_corrections: list) -> None:
    """
    .tid.detail 파일 출력.

    참조: frmMain.cs Calib4File (lines 5619-5661)

    형식 (탭 구분):
    Lon  Lat  Time  Tc(cm)  [StName  HRatio  TimeCorrector  orgHeight  EstimHeight  Weight] × N

    ⚠️ 상세 출력의 Weight는 유효 기준항 간 재정규화 (합=1.0).

    Args:
        output_path: .tid.detail 경로
        nav_points: 처리 완료된 NavPoint 리스트
        all_corrections: 각 포인트별 StationCorrection 리스트
    """
    detail_path = output_path + '.detail' if not output_path.endswith('.detail') else output_path

    with open(detail_path, 'w', encoding='utf-8') as f:
        for nav, corrections in zip(nav_points, all_corrections):
            # 기본 필드
            parts = [
                f"{nav.x:.7f}",
                f"{nav.y:.7f}",
                format_tid_time(nav.t),
                f"{nav.tc:.1f}" if nav.tc > -999.0 else "-999.0",
            ]

            # 유효 기준항 가중치 재정규화
            valid_corrs = [c for c in corrections if c.weight > 0 and c.estim_height > -999.0]
            sum_w = sum(c.weight for c in valid_corrs)

            for c in corrections:
                if c.weight > 0 and c.estim_height > -999.0:
                    # 재정규화된 가중치
                    norm_weight = c.weight / sum_w if sum_w > 0 else 0.0
                    parts.extend([
                        c.station_name,
                        f"{c.h_ratio:.4f}",
                        f"{c.time_corrector:.4f}",
                        f"{c.org_height:.1f}",
                        f"{c.estim_height:.1f}",
                        f"{norm_weight:.5f}",
                    ])

            # 64열까지 빈 문자열 패딩
            while len(parts) < 64:
                parts.append('')

            f.write('\t'.join(parts) + '\n')

    logger.info(f".tid.detail 출력 완료: {len(nav_points)}개 레코드 → {detail_path}")


def write_error(output_path: str, error_points: List[dict]) -> None:
    """
    .tid.err 파일 출력.

    Args:
        output_path: .tid.err 경로
        error_points: 에러 포인트 정보 리스트
    """
    err_path = output_path + '.err' if not output_path.endswith('.err') else output_path

    with open(err_path, 'w', encoding='utf-8') as f:
        if not error_points:
            f.write("No Error Point Detected.\n")
        else:
            for ep in error_points:
                f.write(f"{ep.get('file', 'Unknown')}\t"
                        f"{ep.get('lon', 0):.7f}\t"
                        f"{ep.get('lat', 0):.7f}\t"
                        f"{ep.get('time', '')}\n")

    logger.info(f".tid.err 출력 완료 → {err_path}")
