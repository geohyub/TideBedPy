"""
tide_series.py - 조위 시계열 로드

TOPS 형식 실측/예측조위 파일을 파싱하고,
Akima spline으로 1분 간격 보간 후 기준항에 매칭한다.

참조:
- Series_S.cs readTTS2TS, GetNearstID, AkimaSpline
- clsRefSTInfo.cs SetData4Folder, ExtractSTName4File, findLevelValue
"""

import os
import re
import logging
import bisect
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TideRecord:
    """조위 시계열 단일 레코드"""
    time: datetime
    level: float     # cm


@dataclass
class TideSeries:
    """조위 시계열 데이터"""
    station_name: str = ''
    records: List[TideRecord] = field(default_factory=list)

    # 보간된 데이터 (1분 간격)
    interp_times: Optional[np.ndarray] = None    # 분 단위 (시작부터)
    interp_levels: Optional[np.ndarray] = None   # cm
    interp_start: Optional[datetime] = None      # 보간 시작 시간

    @property
    def date_start(self) -> Optional[datetime]:
        return self.records[0].time if self.records else None

    @property
    def date_end(self) -> Optional[datetime]:
        return self.records[-1].time if self.records else None


def _extract_station_name(lines: List[str]) -> str:
    """
    TOPS 파일 헤더에서 관측소명칭 추출.
    '관측소명칭 : XXX' 또는 '대상조위관측소 : XXX' 형식.

    참조: clsRefSTInfo.cs ExtractSTName4File (lines 175-185)
    """
    for line in lines[:10]:  # 헤더는 첫 10줄 이내
        if ':' in line:
            key_candidates = ['관측소명칭', '관측소명', '대상조위관측소']
            for key in key_candidates:
                if key in line:
                    return line.split(':')[1].strip()
    return ''


def _try_parse_tide_line(line: str) -> Optional[TideRecord]:
    """
    Try to parse a tide data line in multiple formats:
    1. TOPS: YYYY MM DD HH MM  Level
    2. Dash: YYYY-MM-DD HH:MM  Level
    3. Slash: YYYY/MM/DD HH:MM  Level
    4. CSV: YYYY-MM-DD,HH:MM:SS,Level or YYYY-MM-DD HH:MM:SS,Level
    5. Tab: date<tab>time<tab>level

    Returns TideRecord or None.
    """
    line = line.strip()
    if not line or not line[0].isdigit():
        return None

    # Try comma-separated
    if ',' in line:
        csv_parts = [p.strip() for p in line.split(',')]
        # Combined datetime,level or date,time,level
        for combo in _try_csv_datetime(csv_parts):
            if combo:
                return combo

    # Split by whitespace or tab
    parts = re.split(r'[\t ]+', line)
    if len(parts) < 2:
        return None

    # Format 1 (TOPS): YYYY MM DD HH MM Level (6 fields, all space-separated)
    if len(parts) >= 6:
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            hour = int(parts[3])
            minute = int(parts[4])
            level = float(parts[5])
            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                dt = datetime(year, month, day, hour, minute)
                return TideRecord(time=dt, level=level)
        except (ValueError, IndexError):
            pass

    # Format 2/3 (Dash/Slash): YYYY-MM-DD HH:MM Level
    if len(parts) >= 3 and ('-' in parts[0] or '/' in parts[0]) and ':' in parts[1]:
        dt_str = parts[0] + ' ' + parts[1]
        level_str = parts[2]
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                     '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
                     '%Y-%m-%d %H:%M:%S.%f']:
            try:
                dt = datetime.strptime(dt_str, fmt)
                level = float(level_str)
                return TideRecord(time=dt, level=level)
            except ValueError:
                continue

    # Format: combined datetime with T separator
    if len(parts) >= 2 and 'T' in parts[0]:
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M']:
            try:
                dt = datetime.strptime(parts[0], fmt)
                level = float(parts[1])
                return TideRecord(time=dt, level=level)
            except ValueError:
                continue

    return None


def _try_csv_datetime(csv_parts: List[str]) -> List[Optional[TideRecord]]:
    """Try to parse CSV datetime + level combinations."""
    results = []

    if len(csv_parts) >= 2:
        # datetime,level
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                     '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
                     '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M']:
            try:
                dt = datetime.strptime(csv_parts[0], fmt)
                level = float(csv_parts[-1])
                results.append(TideRecord(time=dt, level=level))
                return results
            except ValueError:
                continue

    if len(csv_parts) >= 3:
        # date,time,level
        dt_str = csv_parts[0] + ' ' + csv_parts[1]
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                     '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']:
            try:
                dt = datetime.strptime(dt_str, fmt)
                level = float(csv_parts[2])
                results.append(TideRecord(time=dt, level=level))
                return results
            except ValueError:
                continue

    results.append(None)
    return results


