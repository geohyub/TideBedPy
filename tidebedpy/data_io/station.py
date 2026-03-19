"""
station.py - 기준항 정보 로드

기준항정보.txt (17필드, 탭 구분, EUC-KR/UTF-8)를 파싱한다.
참조: clsRefSTInfo.cs InitRefSTEntry, clsRefStation.cs
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RefStation:
    """기준항 데이터 구조"""
    use: bool = True
    seq: int = -1
    name: str = ''
    longitude: float = -999.9      # X
    latitude: float = -999.9       # Y
    m2_amp: float = 0.0
    m2_phase: float = 0.0
    s2_amp: float = 0.0
    s2_phase: float = 0.0
    k1_amp: float = 0.0
    k1_phase: float = 0.0
    o1_amp: float = 0.0
    o1_phase: float = 0.0
    spr_range: float = -999.9      # 대조차 (cm)
    spr_rise: float = -999.9       # 대조승 (cm)
    msl: float = -999.9            # 평균해면 (cm)
    mhwi: float = -999.9           # 평균고조간격 (hours)

    # 조위 시계열 (tide_series.py에서 할당)
    tide_obs: Optional[object] = None     # 실측 조위 시계열
    tide_pred: Optional[object] = None    # 예측 조위 시계열

    # 임시 태그 (처리 중 사용)
    tag_distance: float = 0.0


def _power_split(line: str) -> List[str]:
    """
    C#의 PowerSplit 재현.
    탭, 스페이스, 콤마, 세미콜론을 모두 구분자로 사용하고,
    연속 구분자를 하나로 합친다.

    참조: GnrlFunctions.cs PowerSplit (lines 281-292)
    """
    return re.split(r'[\t ,;]+', line.strip())


def load_stations(file_path: str) -> List[RefStation]:
    """
    기준항정보.txt를 파싱하여 RefStation 리스트를 반환한다.

    파일 형식 (17필드, 탭 구분):
    Use  Seq  Name  Lon  Lat  M2Amp  M2Phase  S2Amp  S2Phase
    K1Amp  K1Phase  O1Amp  O1Phase  sprRange  sprRise  MSL  MHWI

    참조: clsRefSTInfo.cs InitRefSTEntry (lines 39-92)
    - 첫 줄(헤더) 스킵
    - Use 필드: TRUE/true/t/T → True
    - 17필드 미만 줄은 스킵

    Args:
        file_path: 기준항정보.txt 경로

    Returns:
        RefStation 리스트 (Use=True인 것만)
    """
    from utils.encoding import read_lines

    lines = read_lines(file_path)
    stations = []
    skipped = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # 헤더 줄 스킵: 첫 필드가 TRUE/FALSE가 아닌 줄
        first_field = line.split('\t')[0].strip().upper() if '\t' in line else line.split()[0].strip().upper()
        if first_field not in ('TRUE', 'FALSE', 'T', 'F'):
            logger.debug(f"Line {i+1}: 헤더/비데이터 줄 스킵")
            continue

        fields = _power_split(line)

        if len(fields) < 17:
            skipped += 1
            logger.debug(f"Line {i+1}: 필드 수 부족 ({len(fields)}/17), 스킵")
            continue

        try:
            use_str = fields[0].upper()
            use = use_str in ('TRUE', 'T')

            if not use:
                continue

            station = RefStation(
                use=use,
                seq=int(fields[1]),
                name=fields[2],
                longitude=float(fields[3]),
                latitude=float(fields[4]),
                m2_amp=float(fields[5]),
                m2_phase=float(fields[6]),
                s2_amp=float(fields[7]),
                s2_phase=float(fields[8]),
                k1_amp=float(fields[9]),
                k1_phase=float(fields[10]),
                o1_amp=float(fields[11]),
                o1_phase=float(fields[12]),
                spr_range=float(fields[13]),
                spr_rise=float(fields[14]),
                msl=float(fields[15]),
                mhwi=float(fields[16]),
            )
            stations.append(station)

        except (ValueError, IndexError) as e:
            skipped += 1
            logger.warning(f"Line {i+1}: 파싱 오류 - {e}")
            continue

    logger.info(f"기준항 로드 완료: {len(stations)}개 활성 / {skipped}개 스킵 ({file_path})")
    return stations


def get_station_by_name(stations: List[RefStation], name: str) -> Optional[RefStation]:
    """이름으로 기준항 검색"""
    for st in stations:
        if st.name == name:
            return st
    return None


def get_station_index_by_name(stations: List[RefStation], name: str) -> int:
    """이름으로 기준항 인덱스 검색. 없으면 -1."""
    for i, st in enumerate(stations):
        if st.name == name:
            return i
    return -1
