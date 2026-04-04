"""ViewerPanel -- Rich visualization dashboard for TID correction results.

Auto-loads after correction completion AND supports manual TID file loading.
5 sections: Tide chart, Weight chart, Nav track map, Histogram, Statistics.
"""

import os
import sys
import logging
import html
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QFileDialog, QScrollArea, QGridLayout,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius

from tidebedpy.desktop.widgets.path_row import PathRow

logger = logging.getLogger(__name__)

ACCENT = "#F59E0B"
GRID_COLOR = "#1F2937"

try:
    import pyqtgraph as pg
    import numpy as np
    HAS_PYQTGRAPH = True
except ImportError as e:
    logger.warning(f"Optional module unavailable: {e}")
    HAS_PYQTGRAPH = False

try:
    from tidebedpy.desktop.widgets.tide_chart import TideChart
    HAS_TIDE_CHART = True
except ImportError as e:
    logger.warning(f"Optional module unavailable: {e}")
    HAS_TIDE_CHART = False

try:
    from tidebedpy.desktop.widgets.weight_chart import WeightChart
    HAS_WEIGHT_CHART = True
except ImportError as e:
    logger.warning(f"Optional module unavailable: {e}")
    HAS_WEIGHT_CHART = False

# Coastline reader
try:
    from tidebedpy.output.map_view import _read_shp_polygons
    HAS_SHP_READER = True
except ImportError as e:
    logger.warning(f"Optional module unavailable: {e}")
    HAS_SHP_READER = False

def _find_coastline_path():
    """Search for fareast_merge.shp in common locations."""
    candidates = [
        # config-based
        os.path.join(os.environ.get("TIDEBEDPY_DATA", ""), "해안선", "fareast_merge.shp"),
        # relative to project
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "info", "해안선", "fareast_merge.shp"),
        # legacy locations
        r"C:\Users\JWONLINETEAM\Desktop\TideBed (2)\info\해안선\fareast_merge.shp",
        r"C:\Users\JWONLINETEAM\Desktop\TideBed\info\해안선\fareast_merge.shp",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""

COASTLINE_PATH = _find_coastline_path()


# ── Color utilities ──────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _make_colormap_lut(n: int = 256) -> "np.ndarray":
    """Generate a coolwarm-style LUT (256x4 uint8)."""
    lut = np.zeros((n, 4), dtype=np.uint8)
    for i in range(n):
        t = i / (n - 1)
        if t < 0.5:
            # blue to white
            f = t * 2
            r = int(59 + (255 - 59) * f)
            g = int(76 + (255 - 76) * f)
            b = int(192 + (255 - 192) * f)
        else:
            # white to red
            f = (t - 0.5) * 2
            r = 255
            g = int(255 - (255 - 76) * f)
            b = int(255 - (255 - 76) * f)
        lut[i] = [r, g, b, 220]
    return lut