def read_tops_file(file_path: str) -> Optional[TideSeries]:
    """
    Parse tide file in TOPS or flexible format.

    Supported formats:
    - TOPS: header + 'YYYY MM DD HH MM  LevelCm'
    - Dash/Slash: 'YYYY-MM-DD HH:MM  Level'
    - CSV: 'YYYY-MM-DD,HH:MM,Level'
    - ISO: 'YYYY-MM-DDTHH:MM:SS  Level'

    Station name is extracted from:
    1. TOPS header (official)
    2. Filename (fallback - strip extension, remove common suffixes)

    Reference: Series_S.cs readTTS2TS (lines 176-224)

    Args:
        file_path: Tide file path

    Returns:
        TideSeries object (None on failure)
    """
    from utils.encoding import read_lines

    try:
        lines = read_lines(file_path)
    except Exception as e:
        logger.error(f"File read failed: {file_path} - {e}")
        return None

    # Try to extract station name from header (TOPS format)
    station_name = _extract_station_name(lines)

    # Fallback: use filename as station name
    if not station_name:
        basename = os.path.splitext(os.path.basename(file_path))[0]
        # Remove common suffixes like _obs, _pred, _tide, etc.
        for suffix in ['_obs', '_pred', '_tide', '_tts',
                       '_실측조위', '_예측조위', '_실측', '_예측']:
            if basename.lower().endswith(suffix):
                basename = basename[:-len(suffix)]
        station_name = basename
        logger.debug(f"Using filename as station name: '{station_name}' ({file_path})")

    series = TideSeries(station_name=station_name)

    for i, line in enumerate(lines):
        record = _try_parse_tide_line(line)
        if record:
            series.records.append(record)

    if not series.records:
        logger.debug(f"No valid TOPS data: {file_path}")
        return None

    logger.debug(f"Tide parsed: {station_name} - {len(series.records)} records "
                 f"({series.date_start} ~ {series.date_end})")
    return series


def interpolate_akima(series: TideSeries) -> None:
    """
    Akima spline으로 1분 간격 보간.

    참조: Series_S.cs AkimaSpline (lines 254-279)
    - 시간을 분 단위로 변환
    - Akima spline 적용
    - 1분 간격으로 재샘플링

    Args:
        series: TideSeries (in-place로 interp_* 필드 설정)
    """
    from scipy.interpolate import Akima1DInterpolator

    if not series.records or len(series.records) < 4:
        logger.warning(f"Akima 보간에 충분한 데이터 없음: {series.station_name}")
        return

    t_start = series.records[0].time
    t_end = series.records[-1].time

    # 시간을 분 단위로 변환 (시작부터)
    time_minutes = np.array([
        (r.time - t_start).total_seconds() / 60.0
        for r in series.records
    ])
    levels = np.array([r.level for r in series.records])

    # Akima spline 생성
    try:
        akima = Akima1DInterpolator(time_minutes, levels)
    except Exception as e:
        logger.error(f"Akima 보간 실패 ({series.station_name}): {e}")
        return

    # 1분 간격으로 재샘플링
    total_minutes = int((t_end - t_start).total_seconds() / 60.0)
    interp_t = np.arange(0, total_minutes + 1, dtype=float)
    interp_levels = akima(interp_t)

    series.interp_times = interp_t
    series.interp_levels = interp_levels
    series.interp_start = t_start

    logger.debug(f"Akima 보간 완료: {series.station_name} - "
                 f"{len(interp_t)}개 포인트 (1분 간격)")


