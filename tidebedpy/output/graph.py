"""
graph.py - 조석보정 그래프 시각화

.tid 파일의 조석보정값(Tc)을 시계열 그래프로 출력한다.
검증 시 참조 .tid와 비교 그래프도 생성 가능.

Original: TideBedLite v1.05, Copyright (c) 2014 KHOA / GeoSR
Python:   Junhyub, 2025
"""

import os
import logging
from datetime import datetime
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# matplotlib 임포트 (없으면 기능 비활성)
try:
    import matplotlib
    matplotlib.use('Agg')  # 비대화형 백엔드
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.font_manager as fm
    from matplotlib.ticker import AutoMinorLocator, MaxNLocator
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib 미설치 — 그래프 기능 비활성")


# ── 폰트 초기화 (모듈 로드 시 1회만 실행) ──────────────────────
_FONT_READY = False

def _init_fonts():
    """matplotlib에 한글 폰트를 등록한다. 모듈 최초 1회만."""
    global _FONT_READY
    if _FONT_READY or not HAS_MATPLOTLIB:
        return
    _FONT_READY = True

    # 1) 번들 Pretendard 폰트 시도
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
        plt.rcParams['axes.unicode_minus'] = False
        logger.debug("Pretendard 폰트 등록 완료")
        return

    # 2) 시스템 한글 폰트 fallback
    available = {f.name for f in fm.fontManager.ttflist}
    for fc in ['Malgun Gothic', '맑은 고딕', 'NanumGothic', 'AppleGothic']:
        if fc in available:
            plt.rcParams['font.family'] = fc
            plt.rcParams['axes.unicode_minus'] = False
            logger.debug(f"Fallback 폰트: {fc}")
            return

# 모듈 로드 시점에 즉시 초기화
if HAS_MATPLOTLIB:
    _init_fonts()


# ── 색상 팔레트 ────────────────────────────────────────────
class _C:
    """그래프 색상 상수"""
    BLUE      = '#1976D2'
    BLUE_LIGHT= '#BBDEFB'
    RED       = '#E53935'
    GREEN     = '#43A047'
    GREEN_L   = '#C8E6C9'
    ORANGE    = '#FB8C00'
    GRAY      = '#78909C'
    BG_PANEL  = '#FAFBFC'
    GRID      = '#E0E0E0'
    TEXT      = '#37474F'
    TEXT_LIGHT= '#78909C'
    TITLE     = '#1A237E'


# ── 유틸 ────────────────────────────────────────────────────
def parse_tid_for_graph(file_path: str) -> Tuple[List[datetime], List[float]]:
    """
    .tid 파일에서 시간과 Tc값을 추출한다.
    """
    times = []
    values = []
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('-') or not line[0].isdigit():
                continue
            parts = line.split()
            if len(parts) >= 3 and '/' in parts[0]:
                try:
                    dt = datetime.strptime(f"{parts[0]} {parts[1]}",
                                           '%Y/%m/%d %H:%M:%S')
                    val = float(parts[2])
                    if val > -9.0:
                        times.append(dt)
                        values.append(val)
                except (ValueError, IndexError):
                    continue
    return times, values


def _load_run_summary(tid_path: str) -> Optional[dict]:
    """Load a TideBedPy sidecar summary if one exists."""
    try:
        from tidebedpy.output.summary import load_summary_file
    except Exception:
        try:
            from output.summary import load_summary_file
        except Exception:
            return None

    try:
        return load_summary_file(tid_path)
    except Exception:
        return None


def _build_brief_lines(summary: Optional[dict], max_lines: int = 6) -> List[str]:
    """Build short human-readable briefing lines for chart overlays."""
    if not summary:
        return []

    lines: List[str] = []
    headline = str(summary.get("headline", "")).strip()
    if headline:
        lines.append(headline)

    settings = summary.get("settings", {})
    preset_name = settings.get("preset_name")
    preset_summary = settings.get("preset_summary")
    if preset_name and preset_summary:
        lines.append(f"프리셋: {preset_name} - {preset_summary}")
    elif preset_name:
        lines.append(f"프리셋: {preset_name}")
    elif preset_summary:
        lines.append(f"프리셋 의미: {preset_summary}")

    story = summary.get("story", {})
    for section_name in ("workflow", "quality"):
        section_lines = story.get(section_name, [])
        if section_lines:
            lines.append(str(section_lines[0]))

    contributors = summary.get("contributors", [])[:2]
    if contributors:
        contributor_text = ", ".join(
            f"{item['station_name']} ({item['coverage_pct']:.1f}%)"
            for item in contributors
        )
        lines.append(f"주요 기준항: {contributor_text}")

    trimmed = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        if len(text) > 140:
            text = text[:137].rstrip() + "..."
        trimmed.append(text)
        if len(trimmed) >= max_lines:
            break
    return trimmed


