"""TideChart -- PyQtGraph-based interactive tide correction chart widget."""

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Radius

ACCENT = "#F59E0B"
REF_COLOR = "#3B82F6"
GRID_COLOR = "#1F2937"

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


# ---------------------------------------------------------------
# Custom axis that converts epoch seconds to readable date/time
# ---------------------------------------------------------------
if HAS_PYQTGRAPH:
    class DateTimeAxisItem(pg.AxisItem):
        """X-axis that renders epoch timestamps as human-readable strings."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._range_seconds: float = 7 * 86400  # default assumption

        def tickStrings(self, values, scale, spacing):
            if not values:
                return []
            # Determine visible range to pick format
            vmin, vmax = min(values), max(values)
            self._range_seconds = max(vmax - vmin, 1)

            if self._range_seconds < 7 * 86400:
                fmt = "%m/%d %H:%M"
            else:
                fmt = "%Y/%m/%d"

            strings = []
            for v in values:
                try:
                    strings.append(datetime.fromtimestamp(v).strftime(fmt))
                except (OSError, ValueError, OverflowError):
                    strings.append("")
            return strings

        def tickSpacing(self, minVal, maxVal, size):
            """Return sensible tick spacings based on time range."""
            rng = max(maxVal - minVal, 1)

            # (major_spacing, minor_spacing) in seconds
            candidates = [
                (60,          10),           # 1 min / 10 s
                (300,         60),           # 5 min / 1 min
                (900,         300),          # 15 min / 5 min
                (3600,        900),          # 1 h / 15 min
                (7200,        1800),         # 2 h / 30 min
                (21600,       3600),         # 6 h / 1 h
                (43200,       7200),         # 12 h / 2 h
                (86400,       21600),        # 1 d / 6 h
                (172800,      43200),        # 2 d / 12 h
                (604800,      86400),        # 7 d / 1 d
                (2592000,     604800),       # 30 d / 7 d
                (7776000,     2592000),      # 90 d / 30 d
            ]

            # Pick the spacing that yields ~5-10 major ticks
            for major, minor in candidates:
                n_ticks = rng / major
                if 3 <= n_ticks <= 12:
                    return [(major, 0), (minor, 0)]

            # Fallback: divide range into ~6 ticks
            major = rng / 6
            return [(major, 0), (major / 4, 0)]


class TideChart(QWidget):
    """Interactive tide correction chart with zoom, pan, and crosshair."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curves: list = []
        self._gap_regions: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not HAS_PYQTGRAPH:
            self._fallback = QLabel(
                "pyqtgraph 미설치 -- pip install pyqtgraph 실행 필요"
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

        # -- Custom DateTime axis for the bottom --
        self._dt_axis = DateTimeAxisItem(orientation="bottom")
        self._dt_axis.setPen(pg.mkPen(GRID_COLOR))
        self._dt_axis.setTextPen(pg.mkPen(Dark.MUTED))
        self._dt_axis.setStyle(tickFont=pg.QtGui.QFont(Font.MONO, 10))

        self._plot_widget = pg.PlotWidget(axisItems={"bottom": self._dt_axis})
        self._plot_widget.setMinimumHeight(220)
        self._plot_widget.setStyleSheet(f"""
            border: 1px solid {Dark.BORDER};
            border-radius: {Radius.BASE}px;
        """)

        plot_item = self._plot_widget.getPlotItem()
        plot_item.showGrid(x=True, y=True, alpha=0.3)

        # Left axis styling
        left_axis = plot_item.getAxis("left")
        left_axis.setPen(pg.mkPen(GRID_COLOR))
        left_axis.setTextPen(pg.mkPen(Dark.MUTED))
        left_axis.setStyle(tickFont=pg.QtGui.QFont(Font.MONO, 10))

        # Axis labels with larger font
        label_style = {"color": Dark.TEXT, "font-size": "11px"}
        plot_item.setLabel("left", "Tc (cm)", **label_style)
        plot_item.setLabel("bottom", "", **label_style)  # Time axis formatted by DateTimeAxisItem

        # Crosshair
        self._vline = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen(Dark.MUTED, width=1, style=Qt.PenStyle.DashLine))
        self._hline = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen(Dark.MUTED, width=1, style=Qt.PenStyle.DashLine))
        plot_item.addItem(self._vline, ignoreBounds=True)
        plot_item.addItem(self._hline, ignoreBounds=True)

        # Corner label for crosshair readout
        self._info_label = pg.TextItem(anchor=(0, 0), color=Dark.TEXT)
        self._info_label.setFont(pg.QtGui.QFont(Font.MONO, 10))
        plot_item.addItem(self._info_label, ignoreBounds=True)

        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Store time data for crosshair lookup
        self._time_data: list[datetime] = []
        self._value_data: list[float] = []
        self._epoch_data: list[float] = []

        layout.addWidget(self._plot_widget)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(self, times: list[datetime], values: list[float],
                 label: str = "Correction",
                 gap_threshold_hours: float = 2.0):
        """Plot primary tide correction data with gap detection.

        Args:
            gap_threshold_hours: If consecutive points are more than this many
                hours apart, the line is broken and a red gap band is drawn.
        """
        if not HAS_PYQTGRAPH:
            return

        import numpy as np

        self._time_data = times
        self._value_data = values
        self._epoch_data = [t.timestamp() for t in times]

        # Clear previous curves
        self.clear()

        epochs = np.array(self._epoch_data, dtype=float)
        vals = np.array(values, dtype=float)
        gap_sec = gap_threshold_hours * 3600

        # Insert NaN at gaps so pyqtgraph breaks the line
        if len(epochs) > 1:
            diffs = np.diff(epochs)
            gap_indices = np.where(diffs > gap_sec)[0]  # indices before each gap

            if len(gap_indices) > 0:
                # Save gap endpoint info before inserting NaN
                gap_segments = []
                for gi in gap_indices:
                    t_start = self._epoch_data[gi]
                    t_end = self._epoch_data[gi + 1]
                    v_start = values[gi]
                    v_end = values[gi + 1]
                    gap_segments.append((t_start, t_end, v_start, v_end))

                # Build arrays with NaN inserted at gap positions
                insert_epochs = []
                insert_vals = []
                for gi in gap_indices:
                    mid = (epochs[gi] + epochs[gi + 1]) / 2
                    insert_epochs.append(mid)
                    insert_vals.append(float("nan"))

                epochs = np.insert(epochs, gap_indices + 1, insert_epochs)
                vals = np.insert(vals, gap_indices + 1, insert_vals)

                # Draw thin gray dashed interpolation lines across gaps
                plot_item = self._plot_widget.getPlotItem()
                gap_pen = pg.mkPen("#6B7280", width=1, style=Qt.PenStyle.DashLine)
                for t_start, t_end, v_start, v_end in gap_segments:
                    gap_hours = (t_end - t_start) / 3600
                    # Dashed interpolation line connecting gap endpoints
                    interp_curve = pg.PlotDataItem(
                        [t_start, t_end], [v_start, v_end],
                        pen=gap_pen,
                    )
                    interp_curve.setZValue(-5)
                    plot_item.addItem(interp_curve)
                    self._gap_regions.append(interp_curve)
                    # Subtle gap label at midpoint
                    mid_t = (t_start + t_end) / 2
                    mid_v = (v_start + v_end) / 2
                    label_text = f"{gap_hours:.0f}h" if gap_hours < 48 else f"{gap_hours/24:.1f}d"
                    gap_label = pg.TextItem(
                        text=f"GAP {label_text}",
                        color="#6B7280",
                        anchor=(0.5, 1),
                    )
                    gap_label.setFont(pg.QtGui.QFont("Pretendard", 8))
                    plot_item.addItem(gap_label)
                    gap_label.setPos(mid_t, mid_v)
                    self._gap_regions.append(gap_label)

        pen = pg.mkPen(color=ACCENT, width=2)
        curve = self._plot_widget.plot(
            epochs.tolist(), vals.tolist(),
            pen=pen, name=label, connect="finite",
        )
        self._curves.append(curve)

    def add_reference(self, times: list[datetime], values: list[float],
                      label: str = "Reference"):
        """Overlay a reference series in blue."""
        if not HAS_PYQTGRAPH:
            return

        epochs = [t.timestamp() for t in times]
        pen = pg.mkPen(color=REF_COLOR, width=2, style=Qt.PenStyle.DashLine)
        curve = self._plot_widget.plot(epochs, values, pen=pen, name=label)
        self._curves.append(curve)

        # Add legend if not already present
        plot_item = self._plot_widget.getPlotItem()
        if plot_item.legend is None:
            legend = plot_item.addLegend(
                offset=(10, 10),
                brush=pg.mkBrush(Dark.NAVY + "CC"),
                pen=pg.mkPen(Dark.BORDER),
            )
            legend.setLabelTextColor(Dark.TEXT)

    def clear(self):
        """Remove all curves and gap regions."""
        if not HAS_PYQTGRAPH:
            return
        for c in self._curves:
            self._plot_widget.removeItem(c)
        self._curves.clear()
        for r in self._gap_regions:
            self._plot_widget.removeItem(r)
        self._gap_regions.clear()
        plot_item = self._plot_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_mouse_moved(self, pos):
        if not self._epoch_data:
            return
        vb = self._plot_widget.getPlotItem().vb
        mouse_point = vb.mapSceneToView(pos)
        x, y = mouse_point.x(), mouse_point.y()

        self._vline.setPos(x)
        self._hline.setPos(y)

        # Find nearest time
        idx = self._find_nearest_index(x)
        if idx is not None:
            t = self._time_data[idx]
            v = self._value_data[idx]
            self._info_label.setText(
                f"{t.strftime('%Y/%m/%d %H:%M:%S')} | Tc: {v:,.2f} cm"
            )
            # Position label at top-left of view
            view_range = vb.viewRange()
            self._info_label.setPos(view_range[0][0], view_range[1][1])

    def _find_nearest_index(self, epoch_x: float) -> Optional[int]:
        if not self._epoch_data:
            return None
        best_idx = 0
        best_dist = abs(self._epoch_data[0] - epoch_x)
        for i, e in enumerate(self._epoch_data):
            d = abs(e - epoch_x)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx
