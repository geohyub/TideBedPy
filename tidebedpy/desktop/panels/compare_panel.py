"""ComparePanel -- Compare two TID files side by side."""

import os
import sys
import math
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius

from tidebedpy.desktop.widgets.path_row import PathRow
from tidebedpy.desktop.widgets.tide_chart import TideChart

ACCENT = "#F59E0B"


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Create a dark-theme card frame with optional title."""
    card = QFrame()
    card.setObjectName("cmpCard")
    card.setStyleSheet(f"""
        QFrame#cmpCard {{
            background: {Dark.NAVY};
            border: 1px solid {Dark.BORDER};
            border-radius: {Radius.BASE}px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(Space.BASE, Space.MD, Space.BASE, Space.MD)
    layout.setSpacing(Space.SM)

    if title:
        hdr = QHBoxLayout()
        bar = QFrame()
        bar.setFixedSize(4, 16)
        bar.setStyleSheet(f"background: {ACCENT}; border: none; border-radius: 2px;")
        hdr.addWidget(bar)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"""
            color: {Dark.TEXT_BRIGHT};
            font-size: {Font.SM}px;
            font-weight: {Font.SEMIBOLD};
            background: transparent;
            border: none;
        """)
        hdr.addWidget(lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

    return card, layout


def _stat_label(key: str, value: str) -> QHBoxLayout:
    """Single statistic row: key ... value."""
    row = QHBoxLayout()
    k = QLabel(key)
    k.setStyleSheet(f"""
        color: {Dark.MUTED};
        font-size: {Font.XS}px;
        background: transparent;
        border: none;
    """)
    row.addWidget(k)
    row.addStretch()
    v = QLabel(value)
    v.setStyleSheet(f"""
        color: {Dark.TEXT_BRIGHT};
        font-size: {Font.SM}px;
        font-weight: {Font.SEMIBOLD};
        background: transparent;
        border: none;
    """)
    row.addWidget(v)
    return row


class ComparePanel(QWidget):
    """Panel for comparing two TID files side by side."""

    panel_title = "결과 비교"

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        outer.setSpacing(0)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: {Dark.BG_ALT}; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {Dark.SLATE}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Space.BASE)

        # -- Input card --
        input_card, input_lay = _card("파일 선택")

        self._path_a = PathRow("File A (.tid)", mode="file",
                               file_filter="TID Files (*.tid);;All (*)")
        input_lay.addWidget(self._path_a)

        hint_a = QLabel("  비교 대상 A: 보정 결과 TID 파일")
        hint_a.setStyleSheet(f"color: {Dark.DIM}; font-size: {Font.XS}px; background: transparent; border: none;")
        input_lay.addWidget(hint_a)

        self._path_b = PathRow("File B (.tid)", mode="file",
                               file_filter="TID Files (*.tid);;All (*)")
        input_lay.addWidget(self._path_b)

        hint_b = QLabel("  비교 대상 B: 참조 TID 파일 또는 다른 보정 결과")
        hint_b.setStyleSheet(f"color: {Dark.DIM}; font-size: {Font.XS}px; background: transparent; border: none;")
        input_lay.addWidget(hint_b)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._compare_btn = QPushButton("비교")
        self._compare_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compare_btn.setFixedWidth(120)
        self._compare_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #000000;
                font-size: {Font.SM}px;
                font-weight: {Font.SEMIBOLD};
                border: none;
                border-radius: {Radius.SM}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background: #D97706; }}
            QPushButton:pressed {{ background: #B45309; }}
        """)
        self._compare_btn.clicked.connect(self._run_compare)
        btn_row.addWidget(self._compare_btn)
        btn_row.addStretch()
        input_lay.addLayout(btn_row)

        self._layout.addWidget(input_card)

        # -- Empty state placeholder --
        self._empty_state = QFrame()
        self._empty_state.setStyleSheet(f"""
            QFrame {{
                background: {Dark.NAVY};
                border: 1px dashed {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            }}
        """)
        empty_lay = QVBoxLayout(self._empty_state)
        empty_lay.setContentsMargins(Space.XL, Space.XXL, Space.XL, Space.XXL)
        empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel("[A] vs [B]")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet(f"""
            color: {Dark.DIM};
            font-size: {Font.XL}px;
            font-weight: {Font.BOLD};
            background: transparent;
            border: none;
        """)
        empty_lay.addWidget(empty_icon)

        empty_text = QLabel("두 개의 TID 파일을 선택하고 '비교'를 누르세요")
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.SM}px;
            background: transparent;
            border: none;
            padding-top: {Space.SM}px;
        """)
        empty_lay.addWidget(empty_text)

        self._layout.addWidget(self._empty_state)

        # -- Statistics card (hidden initially) --
        self._stats_card, self._stats_lay = _card("통계")
        self._stats_card.setVisible(False)
        self._layout.addWidget(self._stats_card)

        # -- Charts (hidden initially) --
        self._overlay_card, overlay_lay = _card("보정값 비교")
        self._overlay_chart = TideChart()
        overlay_lay.addWidget(self._overlay_chart)
        self._overlay_card.setVisible(False)
        self._layout.addWidget(self._overlay_card)

        self._diff_card, diff_lay = _card("차이 시계열")
        self._diff_chart = TideChart()
        diff_lay.addWidget(self._diff_chart)
        self._diff_card.setVisible(False)
        self._layout.addWidget(self._diff_card)

        self._layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Compare logic
    # ------------------------------------------------------------------

    def _run_compare(self):
        path_a = self._path_a.path()
        path_b = self._path_b.path()

        if not path_a or not os.path.isfile(path_a):
            self._controller.toast_requested.emit("File A 경로를 확인하세요", "warning")
            return
        if not path_b or not os.path.isfile(path_b):
            self._controller.toast_requested.emit("File B 경로를 확인하세요", "warning")
            return

        try:
            from tidebedpy.output.report import parse_tid_data
        except ImportError:
            self._controller.toast_requested.emit(
                "tidebedpy.output.report 임포트 실패", "error"
            )
            return

        data_a = parse_tid_data(path_a)
        data_b = parse_tid_data(path_b)

        if not data_a:
            self._controller.toast_requested.emit("File A 데이터 없음", "warning")
            return
        if not data_b:
            self._controller.toast_requested.emit("File B 데이터 없음", "warning")
            return

        # Build time-keyed dicts
        dict_a = {t: v for t, v in data_a}
        dict_b = {t: v for t, v in data_b}

        # Match on common timestamps
        common_keys = sorted(set(dict_a.keys()) & set(dict_b.keys()))
        matched = len(common_keys)

        if matched == 0:
            self._controller.toast_requested.emit(
                "공통 시간 데이터가 없습니다", "warning"
            )
            return

        tolerance = 0.01  # meters
        diffs = []
        within = 0
        for key in common_keys:
            d = abs(dict_a[key] - dict_b[key])
            diffs.append(d)
            if d <= tolerance:
                within += 1

        max_diff = max(diffs)
        mean_diff = sum(diffs) / len(diffs)
        rms = math.sqrt(sum(d * d for d in diffs) / len(diffs))
        pct_within = (within / matched) * 100.0

        # Hide empty state, show results
        self._empty_state.setVisible(False)

        # -- Update statistics card --
        self._clear_stats()
        self._stats_lay.addLayout(_stat_label("매칭 레코드", f"{matched:,}"))
        self._stats_lay.addLayout(_stat_label("최대 차이", f"{max_diff:,.4f} m"))
        self._stats_lay.addLayout(_stat_label("평균 차이", f"{mean_diff:,.4f} m"))
        self._stats_lay.addLayout(_stat_label("RMS", f"{rms:,.4f} m"))
        self._stats_lay.addLayout(
            _stat_label(f"허용범위 이내 (+/-{tolerance}m)", f"{pct_within:,.1f}%")
        )
        self._stats_card.setVisible(True)

        # -- Parse datetimes --
        fmt = "%Y/%m/%d %H:%M:%S"
        times = []
        vals_a = []
        vals_b = []
        vals_diff = []
        for key in common_keys:
            try:
                dt = datetime.strptime(key, fmt)
            except ValueError:
                continue
            times.append(dt)
            vals_a.append(dict_a[key] * 100.0)   # m -> cm
            vals_b.append(dict_b[key] * 100.0)
            vals_diff.append((dict_a[key] - dict_b[key]) * 100.0)

        # -- Overlay chart --
        self._overlay_chart.clear()
        self._overlay_chart.set_data(times, vals_a, label="File A")
        self._overlay_chart.add_reference(times, vals_b, label="File B")
        self._overlay_card.setVisible(True)

        # -- Difference chart --
        self._diff_chart.clear()
        self._diff_chart.set_data(times, vals_diff, label="A - B (cm)")
        self._diff_card.setVisible(True)

        self._controller.toast_requested.emit(
            f"비교 완료: {matched:,}개 레코드 매칭", "success"
        )

    def _clear_stats(self):
        """Remove all stat rows from the stats card layout (keep the header)."""
        while self._stats_lay.count() > 1:
            item = self._stats_lay.takeAt(self._stats_lay.count() - 1)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
