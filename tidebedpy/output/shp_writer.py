"""Write correction results as ESRI Shapefile (.shp/.shx/.dbf)."""

import csv
import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",'
    'DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]]'
)


def write_correction_shp(
    output_path: str,
    points: List[Tuple[float, float, str, float]],
    station_names: Optional[List[str]] = None,
) -> str:
    """
    Write nav correction points as a point shapefile.

    Args:
        output_path: Base path (without extension).
                     Creates .shp, .shx, .dbf, .prj
        points: List of (lon, lat, time_iso, tc_cm)
        station_names: Optional list of station names used

    Returns:
        Actual output path (.shp or .csv if fallback)
    """
    if not points:
        logger.warning("Shapefile: 포인트가 없습니다")
        return ""

    try:
        import shapefile  # pyshp
    except ImportError:
        logger.warning(
            "pyshp 미설치 -- Shapefile 대신 CSV로 출력합니다"
        )
        return _write_csv_fallback(output_path, points, station_names)

    w = shapefile.Writer(output_path)
    w.field('Time', 'C', 20)
    w.field('Tc_cm', 'N', 10, 2)
    w.field('Lon', 'N', 12, 6)
    w.field('Lat', 'N', 12, 6)

    for lon, lat, time_str, tc in points:
        w.point(lon, lat)
        w.record(time_str, tc, lon, lat)

    w.close()

    # Write .prj (WGS84)
    prj_path = output_path + ".prj"
    with open(prj_path, 'w') as f:
        f.write(_WGS84_PRJ)

    logger.info(f"Shapefile 생성: {output_path}.shp ({len(points)} pts)")
    return output_path + ".shp"


def _write_csv_fallback(
    output_path: str,
    points: List[Tuple[float, float, str, float]],
    station_names: Optional[List[str]] = None,
) -> str:
    """Fallback CSV writer when pyshp is not available."""
    csv_path = output_path + ".shp.csv"
    os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Longitude', 'Latitude', 'Time', 'Tc_cm'])
        for lon, lat, time_str, tc in points:
            writer.writerow([f'{lon:.6f}', f'{lat:.6f}', time_str, f'{tc:.2f}'])

    logger.info(
        f"Shapefile fallback CSV: {csv_path} ({len(points)} pts)"
    )
    return csv_path
