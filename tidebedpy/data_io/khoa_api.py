"""
khoa_api.py - KHOA 조위관측소 실측·예측 조위 API 다운로드

공공데이터포털(data.go.kr) API를 통해 실측/예측 조위를 다운로드하고
기존 바다누리 CSV 형식으로 내보낸다.

API: 해양수산부 국립해양조사원_조위관측소 실측·예측 조위 조회
엔드포인트: https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService

응답 필드:
  bscTdlvHgt = 실측조위(cm)
  tdlvHgt    = 예측조위(cm)
  obsrvnDt   = 관측일시 (YYYY-MM-DD HH:MM)
  obsvtrNm   = 관측소명
  lat, lot   = 위도, 경도

Junhyub, 2026
"""

import csv
import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── 조위관측소 코드 (data.go.kr API 기준, 2026-03 검증) ──
STATION_LIST: List[Tuple[str, str]] = [
    ('DT_0001', '인천'),
    ('DT_0002', '평택'),
    ('DT_0003', '영광'),
    ('DT_0004', '제주'),
    ('DT_0005', '부산'),
    ('DT_0006', '묵호'),
    ('DT_0007', '목포'),
    ('DT_0008', '안산'),
    ('DT_0010', '서귀포'),
    ('DT_0011', '후포'),
    ('DT_0012', '속초'),
    ('DT_0013', '울릉도'),
    ('DT_0014', '통영'),
    ('DT_0016', '여수'),
    ('DT_0017', '대산'),
    ('DT_0018', '군산'),
    ('DT_0020', '울산'),
    ('DT_0021', '추자도'),
    ('DT_0022', '성산포'),
    ('DT_0023', '모슬포'),
    ('DT_0024', '장항'),
    ('DT_0025', '보령'),
    ('DT_0026', '고흥발포'),
    ('DT_0027', '완도'),
    ('DT_0028', '진도'),
    ('DT_0029', '거제도'),
    ('DT_0031', '거문도'),
    ('DT_0032', '강화대교'),
    ('DT_0035', '흑산도'),
    ('DT_0037', '어청도'),
    ('DT_0039', '왕돌초'),
    ('DT_0042', '교본초'),
    ('DT_0043', '영흥도'),
    ('DT_0044', '영종대교'),
    ('DT_0049', '광양'),
    ('DT_0050', '태안'),
    ('DT_0051', '서천마량'),
    ('DT_0052', '인천송도'),
    ('DT_0056', '부산항신항'),
    ('DT_0057', '동해항'),
    ('DT_0061', '삼천포'),
    ('DT_0062', '마산'),
    ('DT_0063', '가덕도'),
    ('DT_0065', '덕적도'),
    ('DT_0066', '향화도'),
    ('DT_0067', '안흥'),
    ('DT_0068', '위도'),
    ('DT_0091', '포항'),
    ('DT_0092', '여호항'),
    ('DT_0093', '소무의도'),
    ('DT_0094', '서거차도'),
    ('IE_0060', '이어도'),
]

STATION_NAME_TO_CODE: Dict[str, str] = {n: c for c, n in STATION_LIST}
STATION_CODE_TO_NAME: Dict[str, str] = {c: n for c, n in STATION_LIST}

