"""
map_view.py - 기준항/항적 위치 지도 시각화

해안선 shapefile 기반 지도 위에 기준항과 항적을 표시한다.
사용된 기준항을 강조하고, 미사용 기준항은 희미하게 표시.

Original: TideBedLite v1.05, Copyright (c) 2014 KHOA / GeoSR
Python:   Junhyub, 2025
"""

import os
import struct
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe
    from matplotlib.colors import Normalize
    from matplotlib.ticker import AutoMinorLocator, FuncFormatter
    from matplotlib.collections import LineCollection
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ── 폰트 초기화 ─────────────────────────────────────────────
_FONT_READY = False

def _init_fonts():
    global _FONT_READY
    if _FONT_READY or not HAS_MATPLOTLIB:
        return
    _FONT_READY = True
    import matplotlib.font_manager as fm
    fonts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')
    registered = False
    for name in ('Pretendard-Regular.otf', 'Pretendard-Bold.otf',
                 'Pretendard-SemiBold.otf'):
        fp = os.path.join(fonts_dir, name)
        if os.path.isfile(fp):
            fm.fontManager.addfont(fp)
            registered = True
    if registered:
        plt.rcParams['font.family'] = 'Pretendard'
    else:
        available = {f.name for f in fm.fontManager.ttflist}
        for fc in ['Malgun Gothic', '맑은 고딕', 'NanumGothic']:
            if fc in available:
                plt.rcParams['font.family'] = fc
                break
    plt.rcParams['axes.unicode_minus'] = False

if HAS_MATPLOTLIB:
    _init_fonts()


# ── 색상 팔레트 ─────────────────────────────────────────────
class _C:
    LAND       = '#F5F0E8'
    LAND_EDGE  = '#C8B89A'
    OCEAN      = '#E8F1F8'
    GRID       = '#D4E4F0'
    GRID_MINOR = '#E8EFF5'
    USED_ST    = '#D32F2F'
    UNUSED_ST  = '#B0BEC5'
    NAV_LINE   = '#1565C0'
    NAV_START  = '#2E7D32'
    NAV_END    = '#E65100'
    ORANGE     = '#FB8C00'
    TEXT       = '#37474F'
    TITLE      = '#1A237E'
    FRAME      = '#90CAF9'


# ══════════════════════════════════════════════════════════════
#  해안선 SHP 리더 (의존성 없이 .shp 직접 파싱)
# ══════════════════════════════════════════════════════════════
def _read_shp_polygons(shp_path: str,
                       clip_bbox: Tuple[float, float, float, float] = None
                       ) -> List[List[Tuple[float, float]]]:
    """
    .shp 파일에서 폴리곤 좌표를 읽는다 (companion 파일 불필요).
    clip_bbox=(lon_min, lat_min, lon_max, lat_max) 범위만 반환.
    """
    polygons = []
    try:
        with open(shp_path, 'rb') as f:
            # Header (100 bytes)
            file_code = struct.unpack('>i', f.read(4))[0]
            if file_code != 9994:
                return polygons
            f.seek(24)
            file_length = struct.unpack('>i', f.read(4))[0] * 2
            f.seek(32)
            shape_type = struct.unpack('<i', f.read(4))[0]
            f.seek(100)

            # Records
            while f.tell() < file_length:
                try:
                    rec_data = f.read(8)
                    if len(rec_data) < 8:
                        break
                    rec_num, rec_len = struct.unpack('>ii', rec_data)
                    rec_len *= 2
                    rec_start = f.tell()

                    st = struct.unpack('<i', f.read(4))[0]
                    if st == 0:  # null shape
                        f.seek(rec_start + rec_len)
                        continue

                    if st in (3, 5):  # Polyline or Polygon
                        bbox = struct.unpack('<4d', f.read(32))
                        # bbox = (xmin, ymin, xmax, ymax)

                        # 클리핑: bbox가 관심 영역과 겹치지 않으면 skip
                        if clip_bbox:
                            if (bbox[2] < clip_bbox[0] or bbox[0] > clip_bbox[2] or
                                bbox[3] < clip_bbox[1] or bbox[1] > clip_bbox[3]):
                                f.seek(rec_start + rec_len)
                                continue

                        num_parts = struct.unpack('<i', f.read(4))[0]
                        num_points = struct.unpack('<i', f.read(4))[0]
                        parts = list(struct.unpack(f'<{num_parts}i',
                                                   f.read(4 * num_parts)))
                        points = []
                        for _ in range(num_points):
                            x, y = struct.unpack('<2d', f.read(16))
                            points.append((x, y))

                        # 파트별로 분리 + point-level clip
                        for i in range(num_parts):
                            start = parts[i]
                            end = parts[i + 1] if i + 1 < num_parts else num_points
                            ring = points[start:end]
                            if len(ring) < 3:
                                continue
                            if clip_bbox:
                                rxs = [p[0] for p in ring]
                                rys = [p[1] for p in ring]
                                ring_xmin, ring_xmax = min(rxs), max(rxs)
                                ring_ymin, ring_ymax = min(rys), max(rys)
                                # Skip rings completely outside bbox
                                if (ring_xmax < clip_bbox[0] or ring_xmin > clip_bbox[2] or
                                    ring_ymax < clip_bbox[1] or ring_ymin > clip_bbox[3]):
                                    continue
                                # Do NOT filter individual points — this breaks polygon shapes
                            polygons.append(ring)
                    else:
                        f.seek(rec_start + rec_len)

                except (struct.error, EOFError):
                    break

    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"해안선 파일 읽기 실패: {e}")

    return polygons


