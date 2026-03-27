"""
geodesy.py - Vincenty 측지 거리 계산

WGS84 타원체 위의 두 점 사이 거리를 계산한다.
geographiclib 라이브러리 사용 (deprecated geopy.vincenty 대체).

참조: Gavaghan.Geodesy/GeodeticCalculator.cs (Vincenty inverse formula)
"""

from geographiclib.geodesic import Geodesic
from core.error_codes import DistError

# WGS84 타원체 (C# 원본: Ellipsoid.WGS84)
# a = 6,378,137 m, 1/f = 298.257223563
_geod = Geodesic.WGS84


def vincenty_inverse(lon1: float, lat1: float,
                     lon2: float, lat2: float) -> float:
    """
    두 점 사이의 측지 거리를 미터로 계산한다 (WGS84).

    참조: frmMain.cs Vincenty_Inverse (lines 4646-4671)
    C# 함수 시그니처: Vincenty_Inverse(Lon1, Lat1, Lon2, Lat2)
    geographiclib: Inverse(lat1, lon1, lat2, lon2)

    Args:
        lon1, lat1: 첫 번째 점의 경도, 위도 (degrees)
        lon2, lat2: 두 번째 점의 경도, 위도 (degrees)

    Returns:
        측지 거리 (meters). 오류 시 DistError.FAIL
    """
    try:
        result = _geod.Inverse(lat1, lon1, lat2, lon2)
        return result['s12']  # 거리 (meters)
    except Exception:
        return DistError.FAIL