# 관측소 좌표 (lat, lon) - 기준항정보.txt 기반
STATION_COORDS: Dict[str, Tuple[float, float]] = {
    'DT_0001': (37.4517, 126.5928),   # 인천
    'DT_0002': (36.9661, 126.8228),   # 평택
    'DT_0003': (35.2478, 126.4206),   # 영광
    'DT_0004': (33.5167, 126.5267),   # 제주
    'DT_0005': (35.0964, 129.0358),   # 부산
    'DT_0006': (37.5500, 129.1131),   # 묵호
    'DT_0007': (34.7803, 126.3797),   # 목포
    'DT_0008': (37.2925, 126.6656),   # 안산
    'DT_0010': (33.2400, 126.5611),   # 서귀포
    'DT_0011': (36.6783, 129.4517),   # 후포
    'DT_0012': (38.2081, 128.5944),   # 속초
    'DT_0013': (37.4933, 130.9072),   # 울릉도
    'DT_0014': (34.8275, 128.4331),   # 통영
    'DT_0016': (34.7469, 127.7656),   # 여수
    'DT_0017': (36.9847, 126.3517),   # 대산
    'DT_0018': (35.9875, 126.7103),   # 군산
    'DT_0020': (35.4953, 129.3839),   # 울산
    'DT_0021': (33.9500, 126.2947),   # 추자도
    'DT_0022': (33.4739, 126.9256),   # 성산포
    'DT_0023': (33.2142, 126.2500),   # 모슬포
    'DT_0024': (36.0067, 126.6872),   # 장항
    'DT_0025': (36.4078, 126.4886),   # 보령
    'DT_0026': (34.4883, 127.3403),   # 고흥발포
    'DT_0027': (34.3142, 126.7561),   # 완도
    'DT_0028': (34.3775, 126.3089),   # 진도
    'DT_0029': (34.8014, 128.6969),   # 거제도
    'DT_0031': (34.0317, 127.3083),   # 거문도
    'DT_0032': (37.7072, 126.5472),   # 강화대교
    'DT_0035': (34.6836, 125.4350),   # 흑산도
    'DT_0037': (36.1172, 125.9911),   # 어청도
    'DT_0039': (36.7333, 129.7833),   # 왕돌초
    'DT_0042': (33.9167, 125.8833),   # 교본초
    'DT_0043': (37.2500, 126.4833),   # 영흥도
    'DT_0044': (37.5500, 126.5667),   # 영종대교
    'DT_0049': (34.9103, 127.7678),   # 광양
    'DT_0050': (36.9133, 126.1386),   # 태안
    'DT_0051': (36.0833, 126.5500),   # 서천마량
    'DT_0052': (37.3767, 126.6494),   # 인천송도
    'DT_0056': (35.0767, 128.7992),   # 부산항신항
    'DT_0057': (37.4931, 129.1142),   # 동해항
    'DT_0061': (34.9264, 128.0706),   # 삼천포
    'DT_0062': (35.2006, 128.5794),   # 마산
    'DT_0063': (35.0233, 128.8069),   # 가덕도
    'DT_0065': (37.2333, 126.1500),   # 덕적도
    'DT_0066': (37.6167, 126.3833),   # 향화도
    'DT_0067': (36.6736, 126.1322),   # 안흥
    'DT_0068': (35.6167, 126.3000),   # 위도
    'DT_0091': (36.0500, 129.5667),   # 포항
    'DT_0092': (34.5500, 127.4500),   # 여호항
    'DT_0093': (37.4000, 126.4167),   # 소무의도
    'DT_0094': (34.1500, 126.1500),   # 서거차도
    'IE_0060': (32.1228, 125.1822),   # 이어도
}

# API 엔드포인트
_API_URL = ('https://apis.data.go.kr/1192136/surveyTideLevel'
            '/GetSurveyTideLevelApiService')

# 페이지당 최대 행수
_MAX_ROWS = 300


@dataclass
class DownloadResult:
    """API 다운로드 결과."""
    station_code: str
    station_name: str
    csv_path: str = ''
    obs_count: int = 0
    pred_count: int = 0
    date_start: str = ''
    date_end: str = ''
    error: str = ''