def _find_coastline_shp() -> Optional[str]:
    """해안선 shapefile 경로를 자동 탐색한다."""
    # 가능한 경로들
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base, 'info', '해안선', 'fareast_merge.shp'),
        os.path.join(base, '..', 'info', '해안선', 'fareast_merge.shp'),
        # 원본 TideBed 폴더
        os.path.expanduser(r'~\Desktop\TideBed (2)\info\해안선\fareast_merge.shp'),
        r'C:\Users\JWONLINETEAM\Desktop\TideBed (2)\info\해안선\fareast_merge.shp',
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            return p
    return None


# ══════════════════════════════════════════════════════════════
#  축 포맷 유틸
# ══════════════════════════════════════════════════════════════
def _fmt_lon(x, _):
    d = int(x)
    m = abs(x - d) * 60
    return f"{d}°{m:04.1f}'"

def _fmt_lat(x, _):
    d = int(x)
    m = abs(x - d) * 60
    return f"{d}°{m:04.1f}'"


def _draw_coastline(ax, bbox_expand: Tuple[float, float, float, float]):
    """해안선을 그린다. bbox_expand는 확장된 표시 범위."""
    shp_path = _find_coastline_shp()
    if not shp_path:
        logger.debug("해안선 shapefile 없음 — 생략")
        return False

    polys = _read_shp_polygons(shp_path, clip_bbox=bbox_expand)
    if not polys:
        return False

    for ring in polys:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        ax.fill(xs, ys, color=_C.LAND, edgecolor=_C.LAND_EDGE,
                linewidth=0.6, zorder=1, alpha=0.95)

    return True


def _draw_compass(ax, x=0.96, y=0.94, size=0.06):
    """컴팩트한 방위 표시"""
    ax.annotate('',
                xy=(x, y), xycoords='axes fraction',
                xytext=(x, y - size), textcoords='axes fraction',
                arrowprops=dict(arrowstyle='->', color=_C.TITLE, lw=2),
                zorder=20)
    ax.text(x, y + 0.01, 'N', transform=ax.transAxes,
            fontsize=12, fontweight='bold', color=_C.TITLE,
            ha='center', va='bottom', zorder=20,
            path_effects=[pe.withStroke(linewidth=3, foreground='white')])


