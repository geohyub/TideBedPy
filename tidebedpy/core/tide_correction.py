"""
tide_correction.py - 핵심 조석보정 알고리즘

Nav 포인트별 조석보정값(Tc) 산출 파이프라인.
v2.1: UTC 오프셋 지원 + 속도 최적화 (캐싱, 배치 처리)

참조: frmMain.cs getTideEstim, getTidalCorrections, Calib4File
"""

import math
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from functools import lru_cache

import numpy as np

from core.interpolation import compute_idw_weights, compute_idw_weights_batch, StationWeight
from data_io.tide_series import find_level_value
from data_io.navigation import NavPoint

logger = logging.getLogger(__name__)


@dataclass
class StationCorrection:
    """기준항별 조석보정 결과"""
    station_name: str = ''
    arr_idx: int = -1
    weight: float = 0.0           # IDW 가중치 (전체 기준항 대비)
    h_ratio: float = 0.0          # SprRange_point / SprRange_station
    time_corrector: float = 0.0   # MHWI_point - MHWI_station (hours)
    corrected_time: Optional[datetime] = None
    org_height: float = -999.0    # 원시 조위 (cm)
    estim_height: float = -999.0  # 보정된 조위 (cm)


class TideCorrectionEngine:
    """조석보정 엔진 (v2.1 — 속도 최적화 + UTC 오프셋 지원)"""

    def __init__(self, config, stations: list, cotidal):
        """
        Args:
            config: TideBedConfig
            stations: List[RefStation]
            cotidal: CoTidalGrid
        """
        self.config = config
        self.stations = stations
        self.cotidal = cotidal
        self.last_corrections: List[StationCorrection] = []

        # === 속도 최적화: 기준항 좌표 배열 미리 구성 ===
        self._station_lons = np.array([s.longitude for s in stations])
        self._station_lats = np.array([s.latitude for s in stations])

        # === Co-tidal 섹터 캐시 ===
        self._sector_cache = {}

        # === UTC 오프셋 결정 ===
        # utc_offset 속성이 있으면 사용, 없으면 is_kst로 결정
        if hasattr(config, 'utc_offset') and config.utc_offset != 0.0:
            self._utc_offset = config.utc_offset
        elif config.is_kst:
            self._utc_offset = 9.0
        else:
            self._utc_offset = 0.0

        # 조위 데이터는 KST(UTC+9) 기준
        # 보정시간 = Nav시간 + (9 - utc_offset) - TimeCorrector
        self._time_shift = 9.0 - self._utc_offset

    def _get_cotidal_cached(self, x: float, y: float):
        """
        Co-tidal 값을 캐시와 함께 조회한다.
        동일 섹터(0.001도 해상도) 내 반복 조회를 최적화.
        """
        # 캐시 키: 0.001도 해상도로 양자화
        cache_key = (round(x, 3), round(y, 3))
        if cache_key in self._sector_cache:
            return self._sector_cache[cache_key]

        try:
            result = self.cotidal.get_cotidal_values(x, y)
            self._sector_cache[cache_key] = result
            return result
        except ValueError:
            self._sector_cache[cache_key] = None
            return None

    def process_nav_point(self, nav: NavPoint) -> float:
        """
        단일 Nav 포인트의 조석보정값(Tc)을 산출한다.

        참조: frmMain.cs getTideEstim (lines 6001-6055)

        파이프라인:
        1. IDW 가중치 계산 (전체 기준항)
        2. Co-tidal 값 보간 (SprRange, MSL, MHWI)
        3. 기준항별 HRatio, TimeCorrector, 보정시간, 조위 조회
        4. 상위 RankLimit개 가중평균 → Tc(cm)

        Returns:
            Tc (cm). 오류 시 -999.0
        """
        self.last_corrections = []

        # [1] IDW 가중치 계산
        idw_weights = compute_idw_weights(nav.x, nav.y, self.stations)

        # [2] Co-tidal 값 보간 (캐시 사용)
        cotidal_result = self._get_cotidal_cached(nav.x, nav.y)
        if cotidal_result is None:
            logger.warning(f"Co-tidal 보간 실패 ({nav.x:.4f}, {nav.y:.4f})")
            return -999.0

        spr_range, msl, mhwi = cotidal_result

        # MHWI 유효성 검사
        if abs(mhwi) > 1000000.0:
            logger.warning(f"MHWI 값 이상 ({mhwi}) at ({nav.x:.4f}, {nav.y:.4f})")
            return -999.0

        # sprRange NaN 검사
        if math.isnan(spr_range):
            logger.warning(f"SprRange is NaN at ({nav.x:.4f}, {nav.y:.4f})")
            return -999.9

        # Nav 포인트에 Co-tidal 값 저장
        nav.spr_range = spr_range
        nav.msl = msl
        nav.mhwi = mhwi

        # [3] 기준항별 조석보정 계산
        corrections = []
        tide_type = self.config.tide_series_type

        for sw in idw_weights:
            station = self.stations[sw.station_idx]
            corr = StationCorrection(
                station_name=sw.station_name,
                arr_idx=sw.station_idx,
                weight=sw.weight,
            )

            # 조위 시계열 선택
            if tide_type == '예측':
                tide_series = station.tide_pred
            else:
                tide_series = station.tide_obs

            if tide_series is None:
                corr.estim_height = -999.0
                corr.weight = 0.0
                corrections.append(corr)
                continue

            # HRatio = SprRange_point / SprRange_station
            if station.spr_range <= 0 or station.spr_range == -999.9:
                corr.estim_height = -999.0
                corr.weight = 0.0
                corrections.append(corr)
                continue

            corr.h_ratio = spr_range / station.spr_range

            # TimeCorrector = MHWI_point - MHWI_station (hours)
            corr.time_corrector = mhwi - station.mhwi

            # 보정 시간 계산 (일반화된 UTC 오프셋 방식)
            # correctedTime = obsTime + (9 - utc_offset) - TimeCorrector
            corr.corrected_time = nav.t + timedelta(
                hours=self._time_shift - corr.time_corrector
            )

            # 조위 조회 (±2분 이내)
            level = find_level_value(tide_series, corr.corrected_time)

            if level is None:
                corr.org_height = -998.0
                corr.estim_height = -999.0
                corr.weight = 0.0
            else:
                corr.org_height = level
                corr.estim_height = level * corr.h_ratio

                # EstimHeight 유효성 검사
                if corr.estim_height <= -999.0:
                    corr.weight = 0.0

            corrections.append(corr)

        # [4] 가중평균 (상위 RankLimit개)
        rank_limit = min(self.config.rank_limit, 10)
        valid_corrections = [
            c for c in corrections
            if c.weight > 0 and c.estim_height > -999.0
        ][:rank_limit]

        if not valid_corrections:
            self.last_corrections = corrections[:rank_limit]
            return -999.0

        # Tc = Σ(EstimHeight × Weight) / Σ(Weight)
        sum_weighted = sum(c.estim_height * c.weight for c in valid_corrections)
        sum_weights = sum(c.weight for c in valid_corrections)

        if sum_weights <= 0:
            self.last_corrections = corrections[:rank_limit]
            return -999.0

        tc = sum_weighted / sum_weights

        # C# 원본: Math.Round(tc, 2) — cm 단위에서 소수점 2자리
        tc = round(tc, 2)

        self.last_corrections = corrections[:rank_limit]
        return tc

    def process_all(self, nav_points: List[NavPoint],
                    progress_callback=None) -> Tuple[List[NavPoint], List[List[StationCorrection]]]:
        """
        모든 Nav 포인트를 처리한다.

        참조: frmMain.cs Calib4File (lines 5520-5591)

        TimeIntervalSec 필터링:
        - 0: 모든 포인트 처리
        - >0: 이전 출력으로부터 해당 초 이상 경과한 포인트만

        Args:
            nav_points: 전체 NavPoint 리스트
            progress_callback: 진행률 콜백 (current, total)

        Returns:
            (처리된 NavPoint 리스트, 각 포인트별 StationCorrection 리스트)
        """
        processed = []
        all_corrections = []
        interval = self.config.time_interval_sec
        last_output_time = None
        total = len(nav_points)
        error_count = 0

        logger.info(f"조석보정 시작: {total}개 Nav 포인트 (UTC offset: {self._utc_offset:+.1f}h)")

        for i, nav in enumerate(nav_points):
            # TimeIntervalSec 필터링
            if interval > 0 and last_output_time is not None:
                delta = (nav.t - last_output_time).total_seconds()
                if delta < interval:
                    continue

            # 조석보정 계산
            tc = self.process_nav_point(nav)
            nav.tc = tc

            if tc <= -999.0:
                error_count += 1

            processed.append(nav)
            all_corrections.append(list(self.last_corrections))
            last_output_time = nav.t

            # 진행률 보고 (50포인트마다 — 더 자주 갱신)
            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(i + 1, total)

        # 최종 진행률 보고
        if progress_callback:
            progress_callback(total, total)

        logger.info(f"조석보정 완료: {len(processed)}개 처리 / {error_count}개 오류")
        return processed, all_corrections