def _api_request(api_key: str, obs_code: str, req_date: str,
                 minute: int = 1, page: int = 1,
                 num_rows: int = _MAX_ROWS,
                 timeout: int = 30) -> dict:
    """data.go.kr 조위 API 요청 → JSON dict 반환."""
    params = {
        'serviceKey': api_key,
        'type': 'json',
        'obsCode': obs_code,
        'reqDate': req_date,
        'min': str(minute),
        'pageNo': str(page),
        'numOfRows': str(num_rows),
    }
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    full_url = f'{_API_URL}?{query}'
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(full_url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode('utf-8')
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            last_err = ConnectionError(f'API HTTP 오류 {e.code}: {e.reason}')
            if e.code < 500:
                raise last_err  # client error, no retry
        except urllib.error.URLError as e:
            last_err = ConnectionError(f'API 연결 실패: {e.reason}')
        except json.JSONDecodeError:
            raise ValueError('API 응답 JSON 파싱 실패')
        if attempt < 2:
            backoff = 2 ** attempt  # 1s, 2s
            logger.warning(f'API 재시도 {attempt + 1}/3 ({backoff}s 대기): {last_err}')
            time.sleep(backoff)
    raise last_err


def fetch_tide_day(api_key: str, obs_code: str, date_str: str,
                   minute: int = 1) -> List[dict]:
    """
    1일치 조위 데이터 조회 (실측+예측 통합).

    Parameters
    ----------
    api_key : 공공데이터포털 서비스키
    obs_code : 관측소 코드 (예: 'DT_0067')
    date_str : 날짜 'YYYYMMDD'
    minute : 시간 간격 (1=1분, 60=1시간)

    Returns
    -------
    list of dict: [{'obsrvnDt': ..., 'bscTdlvHgt': ..., 'tdlvHgt': ...}, ...]
    """
    all_items = []
    total_count = None

    for page in range(1, 20):  # 안전 상한
        resp = _api_request(api_key, obs_code, date_str,
                            minute=minute, page=page)

        header = resp.get('header', {})
        if header.get('resultCode') != '00':
            msg = header.get('resultMsg', 'Unknown error')
            raise ValueError(f'API 오류: {msg}')

        body = resp.get('body', {})
        if total_count is None:
            total_count = body.get('totalCount', 0)

        items = body.get('items', {}).get('item', [])
        if not items:
            break
        all_items.extend(items)

        if len(all_items) >= total_count:
            break
        time.sleep(0.1)

    return all_items


def fetch_tide_range(api_key: str, obs_code: str,
                     start_date: str, end_date: str,
                     minute: int = 1,
                     progress_callback=None,
                     cache=None) -> List[dict]:
    """
    기간 조위 데이터 조회 (일별 반복).

    Parameters
    ----------
    start_date, end_date : 'YYYYMMDD'
    minute : 시간 간격 (1=1분, 60=1시간)
    progress_callback : callable(current_day, total_days) or None
    cache : TideCache instance or None (opt-in offline cache)

    Returns
    -------
    list of dict (각 행에 실측+예측 모두 포함)
    """
    dt_start = datetime.strptime(start_date, '%Y%m%d')
    dt_end = datetime.strptime(end_date, '%Y%m%d')
    total_days = (dt_end - dt_start).days + 1

    all_data = []
    fail_count = 0
    cache_hit = 0

    for i in range(total_days):
        day = dt_start + timedelta(days=i)
        day_str = day.strftime('%Y%m%d')

        if progress_callback:
            progress_callback(i + 1, total_days)

        # Cache lookup
        if cache:
            cached = cache.get(obs_code, day_str, interval_min=minute)
            if cached:
                logger.info(f"  Cache hit: {obs_code} {day_str}")
                all_data.extend(cached)
                cache_hit += 1
                continue

        try:
            items = fetch_tide_day(api_key, obs_code, day_str, minute)
            if not items:
                fail_count += 1
                logger.warning(f"API 빈 응답 ({obs_code}, {day_str})")
            else:
                all_data.extend(items)
                # Cache store
                if cache:
                    cache.put(obs_code, day_str, items, interval_min=minute)
        except Exception as e:
            fail_count += 1
            logger.warning(f"API 조회 실패 ({obs_code}, {day_str}): {e}")
            continue

        time.sleep(0.2)  # API 부하 방지

    if cache_hit > 0:
        logger.info(f"API 캐시: {obs_code} - {cache_hit}/{total_days}일 캐시 사용")
    if fail_count > 0:
        logger.warning(f"API 수집 경고: {obs_code} - {total_days}일 중 {fail_count}일 실패")

    return all_data


def export_as_badanuri_csv(
    data: List[dict],
    station_name: str,
    output_path: str,
) -> int:
    """
    API 데이터를 바다누리 CSV 형식으로 내보내기.

    출력 컬럼: No, 관측소명, 관측시간, 관측조위(Cm), 예측조위(Cm), 편차(Cm)

    Parameters
    ----------
    data : fetch_tide_day/range 결과 리스트
    station_name : 관측소명
    output_path : CSV 출력 경로

    Returns
    -------
    int : 출력 행수
    """
    # 시간순 정렬 + 중복 제거
    seen = {}
    for item in data:
        t = item.get('obsrvnDt', '').strip()
        if not t:
            continue
        obs = item.get('bscTdlvHgt')   # 실측
        pred = item.get('tdlvHgt')     # 예측
        seen[t] = (obs, pred)

    if not seen:
        return 0

    sorted_times = sorted(seen.keys())

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['No', '관측소명', '관측시간',
                         '관측조위(Cm)', '예측조위(Cm)', '편차(Cm)'])

        for i, t in enumerate(sorted_times, 1):
            obs, pred = seen[t]

            # None/0 처리 (API에서 결측=0 또는 None)
            obs_str = str(int(obs)) if obs and obs != 0 else '-'
            pred_str = str(round(pred, 2)) if pred and pred != 0 else '-'

            # 편차 계산
            dev = '-'
            if obs_str != '-' and pred_str != '-':
                try:
                    dev = str(int(round(float(obs_str) - float(pred_str))))
                except (ValueError, TypeError):
                    dev = '-'

            writer.writerow([i, station_name, t, obs_str, pred_str, dev])

    return len(sorted_times)


