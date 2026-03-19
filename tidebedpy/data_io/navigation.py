"""
navigation.py - Nav file parsing (multi-format, maximum flexibility)

Supported formats (auto-detected):
- Format 1 (After):  YYYY-DDD HH:MM:SS.sss  Lat  Lon  [Depth]  [HexID]
- Format 2 (Legacy): SeqNo YYYY MM DD Seconds Lat Lon ...
- Format 3 (Before): Lat Lon YYYY-DDD HH:MM:SS.sss
- Format 4 (CSV):    Header-based auto-detection (Lat/Lon/Time columns)
- Format 5 (ISO):    YYYY-MM-DD HH:MM:SS  Lat  Lon  [...]
- Format 6 (Generic): Any Lat/Lon + datetime combination (auto-detect column order)

Reference: frmMain.cs chkNavFormat, getTimePosfromNavLine, getTimePosfromNavLine2
"""

import os
import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# Column name patterns for header-based detection (case-insensitive)
LAT_PATTERNS = ['lat', 'latitude', 'y', 'northing', 'lat_wgs84']
LON_PATTERNS = ['lon', 'lng', 'longitude', 'x', 'easting', 'lon_wgs84', 'long']
TIME_PATTERNS = ['time', 'datetime', 'timestamp', 'date_time', 'utc', 'gps_time']
DATE_PATTERNS = ['date', 'day', 'survey_date']


@dataclass
class NavPoint:
    """Nav point data"""
    x: float = 0.0         # Longitude (C# convention: X = Lon)
    y: float = 0.0         # Latitude  (C# convention: Y = Lat)
    t: datetime = field(default_factory=datetime.now)
    tc: float = 0.0        # Tide correction (cm, set after processing)
    spr_range: float = 0.0 # Co-tidal SprRange (after processing)
    msl: float = 0.0       # Co-tidal MSL (after processing)
    mhwi: float = 0.0      # Co-tidal MHWI (after processing)
    is_valid: bool = True


def _is_numeric(s: str) -> bool:
    """Check if string is numeric (GnrlFunctions.cs IsNumeric)"""
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_doy_date(s: str) -> bool:
    """Check if string matches YYYY-DDD format"""
    if '-' not in s:
        return False
    parts = s.split('-')
    if len(parts) != 2:
        return False
    try:
        year = int(parts[0])
        doy = int(parts[1])
        return 1900 <= year <= 2100 and 1 <= doy <= 366
    except ValueError:
        return False


def _is_time_str(s: str) -> bool:
    """Check if string matches HH:MM:SS[.sss] format"""
    if ':' not in s:
        return False
    parts = s.split(':')
    if len(parts) < 2:
        return False
    try:
        h = int(parts[0])
        m = int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def _is_iso_datetime(s: str) -> bool:
    """Check if string matches YYYY-MM-DD or YYYY/MM/DD format"""
    for fmt in [r'\d{4}-\d{2}-\d{2}', r'\d{4}/\d{2}/\d{2}']:
        if re.match(fmt, s):
            return True
    return False


def _is_coord(s: str, min_val: float = -180, max_val: float = 180) -> bool:
    """Check if string is a valid coordinate"""
    try:
        v = float(s)
        return min_val <= v <= max_val
    except ValueError:
        return False


def _is_lat(s: str) -> bool:
    """Check if string could be a latitude value"""
    return _is_coord(s, -90, 90)


def _is_lon(s: str) -> bool:
    """Check if string could be a longitude value"""
    return _is_coord(s, -180, 180)


def _smart_split(line: str) -> Tuple[List[str], str]:
    """
    Split line by auto-detected delimiter.
    Returns (fields, delimiter_type).
    """
    line = line.strip()
    if not line:
        return [], 'none'

    # Try comma first (CSV)
    if ',' in line:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 3:
            return parts, 'comma'

    # Tab
    if '\t' in line:
        parts = [p.strip() for p in line.split('\t')]
        if len(parts) >= 3:
            return parts, 'tab'

    # Semicolon
    if ';' in line:
        parts = [p.strip() for p in line.split(';')]
        if len(parts) >= 3:
            return parts, 'semicolon'

    # Whitespace (default)
    parts = re.split(r'\s+', line)
    return parts, 'space'