def find_level_value(series: TideSeries, target_time: datetime) -> Optional[float]:
    """
    이진탐색으로 target_time에 가장 가까운 조위 값을 찾는다.
    ±2분 이내의 값만 유효.

    참조:
    - Series_S.cs GetNearstID (lines 226-252): 이진탐색
    - clsRefSTInfo.cs findLevelValue (lines 218-236): ±2분 threshold

    Args:
        series: 보간된 TideSeries
        target_time: 검색할 시간

    Returns:
        조위 값 (cm) 또는 None (데이터 없음)
    """
    if series.interp_levels is None or series.interp_start is None:
        # 보간되지 않은 경우 원시 데이터에서 검색
        return _find_level_raw(series, target_time)

    # 보간된 데이터에서 검색 (1분 간격)
    delta_minutes = (target_time - series.interp_start).total_seconds() / 60.0

    if delta_minutes < 0 or delta_minutes > series.interp_times[-1]:
        return None

    # 가장 가까운 인덱스 찾기
    idx = int(round(delta_minutes))
    idx = max(0, min(idx, len(series.interp_levels) - 1))

    # 실제 시간 차이 확인 (±2분 이내)
    actual_time = series.interp_start + timedelta(minutes=float(series.interp_times[idx]))
    diff_minutes = abs((target_time - actual_time).total_seconds()) / 60.0

    if diff_minutes > 2.0:
        return None

    return float(series.interp_levels[idx])


def _find_level_raw(series: TideSeries, target_time: datetime) -> Optional[float]:
    """
    보간되지 않은 원시 데이터에서 이진탐색.
    참조: Series_S.cs GetNearstID
    """
    if not series.records:
        return None

    records = series.records
    lo, hi = 0, len(records) - 1

    # 이진탐색
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if target_time < records[mid].time:
            hi = mid
        elif target_time > records[mid].time:
            lo = mid
        else:
            return records[mid].level  # 정확히 일치

    # 가장 가까운 것 선택
    diff_lo = abs((target_time - records[lo].time).total_seconds())
    diff_hi = abs((target_time - records[hi].time).total_seconds())

    nearest_idx = lo if diff_lo <= diff_hi else hi
    nearest_diff = min(diff_lo, diff_hi)

    if nearest_diff / 60.0 > 2.0:
        return None

    return records[nearest_idx].level


def _read_csv_as_tide(file_path: str, series_type: str = 'OBS') -> Optional[TideSeries]:
    """
    KHOA 바다누리 CSV 파일을 직접 TideSeries로 파싱한다.
    CSV 컬럼: No, 관측소명, 관측시간, 실측조위(Cm), 예측조위(Cm), 잔차(Cm)

    Args:
        file_path: CSV 파일 경로
        series_type: 'OBS' → 실측조위(col 3), 'PRED' → 예측조위(col 4)

    Returns:
        TideSeries 또는 None
    """
    import csv
    encodings = ['utf-8-sig', 'utf-8', 'euc-kr', 'cp949']
    header = None
    rows = None
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                header = next(reader)
                rows = list(reader)
            if len(header) >= 5 and len(rows) > 0:
                break
            header, rows = None, None
        except (UnicodeDecodeError, UnicodeError):
            continue
        except StopIteration:
            return None

    if header is None or rows is None:
        return None

    # CSV 헤더 검증: 관측소명, 관측시간 포함 여부
    header_joined = ','.join(header)
    if '관측소명' not in header_joined or '관측시간' not in header_joined:
        return None

    # 데이터 컬럼 인덱스 결정
    val_col = 3 if series_type == 'OBS' else 4  # 실측조위 or 예측조위

    station_name = ''
    records = []
    for row in rows:
        if len(row) < 5:
            continue
        if not station_name:
            station_name = row[1].strip()
        try:
            dt = datetime.strptime(row[2].strip(), '%Y-%m-%d %H:%M')
            val_str = row[val_col].strip()
            if not val_str or val_str == '':
                continue
            level = float(val_str)
            records.append(TideRecord(time=dt, level=level))
        except (ValueError, IndexError):
            continue

    if not station_name or len(records) < 3:
        return None

    series = TideSeries(station_name=station_name, records=records)
    logger.info(f"CSV 파싱: {station_name} - {len(records)}개 레코드 ({file_path})")
    return series


def _merge_records(existing: List[TideRecord], new: List[TideRecord]) -> List[TideRecord]:
    """두 레코드 리스트를 시간순 정렬 + 중복 제거하여 병합."""
    combined = existing + new
    combined.sort(key=lambda r: r.time)
    # 중복 시간 제거 (나중 값 우선)
    seen = {}
    for rec in combined:
        seen[rec.time] = rec
    merged = sorted(seen.values(), key=lambda r: r.time)
    return merged