def _build_compare_driver_lines(
    summary_a: Optional[dict],
    summary_b: Optional[dict],
    tolerance_cm: float,
    max_lines: int = 6,
) -> List[str]:
    """Build short compare-context lines that explain likely drivers."""
    lines = [f"허용 오차: +/-{tolerance_cm:.2f} cm"]

    if not summary_a or not summary_b:
        lines.append("두 시나리오의 실행 요약을 모두 읽을 수 없었습니다.")
        return lines

    settings_a = summary_a.get("settings", {})
    settings_b = summary_b.get("settings", {})
    inputs_a = summary_a.get("inputs", {})
    inputs_b = summary_b.get("inputs", {})

    pairs = [
        ("tide_model", "모델"),
        ("timezone_offset_hours", "시간대"),
        ("rank_limit", "선정 기준항 수"),
        ("time_interval_sec", "간격"),
    ]
    for key, label in pairs:
        value_a = settings_a.get(key)
        value_b = settings_b.get(key)
        if value_a != value_b:
            lines.append(f"{label}: {value_a} vs {value_b}")

    preset_summary_a = settings_a.get("preset_summary")
    preset_summary_b = settings_b.get("preset_summary")
    if preset_summary_a and preset_summary_b and preset_summary_a != preset_summary_b:
        lines.append("프리셋 의미가 두 시나리오에서 다릅니다.")

    contributors_a = summary_a.get("contributors", [])[:2]
    contributors_b = summary_b.get("contributors", [])[:2]
    if contributors_a and contributors_b:
        lead_a = ", ".join(str(item.get("station_name", "")) for item in contributors_a)
        lead_b = ", ".join(str(item.get("station_name", "")) for item in contributors_b)
        if lead_a != lead_b:
            lines.append(f"주요 기준항: {lead_a} vs {lead_b}")

    for key, label in (("nav_name", "항적"), ("tide_name", "조위"), ("station_name", "기준항 파일")):
        value_a = inputs_a.get(key)
        value_b = inputs_b.get(key)
        if value_a and value_b and value_a != value_b:
            lines.append(f"{label}: {value_a} vs {value_b}")

    if len(lines) == 1:
        lines.append("시나리오 메타데이터는 대체로 유사합니다. residual 군집과 특정 시점 스파이크를 중점적으로 보세요.")

    return lines[:max_lines]


def _add_brief_box(ax, lines: List[str], *, loc: str = "upper right") -> None:
    """Add a readable text briefing box inside a chart."""
    if not lines:
        return

    x = 0.98 if "right" in loc else 0.02
    ha = "right" if "right" in loc else "left"
    y = 0.98 if "upper" in loc else 0.02
    va = "top" if "upper" in loc else "bottom"
    ax.text(
        x,
        y,
        "\n".join(lines),
        transform=ax.transAxes,
        fontsize=7.5,
        ha=ha,
        va=va,
        color=_C.TEXT,
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.6", fc="white", ec=_C.GRID, alpha=0.92),
        zorder=20,
    )


def _annotate_extrema(ax, times: List[datetime], values: List[float]) -> None:
    """Mark min/max points so the reader can orient faster."""
    if not times or not values:
        return

    min_idx = int(np.argmin(values))
    max_idx = int(np.argmax(values))
    extrema = [
        (min_idx, "최소", _C.RED, "top"),
        (max_idx, "최대", _C.GREEN, "bottom"),
    ]

    for idx, label, color, valign in extrema:
        ax.scatter([times[idx]], [values[idx]], color=color, s=26, zorder=8, edgecolors="white", linewidths=0.8)
        offset = -16 if valign == "top" else 12
        ax.annotate(
            f"{label}: {values[idx]:.3f} m",
            xy=(times[idx], values[idx]),
            xytext=(8, offset),
            textcoords="offset points",
            fontsize=7.5,
            color=color,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, alpha=0.9),
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8, alpha=0.7),
            zorder=9,
        )


def _add_contributor_inset(
    ax,
    summary: Optional[dict],
    *,
    loc: str = "lower left",
    title: str = "주요 기준항",
) -> None:
    """Add a compact horizontal bar chart for top station contributors."""
    contributors = (summary or {}).get("contributors", [])[:4]
    if not contributors:
        return

    # Compact inset — smaller to avoid obscuring main chart
    bounds = [0.03, 0.06, 0.20, 0.18] if "left" in loc else [0.77, 0.06, 0.20, 0.18]
    inset = ax.inset_axes(bounds)

    labels = [str(item.get("station_name", "")) for item in contributors][::-1]
    values = [float(item.get("coverage_pct", 0.0)) for item in contributors][::-1]

    bar_height = 0.6 if len(values) <= 3 else 0.5
    inset.barh(range(len(values)), values, height=bar_height,
               color=_C.BLUE_LIGHT, edgecolor=_C.BLUE, alpha=0.90, linewidth=0.6)
    inset.set_yticks(range(len(values)))
    inset.set_yticklabels(labels, fontsize=7, color=_C.TEXT, fontweight="medium")
    inset.set_xlabel("커버리지 %", fontsize=6, color=_C.TEXT_LIGHT, labelpad=1)
    inset.tick_params(axis="x", labelsize=6, colors=_C.TEXT_LIGHT)
    inset.tick_params(axis="y", labelsize=7, colors=_C.TEXT, length=0)
    inset.grid(True, axis="x", linestyle=":", alpha=0.25, color=_C.GRID)
    inset.set_facecolor("white")
    inset.set_title(title, fontsize=7, color=_C.TEXT, pad=2, fontweight="bold")
    for spine in inset.spines.values():
        spine.set_color(_C.GRID)
        spine.set_linewidth(0.5)

    max_value = max(values) if values else 0.0
    inset.set_xlim(0, max(max_value * 1.25, 1.0))
    for idx, value in enumerate(values):
        inset.text(value + max(max_value * 0.02, 0.3), idx, f"{value:.1f}%",
                   va="center", fontsize=6.5, color=_C.BLUE, fontweight="bold")