def detect_nav_format(line: str) -> int:
    """
    Detect nav line format.

    Reference: frmMain.cs chkNavFormat (lines 5145-5161)

    Format 1: YYYY-DDD HH:MM:SS.sss Lat Lon [Depth] [HexID]
    Format 2: SeqNo YYYY MM DD Seconds Lat Lon
    Format 3: Lat Lon YYYY-DDD HH:MM:SS.sss
    Format 5: YYYY-MM-DD HH:MM:SS Lat Lon [...]
    Format 6: Generic lat/lon + datetime

    Returns:
        Format ID (1, 2, 3, 5, 6) or 0 (unknown)
    """
    parts, delim = _smart_split(line)
    if len(parts) < 3:
        return 0

    # Format 1: YYYY-DDD HH:MM:SS.sss Lat Lon ...
    if len(parts) >= 4 and _is_doy_date(parts[0]) and _is_time_str(parts[1]):
        if _is_lat(parts[2]) and _is_lon(parts[3]):
            return 1

    # Format 3: Lat Lon YYYY-DDD HH:MM:SS.sss (Before format)
    if len(parts) >= 4 and _is_lat(parts[0]) and _is_lon(parts[1]):
        if _is_doy_date(parts[2]) and _is_time_str(parts[3]):
            return 3

    # Format 5: YYYY-MM-DD HH:MM:SS Lat Lon ...
    if len(parts) >= 4 and _is_iso_datetime(parts[0]) and _is_time_str(parts[1]):
        if _is_lat(parts[2]) and _is_lon(parts[3]):
            return 5

    # Format 5 variant: YYYY-MM-DDTHH:MM:SS Lat Lon (ISO combined)
    if len(parts) >= 3 and 'T' in parts[0] and _is_iso_datetime(parts[0].split('T')[0]):
        if _is_lat(parts[1]) and _is_lon(parts[2]):
            return 5

    # Format 2: SeqNo YYYY MM DD Seconds Lat Lon
    if len(parts) >= 7:
        try:
            year = int(parts[1])
            month = int(parts[2])
            if 1900 <= year <= 2100 and 1 <= month <= 12:
                return 2
        except (ValueError, IndexError):
            pass

    # Format 6: Generic - try to find lat/lon/time in any order
    has_coord = sum(1 for p in parts if _is_numeric(p) and abs(float(p)) <= 180) >= 2
    has_time = any(_is_time_str(p) or _is_iso_datetime(p) or _is_doy_date(p) for p in parts)
    if has_coord and has_time:
        return 6

    return 0


def _detect_header_columns(header_line: str) -> Optional[dict]:
    """
    Detect column indices from header line.
    Returns dict: {'lat': idx, 'lon': idx, 'time': idx, 'date': idx} or None
    """
    parts, delim = _smart_split(header_line)
    if len(parts) < 3:
        return None

    col_map = {}
    for i, col in enumerate(parts):
        col_lower = col.lower().strip('"\'')
        if any(pat == col_lower for pat in LAT_PATTERNS):
            col_map['lat'] = i
        elif any(pat == col_lower for pat in LON_PATTERNS):
            col_map['lon'] = i
        elif any(pat == col_lower for pat in TIME_PATTERNS):
            col_map['time'] = i
        elif any(pat == col_lower for pat in DATE_PATTERNS):
            col_map['date'] = i

    # Need at least lat and lon
    if 'lat' in col_map and 'lon' in col_map:
        return col_map

    return None


def _parse_format1(line: str) -> Optional[NavPoint]:
    """
    Format 1: YYYY-DDD HH:MM:SS.sss Lat Lon [Depth] [HexID]
    Reference: frmMain.cs getTimePosfromNavLine (lines 5095-5143)
    """
    from utils.time_utils import parse_doy_datetime

    parts, _ = _smart_split(line)
    if len(parts) < 4:
        return None

    try:
        dt = parse_doy_datetime(parts[0], parts[1])
        lat = float(parts[2])
        lon = float(parts[3])
        return NavPoint(x=lon, y=lat, t=dt)
    except (ValueError, IndexError) as e:
        logger.debug(f"Format 1 parse fail: {line.strip()} - {e}")
        return None


def _parse_format2(line: str) -> Optional[NavPoint]:
    """
    Format 2: SeqNo YYYY MM DD Seconds Lat Lon ...
    Reference: frmMain.cs getTimePosfromNavLine2
    """
    parts, _ = _smart_split(line)
    if len(parts) < 7:
        return None

    try:
        year = int(parts[1])
        month = int(parts[2])
        day = int(parts[3])
        seconds = float(parts[4])
        lat = float(parts[5])
        lon = float(parts[6])

        dt = datetime(year, month, day) + timedelta(seconds=seconds)
        return NavPoint(x=lon, y=lat, t=dt)
    except (ValueError, IndexError) as e:
        logger.debug(f"Format 2 parse fail: {line.strip()} - {e}")
        return None


def _parse_format3(line: str) -> Optional[NavPoint]:
    """
    Format 3 (Before/Raw): Lat Lon YYYY-DDD HH:MM:SS.sss
    Before files: column order is Lat Lon then Date Time
    """
    from utils.time_utils import parse_doy_datetime

    parts, _ = _smart_split(line)
    if len(parts) < 4:
        return None

    try:
        lat = float(parts[0])
        lon = float(parts[1])
        dt = parse_doy_datetime(parts[2], parts[3])
        return NavPoint(x=lon, y=lat, t=dt)
    except (ValueError, IndexError) as e:
        logger.debug(f"Format 3 parse fail: {line.strip()} - {e}")
        return None


