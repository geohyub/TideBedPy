"""
csv_to_tops.py - KHOA 바다누리 CSV → TOPS 형식 변환

바다누리 해양정보서비스에서 다운로드한 실시간관측 조위 CSV를
TideBedPy가 읽을 수 있는 TOPS 형식 텍스트로 변환한다.

CSV 컬럼: No, 관측소명, 관측시간, 관측조위(Cm), 예측조위(Cm), 편차(Cm)

Original: TideBedLite v1.05 (c) 2014 KHOA / GeoSR
Python:   Junhyub, 2025
"""

import csv
import os
import logging
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 인코딩 시도 순서
_ENCODINGS = ['utf-8-sig', 'utf-8', 'euc-kr', 'cp949']


@dataclass
class ConvertResult:
    """변환 결과."""
    station_name: str
    obs_path: Optional[str] = None
    pred_path: Optional[str] = None
    obs_count: int = 0
    pred_count: int = 0
    obs_start: str = ''
    obs_end: str = ''
    pred_start: str = ''
    pred_end: str = ''


def _read_csv(file_path: str) -> Tuple[List[str], List[List[str]]]:
    """CSV 파일을 읽어 (header, rows) 반환. 인코딩 자동 감지."""
    for enc in _ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                header = next(reader)
                rows = list(reader)
            # 간단한 유효성 검사
            if len(header) >= 5 and len(rows) > 0:
                return header, rows
        except (UnicodeDecodeError, UnicodeError):
            continue
        except StopIteration:
            raise ValueError(f"빈 CSV 파일: {file_path}")
    raise ValueError(f"CSV 인코딩 감지 실패: {file_path}")


def _dd_to_dms(dd: float) -> Tuple[int, int, int]:
    """Decimal Degrees → (도, 분, 초)."""
    d = int(dd)
    m = int((dd - d) * 60)
    s = round(((dd - d) * 60 - m) * 60)
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    return d, m, s


def _format_coord(lat: float, lon: float) -> Tuple[str, str]:
    """좌표를 TOPS 헤더 형식 문자열로 변환."""
    lat_d, lat_m, lat_s = _dd_to_dms(abs(lat))
    lon_d, lon_m, lon_s = _dd_to_dms(abs(lon))
    ns = 'N' if lat >= 0 else 'S'
    ew = 'E' if lon >= 0 else 'W'
    lat_str = f'{ns}  {lat_d:2d}도 {lat_m:02d}분 {lat_s:02d}초'
    lon_str = f'{ew} {lon_d:3d}도 {lon_m:02d}분 {lon_s:02d}초'
    return lat_str, lon_str


def _parse_datetime(dt_str: str) -> Tuple[str, str, str, str, str]:
    """'2026-03-04 00:00' → ('2026', '03', '04', '00', '00')."""
    dt_str = dt_str.strip()
    date_part, time_part = dt_str.split(' ')
    y, m, d = date_part.split('-')
    hh, mm = time_part.split(':')[:2]  # 초 있으면 무시
    return y, m, d, hh, mm


def _detect_interval(rows: List[List[str]], dt_col: int = 2) -> str:
    """데이터 간격 자동 감지 (1분/10분/1시간)."""
    if len(rows) < 3:
        return '조위'
    try:
        from datetime import datetime
        t1 = datetime.strptime(rows[0][dt_col].strip(), '%Y-%m-%d %H:%M')
        t2 = datetime.strptime(rows[1][dt_col].strip(), '%Y-%m-%d %H:%M')
        diff = (t2 - t1).total_seconds() / 60
        if diff <= 1.5:
            return '1분 간격 실시간관측 조위자료'
        elif diff <= 15:
            return f'{int(diff)}분 간격 1시간조위자료'
        else:
            return '1시간 간격 조위자료'
    except Exception:
        return '조위자료'