def _build_compare_contributor_rows(
    summary_a: Optional[dict],
    summary_b: Optional[dict],
    *,
    limit: int = 4,
) -> List[Tuple[str, float, float]]:
    """Collect a side-by-side contributor coverage table for compare views."""
    contributors_a = (summary_a or {}).get("contributors", [])
    contributors_b = (summary_b or {}).get("contributors", [])
    if not contributors_a and not contributors_b:
        return []

    ordered_names: List[str] = []
    coverage_a = {}
    coverage_b = {}

    for item in contributors_a:
        name = str(item.get("station_name", "")).strip()
        if not name:
            continue
        coverage_a[name] = float(item.get("coverage_pct", 0.0))
        if name not in ordered_names:
            ordered_names.append(name)

    for item in contributors_b:
        name = str(item.get("station_name", "")).strip()
        if not name:
            continue
        coverage_b[name] = float(item.get("coverage_pct", 0.0))
        if name not in ordered_names:
            ordered_names.append(name)

    rows = [
        (name, coverage_a.get(name, 0.0), coverage_b.get(name, 0.0))
        for name in ordered_names
    ]
    rows.sort(key=lambda item: max(item[1], item[2]), reverse=True)
    return rows[:limit]


def _add_compare_contributor_inset(
    ax,
    summary_a: Optional[dict],
    summary_b: Optional[dict],
    *,
    loc: str = "lower right",
    title: str = "기준항 커버리지",
) -> None:
    """Add a compact side-by-side contributor comparison chart."""
    rows = _build_compare_contributor_rows(summary_a, summary_b, limit=4)
    if not rows:
        return

    bounds = [0.62, 0.08, 0.35, 0.28] if "right" in loc else [0.03, 0.08, 0.35, 0.28]
    inset = ax.inset_axes(bounds)

    labels = [row[0] for row in rows][::-1]
    values_a = [row[1] for row in rows][::-1]
    values_b = [row[2] for row in rows][::-1]
    positions = np.arange(len(rows))
    height = 0.34

    inset.barh(positions + height / 2, values_a, height=height,
               color=_C.BLUE, alpha=0.82, label="A안")
    inset.barh(positions - height / 2, values_b, height=height,
               color=_C.RED, alpha=0.72, label="B안")
    inset.set_yticks(positions)
    inset.set_yticklabels(labels, fontsize=6.3, color=_C.TEXT)
    inset.tick_params(axis="x", labelsize=6.3, colors=_C.TEXT_LIGHT)
    inset.tick_params(axis="y", labelsize=6.3, colors=_C.TEXT)
    inset.set_xlabel("커버리지 %", fontsize=6.2, color=_C.TEXT_LIGHT, labelpad=1)
    inset.set_title(title, fontsize=7.4, color=_C.TEXT, pad=2, fontweight="bold")
    inset.grid(True, axis="x", linestyle=":", alpha=0.22, color=_C.GRID)
    inset.set_facecolor("white")
    inset.legend(loc="lower right", fontsize=6.2, frameon=False, ncol=2)
    for spine in inset.spines.values():
        spine.set_color(_C.GRID)
        spine.set_linewidth(0.7)

    max_value = max(values_a + values_b) if (values_a or values_b) else 0.0
    inset.set_xlim(0, max(max_value * 1.2, 1.0))


def _add_top_mismatch_inset(
    ax,
    matched_t: List[datetime],
    residuals_cm: List[float],
    *,
    title: str = "주요 차이 시점",
    limit: int = 5,
) -> None:
    """Add a compact ranking of the largest absolute residual timestamps."""
    if not matched_t or not residuals_cm:
        return

    pairs = sorted(
        zip(matched_t, residuals_cm),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:limit]
    if not pairs:
        return

    labels = [t.strftime("%m/%d %H:%M") for t, _ in pairs][::-1]
    values = [float(v) for _, v in pairs][::-1]
    colors = [_C.RED if value >= 0 else _C.BLUE for value in values]

    inset = ax.inset_axes([0.03, 0.54, 0.34, 0.38])
    inset.barh(range(len(values)), values, color=colors, alpha=0.85)
    inset.axvline(0, color=_C.GRAY, linewidth=0.8, alpha=0.6)
    inset.set_yticks(range(len(values)))
    inset.set_yticklabels(labels, fontsize=6.5, color=_C.TEXT)
    inset.tick_params(axis="x", labelsize=6.5, colors=_C.TEXT_LIGHT)
    inset.tick_params(axis="y", labelsize=6.5, colors=_C.TEXT)
    inset.set_xlabel("Residual (cm)", fontsize=6.5, color=_C.TEXT_LIGHT, labelpad=1)
    inset.set_title(title, fontsize=7.5, color=_C.TEXT, pad=2, fontweight="bold")
    inset.grid(True, axis="x", linestyle=":", alpha=0.25, color=_C.GRID)
    inset.set_facecolor("white")
    for spine in inset.spines.values():
        spine.set_color(_C.GRID)
        spine.set_linewidth(0.7)

    max_abs = max(abs(value) for value in values) if values else 0.0
    inset.set_xlim(-max(max_abs * 1.15, 1.0), max(max_abs * 1.15, 1.0))
    for idx, value in enumerate(values):
        x = value + (0.04 * max_abs if value >= 0 else -0.04 * max_abs)
        ha = "left" if value >= 0 else "right"
        inset.text(x, idx, f"{value:+.2f}", va="center", ha=ha,
                   fontsize=6.2, color=_C.TEXT)