def download_and_export(
    api_key: str,
    station_codes: List[str],
    start_date: str,
    end_date: str,
    output_dir: str,
    minute: int = 1,
    progress_callback=None,
) -> List[DownloadResult]:
    """
    여러 관측소의 조위 데이터를 API로 다운로드하고 바다누리 CSV로 내보내기.

    Parameters
    ----------
    api_key : 공공데이터포털 서비스키
    station_codes : 관측소 코드 리스트 ['DT_0067', ...]
    start_date, end_date : 'YYYYMMDD'
    output_dir : CSV 출력 폴더
    minute : 시간 간격 (1=1분, 60=1시간)
    progress_callback : callable(message_str) or None

    Returns
    -------
    list of DownloadResult
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total_stations = len(station_codes)

    for si, code in enumerate(station_codes):
        name = STATION_CODE_TO_NAME.get(code, code)
        result = DownloadResult(station_code=code, station_name=name,
                                date_start=start_date, date_end=end_date)

        if progress_callback:
            progress_callback(
                f'[{si+1}/{total_stations}] {name} 다운로드 중...')

        try:
            def _progress(cur, tot):
                if progress_callback:
                    progress_callback(
                        f'[{si+1}/{total_stations}] {name} '
                        f'{cur}/{tot}일')

            data = fetch_tide_range(
                api_key, code, start_date, end_date,
                minute=minute, progress_callback=_progress)

            # CSV 내보내기
            csv_name = f'{name}_{start_date}_{end_date}.csv'
            csv_path = os.path.join(output_dir, csv_name)
            count = export_as_badanuri_csv(data, name, csv_path)

            result.csv_path = csv_path
            # 실측/예측 행수 계산
            result.obs_count = sum(
                1 for d in data
                if d.get('bscTdlvHgt') and d['bscTdlvHgt'] != 0)
            result.pred_count = sum(
                1 for d in data
                if d.get('tdlvHgt') and d['tdlvHgt'] != 0)

            logger.info(f"API 다운로드 완료: {name} "
                        f"(실측 {result.obs_count}행, "
                        f"예측 {result.pred_count}행)")

        except Exception as e:
            result.error = str(e)
            logger.error(f"API 다운로드 실패 ({name}): {e}")

        results.append(result)

    return results


# ── Nav 기반 자동 수집 ──

def _haversine_km(lat1, lon1, lat2, lon2):
    """두 좌표 간 거리(km) 계산 - Haversine."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def select_nearby_stations(
    center_lat: float,
    center_lon: float,
    stations: Optional[list] = None,
    max_count: int = 10,
    max_distance_km: float = 300.0,
) -> List[Tuple[str, str, float]]:
    """
    중심 좌표에서 가까운 관측소를 거리순으로 선택.

    Parameters
    ----------
    center_lat, center_lon : Nav 데이터의 중심 좌표
    stations : RefStation 리스트 (있으면 기준항정보 좌표 사용)
    max_count : 최대 관측소 수
    max_distance_km : 최대 거리 제한

    Returns
    -------
    list of (code, name, distance_km) 거리순 정렬
    """
    candidates = []

    # 기준항정보가 있으면 그 좌표 사용, 없으면 내장 좌표 사용
    if stations:
        for st in stations:
            code = STATION_NAME_TO_CODE.get(st.name)
            if not code:
                continue
            dist = _haversine_km(center_lat, center_lon,
                                 st.latitude, st.longitude)
            if dist <= max_distance_km:
                candidates.append((code, st.name, dist))
    else:
        for code, (lat, lon) in STATION_COORDS.items():
            name = STATION_CODE_TO_NAME.get(code, code)
            dist = _haversine_km(center_lat, center_lon, lat, lon)
            if dist <= max_distance_km:
                candidates.append((code, name, dist))

    candidates.sort(key=lambda x: x[2])
    return candidates[:max_count]