def _load_summary_for_output(output_image: str) -> Optional[dict]:
    """Resolve the TID base path from a map image path and load its summary."""
    try:
        from tidebedpy.output.summary import load_summary_file
    except Exception:
        try:
            from output.summary import load_summary_file
        except Exception:
            return None

    candidates = []
    for suffix in ('.corrmap.png', '.map.png', '.compare.png', '.png'):
        if output_image.endswith(suffix):
            candidates.append(output_image[:-len(suffix)])

    stem, _ = os.path.splitext(output_image)
    candidates.append(stem)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            summary = load_summary_file(candidate)
        except Exception:
            summary = None
        if summary:
            return summary
    return None


def _build_map_brief_lines(summary: Optional[dict], max_lines: int = 6) -> List[str]:
    """Build short interpretation lines for map outputs."""
    if not summary:
        return []

    lines: List[str] = []
    headline = str(summary.get('headline', '')).strip()
    if headline:
        lines.append(headline)

    settings = summary.get('settings', {})
    preset_name = settings.get('preset_name')
    preset_summary = settings.get('preset_summary')
    if preset_name and preset_summary:
        lines.append(f"프리셋: {preset_name} - {preset_summary}")
    elif preset_name:
        lines.append(f"프리셋: {preset_name}")
    elif preset_summary:
        lines.append(f"프리셋 의미: {preset_summary}")

    story = summary.get('story', {})
    for section_name in ('workflow', 'quality'):
        section_lines = story.get(section_name, [])
        if section_lines:
            lines.append(str(section_lines[0]))

    contributors = summary.get('contributors', [])[:2]
    if contributors:
        lines.append(
            "주요 기준항: "
            + ", ".join(
                f"{item['station_name']} ({item['coverage_pct']:.1f}%)"
                for item in contributors
            )
        )

    guidance = story.get('guidance', [])
    if guidance:
        lines.append(f"읽는 방법: {guidance[0]}")

    trimmed = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        if len(text) > 130:
            text = text[:127].rstrip() + '...'
        trimmed.append(text)
        if len(trimmed) >= max_lines:
            break
    return trimmed


def _add_brief_box(ax, lines: List[str], *, loc: str = 'lower left') -> None:
    """Add a compact interpretation box inside a map or chart."""
    if not lines:
        return

    x = 0.98 if 'right' in loc else 0.02
    ha = 'right' if 'right' in loc else 'left'
    y = 0.98 if 'upper' in loc else 0.02
    va = 'top' if 'upper' in loc else 'bottom'
    ax.text(
        x,
        y,
        '\n'.join(lines),
        transform=ax.transAxes,
        fontsize=8,
        ha=ha,
        va=va,
        color=_C.TEXT,
        bbox=dict(boxstyle='round,pad=0.55', fc='white', ec='#CCD7E0', alpha=0.95),
        zorder=18,
    )


