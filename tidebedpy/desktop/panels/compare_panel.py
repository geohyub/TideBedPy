"""ComparePanel -- Compare two TID files side by side."""

import os
import sys
import math
import html
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


class _CollapsibleGroup(QWidget):
    """Lightweight collapsible section for grouping cards."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._collapsed = False
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, Space.SM, 0, Space.SM)
        bar = QFrame()
        bar.setFixedSize(4, 14)
        bar.setStyleSheet(f"background: {ACCENT}; border: none; border-radius: 2px;")
        hdr.addWidget(bar)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"color: {Dark.TEXT_BRIGHT}; font-size: {Font.SM}px; "
            f"font-weight: {Font.SEMIBOLD}; background: transparent; border: none;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._toggle = QPushButton("접기")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Dark.MUTED}; "
            f"font-size: {Font.XS}px; border: none; padding: 2px 8px; }} "
            f"QPushButton:hover {{ color: {Dark.TEXT}; }}"
        )
        self._toggle.clicked.connect(self._on_toggle)
        hdr.addWidget(self._toggle)
        main.addLayout(hdr)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(Space.SM)
        main.addWidget(self._body)

    @property
    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_card(self, widget: QWidget):
        self._body_layout.addWidget(widget)

    def _on_toggle(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._toggle.setText("펼치기" if self._collapsed else "접기")


class ComparePanel(QWidget):
    """Panel for comparing two TID files side by side."""

    panel_title = "결과 비교"

    def __init__(self, controller, tr=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._t = tr or (lambda key, default=None, **kwargs: default or key)
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
        input_card, input_lay = _card(self._t("compare_input", "파일 선택"))

        self._path_a = PathRow(self._t("select_file_a", "파일 A (.tid)"), mode="file",
                               file_filter="TID Files (*.tid);;All (*)", tr=self._t)
        input_lay.addWidget(self._path_a)

        hint_a = QLabel("  비교 대상 A: 보정 결과 TID 파일")
        hint_a.setStyleSheet(f"color: {Dark.DIM}; font-size: {Font.XS}px; background: transparent; border: none;")
        input_lay.addWidget(hint_a)

        self._path_b = PathRow(self._t("select_file_b", "파일 B (.tid)"), mode="file",
                               file_filter="TID Files (*.tid);;All (*)", tr=self._t)
        input_lay.addWidget(self._path_b)

        hint_b = QLabel("  비교 대상 B: 참조 TID 파일 또는 다른 보정 결과")
        hint_b.setStyleSheet(f"color: {Dark.DIM}; font-size: {Font.XS}px; background: transparent; border: none;")
        input_lay.addWidget(hint_b)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._compare_btn = QPushButton(self._t("compare_files", "비교"))
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

        empty_text = QLabel(self._t("compare_empty", "두 개의 TID 파일을 선택하고 '비교'를 누르세요"))
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

        # -- Section 1: Statistics --
        self._stats_group = _CollapsibleGroup(self._t("comparison_stats", "통계"))
        self._stats_group.setVisible(False)

        self._context_card, self._context_lay = _card(self._t("comparison_context", "실행 맥락"))
        self._context_card.setVisible(False)
        self._stats_group.add_card(self._context_card)

        self._stats_card, self._stats_lay = _card(self._t("comparison_stats", "통계"))
        self._stats_card.setVisible(False)
        self._stats_group.add_card(self._stats_card)

        self._layout.addWidget(self._stats_group)

        # -- Section 2: Charts --
        self._charts_group = _CollapsibleGroup(self._t("comparison_charts", "차트"))
        self._charts_group.setVisible(False)

        self._overlay_card, overlay_lay = _card("보정값 비교")
        self._overlay_chart = TideChart()
        overlay_lay.addWidget(self._overlay_chart)
        self._overlay_card.setVisible(False)
        self._charts_group.add_card(self._overlay_card)

        self._diff_card, diff_lay = _card("차이 시계열")
        self._diff_chart = TideChart()
        diff_lay.addWidget(self._diff_chart)
        self._diff_card.setVisible(False)
        self._charts_group.add_card(self._diff_card)

        self._layout.addWidget(self._charts_group)

        # -- Section 3: Analysis --
        self._analysis_group = _CollapsibleGroup(self._t("comparison_analysis", "분석"))
        self._analysis_group.setVisible(False)

        self._mismatch_card, mismatch_lay = _card("주요 차이 시점")
        self._mismatch_body = QLabel()
        self._mismatch_body.setWordWrap(True)
        self._mismatch_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._mismatch_body.setStyleSheet(f"""
            QLabel {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 10px 12px;
            }}
        """)
        mismatch_lay.addWidget(self._mismatch_body)
        self._mismatch_card.setVisible(False)
        self._analysis_group.add_card(self._mismatch_card)

        self._contributors_card, contributors_lay = _card("기준항 커버리지")
        self._contributors_body = QLabel()
        self._contributors_body.setWordWrap(True)
        self._contributors_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._contributors_body.setStyleSheet(f"""
            QLabel {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 10px 12px;
            }}
        """)
        contributors_lay.addWidget(self._contributors_body)
        self._contributors_card.setVisible(False)
        self._analysis_group.add_card(self._contributors_card)

        self._layout.addWidget(self._analysis_group)

        self._layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Compare logic
    # ------------------------------------------------------------------

    def _run_compare(self):
        path_a = self._path_a.path()
        path_b = self._path_b.path()
        self._reset_result_view()

        if not path_a or not os.path.isfile(path_a):
            self._controller.toast_requested.emit("파일 A 경로를 확인하세요", "warning")
            return
        if not path_b or not os.path.isfile(path_b):
            self._controller.toast_requested.emit("파일 B 경로를 확인하세요", "warning")
            return

        try:
            from tidebedpy.output.report import parse_tid_data_cm
            from tidebedpy.output.summary import load_summary_file
        except ImportError:
            try:
                from output.report import parse_tid_data_cm
                from output.summary import load_summary_file
            except ImportError:
                self._controller.toast_requested.emit(
                    "TID 비교 모듈을 불러오지 못했습니다.", "error"
                )
                return

        data_a = parse_tid_data_cm(path_a)
        data_b = parse_tid_data_cm(path_b)
        summary_a = load_summary_file(path_a)
        summary_b = load_summary_file(path_b)

        if not data_a:
            self._controller.toast_requested.emit("파일 A 데이터 없음", "warning")
            return
        if not data_b:
            self._controller.toast_requested.emit("파일 B 데이터 없음", "warning")
            return

        # Build time-keyed dicts
        dict_a = {t: v for t, v in data_a}
        dict_b = {t: v for t, v in data_b}

        # Match on common timestamps
        common_keys = sorted(set(dict_a.keys()) & set(dict_b.keys()))
        matched = len(common_keys)
        total_a = len(dict_a)
        total_b = len(dict_b)
        union_count = len(set(dict_a.keys()) | set(dict_b.keys()))
        a_only = max(total_a - matched, 0)
        b_only = max(total_b - matched, 0)
        overlap_pct = (matched / union_count * 100.0) if union_count else 0.0

        if matched == 0:
            self._controller.toast_requested.emit(
                "공통 시간 데이터가 없습니다", "warning"
            )
            return

        tolerance = self._resolve_compare_tolerance(summary_a, summary_b)
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

        # Hide empty state, show result groups
        self._empty_state.setVisible(False)
        self._stats_group.setVisible(True)
        self._charts_group.setVisible(True)
        self._analysis_group.setVisible(True)
        self._populate_context_card(path_a, path_b, summary_a, summary_b)
        self._populate_contributor_card(summary_a, summary_b)

        # -- Update statistics card --
        self._clear_stats()
        self._stats_lay.addLayout(_stat_label("파일 A 레코드", f"{total_a:,}"))
        self._stats_lay.addLayout(_stat_label("파일 B 레코드", f"{total_b:,}"))
        self._stats_lay.addLayout(_stat_label("공통 시점", f"{matched:,}"))
        self._stats_lay.addLayout(_stat_label("겹침 비율", f"{overlap_pct:,.1f}%"))
        self._stats_lay.addLayout(_stat_label("A 전용 시점", f"{a_only:,}"))
        self._stats_lay.addLayout(_stat_label("B 전용 시점", f"{b_only:,}"))
        self._stats_lay.addLayout(_stat_label("최대 차이", f"{max_diff:,.2f} cm"))
        self._stats_lay.addLayout(_stat_label("평균 차이", f"{mean_diff:,.2f} cm"))
        self._stats_lay.addLayout(_stat_label("RMS", f"{rms:,.2f} cm"))
        self._stats_lay.addLayout(
            _stat_label(f"허용 오차 이내 (+/-{tolerance:.2f} cm)", f"{pct_within:,.1f}%")
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
            vals_a.append(dict_a[key])
            vals_b.append(dict_b[key])
            vals_diff.append(dict_a[key] - dict_b[key])

        # -- Overlay chart --
        self._overlay_chart.clear()
        self._overlay_chart.set_data(times, vals_a, label=f"A: {os.path.basename(path_a)}")
        self._overlay_chart.add_reference(times, vals_b, label=f"B: {os.path.basename(path_b)}")
        self._overlay_card.setVisible(True)

        # -- Difference chart --
        self._diff_chart.clear()
        self._diff_chart.set_data(times, vals_diff, label="A - B (cm)")
        self._diff_card.setVisible(True)
        self._populate_mismatch_card(common_keys, dict_a, dict_b, tolerance)

        self._controller.toast_requested.emit(
            f"비교 완료: {matched:,}개 레코드 매칭", "success"
        )

    def _populate_context_card(self, path_a: str, path_b: str,
                               summary_a: dict | None, summary_b: dict | None):
        """Show scenario context so value differences are easier to interpret."""
        self._clear_context()

        body = QLabel()
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"""
            QLabel {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 10px 12px;
            }}
        """)

        sections = [
            self._context_html("시나리오 A", path_a, summary_a),
            self._context_html("시나리오 B", path_b, summary_b),
        ]

        diff_lines = []
        if summary_a and summary_b:
            pairs = [
                ("tide_model", "모델"),
                ("timezone_offset_hours", "시간대"),
                ("rank_limit", "선정 기준항 수"),
                ("time_interval_sec", "간격"),
                ("tolerance_cm", "허용 오차"),
            ]
            settings_a = summary_a.get("settings", {})
            settings_b = summary_b.get("settings", {})
            for key, label in pairs:
                value_a = settings_a.get(key)
                value_b = settings_b.get(key)
                if value_a != value_b:
                    diff_lines.append(f"{label}: {value_a} vs {value_b}")

            input_a = summary_a.get("inputs", {})
            input_b = summary_b.get("inputs", {})
            for key, label in (("nav_name", "항적"), ("tide_name", "조위"), ("station_name", "기준항 파일")):
                value_a = input_a.get(key)
                value_b = input_b.get(key)
                if value_a and value_b and value_a != value_b:
                    diff_lines.append(f"{label}: {value_a} vs {value_b}")

            preset_summary_a = settings_a.get("preset_summary")
            preset_summary_b = settings_b.get("preset_summary")
            if preset_summary_a and preset_summary_b and preset_summary_a != preset_summary_b:
                diff_lines.append("프리셋 의미가 두 시나리오에서 다릅니다.")

            contributors_a = summary_a.get("contributors", [])[:2]
            contributors_b = summary_b.get("contributors", [])[:2]
            if contributors_a and contributors_b:
                lead_a = ", ".join(item["station_name"] for item in contributors_a)
                lead_b = ", ".join(item["station_name"] for item in contributors_b)
                if lead_a != lead_b:
                    diff_lines.append(f"주요 기준항: {lead_a} vs {lead_b}")

        if diff_lines:
            sections.append(
                "<b>차이의 주요 원인</b><br>" +
                "<br>".join(html.escape(line) for line in diff_lines)
            )
        elif summary_a or summary_b:
            sections.append(
                "두 파일의 요약 sidecar 기준 실행 맥락은 대체로 비슷합니다. "
                "그래도 값 차이가 크다면 조위 소스 커버리지, local 데이터 품질, 정확한 매칭 시점을 먼저 확인하세요."
            )
        else:
            sections.append(
                ".summary.json sidecar가 없어 값 자체의 차이만 비교할 수 있습니다."
            )

        body.setText("<br><br>".join(sections))
        self._context_lay.addWidget(body)
        self._context_card.setVisible(True)

    def _context_html(self, title: str, path: str, summary: dict | None) -> str:
        """Render one side of the compare context."""
        if not summary:
            return (
                f"<b>{html.escape(title)}</b><br>"
                f"파일: {html.escape(os.path.basename(path))}<br>"
                ".summary.json sidecar를 찾지 못했습니다."
            )

        settings = summary.get("settings", {})
        counts = summary.get("counts", {})
        inputs = summary.get("inputs", {})
        story = summary.get("story", {})
        contributors = summary.get("contributors", [])[:2]
        workflow = story.get("workflow", [])

        lines = [
            f"<b>{html.escape(title)}</b>",
            f"파일: {html.escape(os.path.basename(path))}",
            f"모델: {html.escape(str(settings.get('tide_model', '')))}",
            f"시간대: {html.escape(str(settings.get('timezone_offset_hours', '')))} h",
            f"선정 기준항 수: {html.escape(str(settings.get('rank_limit', '')))}",
            f"처리 포인트: {counts.get('processed_nav_points', 0):,}",
            f"유효 포인트: {counts.get('valid_points', 0):,}",
        ]

        if inputs.get("nav_name"):
            lines.append(f"항적: {html.escape(str(inputs.get('nav_name')))}")
        if inputs.get("tide_name"):
            lines.append(f"조위: {html.escape(str(inputs.get('tide_name')))}")
        if settings.get("preset_name"):
            lines.append(f"프리셋: {html.escape(str(settings.get('preset_name')))}")
        if settings.get("preset_summary"):
            lines.append(f"프리셋 의미: {html.escape(str(settings.get('preset_summary')))}")
        if contributors:
            contributor_text = ", ".join(
                f"{item['station_name']} ({item['coverage_pct']:.1f}%)"
                for item in contributors
            )
            lines.append(f"주요 기준항: {html.escape(contributor_text)}")
        if workflow:
            lines.append(html.escape(workflow[0]))

        return "<br>".join(lines)

    def _populate_mismatch_card(
        self,
        common_keys: list[str],
        dict_a: dict[str, float],
        dict_b: dict[str, float],
        tolerance_cm: float,
    ) -> None:
        """Show the most important timestamp-level mismatches."""
        ranked = []
        for key in common_keys:
            diff_cm = dict_a[key] - dict_b[key]
            ranked.append((abs(diff_cm), key, dict_a[key], dict_b[key], diff_cm))

        ranked.sort(reverse=True)
        top_items = ranked[:5]

        if not top_items:
            self._mismatch_body.setText("공통 시점 차이를 계산할 수 없습니다.")
            self._mismatch_card.setVisible(True)
            return

        lines = [
            (
                f"<b>먼저 이 시점들을 확인하세요.</b><br>"
                f"허용 오차: +/-{tolerance_cm:.2f} cm<br>"
                f"절대 차이가 큰 순서대로 정렬했습니다."
            )
        ]
        for _abs_diff, key, value_a, value_b, diff_cm in top_items:
            lines.append(
                f"<b>{html.escape(key)}</b><br>"
                f"A: {value_a:+.2f} cm | "
                f"B: {value_b:+.2f} cm | "
                f"A-B: {diff_cm:+.2f} cm"
            )

        self._mismatch_body.setText("<br><br>".join(lines))
        self._mismatch_card.setVisible(True)

    def _build_contributor_rows(
        self,
        summary_a: dict | None,
        summary_b: dict | None,
        *,
        limit: int = 5,
    ) -> list[tuple[str, float, float]]:
        """Build a side-by-side contributor table from two summaries."""
        contributors_a = (summary_a or {}).get("contributors", [])
        contributors_b = (summary_b or {}).get("contributors", [])
        if not contributors_a and not contributors_b:
            return []

        ordered_names: list[str] = []
        coverage_a: dict[str, float] = {}
        coverage_b: dict[str, float] = {}

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

    def _populate_contributor_card(self, summary_a: dict | None, summary_b: dict | None) -> None:
        """Show station contribution coverage side by side."""
        rows = self._build_contributor_rows(summary_a, summary_b)
        if not rows:
            self._contributors_card.setVisible(False)
            self._contributors_body.clear()
            return

        lines = [
            "<b>시나리오별 기준항 기여 커버리지</b><br>"
            "퍼센트가 높을수록 해당 기준항이 더 많은 보정 시점에 영향을 준 것입니다."
        ]
        for name, cov_a, cov_b in rows:
            direction = "유사"
            if abs(cov_a - cov_b) > 1e-9:
                direction = "A 비중 큼" if cov_a > cov_b else "B 비중 큼"
            lines.append(
                f"<b>{html.escape(name)}</b><br>"
                f"A: {cov_a:.1f}% | B: {cov_b:.1f}% | {direction}"
            )

        self._contributors_body.setText("<br><br>".join(lines))
        self._contributors_card.setVisible(True)

    def _clear_context(self):
        while self._context_lay.count() > 1:
            item = self._context_lay.takeAt(self._context_lay.count() - 1)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _resolve_compare_tolerance(self, summary_a: dict | None, summary_b: dict | None) -> float:
        """Choose a compare tolerance in centimeters from available run summaries."""
        tolerance_values = []
        for summary in (summary_a, summary_b):
            if not summary:
                continue
            value = summary.get("settings", {}).get("tolerance_cm")
            try:
                if value is not None:
                    tolerance_values.append(float(value))
            except (TypeError, ValueError):
                continue

        if len(tolerance_values) == 2 and abs(tolerance_values[0] - tolerance_values[1]) < 1e-9:
            return tolerance_values[0]
        if len(tolerance_values) == 1:
            return tolerance_values[0]
        return 1.0

    def _reset_result_view(self) -> None:
        """Hide stale comparison results before a new run."""
        self._empty_state.setVisible(True)
        self._stats_group.setVisible(False)
        self._charts_group.setVisible(False)
        self._analysis_group.setVisible(False)
        self._context_card.setVisible(False)
        self._stats_card.setVisible(False)
        self._overlay_card.setVisible(False)
        self._diff_card.setVisible(False)
        self._mismatch_card.setVisible(False)
        self._contributors_card.setVisible(False)
        self._mismatch_body.clear()
        self._contributors_body.clear()
        self._overlay_chart.clear()
        self._diff_chart.clear()
        self._clear_context()
        self._clear_stats()

    def _clear_stats(self):
        """Remove all stat rows from the stats card layout (keep the header)."""
        while self._stats_lay.count() > 1:
            item = self._stats_lay.takeAt(self._stats_lay.count() - 1)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