def load_tide_folder(folder_path: str,
                     stations: list,
                     series_type: str = 'OBS') -> int:
    """
    조위 폴더의 TOPS/CSV 파일을 읽어 기준항에 매칭한다.
    같은 관측소의 여러 파일(다른 날짜)은 자동으로 통합한다.

    참조: clsRefSTInfo.cs SetData4Folder (lines 130-173)
    - *.txt, *.tts, *.csv 파일 스캔
    - TOPS 형식 우선 시도, 실패 시 KHOA CSV 형식 시도
    - 관측소명칭으로 기준항 이름 매칭
    - 동일 관측소 다중 파일 → 시계열 병합
    - Akima spline 보간 적용

    Args:
        folder_path: 조위 파일 폴더 경로
        stations: RefStation 리스트
        series_type: 'OBS' (실측) 또는 'PRED' (예측)

    Returns:
        매칭된 기준항 수
    """
    if not os.path.isdir(folder_path):
        logger.error(f"조위 폴더를 찾을 수 없음: {folder_path}")
        return 0

    files = [f for f in os.listdir(folder_path)
             if f.lower().endswith(('.txt', '.tts', '.csv', '.tsv', '.dat'))]

    logger.info(f"조위 폴더 스캔: {len(files)}개 파일 ({folder_path})")

    from data_io.station import get_station_by_name

    # 1단계: 모든 파일 파싱 → 관측소별 레코드 수집
    station_records: dict = {}  # station_name → List[TideRecord]
    station_files: dict = {}    # station_name → List[filename]

    for fname in files:
        fpath = os.path.join(folder_path, fname)

        # 1차: TOPS 형식 시도
        series = read_tops_file(fpath)

        # 2차: TOPS 실패 시 KHOA CSV 형식 시도
        if series is None and fname.lower().endswith('.csv'):
            series = _read_csv_as_tide(fpath, series_type)

        if series is None:
            continue

        sname = series.station_name
        # 기준항 매칭 가능한지 확인
        if get_station_by_name(stations, sname) is None:
            logger.debug(f"매칭되지 않은 관측소: '{sname}' ({fname})")
            continue

        # 레코드 누적
        if sname not in station_records:
            station_records[sname] = []
            station_files[sname] = []
        station_records[sname].extend(series.records)
        station_files[sname].append(fname)

    # 2단계: 관측소별 병합 → Akima 보간 → 기준항 할당
    matched = 0
    for sname, records in station_records.items():
        # 시간순 정렬 + 중복 제거
        records = _merge_records([], records)

        merged_series = TideSeries(station_name=sname, records=records)
        interpolate_akima(merged_series)

        station = get_station_by_name(stations, sname)
        if series_type == 'OBS':
            station.tide_obs = merged_series
        else:
            station.tide_pred = merged_series

        matched += 1
        flist = station_files[sname]
        logger.info(f"매칭: '{sname}' \u2190 {len(flist)}개 파일 "
                    f"({len(records)}개 레코드, "
                    f"{merged_series.date_start} ~ {merged_series.date_end})")

    logger.info(f"조위 매칭 완료: {matched}개 기준항 매칭됨")
    return matched


def adjust_tide_year(stations: list, nav_year: int) -> int:
    """
    조위 시계열의 연도를 Nav 데이터 연도에 맞춘다.

    Nav 데이터와 조위 데이터의 연도가 다를 경우(예: Nav=2025, Tide=2026),
    조위 시계열의 모든 레코드 시간을 Nav 연도에 맞춰 조정하고
    Akima 보간을 다시 수행한다.

    Args:
        stations: RefStation 리스트
        nav_year: Nav 데이터의 기준 연도

    Returns:
        조정된 시계열 수
    """
    adjusted = 0

    for station in stations:
        for series in [station.tide_obs, station.tide_pred]:
            if series is None or not series.records:
                continue

            tide_year = series.records[0].time.year
            if tide_year == nav_year:
                continue

            year_diff = nav_year - tide_year
            logger.info(f"연도 조정: {series.station_name} "
                        f"({tide_year} -> {nav_year}, diff={year_diff:+d})")

            # 모든 레코드의 시간 조정
            for rec in series.records:
                try:
                    rec.time = rec.time.replace(year=rec.time.year + year_diff)
                except ValueError:
                    # 2/29 윤년 등 예외: 가까운 날짜로
                    rec.time = rec.time.replace(year=rec.time.year + year_diff,
                                                day=28)

            # Akima 보간 재실행
            interpolate_akima(series)
            adjusted += 1

    if adjusted > 0:
        logger.info(f"연도 조정 완료: {adjusted}개 시계열")
    return adjusted