def _add_colored_track(ax, lons, lats, values, *, linewidth=2.2, alpha=0.65, zorder=4):
    """Draw a continuous navigation track colored by Tc."""
    if len(lons) < 2 or len(lats) < 2 or len(values) < 2:
        return None

    points = np.column_stack([lons, lats]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    track_values = np.asarray(values[:-1], dtype=float)
    if track_values.size == 0:
        return None

    vmin = float(np.nanmin(track_values))
    vmax = float(np.nanmax(track_values))
    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-6

    collection = LineCollection(
        segments,
        cmap='coolwarm',
        norm=Normalize(vmin=vmin, vmax=vmax),
        linewidths=linewidth,
        alpha=alpha,
        zorder=zorder,
    )
    collection.set_array(track_values)
    ax.add_collection(collection)
    return collection


def _annotate_series_extrema(ax, times, values, *, unit='cm') -> None:
    """Mark min/max points on a time-series panel."""
    if not times or not values:
        return

    min_idx = int(np.argmin(values))
    max_idx = int(np.argmax(values))
    markers = [
        (min_idx, '최소', _C.NAV_END, 'top'),
        (max_idx, '최대', _C.NAV_START, 'bottom'),
    ]

    for idx, label, color, valign in markers:
        ax.scatter([times[idx]], [values[idx]], color=color, s=26, zorder=6,
                   edgecolors='white', linewidths=0.8)
        offset = -16 if valign == 'top' else 12
        ax.annotate(
            f"{label}: {values[idx]:.1f} {unit}",
            xy=(times[idx], values[idx]),
            xytext=(8, offset),
            textcoords='offset points',
            fontsize=7.5,
            color=color,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.25', fc='white', ec=color, alpha=0.9),
            arrowprops=dict(arrowstyle='-', color=color, lw=0.8, alpha=0.7),
            zorder=7,
        )


def _identify_used_stations(stations, nav_points, all_corrections=None,
                            threshold_deg=0.5):
    """
    실제 보정에 사용된 기준항을 식별한다.

    1) 조위 데이터가 로드된 기준항 (tide_obs/tide_pred 존재) — 가장 정확
    2) all_corrections 보정 결과에서 가중치>0인 기준항 추가 (합집합)
    3) 위 둘 다 없으면 → 거리 기반 fallback (최후 수단)
    """
    used = set()

    # ── 방법 1: 조위 데이터가 로드된 기준항 (가장 정확) ──
    for i, s in enumerate(stations):
        if s.longitude <= -900 or s.latitude <= -900:
            continue
        if getattr(s, 'tide_obs', None) is not None or \
           getattr(s, 'tide_pred', None) is not None:
            used.add(i)

    # ── 방법 2: all_corrections에서 실제 사용 기준항 추가 (합집합) ──
    if all_corrections:
        for corr_list in all_corrections:
            for c in corr_list:
                if c.weight > 0 and c.estim_height > -999.0:
                    used.add(c.arr_idx)

    if used:
        return used

    # ── 방법 3: 거리 기반 fallback (최후 수단) ──
    if not nav_points:
        return set()

    nav_lons = [p.x for p in nav_points if p.x != 0]
    nav_lats = [p.y for p in nav_points if p.x != 0]
    if not nav_lons:
        return set()

    nav_cx = (min(nav_lons) + max(nav_lons)) / 2
    nav_cy = (min(nav_lats) + max(nav_lats)) / 2
    nav_radius = max(
        max(nav_lons) - min(nav_lons),
        max(nav_lats) - min(nav_lats)
    ) / 2 + threshold_deg

    used = set()
    for i, s in enumerate(stations):
        if s.longitude <= -900 or s.latitude <= -900:
            continue
        dist = ((s.longitude - nav_cx) ** 2 + (s.latitude - nav_cy) ** 2) ** 0.5
        if dist <= nav_radius:
            used.add(i)

    return used


# ══════════════════════════════════════════════════════════════
#  메인 지도 생성
# ══════════════════════════════════════════════════════════════
def generate_station_map(stations, nav_points=None,
                         output_image: str = None,
                         title: str = None,
                         figsize: tuple = (14, 11),
                         dpi: int = 150,
                         all_corrections=None) -> Optional[str]:
    """
    기준항 위치와 항적 데이터를 해안선 지도 위에 표시한다.
    사용 기준항은 크게 강조, 미사용 기준항은 작게 희미하게 표시.

    Args:
        all_corrections: 보정 엔진의 StationCorrection 리스트.
                         제공되면 실제 사용된 기준항만 표시.
    """
    if not HAS_MATPLOTLIB:
        return None
    if not stations:
        return None

    _init_fonts()

    if output_image is None:
        output_image = 'station_map.png'
    summary = _load_summary_for_output(output_image)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor('white')

    # ── 좌표 추출 ──
    all_st = [(i, s) for i, s in enumerate(stations) if s.longitude > -900]
    st_lons = [s.longitude for _, s in all_st]
    st_lats = [s.latitude for _, s in all_st]
    st_names = [s.name for _, s in all_st]
    st_indices = [i for i, _ in all_st]

    nav_lons, nav_lats, nav_tc = [], [], []
    if nav_points:
        for p in nav_points:
            if p.x != 0 and p.y != 0:
                nav_lons.append(p.x)
                nav_lats.append(p.y)
                nav_tc.append(p.tc if p.tc > -999 else 0)

    # ── 사용 기준항 식별 ──
    used_set = _identify_used_stations(stations, nav_points, all_corrections)

    # ── 범위 결정 (항적 중심으로 줌) ──
    if nav_lons:
        # 항적 범위 + 사용 기준항을 포함하되, 항적 영역을 우선
        focus_lons = list(nav_lons)
        focus_lats = list(nav_lats)
        for idx in used_set:
            if stations[idx].longitude > -900:
                focus_lons.append(stations[idx].longitude)
                focus_lats.append(stations[idx].latitude)

        lon_min, lon_max = min(focus_lons), max(focus_lons)
        lat_min, lat_max = min(focus_lats), max(focus_lats)
    else:
        lon_min, lon_max = min(st_lons), max(st_lons)
        lat_min, lat_max = min(st_lats), max(st_lats)

    # 여백 (항적 기준 적절한 확대 — 최소 0.15도)
    lon_span = lon_max - lon_min
    lat_span = lat_max - lat_min
    lon_pad = max(lon_span * 0.2, 0.15)
    lat_pad = max(lat_span * 0.2, 0.15)

    view_bbox = (lon_min - lon_pad, lat_min - lat_pad,
                 lon_max + lon_pad, lat_max + lat_pad)
    ax.set_xlim(view_bbox[0], view_bbox[2])
    ax.set_ylim(view_bbox[1], view_bbox[3])

    # ── 배경 (바다색) ──
    ax.set_facecolor(_C.OCEAN)

    # ── 해안선 ──
    coastline_drawn = _draw_coastline(ax, view_bbox)

    # ── 그리드 ──
    ax.grid(True, which='major', linestyle='-', alpha=0.35,
            color=_C.GRID, zorder=1.5)
    ax.grid(True, which='minor', linestyle=':', alpha=0.15,
            color=_C.GRID_MINOR, zorder=1.5)
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax.yaxis.set_minor_locator(AutoMinorLocator(5))

    # ── 항적 플롯 ──
    if nav_lons:
        if nav_tc and any(t != 0 for t in nav_tc):
            track = _add_colored_track(
                ax, nav_lons, nav_lats, nav_tc,
                linewidth=2.0, alpha=0.55, zorder=4,
            )
            sc = ax.scatter(nav_lons, nav_lats, c=nav_tc, cmap='coolwarm',
                           s=4, alpha=0.7, zorder=5, edgecolors='none')
            cbar = plt.colorbar(track or sc, ax=ax, shrink=0.6, pad=0.015, aspect=30)
            cbar.set_label('조석보정값 Tc (cm)', fontsize=9, color=_C.TEXT)
            cbar.ax.tick_params(labelsize=7, colors='#666')
        else:
            ax.plot(nav_lons, nav_lats, color=_C.NAV_LINE, linewidth=1.0,
                   alpha=0.6, zorder=5)
            ax.scatter(nav_lons, nav_lats, color=_C.NAV_LINE, s=2,
                      alpha=0.4, zorder=5, edgecolors='none')

        # 시작/끝 마커
        if len(nav_lons) > 1:
            ax.scatter([nav_lons[0]], [nav_lats[0]], color=_C.NAV_START,
                      s=100, zorder=8, marker='o', edgecolors='white',
                      linewidths=1.5, label='항적 시작')
            ax.scatter([nav_lons[-1]], [nav_lats[-1]], color=_C.NAV_END,
                      s=100, zorder=8, marker='s', edgecolors='white',
                      linewidths=1.5, label='항적 종료')

    # ── 미사용 기준항 (희미하게) ──
    unused_lons = [st_lons[i] for i in range(len(st_lons))
                   if st_indices[i] not in used_set]
    unused_lats = [st_lats[i] for i in range(len(st_lats))
                   if st_indices[i] not in used_set]

    if unused_lons:
        # 표시 범위 내의 미사용 기준항만
        vis_lons, vis_lats = [], []
        for lon, lat in zip(unused_lons, unused_lats):
            if view_bbox[0] <= lon <= view_bbox[2] and view_bbox[1] <= lat <= view_bbox[3]:
                vis_lons.append(lon)
                vis_lats.append(lat)
        if vis_lons:
            ax.scatter(vis_lons, vis_lats, color=_C.UNUSED_ST, s=50,
                      zorder=3, marker='^', alpha=0.6, edgecolors='#78909C',
                      linewidths=0.5,
                      label=f'미사용 기준항 ({len(vis_lons)}개)')

    # ── 사용 기준항 (강조) ──
    used_lons = [st_lons[i] for i in range(len(st_lons))
                 if st_indices[i] in used_set]
    used_lats = [st_lats[i] for i in range(len(st_lats))
                 if st_indices[i] in used_set]
    used_names = [st_names[i] for i in range(len(st_names))
                  if st_indices[i] in used_set]

    if used_lons:
        ax.scatter(used_lons, used_lats, color=_C.USED_ST, s=160,
                  zorder=9, edgecolors='white', linewidths=2,
                  marker='^', label=f'사용 기준항 ({len(used_lons)}개)')

        # 사용 기준항 이름 라벨
        for lon, lat, name in zip(used_lons, used_lats, used_names):
            ax.annotate(
                name, (lon, lat),
                textcoords='offset points', xytext=(10, 10),
                fontsize=9, fontweight='bold', color=_C.USED_ST,
                bbox=dict(boxstyle='round,pad=0.3', fc='white',
                         ec=_C.USED_ST, alpha=0.92, linewidth=1.2),
                arrowprops=dict(arrowstyle='-', color=_C.USED_ST,
                               lw=0.8, alpha=0.6),
                zorder=10)

    # ── 제목 ──
    if title is None:
        title = '기준항 위치 및 항적 지도'
    ax.set_title(title, fontsize=14, fontweight='bold', pad=14,
                color=_C.TITLE)

    # ── 축 라벨 & 포맷 ──
    ax.set_xlabel('경도 (°E)', fontsize=10, color=_C.TEXT)
    ax.set_ylabel('위도 (°N)', fontsize=10, color=_C.TEXT)
    ax.xaxis.set_major_formatter(FuncFormatter(_fmt_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_lat))
    ax.tick_params(colors='#666', which='both', labelsize=8)

    # ── 축 비율 보정 ──
    mid_lat = (view_bbox[1] + view_bbox[3]) / 2
    ax.set_aspect(1.0 / np.cos(np.radians(mid_lat)))

    # ── 범례 ──
    ax.legend(loc='upper left', fontsize=9, framealpha=0.95,
             edgecolor='#ddd', fancybox=True)

    # ── 통계 박스 ──
    stats_lines = []
    if used_lons:
        stats_lines.append(f'사용 기준항: {len(used_lons)}개')
    if nav_lons:
        stats_lines.append(f'항적: {len(nav_lons):,}개 포인트')
        valid_tc = [t for t in nav_tc if t != 0]
        if valid_tc:
            stats_lines.append(f'Tc: {min(valid_tc):.1f} ~ {max(valid_tc):.1f} cm')
    stats_lines.append(f'경도: {lon_min:.4f}° ~ {lon_max:.4f}°')
    stats_lines.append(f'위도: {lat_min:.4f}° ~ {lat_max:.4f}°')

    ax.text(0.98, 0.02, '\n'.join(stats_lines),
           transform=ax.transAxes, fontsize=8, va='bottom', ha='right',
           bbox=dict(boxstyle='round,pad=0.5', fc='white',
                    ec='#ccc', alpha=0.92),
           zorder=15)
    # brief box는 tide graph에서만 표시 (지도에서는 제거)

    # ── 프레임 ──
    for spine in ax.spines.values():
        spine.set_color(_C.FRAME)
        spine.set_linewidth(1)

    # ── 방위 표시 ──
    _draw_compass(ax)

    # ── 워터마크 ──
    fig.text(0.995, 0.003, 'TideBedPy  |  by Junhyub',
            fontsize=7, color='#bbb', ha='right', va='bottom', style='italic')

    plt.tight_layout()
    plt.savefig(output_image, dpi=dpi, bbox_inches='tight',
               facecolor='white', edgecolor='none')
    plt.close(fig)

    logger.info(f"지도 생성: {output_image}")
    return output_image


# ══════════════════════════════════════════════════════════════
#  보정 결과 지도 (Tc 컬러맵 + 시계열)
# ══════════════════════════════════════════════════════════════
def generate_correction_map(stations, nav_points,
                            output_image: str = None,
                            dpi: int = 150,
                            all_corrections=None) -> Optional[str]:
    """
    보정 결과를 색상으로 표현한 항적 지도.
    상단: 해안선 지도 + Tc 컬러맵 항적
    하단: 시간별 Tc 변화 그래프

    Args:
        all_corrections: 보정 엔진의 StationCorrection 리스트.
                         제공되면 실제 사용된 기준항만 표시.
    """
    if not HAS_MATPLOTLIB or not nav_points:
        return None

    _init_fonts()

    if output_image is None:
        output_image = 'correction_map.png'
    summary = _load_summary_for_output(output_image)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 13), dpi=dpi,
                                     height_ratios=[3, 1])
    fig.patch.set_facecolor('white')

    nav_lons = [p.x for p in nav_points if p.x != 0]
    nav_lats = [p.y for p in nav_points if p.x != 0]
    nav_tc = [p.tc if p.tc > -999 else 0 for p in nav_points if p.x != 0]
    times = [p.t for p in nav_points if p.x != 0]

    if not nav_lons:
        plt.close(fig)
        return None

    # 사용 기준항 식별
    used_set = _identify_used_stations(stations, nav_points, all_corrections)
    all_st = [(i, s) for i, s in enumerate(stations) if s.longitude > -900]

    # 범위 (항적 + 사용 기준항)
    focus_lons = list(nav_lons)
    focus_lats = list(nav_lats)
    for idx in used_set:
        if stations[idx].longitude > -900:
            focus_lons.append(stations[idx].longitude)
            focus_lats.append(stations[idx].latitude)

    lon_min, lon_max = min(focus_lons), max(focus_lons)
    lat_min, lat_max = min(focus_lats), max(focus_lats)
    lon_pad = max((lon_max - lon_min) * 0.2, 0.15)
    lat_pad = max((lat_max - lat_min) * 0.2, 0.15)

    view_bbox = (lon_min - lon_pad, lat_min - lat_pad,
                 lon_max + lon_pad, lat_max + lat_pad)
    ax1.set_xlim(view_bbox[0], view_bbox[2])
    ax1.set_ylim(view_bbox[1], view_bbox[3])

    # ── 상단: 지도 ──
    ax1.set_facecolor(_C.OCEAN)
    _draw_coastline(ax1, view_bbox)

    # 항적 (Tc 컬러맵)
    track = _add_colored_track(
        ax1, nav_lons, nav_lats, nav_tc,
        linewidth=2.4, alpha=0.65, zorder=4,
    )
    sc = ax1.scatter(nav_lons, nav_lats, c=nav_tc, cmap='coolwarm',
                    s=5, alpha=0.7, zorder=5, edgecolors='none')
    cbar = plt.colorbar(track or sc, ax=ax1, shrink=0.7, pad=0.015, aspect=30)
    cbar.set_label('Tc (cm)', fontsize=9, color=_C.TEXT)
    cbar.ax.tick_params(labelsize=7)

    # 미사용 기준항 (범위 내만)
    for i, s in all_st:
        if i not in used_set:
            if view_bbox[0] <= s.longitude <= view_bbox[2] and \
               view_bbox[1] <= s.latitude <= view_bbox[3]:
                ax1.scatter(s.longitude, s.latitude, color=_C.UNUSED_ST,
                           s=40, zorder=3, marker='^', alpha=0.5,
                           edgecolors='#78909C', linewidths=0.5)

    # 사용 기준항
    for i, s in all_st:
        if i in used_set:
            ax1.scatter(s.longitude, s.latitude, color=_C.USED_ST,
                       s=140, zorder=9, marker='^', edgecolors='white',
                       linewidths=2)
            ax1.annotate(s.name, (s.longitude, s.latitude),
                        textcoords='offset points', xytext=(10, 10),
                        fontsize=8, fontweight='bold', color=_C.USED_ST,
                        bbox=dict(boxstyle='round,pad=0.3', fc='white',
                                 ec=_C.USED_ST, alpha=0.9),
                        zorder=10)

    ax1.set_title('조석보정 결과 지도', fontsize=14, fontweight='bold',
                 pad=14, color=_C.TITLE)
    ax1.set_xlabel('경도 (°E)', fontsize=10, color=_C.TEXT)
    ax1.set_ylabel('위도 (°N)', fontsize=10, color=_C.TEXT)
    ax1.grid(True, alpha=0.3, color=_C.GRID, zorder=1.5)
    ax1.xaxis.set_major_formatter(FuncFormatter(_fmt_lon))
    ax1.yaxis.set_major_formatter(FuncFormatter(_fmt_lat))
    ax1.tick_params(colors='#666', which='both', labelsize=8)

    mid_lat = (view_bbox[1] + view_bbox[3]) / 2
    ax1.set_aspect(1.0 / np.cos(np.radians(mid_lat)))
    _draw_compass(ax1)

    # ── 하단: Tc 시계열 ──
    ax2.set_facecolor('#FAFBFC')
    ax2.plot(times, nav_tc, color='#1976D2', linewidth=0.8, alpha=0.8)
    ax2.fill_between(times, nav_tc, alpha=0.12, color='#1976D2')
    ax2.axhline(y=0, color='#999', linewidth=0.5)
    mean_tc = sum(nav_tc) / len(nav_tc)
    ax2.axhline(y=mean_tc, color=_C.ORANGE, linewidth=0.9,
                linestyle='--', alpha=0.7)
    _annotate_series_extrema(ax2, times, nav_tc, unit='cm')

    stats_lines = [
        f"Samples: {len(nav_tc):,}",
        f"Mean: {mean_tc:.1f} cm",
        f"Range: {min(nav_tc):.1f} ~ {max(nav_tc):.1f} cm",
    ]
    ax2.text(0.02, 0.95, '\n'.join(stats_lines), transform=ax2.transAxes,
             fontsize=8, va='top', ha='left',
             bbox=dict(boxstyle='round,pad=0.45', fc='white',
                       ec='#D6DEE5', alpha=0.94))

    ax2.set_title('시간별 조석보정값', fontsize=11, fontweight='bold',
                 pad=8, color=_C.TEXT)
    ax2.set_xlabel('시간', fontsize=10, color=_C.TEXT)
    ax2.set_ylabel('Tc (cm)', fontsize=10, color=_C.TEXT)
    ax2.grid(True, alpha=0.3, color='#E0E0E0')
    ax2.tick_params(colors='#666', labelsize=8)
    for spine in ax2.spines.values():
        spine.set_color('#E0E0E0')

    import matplotlib.dates as mdates
    time_range = (times[-1] - times[0]).total_seconds() / 3600
    if time_range <= 24:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    elif time_range <= 72:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    else:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

    for spine in ax1.spines.values():
        spine.set_color(_C.FRAME)
        spine.set_linewidth(1)

    fig.text(0.995, 0.003, 'TideBedPy  |  by Junhyub',
            fontsize=7, color='#bbb', ha='right', va='bottom', style='italic')

    plt.tight_layout()
    plt.savefig(output_image, dpi=dpi, bbox_inches='tight',
               facecolor='white', edgecolor='none')
    plt.close(fig)

    logger.info(f"보정 결과 지도 생성: {output_image}")
    return output_image
