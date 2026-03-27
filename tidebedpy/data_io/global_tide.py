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
            "pyTMD 라이브러리가 설치되지 않았습니다.\n"
            "설치: pip install pyTMD\n"
            "글로벌 조석 모델을 사용하려면 pyTMD와 모델 데이터가 필요합니다."
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

    try:
        # pyTMD v2.x API
        from pyTMD.compute import tide_elevations

        # Convert datetimes to pyTMD time format
        tide_m = tide_elevations(
            lon_arr, lat_arr, times,
            DIRECTORY=model_dir,
            MODEL=pytmd_model,
            EPSG=4326,
            TYPE='drift',
        )

        # Convert from meters to centimeters
        tide_cm = (np.array(tide_m) * 100.0).tolist()

    except ImportError:
        # Fallback: try pyTMD v1.x API
        try:
            from pyTMD.predict import predict_tide
            from pyTMD.read_tide_model import read_tide_model
            from pyTMD.time import convert_datetime

            # Convert datetime to pyTMD delta times
            delta_time = convert_datetime(np.array(times))

            # Read model constituents
            amp, ph, c = read_tide_model(
                model_dir, model_file=pytmd_model,
                EPSG=4326, TYPE='z',
            )

            # Predict
            tide_m = predict_tide(
                delta_time, amp, ph,
                DELTAT=0.0, CORRECTIONS='GOT',
            )
            tide_cm = (np.array(tide_m) * 100.0).tolist()

        except Exception as e:
            logger.error(f"pyTMD v1.x fallback 실패: {e}")
            raise

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
