"""WeightChart -- PyQtGraph-based stacked area chart for station weights."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Radius

try:
    import pyqtgraph as pg
    import numpy as np
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

# 10-color palette for stations — high contrast, easily distinguishable
PALETTE = [
    "#F59E0B",  # amber (accent)
    "#3B82F6",  # blue
    "#EF4444",  # red
    "#10B981",  # emerald
    "#A855F7",  # purple
    "#EC4899",  # pink
    "#06B6D4",  # cyan
    "#F97316",  # orange
    "#6366F1",  # indigo
    "#14B8A6",  # teal
]

GAP_COLOR = "#EF444440"


class WeightChart(QWidget):
    """Stacked area chart showing station contribution weights over time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not HAS_PYQTGRAPH:
            self._fallback = QLabel(
                "pyqtgraph / numpy 미설치 -- pip install pyqtgraph numpy 실행 필요"
            )
            self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback.setStyleSheet(f"""
                color: {Dark.MUTED};
                font-size: {Font.SM}px;
                background: {Dark.BG};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
                padding: 40px;
            """)
            layout.addWidget(self._fallback)
            return

        pg.setConfigOptions(antialias=True, background=Dark.BG, foreground=Dark.TEXT)

        self._plot_widget = pg.PlotWidget()

        self._plot_widget.setStyleSheet(f"""
            border: 1px solid {Dark.BORDER};
            border-radius: {Radius.BASE}px;
        """)

        plot_item = self._plot_widget.getPlotItem()
        plot_item.showGrid(x=True, y=True, alpha=0.15)
        for axis_name in ("bottom", "left"):
            ax = plot_item.getAxis(axis_name)
            ax.setPen(pg.mkPen("#374151", width=0.5))
            ax.setTextPen(pg.mkPen(Dark.TEXT))
            ax.setTickFont(pg.QtGui.QFont("Pretendard", 9))
        label_style = {"color": Dark.TEXT, "font-size": "11px"}
        plot_item.setLabel("left", "기여도 (Weight)", **label_style)
        plot_item.setLabel("bottom", "", **label_style)
        plot_item.setYRange(0, 1.05)

        layout.addWidget(self._plot_widget, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(self, times: list[datetime],
                 station_weights_dict: dict[str, list[float]]):
        """
        Plot stacked area chart.

        Args:
            times: list of datetime for X axis
            station_weights_dict: {station_name: [weight_per_time_point]}
                Each weight is 0-1, stacked total should be ~1.0.
        """
        if not HAS_PYQTGRAPH:
            return

        self.clear()

        if not times or not station_weights_dict:
            return

        epochs = np.array([t.timestamp() for t in times])
        n = len(epochs)
        station_names = list(station_weights_dict.keys())

        # Build cumulative stack
        cumulative = np.zeros(n)
        color_idx = 0

        # Draw stacked areas in REVERSE order (top layer first) using fillLevel
        # so each layer fills down to 0 and gets occluded by the one below
        reversed_names = list(reversed(station_names))
        reversed_cumulative = []

        # Pre-compute cumulative sums for each layer top
        cum = np.zeros(n)
        layer_tops = {}
        for name in station_names:
            cum = cum + np.array(station_weights_dict[name])
            layer_tops[name] = cum.copy()

        # Build legend as TextItem (safe — no addLegend/removeItem crashes)
        plot_item = self._plot_widget.getPlotItem()

        # Draw from top to bottom (reverse so lower layers occlude)
        from PySide6.QtGui import QColor
        for name in reversed_names:
            idx = station_names.index(name)
            color_hex = PALETTE[idx % len(PALETTE)]
            top = layer_tops[name]

            # Use QColor with high alpha for clear color distinction
            fill_color = QColor(color_hex)
            fill_color.setAlpha(220)

            curve = pg.PlotCurveItem(
                epochs, top,
                pen=pg.mkPen(color_hex, width=1.5),
                brush=pg.mkBrush(fill_color),
                fillLevel=0,
            )
            self._plot_widget.addItem(curve)
            self._items.append(curve)

        # Manual legend box (top-right) — readable size
        legend_lines = []
        for i, name in enumerate(station_names):
            color = PALETTE[i % len(PALETTE)]
            legend_lines.append(
                f"<span style='color:{color};font-size:16px;font-weight:bold;'>"
                f"&#9632;</span> "
                f"<span style='color:{Dark.TEXT};font-size:12px;'>{name}</span>"
            )
        legend_html = "<br>".join(legend_lines)
        legend_item = pg.TextItem(
            html=f"<div style='background:{Dark.NAVY}F0;padding:8px 14px;"
                 f"border:1px solid {Dark.BORDER};border-radius:6px;'>"
                 f"{legend_html}</div>",
            anchor=(1, 0),
        )
        legend_item.setPos(float(epochs[-1]), 1.05)
        plot_item.addItem(legend_item)
        self._items.append(legend_item)

        cumulative = cum

        # Set X range explicitly (PlotCurveItem with addItem doesn't auto-range)
        margin = (epochs[-1] - epochs[0]) * 0.02 if n > 1 else 1
        plot_item.setXRange(float(epochs[0] - margin), float(epochs[-1] + margin), padding=0)

        # Format time axis — max 6 ticks to avoid overlap
        try:
            ax = plot_item.getAxis("bottom")
            max_ticks = 6
            step = max(1, n // max_ticks)
            # Choose format based on time range
            total_hours = (epochs[-1] - epochs[0]) / 3600 if n > 1 else 0
            if total_hours > 48:
                fmt = "%m/%d"
            else:
                fmt = "%m/%d %H:%M"
            ticks = []
            for i in range(0, n, step):
                ticks.append((float(epochs[i]), times[i].strftime(fmt)))
            ax.setTicks([ticks])
        except Exception:
            pass

    def clear(self):
        """Remove all items."""
        if not HAS_PYQTGRAPH:
            return
        for item in self._items:
            try:
                self._plot_widget.removeItem(item)
            except Exception:
                pass
        self._items.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_gap_region(self, epochs, start_idx: int, end_idx: int):
        """Add a red translucent region for gaps."""
        x0 = epochs[start_idx]
        x1 = epochs[end_idx]
        # Extend slightly for visibility
        margin = (x1 - x0) * 0.05 if x1 > x0 else 30
        region = pg.LinearRegionItem(
            values=[x0 - margin, x1 + margin],
            movable=False,
            brush=pg.mkBrush(GAP_COLOR),
            pen=pg.mkPen(None),
        )
        self._plot_widget.addItem(region)
        self._items.append(region)

    @staticmethod
    def _make_time_ticks(times: list[datetime], epochs):
        """Generate tick labels for time axis."""
        if not times:
            return []
        n = len(times)
        step = max(1, n // 8)
        ticks = [(float(epochs[i]), times[i].strftime("%m/%d %H:%M"))
                 for i in range(0, n, step)]
        return [ticks]