@dataclass
class AutoFetchResult:
    """자동 수집 결과."""
    station_code: str
    station_name: str
    distance_km: float
    tops_obs_path: str = ''
    tops_pred_path: str = ''
    record_count: int = 0
    error: str = ''


def auto_fetch_for_nav(
    api_key: str,
    nav_points: list,
    output_dir: str,
    stations: Optional[list] = None,
    max_stations: int = 10,
    max_distance_km: float = 300.0,
    minute: int = 10,
    progress_callback=None,
    selected_stations: Optional[List[Tuple[str, str, float]]] = None,
) -> List[AutoFetchResult]:
    """
    Nav 데이터에서 시간범위/위치를 추출하고 API로 조위 자동 수집 → TOPS 생성.

    Parameters
    ----------
    api_key : 공공데이터포털 서비스키
    nav_points : NavPoint 리스트 (시간순 정렬)
    output_dir : TOPS 출력 폴더
    stations : RefStation 리스트 (있으면 기준항정보 좌표 사용)
    max_stations : 최대 수집 관측소 수
    max_distance_km : 최대 거리 제한(km)
    minute : API 시간 간격 (10=10분)
    progress_callback : callable(message_str) or None
    selected_stations : 다이얼로그에서 선택된 관측소 리스트 (code, name, dist)
                        지정 시 자동 선정 대신 이 목록만 수집

    Returns
    -------
    list of AutoFetchResult
    """
    if not nav_points:
        raise ValueError('Nav 데이터가 없습니다')

    # 1) Nav에서 시간범위 추출
    t_start = nav_points[0].t
    t_end = nav_points[-1].t

    date_start = (t_start - timedelta(hours=6)).strftime('%Y%m%d')
    date_end = (t_end + timedelta(hours=6)).strftime('%Y%m%d')

    if progress_callback:
        progress_callback(
            f'Nav 분석: {t_start:%Y-%m-%d %H:%M} ~ {t_end:%Y-%m-%d %H:%M}')

    # 2) 관측소 선정: 다이얼로그 결과 우선, 없으면 자동 선정
    if selected_stations:
        nearby = selected_stations
    else:
        lats = [p.y for p in nav_points]
        lons = [p.x for p in nav_points]
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)
        nearby = select_nearby_stations(
            center_lat, center_lon, stations, max_stations, max_distance_km)

    logger.info(f"Auto-fetch: 기간 {date_start}~{date_end}, "
                f"{len(nearby)}개 관측소")

    if not nearby:
        raise ValueError('범위 내 관측소가 없습니다')

    logger.info(f"선정 관측소 {len(nearby)}개: "
                + ', '.join(f'{n}({d:.0f}km)' for _, n, d in nearby))

    # 3) 출력 폴더 생성 (이전 실행의 잔여 파일 정리)
    obs_dir = os.path.join(output_dir, 'api_실측조위')
    pred_dir = os.path.join(output_dir, 'api_예측조위')
    for d in (obs_dir, pred_dir):
        if os.path.isdir(d):
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                if os.path.isfile(fp) and f.endswith('.txt'):
                    os.remove(fp)
        os.makedirs(d, exist_ok=True)

    # 4) 각 관측소 데이터 수집 → TOPS 변환
    results = []

    for si, (code, name, dist) in enumerate(nearby):
        res = AutoFetchResult(
            station_code=code, station_name=name, distance_km=dist)

        if progress_callback:
            progress_callback(
                f'[{si+1}/{len(nearby)}] {name} ({dist:.0f}km) 수집 중...')

        try:
            data = fetch_tide_range(api_key, code, date_start, date_end,
                                    minute=minute)

            if not data:
                res.error = '데이터 없음'
                results.append(res)
                continue

            res.record_count = len(data)

            # TOPS 실측 파일 생성
            obs_path = os.path.join(obs_dir, f'{name}_실측조위.txt')
            _write_tops_from_api(data, name, obs_path, use_obs=True)
            res.tops_obs_path = obs_path

            # TOPS 예측 파일 생성
            pred_path = os.path.join(pred_dir, f'{name}_예측조위.txt')
            _write_tops_from_api(data, name, pred_path, use_obs=False)
            res.tops_pred_path = pred_path

            logger.info(f"TOPS 생성: {name} ({res.record_count}행)")

        except Exception as e:
            res.error = str(e)
            logger.error(f"Auto-fetch 실패 ({name}): {e}")

        results.append(res)

    return results