def _parse_format5(line: str) -> Optional[NavPoint]:
    """
    Format 5: YYYY-MM-DD HH:MM:SS Lat Lon [...] or YYYY-MM-DDTHH:MM:SS Lat Lon
    ISO datetime format.
    """
    parts, _ = _smart_split(line)
    if len(parts) < 3:
        return None

    try:
        # Try combined ISO: YYYY-MM-DDTHH:MM:SS
        if 'T' in parts[0]:
            dt_str = parts[0]
            for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
                        '%Y/%m/%dT%H:%M:%S.%f', '%Y/%m/%dT%H:%M:%S']:
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    lat = float(parts[1])
                    lon = float(parts[2])
                    return NavPoint(x=lon, y=lat, t=dt)
                except ValueError:
                    continue

        # Separate date and time: YYYY-MM-DD HH:MM:SS Lat Lon
        if len(parts) >= 4:
            dt_str = parts[0] + ' ' + parts[1]
            for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S',
                        '%Y/%m/%d %H:%M:%S.%f', '%Y/%m/%d %H:%M:%S',
                        '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M']:
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    lat = float(parts[2])
                    lon = float(parts[3])
                    return NavPoint(x=lon, y=lat, t=dt)
                except ValueError:
                    continue
    except (ValueError, IndexError) as e:
        logger.debug(f"Format 5 parse fail: {line.strip()} - {e}")

    return None


def _parse_format6(line: str) -> Optional[NavPoint]:
    """
    Format 6: Generic - try to find lat/lon/time in any column order.
    Scans each field to identify its type.
    """
    from utils.time_utils import parse_doy_datetime

    parts, _ = _smart_split(line)
    if len(parts) < 3:
        return None

    lat = None
    lon = None
    dt = None

    # First pass: identify date/time fields
    for i, p in enumerate(parts):
        if _is_doy_date(p) and dt is None:
            # Next field should be time
            if i + 1 < len(parts) and _is_time_str(parts[i + 1]):
                try:
                    dt = parse_doy_datetime(p, parts[i + 1])
                except:
                    pass
        elif _is_iso_datetime(p) and dt is None:
            if i + 1 < len(parts) and _is_time_str(parts[i + 1]):
                dt_str = p + ' ' + parts[i + 1]
                for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S',
                            '%Y/%m/%d %H:%M:%S.%f', '%Y/%m/%d %H:%M:%S']:
                    try:
                        dt = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue
        elif 'T' in p and _is_iso_datetime(p.split('T')[0]) and dt is None:
            for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                try:
                    dt = datetime.strptime(p, fmt)
                    break
                except ValueError:
                    continue

    # Second pass: find lat/lon (numeric fields that aren't part of datetime)
    coords = []
    for i, p in enumerate(parts):
        if _is_numeric(p):
            val = float(p)
            # Skip if it's clearly not a coordinate
            if abs(val) > 180 or abs(val) < 0.001:
                continue
            coords.append((i, val))

    if len(coords) >= 2 and dt is not None:
        # Heuristic: first coord < 90 is lat, > 90 is lon (Korea)
        # Or first is lat, second is lon
        c1, c2 = coords[0][1], coords[1][1]
        if abs(c1) <= 90 and abs(c2) > 90:
            lat, lon = c1, c2
        elif abs(c2) <= 90 and abs(c1) > 90:
            lat, lon = c2, c1
        else:
            lat, lon = c1, c2

        return NavPoint(x=lon, y=lat, t=dt)

    return None


def _parse_csv_line(line: str, col_map: dict) -> Optional[NavPoint]:
    """
    Parse CSV line using column index map.
    """
    parts, _ = _smart_split(line)
    if len(parts) <= max(col_map.values()):
        return None

    try:
        lat = float(parts[col_map['lat']])
        lon = float(parts[col_map['lon']])

        dt = None

        # Combined datetime column
        if 'time' in col_map:
            dt_str = parts[col_map['time']]
            # Also append date column if separate
            if 'date' in col_map and col_map['date'] != col_map['time']:
                dt_str = parts[col_map['date']] + ' ' + dt_str

            for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S',
                        '%Y/%m/%d %H:%M:%S.%f', '%Y/%m/%d %H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M',
                        '%Y-%m-%d', '%Y/%m/%d',
                        '%d/%m/%Y %H:%M:%S', '%m/%d/%Y %H:%M:%S']:
                try:
                    dt = datetime.strptime(dt_str.strip(), fmt)
                    break
                except ValueError:
                    continue

        elif 'date' in col_map:
            dt_str = parts[col_map['date']]
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
                        '%Y-%m-%d', '%Y/%m/%d']:
                try:
                    dt = datetime.strptime(dt_str.strip(), fmt)
                    break
                except ValueError:
                    continue

        if dt is None:
            return None

        return NavPoint(x=lon, y=lat, t=dt)

    except (ValueError, IndexError, KeyError) as e:
        logger.debug(f"CSV parse fail: {line.strip()} - {e}")
        return None


