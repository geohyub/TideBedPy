"""
global_tide.py - Global tidal model prediction via pyTMD.

Wraps pyTMD for overseas tidal prediction using FES2014, TPXO9 etc.
Used when the KHOA Co-tidal DB does not cover the survey area.

References:
    https://github.com/tsutterley/pyTMD
"""

import logging
from datetime import datetime
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def predict_tide_pytmd(
    lons: List[float],
    lats: List[float],
    times: List[datetime],
    model: str = 'FES2014',
    model_dir: Optional[str] = None,
) -> List[float]:
    """
    Predict tidal heights using pyTMD global models.

    Args:
        lons: Longitudes (degrees) for each point.
        lats: Latitudes (degrees) for each point.
        times: Datetime objects for each point.
        model: Model name — 'FES2014' or 'TPXO9'.
        model_dir: Path to the model data directory.
            If None, pyTMD uses its default data directory.

    Returns:
        List of tide heights in cm (same unit as TideBedPy internal).

    Raises:
        ImportError: If pyTMD is not installed.
        ValueError: If model is unsupported.
        FileNotFoundError: If model directory does not exist.
    """
    try:
        import pyTMD
    except ImportError:
        raise ImportError(
            "pyTMD 미설치. 글로벌 조석 모델(FES2014/TPXO9) 사용을 위해 설치하세요:\n"
            "  pip install pyTMD\n"
            "모델 데이터는 별도 다운로드 필요:\n"
            "  FES2014: https://www.aviso.altimetry.fr/en/data/products/auxiliary-products/global-tide-fes.html\n"
            "  TPXO9: https://www.tpxo.net/global/tpxo9-atlas"
        )

    import os
    if model_dir and not os.path.isdir(model_dir):
        raise FileNotFoundError(
            f"모델 데이터 디렉토리를 찾을 수 없습니다: {model_dir}"
        )

    # Map model name to pyTMD model identifier
    model_map = {
        'FES2014': 'FES2014',
        'TPXO9': 'TPXO9-atlas-v5',
    }
    pytmd_model = model_map.get(model)
    if pytmd_model is None:
        raise ValueError(
            f"지원하지 않는 모델: {model}. "
            f"사용 가능: {', '.join(model_map.keys())}"
        )

    logger.info(
        f"pyTMD 예측 시작: model={model}, points={len(lons)}"
    )

    lon_arr = np.array(lons, dtype=np.float64)
    lat_arr = np.array(lats, dtype=np.float64)

    # Convert Python datetimes to numpy datetime64 for pyTMD
    delta_time = np.array(times, dtype="datetime64[us]")

    try:
        from pyTMD.compute import tide_elevations

        # pyTMD v3.x uses lowercase parameter names;
        # v2.x uses UPPERCASE.  Try v3 first, fall back to v2.
        try:
            tide_m = tide_elevations(
                lon_arr, lat_arr, delta_time,
                directory=model_dir,
                model=pytmd_model,
                EPSG=4326,
                TYPE='drift',
            )
        except TypeError:
            # v2.x uppercase parameters
            tide_m = tide_elevations(
                lon_arr, lat_arr, delta_time,
                DIRECTORY=model_dir,
                MODEL=pytmd_model,
                EPSG=4326,
                TYPE='drift',
            )

        # Convert from meters to centimeters
        tide_cm = (np.asarray(tide_m, dtype=float) * 100.0).tolist()

    except ImportError as e:
        logger.error(f"pyTMD.compute 임포트 실패: {e}")
        raise ImportError(
            "pyTMD.compute.tide_elevations을 임포트할 수 없습니다.\n"
            "pyTMD >= 2.0 이 필요합니다: pip install pyTMD"
        ) from e

    except Exception as e:
        logger.error(f"pyTMD 예측 실패: {e}")
        raise

    # Replace NaN with error code
    result = []
    for val in tide_cm:
        if np.isnan(val) or np.isinf(val):
            result.append(-999.0)
        else:
            result.append(round(val, 2))

    valid = sum(1 for v in result if v > -999.0)
    logger.info(
        f"pyTMD 예측 완료: {valid}/{len(result)} 유효"
    )

    return result