def _auto_xfmt(ax, hours):
    """시간 범위에 따른 X축 포맷 자동 설정"""
    if hours <= 24:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    elif hours <= 72:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    elif hours <= 336:  # 14일
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_minor_locator(AutoMinorLocator())


def _style_ax(ax, ylabel='', xlabel='', title=''):
    """공통 축 스타일 적용"""
    if title:
        ax.set_title(title, fontsize=11, fontweight='bold',
                     color=_C.TEXT, pad=8)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=_C.TEXT)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=_C.TEXT)
    ax.grid(True, which='major', linestyle='-', alpha=0.4, color=_C.GRID)
    ax.grid(True, which='minor', linestyle=':', alpha=0.2, color=_C.GRID)
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(colors=_C.TEXT_LIGHT, which='both', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(_C.GRID)
        spine.set_linewidth(0.8)
    ax.set_facecolor(_C.BG_PANEL)


# ══════════════════════════════════════════════════════════════
#  메인 조석 그래프
# ══════════════════════════════════════════════════════════════
def generate_tide_graph(tid_path: str, output_image: str = None,
                        reference_path: str = None,
                        title: str = None,
                        figsize: tuple = (16, 6),
                        dpi: int = 150,
                        tolerance_cm: float = 1.0) -> Optional[str]:
    """
    조석보정 결과 그래프를 생성한다.
    참조 파일이 있으면 자동으로 비교 모드(3패널)로 전환.

    Args:
        tolerance_cm: 허용 편차 범위 (cm). 기본값 1.0cm.
    """
    if not HAS_MATPLOTLIB:
        logger.error("matplotlib가 설치되지 않아 그래프를 생성할 수 없습니다.")
        return None

    _init_fonts()

    times, values = parse_tid_for_graph(tid_path)
    summary = _load_run_summary(tid_path)
    if not times:
        logger.error(f"그래프 데이터가 없습니다: {tid_path}")
        return None

    if output_image is None:
        output_image = tid_path + '.png'

    basename = os.path.basename(tid_path)

    # ── 참조 파일이 있으면 비교 모드 ──
    has_ref = (reference_path and os.path.isfile(reference_path))
    ref_times, ref_values = [], []
    if has_ref:
        ref_times, ref_values = parse_tid_for_graph(reference_path)
        if not ref_times:
            has_ref = False

    if has_ref:
        return _generate_comparison_layout(
            times, values, ref_times, ref_values,
            tid_path, reference_path,
            basename, output_image, title, dpi, tolerance_cm)

    # ── 단독 결과 그래프 (참조 없음) ──
    fig, ax = plt.subplots(figsize=(18, 7), dpi=dpi)

    ax.plot(times, values, color=_C.BLUE, linewidth=1.2,
            label='조석보정값 Tc', zorder=3)
    ax.fill_between(times, values, alpha=0.10, color=_C.BLUE, zorder=2)

    if title is None:
        title = f'조석보정 결과 — {basename}'
    _style_ax(ax, ylabel='조석보정값 Tc (m)', xlabel='시간')
    ax.set_title(title, fontsize=14, fontweight='bold',
                 color=_C.TITLE, pad=14)

    hours = (times[-1] - times[0]).total_seconds() / 3600
    _auto_xfmt(ax, hours)

    mean_v = sum(values) / len(values)
    ax.axhline(y=mean_v, color=_C.ORANGE, linewidth=1.0,
               linestyle='--', alpha=0.6, zorder=1,
               label=f'평균: {mean_v:.3f} m')

    # 통계 박스 — 읽기 쉬운 크기
    stats = (f'데이터: {len(values):,}개\n'
             f'평균: {mean_v:.3f} m\n'
             f'범위: {min(values):.3f} ~ {max(values):.3f} m')
    ax.text(0.02, 0.97, stats, transform=ax.transAxes, fontsize=9,
            va='top', ha='left', linespacing=1.5,
            bbox=dict(boxstyle='round,pad=0.6', fc='white',
                      ec=_C.GRID, alpha=0.92))
    _annotate_extrema(ax, times, values)
    _add_brief_box(ax, _build_brief_lines(summary, max_lines=5), loc='upper right')
    _add_contributor_inset(ax, summary, loc='lower left')
    ax.legend(loc='lower right', fontsize=9, framealpha=0.9,
              edgecolor=_C.GRID)
    ax.axhline(y=0, color=_C.GRAY, linewidth=0.5, alpha=0.4)

    fig.text(0.995, 0.005, 'TideBedPy', fontsize=7,
             color='#bbb', ha='right', va='bottom', style='italic')

    plt.tight_layout()
    plt.savefig(output_image, dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    logger.info(f"조석 그래프 생성: {output_image}")
    return output_image


# ══════════════════════════════════════════════════════════════
#  비교 레이아웃 (3패널)
# ══════════════════════════════════════════════════════════════
def _generate_comparison_layout(
        times1, values1, times2, values2,
        tid_path, reference_path,
        basename, output_image, title, dpi, tolerance_cm=1.0):
    """
    3패널 비교 그래프:
      상단  - 시계열 오버레이 (두 데이터셋)
      중단  - 잔차(Residual) 라인 + 허용 오차 밴드
      하단  - 잔차 히스토그램 + 통계

    Args:
        tolerance_cm: 허용 편차 범위 (cm). 기본값 1.0cm.
    """
    tol = tolerance_cm
    summary_a = _load_run_summary(tid_path)
    summary_b = _load_run_summary(reference_path)
    # 시간 매칭
    ref_dict = {t: v for t, v in zip(times2, values2)}
    matched_t, matched_v1, matched_v2, residuals = [], [], [], []
    for t, v in zip(times1, values1):
        if t in ref_dict:
            matched_t.append(t)
            matched_v1.append(v)
            matched_v2.append(ref_dict[t])
            residuals.append((v - ref_dict[t]) * 100)  # cm

    residuals_np = np.array(residuals) if residuals else np.array([0])

    fig = plt.figure(figsize=(16, 11), dpi=dpi)
    fig.patch.set_facecolor('white')

    # GridSpec: 상단 40%, 중단 30%, 하단 30%
    gs = fig.add_gridspec(3, 1, height_ratios=[4, 2.5, 2],
                          hspace=0.08)
    ax_top = fig.add_subplot(gs[0])
    ax_mid = fig.add_subplot(gs[1], sharex=ax_top)
    ax_bot = fig.add_subplot(gs[2])

    hours = (times1[-1] - times1[0]).total_seconds() / 3600

    # ── 상단: 시계열 오버레이 ──────────────────────────────
    ax_top.plot(times2, values2, color=_C.RED, linewidth=1.8,
                label='참조값 (원본 TideBedLite)', alpha=0.85, zorder=3)
    ax_top.plot(times1, values1, color=_C.BLUE, linewidth=1.0,
                label='결과값 (TideBedPy)', alpha=0.95, zorder=4,
                linestyle='-')
    ax_top.fill_between(times1, values1, alpha=0.08, color=_C.BLUE, zorder=2)

    if title is None:
        title = f'조석보정 비교 검증 — {basename}'
    _style_ax(ax_top, ylabel='조석보정값 Tc (m)')
    ax_top.set_title(title, fontsize=14, fontweight='bold',
                     color=_C.TITLE, pad=14)
    ax_top.legend(loc='upper right', fontsize=9, framealpha=0.95,
                  edgecolor=_C.GRID, ncol=2)
    _annotate_extrema(ax_top, times1, values1)
    _add_brief_box(
        ax_top,
        _build_compare_driver_lines(summary_a, summary_b, tol),
        loc='upper left',
    )
    _add_compare_contributor_inset(ax_top, summary_a, summary_b, loc='lower right')

    # 데이터 통계
    mean_v = sum(values1) / len(values1)
    stats = (f'데이터: {len(values1):,}개  |  '
             f'평균: {mean_v:.3f}m  |  '
             f'범위: {min(values1):.3f} ~ {max(values1):.3f}m')
    ax_top.text(0.02, 0.04, stats, transform=ax_top.transAxes, fontsize=8,
                color=_C.TEXT_LIGHT,
                bbox=dict(boxstyle='round,pad=0.4', fc='white',
                          ec=_C.GRID, alpha=0.85))

    _auto_xfmt(ax_top, hours)
    plt.setp(ax_top.get_xticklabels(), visible=False)

    # ── 중단: 잔차(Residual) 라인 + 허용 오차 밴드 ──────────
    if matched_t:
        ax_mid.fill_between(matched_t, residuals, 0,
                            where=[abs(r) <= tol for r in residuals],
                            color=_C.GREEN_L, alpha=0.5, zorder=2,
                            label=f'±{tol}cm 이내')
        ax_mid.fill_between(matched_t, residuals, 0,
                            where=[abs(r) > tol for r in residuals],
                            color='#FFCDD2', alpha=0.6, zorder=2,
                            label=f'±{tol}cm 초과')
        ax_mid.plot(matched_t, residuals, color=_C.TEXT, linewidth=0.5,
                    alpha=0.7, zorder=3)

        # 허용 오차 밴드
        ax_mid.axhline(y=tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.6)
        ax_mid.axhline(y=-tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.6)
        ax_mid.axhline(y=0, color=_C.GRAY, linewidth=0.8, alpha=0.5)

        ax_mid.text(matched_t[-1], tol, f' +{tol}cm', fontsize=7,
                    color=_C.RED, va='bottom', ha='left', alpha=0.7)
        ax_mid.text(matched_t[-1], -tol, f' −{tol}cm', fontsize=7,
                    color=_C.RED, va='top', ha='left', alpha=0.7)

        # y축 대칭
        max_abs = max(abs(residuals_np.min()), abs(residuals_np.max()), tol * 1.5)
        ax_mid.set_ylim(-max_abs * 1.3, max_abs * 1.3)
        peak_idx = int(np.argmax(np.abs(residuals_np)))
        peak_time = matched_t[peak_idx]
        peak_value = residuals[peak_idx]
        peak_offset = 12 if peak_value >= 0 else -18
        peak_va = 'bottom' if peak_value >= 0 else 'top'
        ax_mid.scatter([peak_time], [peak_value], color=_C.ORANGE, s=32,
                       zorder=5, edgecolors='white', linewidths=0.8)
        ax_mid.annotate(
            f'최대 차이 {peak_value:+.3f}cm',
            xy=(peak_time, peak_value),
            xytext=(10, peak_offset),
            textcoords='offset points',
            fontsize=7.5,
            color=_C.ORANGE,
            fontweight='bold',
            va=peak_va,
            bbox=dict(boxstyle='round,pad=0.25', fc='white',
                      ec=_C.ORANGE, alpha=0.9),
            arrowprops=dict(arrowstyle='->', color=_C.ORANGE,
                            lw=0.8, alpha=0.7),
            zorder=6,
        )

    _style_ax(ax_mid, ylabel='잔차 (cm)')
    ax_mid.set_title('잔차 분포 (결과 − 참조)', fontsize=10,
                     fontweight='bold', color=_C.TEXT, pad=6, loc='left')
    ax_mid.legend(loc='upper right', fontsize=8, framealpha=0.9,
                  edgecolor=_C.GRID, ncol=2)
    _auto_xfmt(ax_mid, hours)

    # ── 하단: 잔차 히스토그램 + 통계 ──────────────────────
    if len(residuals) > 0:
        # 히스토그램
        n_bins = min(100, max(20, len(residuals) // 200))
        counts, bins, patches = ax_bot.hist(
            residuals_np, bins=n_bins, color=_C.BLUE_LIGHT,
            edgecolor=_C.BLUE, linewidth=0.5, alpha=0.8, zorder=3)

        # 허용범위 강조
        for patch, left_edge in zip(patches, bins[:-1]):
            right_edge = left_edge + (bins[1] - bins[0])
            if abs(left_edge) <= tol and abs(right_edge) <= tol:
                patch.set_facecolor(_C.GREEN_L)
                patch.set_edgecolor(_C.GREEN)

        ax_bot.axvline(x=0, color=_C.GRAY, linewidth=1, alpha=0.5)
        ax_bot.axvline(x=tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.5)
        ax_bot.axvline(x=-tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.5)

        # 통계 계산
        max_diff = np.max(np.abs(residuals_np))
        mean_diff = np.mean(residuals_np)
        std_diff = np.std(residuals_np)
        within_tol = np.sum(np.abs(residuals_np) <= tol) / len(residuals_np) * 100
        rms_diff = np.sqrt(np.mean(residuals_np ** 2))

        # 통계 박스
        verdict = "PASS" if max_diff <= tol else f"PASS (±{tol}cm 내)" if within_tol >= 99 else "검토 필요"
        verdict_color = _C.GREEN if max_diff <= tol else _C.ORANGE

        stats_text = (
            f'매칭 포인트: {len(residuals):,}개\n'
            f'최대 편차: {max_diff:.4f} cm\n'
            f'평균 편차: {mean_diff:+.4f} cm\n'
            f'표준편차 (σ): {std_diff:.4f} cm\n'
            f'RMS: {rms_diff:.4f} cm\n'
            f'±{tol}cm 이내: {within_tol:.1f}%'
        )
        ax_bot.text(0.98, 0.95, stats_text, transform=ax_bot.transAxes,
                    fontsize=9, va='top', ha='right',
                    bbox=dict(boxstyle='round,pad=0.6', fc='white',
                              ec=_C.GRID, alpha=0.95))

        # 판정 뱃지
        ax_bot.text(0.98, 0.02, f'  {verdict}  ',
                    transform=ax_bot.transAxes,
                    fontsize=11, fontweight='bold', va='bottom', ha='right',
                    color='white',
                    bbox=dict(boxstyle='round,pad=0.4',
                              fc=verdict_color, ec='none', alpha=0.9))

    _style_ax(ax_bot, ylabel='빈도 (개)', xlabel='잔차 (cm)')
    ax_bot.set_title('잔차 히스토그램', fontsize=10,
                     fontweight='bold', color=_C.TEXT, pad=6, loc='left')
    ax_bot.yaxis.set_major_locator(MaxNLocator(integer=True))
    _add_top_mismatch_inset(ax_bot, matched_t, residuals)

    # 워터마크
    _add_top_mismatch_inset(ax_hist, matched_t, residuals)

    fig.text(0.995, 0.003, 'TideBedPy  |  by Junhyub',
             fontsize=7, color='#bbb', ha='right', va='bottom',
             style='italic')

    plt.savefig(output_image, dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    logger.info(f"비교 그래프 생성: {output_image}")
    return output_image


# ══════════════════════════════════════════════════════════════
#  독립 비교 그래프 (compare.png)
# ══════════════════════════════════════════════════════════════
def generate_comparison_graph(tid_path: str, reference_path: str,
                               output_image: str = None,
                               dpi: int = 150,
                               tolerance_cm: float = 1.0) -> Optional[str]:
    """
    결과와 참조 .tid의 상세 비교 그래프를 생성한다.
    상단: 시계열 오버레이 + 최대편차 구간 확대
    하단: 잔차 + 히스토그램

    Args:
        tolerance_cm: 허용 편차 범위 (cm). 기본값 1.0cm.
    """
    if not HAS_MATPLOTLIB:
        return None

    _init_fonts()
    tol = tolerance_cm

    times1, values1 = parse_tid_for_graph(tid_path)
    times2, values2 = parse_tid_for_graph(reference_path)
    summary_a = _load_run_summary(tid_path)
    summary_b = _load_run_summary(reference_path)

    if not times1 or not times2:
        return None

    if output_image is None:
        output_image = tid_path + '.compare.png'

    basename = os.path.basename(tid_path)

    # 시간 매칭
    ref_dict = {t: v for t, v in zip(times2, values2)}
    matched_t, matched_v1, matched_v2, residuals = [], [], [], []
    for t, v in zip(times1, values1):
        if t in ref_dict:
            matched_t.append(t)
            matched_v1.append(v)
            matched_v2.append(ref_dict[t])
            residuals.append((v - ref_dict[t]) * 100)

    residuals_np = np.array(residuals) if residuals else np.array([0])

    fig = plt.figure(figsize=(18, 12), dpi=dpi)
    fig.patch.set_facecolor('white')

    # 2x2 레이아웃
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1],
                          width_ratios=[3, 1], hspace=0.25, wspace=0.15)

    ax_main = fig.add_subplot(gs[0, 0])    # 좌상: 전체 시계열
    ax_zoom = fig.add_subplot(gs[0, 1])    # 우상: 확대 뷰
    ax_res  = fig.add_subplot(gs[1, 0])    # 좌하: 잔차
    ax_hist = fig.add_subplot(gs[1, 1])    # 우하: 히스토그램

    hours = (times1[-1] - times1[0]).total_seconds() / 3600

    # ── 좌상: 전체 시계열 비교 ──────────────────────────────
    ax_main.plot(times2, values2, color=_C.RED, linewidth=2.0,
                 label='참조값 (TideBedLite)', alpha=0.7, zorder=3)
    ax_main.plot(times1, values1, color=_C.BLUE, linewidth=1.0,
                 label='결과값 (TideBedPy)', alpha=0.95, zorder=4)
    ax_main.fill_between(times1, values1, alpha=0.08, color=_C.BLUE, zorder=2)

    _style_ax(ax_main, ylabel='Tc (m)')
    ax_main.set_title(f'조석보정 비교 검증 - {basename}',
                      fontsize=13, fontweight='bold', color=_C.TITLE, pad=10)
    ax_main.legend(loc='upper right', fontsize=9, framealpha=0.9)
    _annotate_extrema(ax_main, times1, values1)
    _add_brief_box(
        ax_main,
        _build_compare_driver_lines(summary_a, summary_b, tol),
        loc='upper left',
    )
    _add_compare_contributor_inset(ax_main, summary_a, summary_b, loc='lower right')
    _auto_xfmt(ax_main, hours)

    # 최대 편차 구간 표시 (확대 영역)
    if matched_t and len(residuals) > 0:
        max_idx = int(np.argmax(np.abs(residuals_np)))
        zoom_center = matched_t[max_idx]

        # 확대 범위: 최대편차 전후 6시간
        from datetime import timedelta
        zoom_start = zoom_center - timedelta(hours=6)
        zoom_end = zoom_center + timedelta(hours=6)

        # 확대 영역 하이라이트
        ax_main.axvspan(zoom_start, zoom_end,
                        alpha=0.1, color=_C.ORANGE, zorder=1)
        ax_main.annotate('확대 구간', xy=(zoom_center, max(values1)),
                         fontsize=7, color=_C.ORANGE, ha='center',
                         va='bottom')

        # ── 우상: 확대 뷰 ────────────────────────────────
        zoom_t1, zoom_v1, zoom_v2 = [], [], []
        for t, v1, v2 in zip(matched_t, matched_v1, matched_v2):
            if zoom_start <= t <= zoom_end:
                zoom_t1.append(t)
                zoom_v1.append(v1)
                zoom_v2.append(v2)

        if zoom_t1:
            ax_zoom.plot(zoom_t1, zoom_v2, color=_C.RED, linewidth=2.5,
                         label='참조', alpha=0.7, marker='o', markersize=1.5)
            ax_zoom.plot(zoom_t1, zoom_v1, color=_C.BLUE, linewidth=1.2,
                         label='결과', alpha=0.95, marker='s', markersize=1.5)

            # 최대편차 포인트 강조
            if zoom_center in [t for t in zoom_t1]:
                peak_idx = zoom_t1.index(zoom_center)
                ax_zoom.annotate(
                    f'Δ={residuals[max_idx]:.3f}cm',
                    xy=(zoom_center, zoom_v1[peak_idx]),
                    xytext=(10, 15), textcoords='offset points',
                    fontsize=8, color=_C.RED, fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color=_C.RED, lw=1.2))
            _add_brief_box(
                ax_zoom,
                [
                    f"최대 residual: {residuals[max_idx]:+.3f} cm",
                    f"확대 구간: {zoom_start:%m/%d %H:%M} - {zoom_end:%m/%d %H:%M}",
                ],
                loc='lower left',
            )

        _style_ax(ax_zoom, ylabel='Tc (m)')
        ax_zoom.set_title('최대편차 구간 확대', fontsize=10,
                          fontweight='bold', color=_C.ORANGE, pad=6)
        ax_zoom.legend(fontsize=8, loc='upper right')
        ax_zoom.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    else:
        ax_zoom.text(0.5, 0.5, '매칭 데이터 없음', transform=ax_zoom.transAxes,
                     ha='center', va='center', fontsize=10, color=_C.GRAY)
        _style_ax(ax_zoom)

    # ── 좌하: 잔차 시계열 ────────────────────────────────
    if matched_t:
        ax_res.fill_between(matched_t, residuals, 0,
                            where=[abs(r) <= tol for r in residuals],
                            color=_C.GREEN_L, alpha=0.5,
                            label=f'±{tol}cm 이내')
        ax_res.fill_between(matched_t, residuals, 0,
                            where=[abs(r) > tol for r in residuals],
                            color='#FFCDD2', alpha=0.6,
                            label=f'±{tol}cm 초과')
        ax_res.plot(matched_t, residuals, color=_C.TEXT, linewidth=0.5,
                    alpha=0.6)

        ax_res.axhline(y=0, color=_C.GRAY, linewidth=0.8, alpha=0.5)
        ax_res.axhline(y=tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.5)
        ax_res.axhline(y=-tol, color=_C.RED, linewidth=0.8,
                       linestyle='--', alpha=0.5)

        max_abs = max(abs(residuals_np.min()), abs(residuals_np.max()), tol * 1.5)
        ax_res.set_ylim(-max_abs * 1.3, max_abs * 1.3)
        peak_idx = int(np.argmax(np.abs(residuals_np)))
        peak_time = matched_t[peak_idx]
        peak_value = residuals[peak_idx]
        peak_offset = 12 if peak_value >= 0 else -18
        peak_va = 'bottom' if peak_value >= 0 else 'top'
        ax_res.scatter([peak_time], [peak_value], color=_C.ORANGE, s=32,
                       zorder=5, edgecolors='white', linewidths=0.8)
        ax_res.annotate(
            f'최대 차이 {peak_value:+.3f}cm',
            xy=(peak_time, peak_value),
            xytext=(10, peak_offset),
            textcoords='offset points',
            fontsize=7.5,
            color=_C.ORANGE,
            fontweight='bold',
            va=peak_va,
            bbox=dict(boxstyle='round,pad=0.25', fc='white',
                      ec=_C.ORANGE, alpha=0.9),
            arrowprops=dict(arrowstyle='->', color=_C.ORANGE,
                            lw=0.8, alpha=0.7),
            zorder=6,
        )

    _style_ax(ax_res, ylabel='잔차 (cm)', xlabel='시간')
    ax_res.set_title('잔차 (결과 − 참조)', fontsize=10,
                     fontweight='bold', color=_C.TEXT, pad=6, loc='left')
    _auto_xfmt(ax_res, hours)

    # ── 우하: 히스토그램 + 통계 ─────────────────────────
    if len(residuals) > 0:
        n_bins = min(80, max(20, len(residuals) // 200))
        ax_hist.hist(residuals_np, bins=n_bins, orientation='horizontal',
                     color=_C.BLUE_LIGHT, edgecolor=_C.BLUE,
                     linewidth=0.5, alpha=0.8)

        ax_hist.axhline(y=0, color=_C.GRAY, linewidth=0.8, alpha=0.5)
        ax_hist.axhline(y=tol, color=_C.RED, linewidth=0.8,
                        linestyle='--', alpha=0.5)
        ax_hist.axhline(y=-tol, color=_C.RED, linewidth=0.8,
                        linestyle='--', alpha=0.5)

        max_diff = np.max(np.abs(residuals_np))
        mean_diff = np.mean(residuals_np)
        std_diff = np.std(residuals_np)
        rms_diff = np.sqrt(np.mean(residuals_np ** 2))
        within_tol = np.sum(np.abs(residuals_np) <= tol) / len(residuals_np) * 100

        verdict = "PASS" if max_diff <= tol else "PASS" if within_tol >= 99 else "검토 필요"
        verdict_color = _C.GREEN if within_tol >= 99 else _C.ORANGE

        stats = (
            f'매칭: {len(residuals):,}개\n'
            f'최대: {max_diff:.4f}cm\n'
            f'평균: {mean_diff:+.4f}cm\n'
            f'σ: {std_diff:.4f}cm\n'
            f'RMS: {rms_diff:.4f}cm\n'
            f'±{tol}cm: {within_tol:.1f}%\n'
            f'판정: {verdict}'
        )
        ax_hist.text(0.95, 0.95, stats, transform=ax_hist.transAxes,
                     fontsize=8, va='top', ha='right',
                     bbox=dict(boxstyle='round,pad=0.5', fc='white',
                               ec=_C.GRID, alpha=0.95))

    _style_ax(ax_hist, xlabel='빈도 (개)')
    ax_hist.set_title('잔차 분포', fontsize=10, fontweight='bold',
                      color=_C.TEXT, pad=6, loc='left')

    # 워터마크
    fig.text(0.995, 0.003, 'TideBedPy  |  by Junhyub',
             fontsize=7, color='#bbb', ha='right', va='bottom',
             style='italic')

    plt.savefig(output_image, dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    logger.info(f"비교 그래프 생성: {output_image}")
    return output_image