def _write_tops_file(path: str, station_name: str, interval_desc: str,
                     lat_str: str, lon_str: str, period_label: str,
                     rows: List[Tuple[str, int]],
                     start_str: str, end_str: str):
    """TOPS 형식 파일 쓰기. rows = [(datetime_str, level_int), ...]"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'<TOPS - {interval_desc}>\n')
        f.write('\n')
        f.write(f'관측소명 : {station_name}\n')
        if lat_str:
            f.write(f'위도(WGS84) : {lat_str}\n')
            f.write(f'경도(WGS84) : {lon_str}\n')
        f.write(f'{period_label} : {start_str} ~ {end_str}\n')
        f.write('\n')
        for dt_str, level in rows:
            y, m, d, hh, mm = _parse_datetime(dt_str)
            f.write(f'{y} {m} {d} {hh} {mm}  {level}\n')


def batch_convert(
    csv_paths: List[str],
    output_dir: str,
    station_coords: Optional[Dict[str, Tuple[float, float]]] = None,
    export_observed: bool = True,
    export_predicted: bool = True,
) -> List[ConvertResult]:
    """
    여러 CSV 파일을 관측소별로 그룹핑하여 통합 TOPS 파일로 변환.
    같은 관측소의 여러 날짜 파일은 자동 병합한다.
    """
    from datetime import datetime as dt

    os.makedirs(output_dir, exist_ok=True)

    # 1단계: 관측소별 행 수집
    station_obs: Dict[str, List] = {}   # station_name → [(datetime_str, level_str), ...]
    station_pred: Dict[str, List] = {}
    station_interval: Dict[str, str] = {}

    for path in csv_paths:
        try:
            header, rows = _read_csv(path)
        except Exception as e:
            logger.error(f"CSV 읽기 실패 ({path}): {e}")
            continue

        if not rows:
            continue

        sname = rows[0][1].strip() if len(rows[0]) > 1 else '미상'

        # 간격 감지 (첫 파일 기준)
        if sname not in station_interval:
            station_interval[sname] = _detect_interval(rows)

        # 실측 행 수집
        if export_observed:
            for r in rows:
                if len(r) > 3 and r[3].strip() not in ('-', '', 'null'):
                    station_obs.setdefault(sname, []).append(
                        (r[2].strip(), r[3].strip()))

        # 예측 행 수집
        if export_predicted:
            for r in rows:
                if len(r) > 4 and r[4].strip() not in ('-', '', 'null'):
                    station_pred.setdefault(sname, []).append(
                        (r[2].strip(), r[4].strip()))

    # 2단계: 관측소별 정렬 + 중복 제거 + TOPS 출력
    all_stations = set(list(station_obs.keys()) + list(station_pred.keys()))
    results = []

    for sname in sorted(all_stations):
        result = ConvertResult(station_name=sname)
        interval_desc = station_interval.get(sname, '조위자료')

        # 좌표
        lat_str, lon_str = '', ''
        if station_coords and sname in station_coords:
            lon, lat = station_coords[sname]
            lat_str, lon_str = _format_coord(lat, lon)

        # ── 실측조위 ──
        if sname in station_obs and station_obs[sname]:
            raw = station_obs[sname]
            # 시간순 정렬 + 중복 제거
            seen = {}
            for dt_str, val in raw:
                seen[dt_str] = val
            sorted_items = sorted(seen.items(), key=lambda x: x[0])
            data_rows = [(d, int(round(float(v)))) for d, v in sorted_items]

            obs_path = os.path.join(output_dir, f'{sname}_실측조위.txt')
            start_str = sorted_items[0][0] + ':00'
            end_str = sorted_items[-1][0] + ':00'
            _write_tops_file(obs_path, sname, interval_desc,
                             lat_str, lon_str, '관측기간',
                             data_rows, start_str, end_str)
            result.obs_path = obs_path
            result.obs_count = len(data_rows)
            result.obs_start = start_str
            result.obs_end = end_str
            logger.info(f"실측조위 변환: {sname} ({len(data_rows)}행) → {obs_path}")

        # ── 예측조위 ──
        if sname in station_pred and station_pred[sname]:
            raw = station_pred[sname]
            seen = {}
            for dt_str, val in raw:
                seen[dt_str] = val
            sorted_items = sorted(seen.items(), key=lambda x: x[0])
            data_rows = [(d, int(round(float(v)))) for d, v in sorted_items]

            pred_path = os.path.join(output_dir, f'{sname}_예측조위.txt')
            start_str = sorted_items[0][0] + ':00'
            end_str = sorted_items[-1][0] + ':00'
            _write_tops_file(pred_path, sname,
                             interval_desc.replace('실시간관측', '예측'),
                             lat_str, lon_str, '자료기간',
                             data_rows, start_str, end_str)
            result.pred_path = pred_path
            result.pred_count = len(data_rows)
            result.pred_start = start_str
            result.pred_end = end_str
            logger.info(f"예측조위 변환: {sname} ({len(data_rows)}행) → {pred_path}")

        results.append(result)

    return results