def parse_nav_line(line: str, format_id: int, col_map: dict = None) -> Optional[NavPoint]:
    """Parse nav line by format ID"""
    if format_id == 1:
        return _parse_format1(line)
    elif format_id == 2:
        return _parse_format2(line)
    elif format_id == 3:
        return _parse_format3(line)
    elif format_id == 4 and col_map:
        return _parse_csv_line(line, col_map)
    elif format_id == 5:
        return _parse_format5(line)
    elif format_id == 6:
        return _parse_format6(line)
    return None


FORMAT_NAMES = {
    0: 'Unknown',
    1: 'After (YYYY-DDD HH:MM:SS Lat Lon)',
    2: 'Legacy (SeqNo YYYY MM DD Sec Lat Lon)',
    3: 'Before (Lat Lon YYYY-DDD HH:MM:SS)',
    4: 'CSV (header-based)',
    5: 'ISO (YYYY-MM-DD HH:MM:SS Lat Lon)',
    6: 'Generic (auto-detected)',
}


def load_nav_file(file_path: str) -> List[NavPoint]:
    """
    Load a single nav file with auto-format detection.

    Supports any delimiter (space, tab, comma, semicolon).
    Supports with or without header row.
    Supports multiple coordinate/datetime formats.

    Reference: frmMain.cs Calib4File (lines 5520-5591)

    Args:
        file_path: Nav file path

    Returns:
        List of NavPoint
    """
    from utils.encoding import read_lines

    lines = read_lines(file_path)
    if not lines:
        return []

    # Step 1: Check for CSV header
    col_map = None
    header_line_idx = -1
    if lines:
        col_map = _detect_header_columns(lines[0])
        if col_map:
            header_line_idx = 0
            logger.debug(f"CSV header detected: {col_map} ({file_path})")

    # Step 2: Detect format from first data line
    format_id = 0
    start_idx = header_line_idx + 1 if col_map else 0

    if col_map:
        format_id = 4
    else:
        for line in lines[start_idx:]:
            line = line.strip()
            if not line:
                continue
            fmt = detect_nav_format(line)
            if fmt > 0:
                format_id = fmt
                break

    if format_id == 0:
        logger.warning(f"Nav format detection failed: {file_path}")
        return []

    logger.debug(f"Nav format: {FORMAT_NAMES.get(format_id, 'Unknown')} ({file_path})")

    # Step 3: Parse all lines
    points = []
    for i, line in enumerate(lines):
        if i <= header_line_idx:
            continue
        line = line.strip()
        if not line:
            continue

        point = parse_nav_line(line, format_id, col_map)
        if point:
            points.append(point)

    logger.info(f"Nav file loaded: {len(points)} points ({os.path.basename(file_path)}) "
                f"[{FORMAT_NAMES.get(format_id, '?')}]")
    return points


def load_nav_directory(directory: str) -> List[NavPoint]:
    """
    Load all nav files from directory and sort by time.

    Supports mixed file extensions: .txt, .csv, .tsv, .nav, .dat

    Args:
        directory: Nav file directory path

    Returns:
        Time-sorted NavPoint list
    """
    if not os.path.isdir(directory):
        logger.error(f"Nav directory not found: {directory}")
        return []

    supported_ext = ('.txt', '.csv', '.tsv', '.nav', '.dat')
    all_points = []
    files = sorted([f for f in os.listdir(directory)
                     if f.lower().endswith(supported_ext)])

    logger.info(f"Nav directory scan: {len(files)} files ({directory})")

    for fname in files:
        fpath = os.path.join(directory, fname)
        points = load_nav_file(fpath)
        all_points.extend(points)

    # Time sort
    all_points.sort(key=lambda p: p.t)

    logger.info(f"Nav total loaded: {len(all_points)} points")
    if all_points:
        logger.info(f"  Time range: {all_points[0].t} ~ {all_points[-1].t}")

    return all_points


def load_nav_files(file_paths: List[str]) -> List[NavPoint]:
    """
    Load specific nav files (not a directory).
    Useful for GUI where user selects individual files.

    Args:
        file_paths: List of file paths

    Returns:
        Time-sorted NavPoint list
    """
    all_points = []
    for fpath in file_paths:
        if os.path.isfile(fpath):
            points = load_nav_file(fpath)
            all_points.extend(points)

    all_points.sort(key=lambda p: p.t)
    logger.info(f"Nav files loaded: {len(all_points)} points from {len(file_paths)} files")
    return all_points
