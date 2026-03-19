"""
interpolation.py - IDW 가중치 + 이중선형 보간

핵심 보간 함수:
1. bilinear_interpolate: 2×2 격자 이중선형 보간 (C#의 getBicubicInterpol)
2. compute_idw_weights: 전체 기준항 대상 IDW(1/d²) 가중치 계산
3. compute_idw_weights_batch: 배치 IDW (속도 최적화)

참조: frmMain.cs GetInfValueInstantly, getBicubicInterpol
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from core.geodesy import vincenty_inverse

logger = logging.getLogger(__name__)


@dataclass
class StationWeight:
    """기준항 가중치 정보"""
    station_idx: int     # RefStation 리스트 내 인덱스
    station_name: str    # 기준항 이름
    weight: float        # IDW 가중치 (전체 기준항 대비 정규화)
    distance_m: float    # 거리 (meters)


def bilinear_interpolate(x_delta: float, y_delta: float,
                         v00: float, v01: float,
                         v10: float, v11: float) -> float:
    """
    2×2 격자 이중선형 보간.

    참조: frmMain.cs getBicubicInterpol (lines 6066-6071)
    주의: C# 함수명은 'bicubic'이지만 실제로는 bilinear임.

    격자 배치:
        V01 --- V11  (Y+1)
        |       |
        V00 --- V10  (Y)
        (X)    (X+1)

    수식:
        a = V00 + (V10 - V00) * xDelta    (X 방향 보간)
        b = V01 + (V11 - V01) * xDelta    (X 방향 보간)
        result = a + (b - a) * yDelta      (Y 방향 보간)
    """
    a = v00 + (v10 - v00) * x_delta
    b = v01 + (v11 - v01) * x_delta
    return a + (b - a) * y_delta


def compute_idw_weights(nav_lon: float, nav_lat: float,
                        stations: list) -> List[StationWeight]:
    """
    모든 기준항에 대해 IDW(1/d²) 가중치를 계산한다.

    참조: frmMain.cs GetInfValueInstantly (lines 5669-5690)

    알고리즘:
    1. 모든 기준항까지 Vincenty 거리 계산
    2. 거리순 정렬
    3. sum_weights = Σ(1/d²) [전체 기준항]
    4. weight[i] = (1/d[i]²) / sum_weights

    ⚠️ 핵심: 정규화 분모는 '전체' 기준항 대상 (상위 N개만이 아님!)
       따라서 상위 10개 weight의 합 < 1.0

    Args:
        nav_lon: Nav 포인트 경도
        nav_lat: Nav 포인트 위도
        stations: RefStation 리스트

    Returns:
        거리순 정렬된 StationWeight 리스트 (전체 기준항)
    """
    weights = []
    sum_inv_d2 = 0.0

    for i, st in enumerate(stations):
        dist = vincenty_inverse(nav_lon, nav_lat, st.longitude, st.latitude)
        if dist <= 0:
            dist = 0.001  # 0 방지 (동일 위치)
        inv_d2 = 1.0 / (dist * dist)
        sum_inv_d2 += inv_d2
        weights.append(StationWeight(
            station_idx=i,
            station_name=st.name,
            weight=inv_d2,  # 임시 (나중에 정규화)
            distance_m=dist
        ))

    # 정규화
    if sum_inv_d2 > 0:
        for w in weights:
            w.weight = w.weight / sum_inv_d2

    # 거리순 정렬 (가까운 것 먼저)
    weights.sort(key=lambda w: w.distance_m)

    return weights


def compute_idw_weights_batch(nav_lons: np.ndarray, nav_lats: np.ndarray,
                               station_lons: np.ndarray, station_lats: np.ndarray,
                               station_names: list) -> List[List[StationWeight]]:
    """
    배치 IDW 가중치 계산 (속도 최적화용).

    여러 Nav 포인트에 대해 한 번에 IDW 가중치를 계산한다.
    단, Vincenty 거리 계산은 여전히 개별 호출 필요.

    Args:
        nav_lons: Nav 경도 배열
        nav_lats: Nav 위도 배열
        station_lons: 기준항 경도 배열
        station_lats: 기준항 위도 배열
        station_names: 기준항 이름 리스트

    Returns:
        각 Nav 포인트별 StationWeight 리스트
    """
    n_nav = len(nav_lons)
    n_st = len(station_lons)
    all_weights = []

    for i in range(n_nav):
        weights = []
        sum_inv_d2 = 0.0

        for j in range(n_st):
            dist = vincenty_inverse(nav_lons[i], nav_lats[i],
                                     station_lons[j], station_lats[j])
            if dist <= 0:
                dist = 0.001
            inv_d2 = 1.0 / (dist * dist)
            sum_inv_d2 += inv_d2
            weights.append(StationWeight(
                station_idx=j,
                station_name=station_names[j],
                weight=inv_d2,
                distance_m=dist
            ))

        if sum_inv_d2 > 0:
            for w in weights:
                w.weight /= sum_inv_d2

        weights.sort(key=lambda w: w.distance_m)
        all_weights.append(weights)

    return all_weights