def _write_tops_from_api(data: List[dict], station_name: str,
                         output_path: str, use_obs: bool = True):
    """API 데이터를 TOPS 형식으로 직접 변환."""
    # 시간순 정렬 + 중복 제거
    seen = {}
    for item in data:
        t = item.get('obsrvnDt', '').strip()
        if not t:
            continue
        val = item.get('bscTdlvHgt') if use_obs else item.get('tdlvHgt')
        if val is not None and val != 0:
            seen[t] = val

    if not seen:
        return

    sorted_times = sorted(seen.keys())
    t_first = sorted_times[0]
    t_last = sorted_times[-1]

    label = '실측자료' if use_obs else '예측자료'

    # 좌표 조회
    code = STATION_NAME_TO_CODE.get(station_name, '')
    lat, lon = STATION_COORDS.get(code, (0, 0))

    # 위도/경도를 도분초로 변환
    def dms(deg, is_lat=True):
        d = abs(deg)
        dd = int(d)
        mm = int((d - dd) * 60)
        ss = int(((d - dd) * 60 - mm) * 60)
        h = ('N' if is_lat else 'E') if deg >= 0 else ('S' if is_lat else 'W')
        return f'{h}  {dd:3d}도 {mm:02d}분 {ss:02d}초'

    with open(output_path, 'w', encoding='euc-kr') as f:
        f.write(f'<TOPS - API {label}>\n')
        f.write('\n')
        f.write(f'대상조위관측소 : {station_name}\n')
        f.write(f'위도(WGS84) : {dms(lat, True)}\n')
        f.write(f'경도(WGS84) : {dms(lon, False)}\n')
        f.write(f'관측기간 : {t_first}:00 ~ {t_last}:00\n')
        f.write('\n')

        for t in sorted_times:
            val = seen[t]
            # 'YYYY-MM-DD HH:MM' → 'YYYY MM DD HH MM'
            try:
                dt = datetime.strptime(t, '%Y-%m-%d %H:%M')
                f.write(f'{dt.year} {dt.month:02d} {dt.day:02d} '
                        f'{dt.hour:02d} {dt.minute:02d}   '
                        f'{int(round(val))}\n')
            except ValueError:
                continue