class ViewerPanel(QWidget):
    """Interactive viewer for TID correction result files."""

    def __init__(self, controller, tr=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._t = tr or (lambda key, default=None, **kwargs: default or key)
        self._viz_data: Optional[Dict] = None
        self._tab_empty_labels: Dict[int, QLabel] = {}
        self._build_ui()

    # ══════════════════════════════════════════════════════════
    #  UI Construction
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        from PySide6.QtWidgets import QStackedWidget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title
        title = QLabel(self._t("viewer_title", "결과 뷰어"))
        title.setStyleSheet(f"""
            color: {Dark.TEXT_BRIGHT};
            font-size: {Font.LG}px;
            font-weight: {Font.BOLD};
            padding: {Space.BASE}px {Space.LG}px {Space.SM}px;
            background: transparent;
        """)
        outer.addWidget(title)

        # Tab bar
        self._tab_bar = QHBoxLayout()
        self._tab_bar.setContentsMargins(Space.LG, 0, Space.LG, 0)
        self._tab_bar.setSpacing(4)
        self._tab_buttons: List[QPushButton] = []
        tab_names = [
            self._t("time_series", "시계열"),
            self._t("contribution", "기여도"),
            self._t("track_map", "항적 지도"),
            self._t("distribution", "분포"),
            self._t("statistics", "통계"),
            self._t("file_load", "파일 로드"),
        ]
        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Dark.MUTED};
                    font-size: {Font.SM}px;
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    color: {Dark.TEXT};
                    background: {Dark.NAVY};
                }}
                QPushButton:checked {{
                    color: {ACCENT};
                    border-bottom: 2px solid {ACCENT};
                    font-weight: {Font.SEMIBOLD};
                }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            self._tab_bar.addWidget(btn)
        self._tab_bar.addStretch()
        outer.addLayout(self._tab_bar)

        # Separator line
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Dark.BORDER};")
        outer.addWidget(sep)

        # Stacked content
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {Dark.BG};")
        outer.addWidget(self._stack, 1)

        # Build each tab page
        self._pages: List[QWidget] = []

        # Tab 0: Tide chart
        page0 = self._make_page()
        self._content = page0.layout()
        self._build_tide_chart_card()
        self._pages.append(page0)
        self._stack.addWidget(page0)

        # Tab 1: Weight chart
        page1 = self._make_page()
        self._content = page1.layout()
        self._build_weight_chart_card()
        self._add_tab_empty_label(page1, 1)
        self._pages.append(page1)
        self._stack.addWidget(page1)

        # Tab 2: Map
        page2 = self._make_page()
        self._content = page2.layout()
        self._build_map_card()
        self._add_tab_empty_label(page2, 2, "항적 데이터가 로드되면 지도에 표시됩니다")
        self._pages.append(page2)
        self._stack.addWidget(page2)

        # Tab 3: Histogram
        page3 = self._make_page()
        self._content = page3.layout()
        self._build_histogram_card()
        self._add_tab_empty_label(page3, 3)
        self._pages.append(page3)
        self._stack.addWidget(page3)

        # Tab 4: Statistics
        page4 = self._make_page()
        self._content = page4.layout()
        self._build_stats_card()
        self._add_tab_empty_label(page4, 4)
        self._pages.append(page4)
        self._stack.addWidget(page4)

        # Tab 5: File loader
        page5 = self._make_page()
        self._content = page5.layout()
        self._build_file_loader_card()
        self._pages.append(page5)
        self._stack.addWidget(page5)

        # Empty state overlay
        self._empty = QFrame(self._stack)
        self._empty.setStyleSheet(f"""
            QFrame {{
                background: {Dark.BG};
                border: 2px dashed {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            }}
        """)
        empty_layout = QVBoxLayout(self._empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl = QLabel("[TID]")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color: {Dark.DIM}; font-size: 28px; background: transparent; border: none;"
        )
        empty_layout.addWidget(icon_lbl)
        hint_lbl = QLabel(self._t("viewer_empty", "TID 파일을 불러오거나 보정을 실행하면 결과가 표시됩니다"))
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_lbl.setStyleSheet(
            f"color: {Dark.MUTED}; font-size: {Font.SM}px; background: transparent; border: none;"
        )
        empty_layout.addWidget(hint_lbl)

        # Select first tab
        self._switch_tab(0)

    def _make_page(self) -> QWidget:
        """Create a page widget for the stacked content."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(Space.LG, Space.SM, Space.LG, Space.LG)
        layout.setSpacing(0)
        return page

    def _add_tab_empty_label(self, page: QWidget, tab_idx: int, text: str = ""):
        """Add a centered empty-state label to a tab page."""
        msg = text or "보정 완료 후 자동으로 표시됩니다"
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {Dark.MUTED}; font-size: {Font.SM}px; "
            f"background: transparent; border: none; padding: 40px 0;"
        )
        page.layout().addWidget(lbl)
        self._tab_empty_labels[tab_idx] = lbl

    def _hide_tab_empty(self, tab_idx: int):
        """Hide the per-tab empty label for the given index."""
        lbl = self._tab_empty_labels.get(tab_idx)
        if lbl:
            lbl.setVisible(False)

    def _switch_tab(self, idx: int):
        """Switch to the tab at the given index."""
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == idx)

    # ── File Loader Card ──

    def _build_file_loader_card(self):
        card = self._card("fileLoaderCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(Space.BASE, Space.MD, Space.BASE, Space.MD)
        layout.setSpacing(Space.SM)
        layout.addLayout(self._card_header("TID 파일 로드"))

        self._file_rows: List[PathRow] = []
        for i in range(3):
            row = PathRow(
                f"파일 {i + 1}",
                hint=self._t("viewer_file_hint", "TID 파일 경로를 입력하거나 탐색하세요"),
                mode="file",
                file_filter="TID (*.tid);;All (*.*)",
            )
            self._file_rows.append(row)
            layout.addWidget(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._load_btn = QPushButton(self._t("load", "불러오기"))
        self._load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._load_btn.setFixedWidth(120)
        self._load_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: {Dark.BG};
                font-size: {Font.SM}px;
                font-weight: {Font.SEMIBOLD};
                border: none;
                border-radius: {Radius.SM}px;
                padding: 10px 28px;
            }}
            QPushButton:hover {{ background: #D97706; }}
        """)
        self._load_btn.clicked.connect(self._load_files)
        btn_row.addWidget(self._load_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch(1)

        self._content.addWidget(card, 1)

    # ── 1. Tide Chart Card ──

    def _build_tide_chart_card(self):
        self._tide_card = self._card("tideChartCard")
        layout = QVBoxLayout(self._tide_card)
        layout.setContentsMargins(Space.SM, Space.SM, Space.SM, Space.SM)
        layout.setSpacing(0)
        layout.addLayout(self._card_header("조석 보정값 시계열", accent_color=Dark.SLATE))

        if HAS_TIDE_CHART:
            self._tide_chart = TideChart()
            layout.addWidget(self._tide_chart, 1)
        else:
            self._tide_chart = None
            layout.addWidget(self._missing_label("pyqtgraph"))

        self._content.addWidget(self._tide_card, 1)

    # ── 2. Weight Chart Card ──

    def _build_weight_chart_card(self):
        self._weight_card = self._card("weightChartCard")
        layout = QVBoxLayout(self._weight_card)
        layout.setContentsMargins(Space.SM, Space.SM, Space.SM, Space.SM)
        layout.setSpacing(0)
        layout.addLayout(self._card_header("관측소 기여도", accent_color=Dark.SLATE))

        if HAS_WEIGHT_CHART:
            self._weight_chart = WeightChart()
            layout.addWidget(self._weight_chart, 1)
        else:
            self._weight_chart = None
            layout.addWidget(self._missing_label("pyqtgraph / numpy"))

        self._content.addWidget(self._weight_card, 1)

    # ── 3. Navigation Track Map Card ──

    def _build_map_card(self):
        self._map_card = self._card("mapCard")
        layout = QVBoxLayout(self._map_card)
        layout.setContentsMargins(Space.SM, Space.SM, Space.SM, Space.SM)
        layout.setSpacing(0)
        layout.addLayout(self._card_header("항적 지도", accent_color=Dark.SLATE))
        self._map_header_lbl = self._last_header_label

        if HAS_PYQTGRAPH:
            pg.setConfigOptions(background='#0D1117')
            self._map_widget = pg.PlotWidget()
            self._map_widget.setBackground('#162032')  # ocean navy blue
            self._map_widget.setStyleSheet(f"""
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            """)
            plot_item = self._map_widget.getPlotItem()
            plot_item.showGrid(x=True, y=True, alpha=0.15)
            tick_font = pg.QtGui.QFont("Pretendard", 10)
            for axis_name in ("bottom", "left"):
                ax = plot_item.getAxis(axis_name)
                ax.setPen(pg.mkPen(GRID_COLOR))
                ax.setTextPen(pg.mkPen(Dark.MUTED))
                ax.setTickFont(tick_font)
            label_style = {"font-size": "11px", "color": Dark.TEXT}
            plot_item.setLabel("bottom", "경도", units=None, **label_style)
            plot_item.setLabel("left", "위도", units=None, **label_style)
            plot_item.setAspectLocked(False)
            layout.addWidget(self._map_widget, 1)
        else:
            self._map_widget = None
            layout.addWidget(self._missing_label("pyqtgraph"))

        self._content.addWidget(self._map_card, 1)

    # ── 4. Histogram Card ──

    def _build_histogram_card(self):
        self._hist_card = self._card("histCard")
        layout = QVBoxLayout(self._hist_card)
        layout.setContentsMargins(Space.SM, Space.SM, Space.SM, Space.SM)
        layout.setSpacing(0)
        layout.addLayout(self._card_header("분포 히스토그램", accent_color=Dark.SLATE))

        if HAS_PYQTGRAPH:
            self._hist_widget = pg.PlotWidget()
            self._hist_widget.setStyleSheet(f"""
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            """)
            plot_item = self._hist_widget.getPlotItem()
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            plot_item.getAxis("bottom").setPen(pg.mkPen(GRID_COLOR))
            plot_item.getAxis("left").setPen(pg.mkPen(GRID_COLOR))
            plot_item.getAxis("bottom").setTextPen(pg.mkPen(Dark.MUTED))
            plot_item.getAxis("left").setTextPen(pg.mkPen(Dark.MUTED))
            plot_item.setLabel("left", "빈도")
            plot_item.setLabel("bottom", "Tc (cm)")
            layout.addWidget(self._hist_widget, 1)
        else:
            self._hist_widget = None
            layout.addWidget(self._missing_label("pyqtgraph"))

        self._content.addWidget(self._hist_card, 1)

    # ── 5. Statistics Card ──

    def _build_stats_card(self):
        self._stats_card = self._card("statsCard")
        layout = QVBoxLayout(self._stats_card)
        layout.setContentsMargins(Space.BASE, Space.SM, Space.BASE, Space.SM)
        layout.setSpacing(Space.SM)
        layout.addLayout(self._card_header("통계 요약", accent_color=Dark.SLATE))

        self._summary_story = QLabel()
        self._summary_story.setWordWrap(True)
        self._summary_story.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._summary_story.setStyleSheet(f"""
            QLabel {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 10px 12px;
            }}
        """)
        layout.addWidget(self._summary_story)

        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(Space.SM)
        layout.addLayout(self._stats_grid)
        layout.addStretch(1)  # push grid to top

        self._content.addWidget(self._stats_card, 1)

    # ══════════════════════════════════════════════════════════
    #  Public API: receive data from CorrectionWorker
    # ══════════════════════════════════════════════════════════

    def load_result_data(self, viz_data: dict):
        """Parse viz_data from CorrectionWorker and populate all charts.

        Expected keys:
            processed: [(lon, lat, iso_time, tc_cm), ...]
            stations:  [(name, lon, lat), ...]
            output_path: str
            elapsed: float
            weight_times: [iso_time_str, ...]
            station_weights: {name: [w, ...], ...}
        """
        self._viz_data = viz_data
        self._empty.setVisible(False)
        for tab_idx in self._tab_empty_labels:
            self._hide_tab_empty(tab_idx)

        processed = viz_data.get("processed", [])
        stations = viz_data.get("stations", [])
        elapsed = viz_data.get("elapsed", 0.0)
        weight_times_raw = viz_data.get("weight_times", [])
        station_weights = viz_data.get("station_weights", {})

        if not processed:
            return

        # Parse processed data
        times: List[datetime] = []
        tc_values: List[float] = []
        lons: List[float] = []
        lats: List[float] = []
        for lon, lat, iso_time, tc in processed:
            try:
                t = datetime.fromisoformat(iso_time)
                times.append(t)
                tc_values.append(float(tc))
                lons.append(float(lon))
                lats.append(float(lat))
            except (ValueError, TypeError):
                continue

        if not times:
            return

        tc_arr = np.array(tc_values) if HAS_PYQTGRAPH else tc_values

        # Confidence data from worker
        confidence_per_point = viz_data.get("confidence_per_point", [])

        # ── 1. Tide correction time series ──
        try:
            self._populate_tide_chart(times, tc_values, confidence_per_point)
        except Exception as e:
            logger.error(f"시계열 차트 오류: {e}")

        # ── 2. Station weight chart ──
        try:
            self._populate_weight_chart(weight_times_raw, station_weights)
        except Exception as e:
            logger.error(f"기여도 차트 오류: {e}")

        # ── 3. Navigation track map ──
        try:
            self._populate_map(lons, lats, tc_values, stations, confidence_per_point)
        except Exception as e:
            logger.error(f"항적 지도 오류: {e}")

        # ── 4. Histogram ──
        try:
            self._populate_histogram_from_array(tc_arr)
        except Exception as e:
            logger.error(f"히스토그램 오류: {e}")

        # ── 5. Statistics summary ──
        try:
            self._populate_stats_from_result(
                times, tc_arr, stations, elapsed, viz_data
            )
        except Exception as e:
            logger.error(f"통계 요약 오류: {e}")

        self._populate_summary_story(viz_data.get("summary"))

        # Switch to first visualization tab
        self._switch_tab(0)

    # ══════════════════════════════════════════════════════════
    #  Manual TID file loading
    # ══════════════════════════════════════════════════════════

    def _load_files(self):
        """Load TID files from PathRow inputs and display charts/stats."""
        try:
            from tidebedpy.output.report import parse_tid_data_cm
            from tidebedpy.output.summary import load_summary_file
        except ImportError as e:
            logger.warning(f"Optional module unavailable: {e}")
            from output.report import parse_tid_data_cm
            from output.summary import load_summary_file

        all_series = []
        primary_path = ""
        for row in self._file_rows:
            path = row.text().strip()
            if path and os.path.isfile(path):
                raw = parse_tid_data_cm(path)
                times = []
                values = []
                for t_str, tc_val in raw:
                    try:
                        t = datetime.strptime(t_str, "%Y/%m/%d %H:%M:%S")
                        times.append(t)
                        values.append(float(tc_val))
                    except (ValueError, TypeError):
                        continue
                if times:
                    if not primary_path:
                        primary_path = path
                    all_series.append((os.path.basename(path), times, values))

        if not all_series:
            self._controller.toast_requested.emit("유효한 TID 파일이 없습니다", "warning")
            return

        self._empty.setVisible(False)
        for tab_idx in self._tab_empty_labels:
            self._hide_tab_empty(tab_idx)

        # Use first series as primary
        name0, times0, values0 = all_series[0]

        # ── 1. Tide chart ──
        if self._tide_chart and HAS_TIDE_CHART:
            self._tide_chart.set_data(times0, values0, label=name0)
            for name, times, values in all_series[1:]:
                self._tide_chart.add_reference(times, values, label=name)

        # ── 2. Weight chart -- not available from TID file ──
        # (no data to show)

        # ── 3. Map -- not available from TID file alone ──
        # (no data to show)

        # ── 4. Histogram (multi-series overlay) ──
        if self._hist_widget and HAS_PYQTGRAPH:
            self._hist_widget.clear()
            colors = [ACCENT, "#3B82F6", "#10B981"]
            for i, (name, _times, values) in enumerate(all_series):
                arr = np.array(values)
                y, x = np.histogram(arr, bins=50)
                color = colors[i % len(colors)]
                self._hist_widget.plot(
                    x, y, stepMode="center",
                    fillLevel=0, fillOutline=True,
                    brush=pg.mkBrush(color + "60"),
                    pen=pg.mkPen(color, width=1.5),
                    name=name,
                )
            # Add stats annotation for primary series
            arr0 = np.array(values0)
            self._add_hist_annotations(arr0)

        # ── 5. Stats grid ──
        self._populate_stats_from_files(all_series)
        file_summary = load_summary_file(primary_path) if primary_path else None
        if not file_summary:
            file_summary = self._build_fallback_summary(primary_path, name0, times0, values0)
        self._populate_summary_story(file_summary)

    # ══════════════════════════════════════════════════════════
    #  Chart population helpers
    # ══════════════════════════════════════════════════════════

    def _populate_summary_story(self, summary: Optional[dict]):
        """Render the shared run summary in the statistics tab."""
        if not hasattr(self, "_summary_story"):
            return

        if not summary:
            self._summary_story.setText(
                "이 결과에는 아직 실행 요약이 없습니다. 현재는 TID 파일에서 읽은 차트와 통계만 표시합니다."
            )
            return

        story = summary.get("story", {})
        settings = summary.get("settings", {})
        lines = []

        headline = summary.get("headline", "").strip()
        if headline:
            lines.append(f"<b>{html.escape(headline)}</b>")

        preset_name = str(settings.get("preset_name", "")).strip()
        preset_summary = str(settings.get("preset_summary", "")).strip()
        if preset_name and preset_summary:
            lines.append(
                f"<b>프리셋</b>: {html.escape(preset_name)} - {html.escape(preset_summary)}"
            )
        elif preset_name:
            lines.append(f"<b>프리셋</b>: {html.escape(preset_name)}")
        elif preset_summary:
            lines.append(f"<b>프리셋</b>: {html.escape(preset_summary)}")

        for section_name in ("workflow", "rationale", "quality", "stations"):
            section_lines = story.get(section_name, [])
            if section_lines:
                lines.append(html.escape(section_lines[0]))

        contributors = summary.get("contributors", [])[:3]
        if contributors:
            contributor_text = ", ".join(
                f"{item['station_name']} ({item['coverage_pct']:.1f}%, w {item['avg_weight']:.3f})"
                for item in contributors
            )
            lines.append(f"주요 기준항: {html.escape(contributor_text)}")

        guidance = story.get("guidance", [])[:2]
        for guidance_line in guidance:
            lines.append(f"읽는 방법: {html.escape(guidance_line)}")

        generated_files = summary.get("generated_files", [])[:4]
        if generated_files:
            file_text = ", ".join(os.path.basename(path) for path in generated_files)
            lines.append(f"생성 파일: {html.escape(file_text)}")

        self._summary_story.setText("<br>".join(lines))

    def _build_fallback_summary(
        self,
        file_path: str,
        name: str,
        times: List[datetime],
        values: List[float],
    ) -> dict:
        """Create a minimal summary when a sidecar summary file is absent."""
        min_val = min(values) if values else 0.0
        max_val = max(values) if values else 0.0
        mean_val = sum(values) / len(values) if values else 0.0
        return {
            "headline": (
                f"{name} 파일에는 요약 sidecar가 없어 TID 기반 임시 요약만 표시합니다."
            ),
            "generated_files": [file_path] if file_path else [],
            "story": {
                "workflow": [
                    (
                        f"TID 파일 '{os.path.basename(file_path) if file_path else name}'에는 "
                        f"{len(values):,}개 레코드가 있으며, 시간 범위는 "
                        f"{times[0].strftime('%Y-%m-%d %H:%M:%S')} 부터 "
                        f"{times[-1].strftime('%Y-%m-%d %H:%M:%S')} 까지입니다."
                    )
                    if times
                    else "유효한 시간 범위를 확인할 수 없습니다."
                ],
                "rationale": [
                    "이 TID 출력 옆에 .summary.json 파일이 없어 원래 실행 맥락을 확인할 수 없습니다."
                ],
                "quality": [
                    (
                        f"TID 단독 통계: 저장된 m 단위를 desktop cm 단위로 변환한 결과 평균 {mean_val:,.2f} cm, 범위 {min_val:,.2f} ~ {max_val:,.2f} cm입니다."
                    )
                ],
                "stations": [
                    "실행 요약 sidecar가 없어서 기준항 기여 정보는 확인할 수 없습니다."
                ],
                "guidance": [
                    "수동 TID 보기에서는 저장된 m 값을 cm로 바꿔 live correction 화면과 같은 단위로 표시합니다.",
                    "이 임시 화면은 크기 확인용으로 사용하고, 전체 보정 근거는 요약 sidecar 기준으로 해석하는 것이 좋습니다.",
                ],
            },
            "contributors": [],
        }

    def _populate_tide_chart(self, times: List[datetime], values: List[float],
                             confidence: Optional[List[float]] = None):
        """Fill tide correction time series chart with confidence overlay."""
        if not self._tide_chart or not HAS_TIDE_CHART:
            return
        self._tide_chart.set_data(times, values, label="Tc")

        # Add confidence color bands as background overlay
        if confidence and HAS_PYQTGRAPH and len(confidence) == len(times) and len(times) > 1:
            try:
                plot_item = self._tide_chart._plot_widget.getPlotItem()
                timestamps = np.array([t.timestamp() for t in times])

                # Group consecutive points by confidence level into spans
                CONF_COLORS = {
                    "high":   (16, 185, 129, 25),   # green  #10B981
                    "medium": (245, 158, 11, 25),    # yellow #F59E0B
                    "low":    (239, 68, 68, 25),     # red    #EF4444
                }

                def _conf_level(c):
                    if c > 0.8:
                        return "high"
                    elif c >= 0.5:
                        return "medium"
                    return "low"

                # Build spans of uniform confidence level
                spans = []
                cur_level = _conf_level(confidence[0])
                span_start = 0
                for i in range(1, len(confidence)):
                    lvl = _conf_level(confidence[i])
                    if lvl != cur_level:
                        spans.append((span_start, i - 1, cur_level))
                        cur_level = lvl
                        span_start = i
                spans.append((span_start, len(confidence) - 1, cur_level))

                # Add LinearRegionItem for each span (only medium/low to avoid clutter)
                for s_start, s_end, level in spans:
                    if level == "high":
                        continue  # skip high-confidence -- clean background
                    t0 = float(timestamps[s_start])
                    t1 = float(timestamps[min(s_end + 1, len(timestamps) - 1)])
                    if t1 <= t0:
                        t1 = t0 + 1.0
                    rgba = CONF_COLORS[level]
                    region = pg.LinearRegionItem(
                        values=(t0, t1),
                        orientation='vertical',
                        movable=False,
                        brush=pg.mkBrush(*rgba),
                        pen=pg.mkPen(None),
                    )
                    region.setZValue(-10)
                    plot_item.addItem(region)
            except Exception as e:
                logger.debug(f"신뢰도 오버레이 생략: {e}")

    def _populate_weight_chart(self, weight_times_raw: list, station_weights: dict):
        """Fill station weight contribution chart."""
        if not self._weight_chart or not HAS_WEIGHT_CHART:
            return
        if not weight_times_raw or not station_weights:
            logger.debug("기여도 차트: weight_times 또는 station_weights 비어 있음")
            return

        weight_times: List[datetime] = []
        for ts in weight_times_raw:
            try:
                weight_times.append(datetime.fromisoformat(ts))
            except (ValueError, TypeError):
                continue

        if not weight_times:
            logger.debug("기여도 차트: 파싱된 weight_times가 비어 있음")
            return

        # Align station weight lists to match len(weight_times)
        n = len(weight_times)
        aligned_weights: Dict[str, List[float]] = {}
        for name, wlist in station_weights.items():
            if len(wlist) >= n:
                aligned_weights[name] = wlist[:n]
            else:
                # Pad shorter lists with 0.0
                aligned_weights[name] = list(wlist) + [0.0] * (n - len(wlist))

        if not aligned_weights:
            logger.debug("기여도 차트: 정렬된 station_weights가 비어 있음")
            return

        self._weight_chart.set_data(weight_times, aligned_weights)

    def _populate_map(self, lons: List[float], lats: List[float],
                      tc_values: List[float],
                      stations: List[Tuple[str, float, float]],
                      confidence: Optional[List[float]] = None):
        """Fill the navigation track map with coastline, nav track, and stations."""
        if not self._map_widget or not HAS_PYQTGRAPH:
            return
        if not lons:
            return

        self._map_widget.clear()
        plot_item = self._map_widget.getPlotItem()

        lon_arr = np.array(lons)
        lat_arr = np.array(lats)
        tc_arr = np.array(tc_values)

        # Bounding box with padding
        lon_min, lon_max = float(lon_arr.min()), float(lon_arr.max())
        lat_min, lat_max = float(lat_arr.min()), float(lat_arr.max())

        # Include station positions in bbox
        for _name, slon, slat in stations:
            if slon > -900 and slat > -900:
                lon_min = min(lon_min, slon)
                lon_max = max(lon_max, slon)
                lat_min = min(lat_min, slat)
                lat_max = max(lat_max, slat)

        lon_pad = max((lon_max - lon_min) * 0.15, 0.05)
        lat_pad = max((lat_max - lat_min) * 0.15, 0.05)
        bbox = (
            lon_min - lon_pad, lat_min - lat_pad,
            lon_max + lon_pad, lat_max + lat_pad,
        )

        # ── Disable auto range BEFORE adding coastline items ──
        vb = plot_item.getViewBox()
        vb.disableAutoRange()
        vb.enableAutoRange(enable=False)

        # ── Coastline polygons ──
        if hasattr(self, '_map_header_lbl'):
            self._map_header_lbl.setText("항적 지도 (로딩 중...)")
            QApplication.processEvents()
        self._draw_coastline_on_map(plot_item, bbox)
        if hasattr(self, '_map_header_lbl'):
            self._map_header_lbl.setText("항적 지도")

        # ── Nav track scatter colored by Tc ──
        tc_min, tc_max = float(tc_arr.min()), float(tc_arr.max())
        tc_range = tc_max - tc_min if tc_max != tc_min else 1.0

        lut = _make_colormap_lut(256)

        # Downsample for performance (max ~5000 points)
        n_pts = len(lon_arr)
        step = max(1, n_pts // 5000)
        d_lon = lon_arr[::step]
        d_lat = lat_arr[::step]
        d_tc = tc_arr[::step]

        indices = ((d_tc - tc_min) / tc_range * 255).clip(0, 255).astype(int)
        brushes = [pg.mkBrush(*lut[idx]) for idx in indices]

        scatter = pg.ScatterPlotItem(
            x=d_lon, y=d_lat,
            brush=brushes,
            pen=pg.mkPen(None),
            size=6,
            symbol="o",
        )
        plot_item.addItem(scatter)

        # ── Colorbar (manual) ──
        self._add_map_colorbar(plot_item, tc_min, tc_max, lut, bbox)

        # ── Station markers ──
        for name, slon, slat in stations:
            if slon <= -900 or slat <= -900:
                continue
            st_scatter = pg.ScatterPlotItem(
                x=[slon], y=[slat],
                brush=pg.mkBrush("white"),
                pen=pg.mkPen(Dark.RED, width=2),
                size=14,
                symbol="t",
            )
            plot_item.addItem(st_scatter)

            text_item = pg.TextItem(
                text=name, anchor=(0, 1),
                color="white",
                border=pg.mkPen(Dark.BORDER),
                fill=pg.mkBrush("#0D1117CC"),
            )
            text_item.setPos(slon, slat)
            text_item.setFont(pg.QtGui.QFont("Pretendard", 10, pg.QtGui.QFont.Weight.Bold))
            plot_item.addItem(text_item)

        # ── Map legend (top-left) ──
        legend_lines = [
            f"Nav Track ({len(lons):,} pts)",
            f"Tc range: {tc_min:.1f} ~ {tc_max:.1f} cm",
            f"Stations: {len(stations)}",
        ]
        for name, _, _ in stations:
            legend_lines.append(f"  -- {name}")

        # Confidence badge
        if confidence and len(confidence) > 0:
            valid_conf = [c for c in confidence if c > 0.0]
            if valid_conf:
                avg_conf = sum(valid_conf) / len(valid_conf)
                if avg_conf > 0.8:
                    legend_lines.append("Confidence: HIGH")
                elif avg_conf >= 0.5:
                    legend_lines.append("Confidence: MEDIUM")
                else:
                    legend_lines.append("Confidence: LOW")

        legend_text = pg.TextItem(
            text="\n".join(legend_lines),
            anchor=(0, 0),
            color=Dark.TEXT,
            border=pg.mkPen(Dark.BORDER),
            fill=pg.mkBrush("#0D1117DD"),
        )
        legend_text.setFont(pg.QtGui.QFont("Pretendard", 9))
        legend_text.setPos(bbox[0] + (bbox[2] - bbox[0]) * 0.01,
                           bbox[3] - (bbox[3] - bbox[1]) * 0.01)
        plot_item.addItem(legend_text)

        # ── Set initial view to Korean peninsula with data highlighted ──
        vb = plot_item.getViewBox()
        vb.disableAutoRange()
        # Full Korea view: lon 124~132, lat 33~43
        vb.setRange(xRange=(124.0, 132.0), yRange=(33.0, 43.0), padding=0.02)

    def _draw_coastline_on_map(self, plot_item, bbox):
        """Draw coastline polygons from fareast_merge.shp, clipped to bbox."""
        if not HAS_SHP_READER:
            return

        shp_path = COASTLINE_PATH
        if not os.path.isfile(shp_path):
            return

        try:
            # Load ALL polygons — PyQtGraph handles zoom/pan interactively
            # View range is locked to data bbox separately
            polygons = _read_shp_polygons(shp_path, clip_bbox=None)
        except Exception:
            return

        from PySide6.QtGui import QPolygonF, QColor, QPen, QBrush
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QGraphicsPolygonItem

        land_brush = QBrush(QColor(30, 41, 59, 255))    # #1E293B solid
        land_pen = QPen(QColor(74, 85, 104, 200), 0.5)   # thin border

        for ring in polygons:
            n_ring = len(ring)
            if n_ring < 3:
                continue
            # Adaptive downsample: keep at least 3000 pts for large rings,
            # small rings (<500 pts) are kept intact
            if n_ring > 500:
                max_pts = max(3000, min(n_ring, 8000))
                step = max(1, n_ring // max_pts)
                if step > 1:
                    ring = ring[::step] + [ring[-1]]

            poly_points = [QPointF(float(p[0]), float(p[1])) for p in ring]
            qpoly = QPolygonF(poly_points)
            poly_item = QGraphicsPolygonItem(qpoly)
            poly_item.setBrush(land_brush)
            poly_item.setPen(land_pen)
            plot_item.addItem(poly_item)

    def _add_map_colorbar(self, plot_item, tc_min: float, tc_max: float,
                          lut: "np.ndarray", bbox):
        """Add a simple vertical colorbar legend to the map."""
        # Place colorbar as text annotations on the right side
        n_labels = 5
        tc_range = tc_max - tc_min if tc_max != tc_min else 1.0

        # Create a vertical gradient bar using ImageItem
        bar_width = (bbox[2] - bbox[0]) * 0.02
        bar_left = bbox[2] + (bbox[2] - bbox[0]) * 0.01
        bar_bottom = bbox[1] + (bbox[3] - bbox[1]) * 0.15
        bar_top = bbox[3] - (bbox[3] - bbox[1]) * 0.15
        bar_height = bar_top - bar_bottom

        # Gradient image (1 x 256)
        img_data = np.zeros((256, 1, 4), dtype=np.uint8)
        for i in range(256):
            img_data[i, 0] = lut[i]

        img_item = pg.ImageItem(img_data)
        img_item.setRect(bar_left, bar_bottom, bar_width, bar_height)
        plot_item.addItem(img_item)

        # Labels along the bar
        for i in range(n_labels):
            frac = i / (n_labels - 1)
            val = tc_min + frac * tc_range
            y_pos = bar_bottom + frac * bar_height
            label = pg.TextItem(
                text=f"{val:.1f}",
                anchor=(0, 0.5),
                color=Dark.TEXT,
            )
            label.setPos(bar_left + bar_width * 1.3, y_pos)
            label.setFont(pg.QtGui.QFont("Pretendard", 7))
            plot_item.addItem(label)

        # Title
        title_item = pg.TextItem(
            text="Tc (cm)",
            anchor=(0.5, 1),
            color=Dark.MUTED,
        )
        title_item.setPos(bar_left + bar_width * 0.5, bar_top + bar_height * 0.08)
        title_item.setFont(pg.QtGui.QFont("Pretendard", 8))
        plot_item.addItem(title_item)

    def _populate_histogram_from_array(self, tc_arr: "np.ndarray"):
        """Fill histogram from numpy array of Tc values with gradient fill."""
        if not self._hist_widget or not HAS_PYQTGRAPH:
            return

        self._hist_widget.clear()

        y, x = np.histogram(tc_arr, bins=50)
        r, g, b = _hex_to_rgb(ACCENT)

        # Gradient brush: transparent at bottom, accent color at top
        from PySide6.QtGui import QLinearGradient, QColor, QBrush
        from PySide6.QtCore import QPointF
        gradient = QLinearGradient(QPointF(0, 0), QPointF(0, 1))
        gradient.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
        gradient.setColorAt(0.0, QColor(r, g, b, 180))  # top: accent
        gradient.setColorAt(1.0, QColor(r, g, b, 30))    # bottom: transparent

        self._hist_widget.plot(
            x, y, stepMode="center",
            fillLevel=0, fillOutline=True,
            brush=QBrush(gradient),
            pen=pg.mkPen(ACCENT, width=1),
        )

        # Fix axis range to data
        plot_item = self._hist_widget.getPlotItem()
        plot_item.setXRange(float(x[0]), float(x[-1]), padding=0.02)
        plot_item.setYRange(0, float(y.max()) * 1.15, padding=0)
        plot_item.enableAutoRange(axis="x", enable=False)
        plot_item.enableAutoRange(axis="y", enable=False)

        self._add_hist_annotations(tc_arr)

    def _add_hist_annotations(self, tc_arr: "np.ndarray"):
        """Add mean/std lines and stats text box to histogram."""
        if not HAS_PYQTGRAPH or self._hist_widget is None:
            return

        plot_item = self._hist_widget.getPlotItem()
        mean_val = float(tc_arr.mean())
        std_val = float(tc_arr.std())
        min_val = float(tc_arr.min())
        max_val = float(tc_arr.max())

        # Mean line (solid accent)
        mean_line = pg.InfiniteLine(
            pos=mean_val, angle=90, movable=False,
            pen=pg.mkPen(ACCENT, width=2),
        )
        plot_item.addItem(mean_line)

        # +/- 1 std lines (dashed gray)
        std_pen = pg.mkPen("#6B7280", width=1, style=Qt.PenStyle.DashLine)
        std_minus = pg.InfiniteLine(
            pos=mean_val - std_val, angle=90, movable=False, pen=std_pen,
        )
        std_plus = pg.InfiniteLine(
            pos=mean_val + std_val, angle=90, movable=False, pen=std_pen,
        )
        plot_item.addItem(std_minus)
        plot_item.addItem(std_plus)

        # Stats text box inside chart, top-right, semi-transparent dark bg
        stats_text = (
            f"Mean: {mean_val:,.2f} cm\n"
            f"Std: {std_val:,.2f} cm\n"
            f"Min: {min_val:,.2f} cm\n"
            f"Max: {max_val:,.2f} cm"
        )
        text_item = pg.TextItem(
            text=stats_text,
            anchor=(1, 0),
            color=Dark.TEXT,
            border=pg.mkPen(Dark.BORDER),
            fill=pg.mkBrush(Dark.BG + "DD"),
        )
        text_item.setFont(pg.QtGui.QFont("Pretendard", 9))
        plot_item.addItem(text_item)

        # Position at top-right of data range (fixed, not auto-repositioning)
        text_item.setPos(float(tc_arr.max()), float(np.histogram(tc_arr, bins=50)[0].max()) * 1.05)

    def _populate_stats_from_result(self, times: List[datetime],
                                    tc_arr: "np.ndarray",
                                    stations: List[Tuple[str, float, float]],
                                    elapsed: float,
                                    viz_data: Optional[Dict] = None):
        """Fill the stats grid from CorrectionWorker result data (3x3 grid + confidence row)."""
        self._clear_stats_grid()

        if len(times) < 2:
            duration_str = "N/A"
        else:
            dur_sec = (times[-1] - times[0]).total_seconds()
            dur_h = int(dur_sec // 3600)
            dur_m = int((dur_sec % 3600) // 60)
            duration_str = f"{dur_h}h {dur_m}m" if dur_h > 0 else f"{dur_m}m"

        elapsed_str = f"{elapsed:.1f}s" if elapsed else "N/A"

        mean_val = float(tc_arr.mean())
        std_val = float(tc_arr.std())
        min_val = float(tc_arr.min())
        max_val = float(tc_arr.max())
        range_val = max_val - min_val

        # Station names for display
        is_api = self._viz_data.get("use_api", False) if self._viz_data else False
        rank_limit = self._viz_data.get("rank_limit", "?") if self._viz_data else "?"
        st_names = ", ".join(n for n, _, _ in stations) if stations else "N/A"
        st_display = f"{len(stations)}개" if is_api else f"{len(stations)}개 (N={rank_limit})"

        # 3x3 grid
        metrics = [
            ("총 포인트",    f"{len(tc_arr):,}"),
            ("기간",        duration_str),
            ("처리 시간",    elapsed_str),
            ("평균 Tc",     f"{mean_val:,.2f} cm"),
            ("표준편차 Tc",  f"{std_val:,.2f} cm"),
            ("범위",        f"{range_val:,.2f} cm"),
            ("최소 Tc",     f"{min_val:,.2f} cm"),
            ("최대 Tc",     f"{max_val:,.2f} cm"),
            ("관측소",       st_display),
        ]

        for idx, (label, value) in enumerate(metrics):
            row = idx // 3
            col = idx % 3
            self._add_stat_cell(row, col, label, value)

        # ── Confidence / uncertainty metrics (row 3) ──
        vd = viz_data or self._viz_data or {}
        avg_dist = vd.get("avg_station_distance_km", 0.0)
        max_dist = vd.get("max_station_distance_km", 0.0)
        extrap_count = vd.get("extrapolation_count", 0)
        gap_count = vd.get("data_gap_count", 0)
        total_pts = len(tc_arr) if len(tc_arr) > 0 else 1
        extrap_pct = extrap_count / total_pts * 100.0

        if avg_dist > 0 or max_dist > 0 or extrap_count > 0 or gap_count > 0:
            # Row 3: confidence metrics
            self._add_stat_cell(3, 0, "평균 관측소 거리", f"{avg_dist:,.1f} km")
            self._add_stat_cell(3, 1, "최대 관측소 거리", f"{max_dist:,.1f} km")

            # Extrapolation cell with red warning when > 5%
            extrap_text = f"{extrap_count:,}개 ({extrap_pct:.1f}%)"
            if extrap_pct > 5.0:
                self._add_stat_cell(3, 2, "외삽 구간", extrap_text,
                                    value_color=Dark.RED)
            else:
                self._add_stat_cell(3, 2, "외삽 구간", extrap_text)

            # Row 4: data gap count
            self._add_stat_cell(4, 0, "데이터 갭", f"{gap_count:,}개")

    def _populate_stats_from_files(self, series_list):
        """Fill the stats grid for manual TID file loading."""
        self._clear_stats_grid()

        if not HAS_PYQTGRAPH:
            return

        # Header row
        headers = ["파일", "포인트", "평균 (cm)", "최소 (cm)", "최대 (cm)", "표준편차 (cm)", "범위 (cm)"]
        for col_idx, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet(f"""
                color: {Dark.TEXT_BRIGHT};
                font-size: {Font.XS}px;
                font-weight: {Font.SEMIBOLD};
                background: transparent;
                padding: 4px 8px;
            """)
            self._stats_grid.addWidget(lbl, 0, col_idx)

        for row_idx, (name, _times, values) in enumerate(series_list, start=1):
            arr = np.array(values)
            stats = [
                name,
                f"{len(arr):,}",
                f"{arr.mean():.2f}",
                f"{arr.min():.2f}",
                f"{arr.max():.2f}",
                f"{arr.std():.2f}",
                f"{arr.max() - arr.min():.2f}",
            ]
            for col_idx, val in enumerate(stats):
                lbl = QLabel(val)
                lbl.setStyleSheet(f"""
                    color: {Dark.TEXT};
                    font-size: {Font.SM}px;
                    background: transparent;
                    padding: 4px 8px;
                """)
                self._stats_grid.addWidget(lbl, row_idx, col_idx)

    # ══════════════════════════════════════════════════════════
    #  Widget helpers
    # ══════════════════════════════════════════════════════════

    def _add_stat_cell(self, row: int, col: int, label: str, value: str,
                       value_color: Optional[str] = None):
        """Add a single professional metric card to the stats grid."""
        cell = QFrame()
        cell.setMinimumHeight(80)
        cell.setStyleSheet(f"""
            QFrame {{
                background: {Dark.BG};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 10px 14px;
            }}
        """)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(8, 8, 8, 8)
        cell_layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.XS}px;
            background: transparent;
            border: none;
            padding: 0;
        """)
        cell_layout.addWidget(lbl)

        val_clr = value_color or Dark.TEXT_BRIGHT
        val = QLabel(value)
        val.setStyleSheet(f"""
            color: {val_clr};
            font-size: 20px;
            font-weight: {Font.BOLD};
            background: transparent;
            border: none;
            padding: 0;
        """)
        cell_layout.addWidget(val)
        cell_layout.addStretch()

        self._stats_grid.addWidget(cell, row, col)

    def _clear_stats_grid(self):
        """Remove all widgets from the stats grid."""
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _card(self, obj_name: str = "viewerCard") -> QFrame:
        card = QFrame()
        card.setObjectName(obj_name)
        card.setStyleSheet(f"""
            QFrame#{obj_name} {{
                background: {Dark.NAVY};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            }}
        """)
        return card

    def _card_header(self, title: str,
                     accent_color: str = None) -> QHBoxLayout:
        """Create a card header with accent bar and title label.

        Args:
            title: Header text.
            accent_color: Bar color. Defaults to ACCENT for primary cards,
                          pass Dark.SLATE for secondary cards.
        """
        if accent_color is None:
            accent_color = ACCENT
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 4)
        hdr.setSpacing(6)
        bar = QFrame()
        bar.setFixedSize(3, 14)
        bar.setStyleSheet(f"background: {accent_color}; border: none; border-radius: 1px;")
        hdr.addWidget(bar)
        lbl = QLabel(title)
        lbl.setFixedHeight(16)
        lbl.setStyleSheet(f"""
            color: {Dark.TEXT_BRIGHT};
            font-size: {Font.SM}px;
            font-weight: {Font.SEMIBOLD};
            background: transparent;
            border: none;
        """)
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._last_header_label = lbl
        return hdr

    def _missing_label(self, pkg: str) -> QLabel:
        lbl = QLabel(f"{pkg} 미설치 -- pip install {pkg}")
        lbl.setStyleSheet(
            f"color: {Dark.MUTED}; font-size: {Font.SM}px; padding: 40px;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl
