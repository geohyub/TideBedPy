"""CorrectionPanel — Main tidal correction workflow panel."""

import json
import os
import sys
import subprocess
import time

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QLineEdit, QPushButton, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QSpinBox, QDoubleSpinBox, QListWidget, QAbstractItemView,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius

from tidebedpy.desktop.widgets.path_row import PathRow
from tidebedpy.desktop.widgets.log_viewer import LogViewer
from tidebedpy.desktop.widgets.progress_bar import TideProgressBar
from tidebedpy.desktop.services.correction_worker import CorrectionWorker

try:
    from tidebedpy.desktop.widgets.tide_chart import TideChart
    from tidebedpy.desktop.widgets.weight_chart import WeightChart
    HAS_CHARTS = True
except ImportError:
    HAS_CHARTS = False

# PREPROCESSING accent
ACCENT = "#F59E0B"

# Timezone options
TIMEZONE_OPTIONS = [
    ("GMT (UTC+0)", 0.0),
    ("KST (UTC+9)", 9.0),
    ("JST (UTC+9)", 9.0),
    ("CST (UTC+8)", 8.0),
    ("UTC+1", 1.0), ("UTC+2", 2.0), ("UTC+3", 3.0), ("UTC+4", 4.0),
    ("UTC+5", 5.0), ("UTC+6", 6.0), ("UTC+7", 7.0), ("UTC+8", 8.0),
    ("UTC+9", 9.0), ("UTC+10", 10.0), ("UTC+11", 11.0), ("UTC+12", 12.0),
    ("UTC-1", -1.0), ("UTC-2", -2.0), ("UTC-3", -3.0), ("UTC-4", -4.0),
    ("UTC-5", -5.0), ("UTC-6", -6.0), ("UTC-7", -7.0), ("UTC-8", -8.0),
    ("UTC-9", -9.0), ("UTC-10", -10.0), ("UTC-11", -11.0), ("UTC-12", -12.0),
]


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Create a dark-theme card frame with optional title."""
    card = QFrame()
    card.setObjectName("corrCard")
    card.setStyleSheet(f"""
        QFrame#corrCard {{
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


def _sep() -> QFrame:
    """Thin horizontal separator."""
    s = QFrame()
    s.setFixedHeight(1)
    s.setStyleSheet(f"background: {Dark.BORDER}; border: none;")
    return s


class CollapsibleSection(QWidget):
    """Collapsible card with toggle button."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._collapsed = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        bar = QFrame()
        bar.setFixedSize(4, 16)
        bar.setStyleSheet(f"background: {ACCENT}; border: none; border-radius: 2px;")
        header.addWidget(bar)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"""
            color: {Dark.TEXT_BRIGHT};
            font-size: {Font.SM}px;
            font-weight: {Font.SEMIBOLD};
            background: transparent;
        """)
        header.addWidget(lbl)

        # Auto status badge
        self._auto_badge = QLabel("자동 탐색됨")
        self._auto_badge.setStyleSheet(f"""
            background: {Dark.GREEN}1A;
            color: {Dark.GREEN};
            font-size: 10px;
            font-weight: {Font.MEDIUM};
            border-radius: 4px;
            padding: 2px 8px;
            border: none;
        """)
        self._auto_badge.setVisible(False)
        header.addWidget(self._auto_badge)

        header.addStretch()

        self._toggle_btn = QPushButton("펼치기")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Dark.MUTED};
                font-size: {Font.XS}px;
                border: none;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ color: {Dark.TEXT}; }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self._toggle_btn)

        main_layout.addLayout(header)

        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, Space.SM, 0, 0)
        self._content_layout.setSpacing(Space.SM)
        main_layout.addWidget(self._content)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._content.setVisible(not collapsed)
        self._toggle_btn.setText("펼치기" if collapsed else "접기")

    def set_auto_discovered(self, discovered: bool):
        self._auto_badge.setVisible(discovered)
        if discovered:
            self.set_collapsed(True)

    def _toggle(self):
        self.set_collapsed(not self._collapsed)


class CorrectionPanel(QWidget):
    """Main tidal correction workflow panel."""

    panel_title = "조석보정"

    # Config file for recent paths
    _CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".tidebedpy")
    _CONFIG_FILE = os.path.join(_CONFIG_DIR, "recent.json")

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._worker = None
        self._thread = None
        self._is_running = False

        self._history_entries = []
        self._build_ui()
        self._auto_discover_paths()
        self._load_saved_api_key()
        self._load_recent_paths()
        self._load_history()

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
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(Space.BASE)

        self._build_drop_zone()
        self._build_input_card()
        self._build_db_card()
        self._build_options_card()
        self._build_control_section()
        self._build_log_card()
        self._build_result_preview()

        self._content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ────────────────────────────────────────────
    #  Drop Zone (A3: Drag-and-Drop Quick Start)
    # ────────────────────────────────────────────
    def _build_drop_zone(self):
        self._drop_zone = QFrame()
        self._drop_zone.setFixedHeight(46)
        self._drop_zone.setAcceptDrops(True)
        self._drop_zone_default_ss = f"""
            QFrame {{
                background: {Dark.NAVY};
                border: 2px dashed {Dark.BORDER};
                border-radius: {Radius.SM}px;
            }}
        """
        self._drop_zone_hover_ss = f"""
            QFrame {{
                background: {Dark.NAVY};
                border: 2px dashed {ACCENT};
                border-radius: {Radius.SM}px;
            }}
        """
        self._drop_zone_ready_ss = f"""
            QFrame {{
                background: {Dark.NAVY};
                border: 2px solid {Dark.GREEN};
                border-radius: {Radius.SM}px;
            }}
        """
        self._drop_zone.setStyleSheet(self._drop_zone_default_ss)

        dz_layout = QHBoxLayout(self._drop_zone)
        dz_layout.setContentsMargins(Space.BASE, 0, Space.BASE, 0)
        dz_layout.setSpacing(Space.SM)

        self._drop_label = QLabel("Nav 폴더를 여기에 드래그하세요")
        self._drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_label.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.SM}px;
            background: transparent;
            border: none;
        """)
        dz_layout.addWidget(self._drop_label, 1)

        self._drop_status = QLabel("")
        self._drop_status.setStyleSheet(f"""
            color: {Dark.GREEN};
            font-size: {Font.XS}px;
            font-weight: {Font.MEDIUM};
            background: transparent;
            border: none;
        """)
        self._drop_status.setVisible(False)
        dz_layout.addWidget(self._drop_status)

        # Install drag-drop event filter on the drop zone frame
        self._drop_zone.dragEnterEvent = self._dz_drag_enter
        self._drop_zone.dragLeaveEvent = self._dz_drag_leave
        self._drop_zone.dropEvent = self._dz_drop

        self._content_layout.addWidget(self._drop_zone)

    def _dz_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_zone.setStyleSheet(self._drop_zone_hover_ss)
        else:
            event.ignore()

    def _dz_drag_leave(self, event):
        self._drop_zone.setStyleSheet(self._drop_zone_default_ss)

    def _dz_drop(self, event):
        urls = event.mimeData().urls()
        if not urls:
            self._drop_zone.setStyleSheet(self._drop_zone_default_ss)
            return
        path = urls[0].toLocalFile()
        if os.path.isdir(path):
            event.acceptProposedAction()
            if self._batch_mode.isChecked():
                # In batch mode, add to batch list
                self._batch_list.addItem(path)
            else:
                self._nav_row.set_text(path)
                self._on_nav_changed(path)
            self._update_drop_zone_status()
        else:
            self._drop_zone.setStyleSheet(self._drop_zone_default_ss)

    def _update_drop_zone_status(self):
        """Check if all required fields are filled and show ready status."""
        has_nav = bool(self._nav_row.text() and os.path.isdir(self._nav_row.text()))
        if self._batch_mode.isChecked():
            has_nav = self._batch_list.count() > 0
        has_tide = self._api_check.isChecked() or bool(
            self._tide_row.text() and os.path.isdir(self._tide_row.text())
        )
        has_db = bool(self._db_row.text())
        has_station = bool(self._station_row.text())
        has_output = bool(self._output_row.text())

        if has_nav and has_tide and has_db and has_station and has_output:
            self._drop_zone.setStyleSheet(self._drop_zone_ready_ss)
            self._drop_status.setText("-- 바로 실행 가능 --")
            self._drop_status.setVisible(True)
        else:
            self._drop_zone.setStyleSheet(self._drop_zone_default_ss)
            self._drop_status.setVisible(False)

    # ────────────────────────────────────────────
    #  Input Card
    # ────────────────────────────────────────────
    def _build_input_card(self):
        card, layout = _card("입력 파일 설정")

        # Batch mode toggle (A2)
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        self._batch_mode = QCheckBox("Batch 모드 (다중 폴더 처리)")
        self._batch_mode.setStyleSheet(f"""
            QCheckBox {{
                color: {Dark.MUTED};
                font-size: {Font.XS}px;
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {Dark.BORDER_H};
                border-radius: 3px;
                background: {Dark.BG_ALT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
            }}
        """)
        self._batch_mode.toggled.connect(self._toggle_batch_mode)
        batch_row.addWidget(self._batch_mode)
        batch_row.addStretch()
        layout.addLayout(batch_row)

        # Single nav row (default)
        self._nav_row = PathRow("항적 폴더", "Nav 데이터 폴더 (Before/After 모두 지원)", mode="folder")
        self._nav_row.path_changed.connect(self._on_nav_changed)
        layout.addWidget(self._nav_row)

        # Batch list widget (hidden by default)
        self._batch_widget = QWidget()
        batch_inner = QVBoxLayout(self._batch_widget)
        batch_inner.setContentsMargins(0, 0, 0, 0)
        batch_inner.setSpacing(Space.SM)

        batch_hint = QLabel("처리할 Nav 폴더 목록")
        batch_hint.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.XS}px;
            background: transparent;
        """)
        batch_inner.addWidget(batch_hint)

        self._batch_list = QListWidget()
        self._batch_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._batch_list.setMinimumHeight(90)
        self._batch_list.setMaximumHeight(150)
        self._batch_list.setStyleSheet(f"""
            QListWidget {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 3px 6px;
                border-radius: 2px;
            }}
            QListWidget::item:selected {{
                background: {ACCENT}33;
                color: {Dark.TEXT_BRIGHT};
            }}
        """)
        batch_inner.addWidget(self._batch_list)

        batch_btn_row = QHBoxLayout()
        batch_btn_row.setSpacing(Space.SM)

        self._batch_add_btn = QPushButton("폴더 추가")
        self._batch_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._batch_add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.XS}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{ background: {Dark.SURFACE}; }}
        """)
        self._batch_add_btn.clicked.connect(self._batch_add_folder)
        batch_btn_row.addWidget(self._batch_add_btn)

        self._batch_remove_btn = QPushButton("선택 삭제")
        self._batch_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._batch_remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.XS}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{ background: {Dark.SURFACE}; border-color: {Dark.RED}; }}
        """)
        self._batch_remove_btn.clicked.connect(self._batch_remove_selected)
        batch_btn_row.addWidget(self._batch_remove_btn)
        batch_btn_row.addStretch()
        batch_inner.addLayout(batch_btn_row)

        self._batch_widget.setVisible(False)
        layout.addWidget(self._batch_widget)

        layout.addWidget(_sep())

        self._tide_row = PathRow("조위 폴더", "실측/예측 조위 파일 폴더 (TOPS/CSV 등)", mode="folder")
        self._tide_row.path_changed.connect(self._on_tide_changed)
        layout.addWidget(self._tide_row)

        # API checkbox
        api_row = QHBoxLayout()
        api_row.setContentsMargins(0, 0, 0, 0)
        self._api_check = QCheckBox("API 자동수집 (항적 좌표 기반 자동 다운로드)")
        self._api_check.setStyleSheet(f"""
            QCheckBox {{
                color: {Dark.MUTED};
                font-size: {Font.XS}px;
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox:disabled {{
                color: {Dark.DIM};
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {Dark.BORDER_H};
                border-radius: 3px;
                background: {Dark.BG_ALT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
            }}
            QCheckBox::indicator:disabled {{
                background: {Dark.NAVY};
                border-color: {Dark.BORDER};
            }}
        """)
        self._api_check.toggled.connect(self._toggle_api)
        api_row.addWidget(self._api_check)
        api_row.addStretch()
        layout.addLayout(api_row)

        # API key row (hidden initially)
        self._api_widget = QWidget()
        api_inner = QHBoxLayout(self._api_widget)
        api_inner.setContentsMargins(110 + Space.SM, 0, 0, 0)
        api_inner.setSpacing(Space.SM)
        api_lbl = QLabel("API 키")
        api_lbl.setStyleSheet(f"color: {Dark.TEXT}; font-size: {Font.SM}px; background: transparent;")
        api_inner.addWidget(api_lbl)
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("공공데이터포털 서비스키")
        self._api_key_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{ border-color: {Dark.ORANGE}; }}
        """)
        api_inner.addWidget(self._api_key_edit, 1)
        self._api_widget.setVisible(False)
        layout.addWidget(self._api_widget)

        layout.addWidget(_sep())

        self._output_row = PathRow(
            "출력 TID", "조석보정 결과 (.tid) 저장 경로",
            mode="save", file_filter="TID (*.tid);;All (*.*)",
        )
        layout.addWidget(self._output_row)

        self._content_layout.addWidget(card)

    # ────────────────────────────────────────────
    #  DB Card (Collapsible)
    # ────────────────────────────────────────────
    def _build_db_card(self):
        card = QFrame()
        card.setObjectName("corrCard")
        card.setStyleSheet(f"""
            QFrame#corrCard {{
                background: {Dark.NAVY};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(Space.BASE, Space.MD, Space.BASE, Space.MD)
        card_layout.setSpacing(Space.SM)

        self._db_section = CollapsibleSection("개정수 DB 설정")

        self._db_row = PathRow("개정수 DB", "File_Catalog.txt + CT/ 폴더가 있는 디렉토리", mode="folder")
        self._db_section.content_layout.addWidget(self._db_row)

        self._station_row = PathRow(
            "기준항 정보", "기준항정보.txt 파일",
            mode="file", file_filter="텍스트 (*.txt);;All (*.*)",
        )
        self._station_row.path_changed.connect(self._on_station_changed)
        self._db_section.content_layout.addWidget(self._station_row)

        card_layout.addWidget(self._db_section)
        self._content_layout.addWidget(card)

    # ────────────────────────────────────────────
    #  Options Card
    # ────────────────────────────────────────────
    def _build_options_card(self):
        card, layout = _card("보정 옵션")

        # Row 0: Tide model, output format
        row0 = QHBoxLayout()
        row0.setSpacing(Space.LG)

        row0.addLayout(self._option_group("조석 모델", self._make_tide_model_combo()))
        row0.addLayout(self._option_group("출력 포맷", self._make_output_format_combo()))
        row0.addStretch()

        layout.addLayout(row0)

        # Model directory row (hidden by default, shown for global models)
        self._model_dir_row = PathRow(
            "모델 경로", "pyTMD 모델 데이터 디렉토리 (FES2014/TPXO9)",
            mode="folder",
        )
        self._model_dir_row.setVisible(False)
        layout.addWidget(self._model_dir_row)

        # Row 1: Tide type, rank limit, timezone
        row1 = QHBoxLayout()
        row1.setSpacing(Space.LG)

        row1.addLayout(self._option_group("조위 유형", self._make_tide_type_combo()))
        row1.addLayout(self._option_group("기준항 수", self._make_rank_spin()))
        row1.addLayout(self._option_group("시간대", self._make_tz_combo()))
        row1.addStretch()

        layout.addLayout(row1)

        # Row 2: Time interval, checkboxes, tolerance
        row2 = QHBoxLayout()
        row2.setSpacing(Space.LG)

        row2.addLayout(self._option_group("시간 간격", self._make_interval_spin()))

        self._detail_check = self._styled_check("상세출력", True)
        row2.addWidget(self._detail_check)

        self._graph_check = self._styled_check("그래프", True)
        row2.addWidget(self._graph_check)

        row2.addLayout(self._option_group("허용 편차", self._make_tolerance_spin()))

        row2.addStretch()
        layout.addLayout(row2)

        # Row 3: Validation
        row3 = QHBoxLayout()
        row3.setSpacing(Space.MD)

        self._validate_check = self._styled_check("검증:", False)
        self._validate_check.toggled.connect(self._toggle_validate)
        row3.addWidget(self._validate_check)

        self._validate_edit = QLineEdit()
        self._validate_edit.setEnabled(False)
        self._validate_edit.setPlaceholderText("참조 TID 파일 경로")
        self._validate_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 5px 8px;
            }}
            QLineEdit:focus {{ border-color: {Dark.ORANGE}; }}
            QLineEdit:disabled {{ color: {Dark.DIM}; }}
        """)
        row3.addWidget(self._validate_edit, 1)

        self._validate_btn = QPushButton("탐색")
        self._validate_btn.setEnabled(False)
        self._validate_btn.setFixedWidth(54)
        self._validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.XS}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 5px 0;
            }}
            QPushButton:hover {{ background: {Dark.SURFACE}; }}
            QPushButton:disabled {{ color: {Dark.DIM}; }}
        """)
        self._validate_btn.clicked.connect(self._browse_validate)
        row3.addWidget(self._validate_btn)

        layout.addLayout(row3)

        self._content_layout.addWidget(card)

    # ────────────────────────────────────────────
    #  Control Section (buttons + progress)
    # ────────────────────────────────────────────
    def _build_control_section(self):
        frame = QFrame()
        frame.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.SM)

        # Progress bar
        self._progress = TideProgressBar(accent=ACCENT)
        layout.addWidget(self._progress)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Space.SM)

        # Run button
        self._run_btn = QPushButton("  보정 수행  ")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: {Dark.BG};
                font-size: {Font.SM}px;
                font-weight: {Font.BOLD};
                border: none;
                border-radius: {Radius.SM}px;
                padding: 10px 28px;
            }}
            QPushButton:hover {{ background: #D97706; }}
            QPushButton:disabled {{ background: {Dark.SLATE}; color: {Dark.DIM}; }}
        """)
        self._run_btn.clicked.connect(self._run)
        btn_row.addWidget(self._run_btn)

        # Stop button
        self._stop_btn = QPushButton("  중지  ")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background: {Dark.SURFACE}; border-color: {Dark.RED}; }}
            QPushButton:disabled {{ color: {Dark.DIM}; }}
        """)
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._stop_btn)

        # Separator
        vsep = QFrame()
        vsep.setFixedSize(1, 28)
        vsep.setStyleSheet(f"background: {Dark.BORDER}; border: none;")
        btn_row.addWidget(vsep)

        # Utility buttons
        for label, callback in [
            ("INI 불러오기", self._load_ini),
            ("세팅 저장", self._save_preset),
            ("세팅 불러오기", self._load_preset),
            ("초기화", self._reset),
        ]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Dark.SLATE};
                    color: {Dark.TEXT};
                    font-size: {Font.XS}px;
                    border: 1px solid {Dark.BORDER};
                    border-radius: {Radius.SM}px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background: {Dark.SURFACE};
                    color: {Dark.TEXT_BRIGHT};
                }}
            """)
            btn.clicked.connect(callback)
            btn_row.addWidget(btn)

        # History combo (A4: Project History)
        self._history_combo = QComboBox()
        self._history_combo.setFixedWidth(180)
        self._history_combo.setPlaceholderText("최근 보정")
        self._style_combo(self._history_combo)
        self._history_combo.activated.connect(self._on_history_selected)
        btn_row.addWidget(self._history_combo)

        btn_row.addStretch()

        # Open output folder button (hidden initially)
        self._open_folder_btn = QPushButton("출력 폴더 열기")
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.setVisible(False)
        self._open_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.GREEN}1A;
                color: {Dark.GREEN};
                font-size: {Font.XS}px;
                font-weight: {Font.MEDIUM};
                border: 1px solid {Dark.GREEN}40;
                border-radius: {Radius.SM}px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{ background: {Dark.GREEN}33; }}
        """)
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._open_folder_btn)

        layout.addLayout(btn_row)

        self._content_layout.addWidget(frame)

    # ────────────────────────────────────────────
    #  Log Card
    # ────────────────────────────────────────────
    def _build_log_card(self):
        card, layout = _card("처리 로그")
        self._log_viewer = LogViewer()
        self._log_viewer.setMinimumHeight(200)
        layout.addWidget(self._log_viewer, 1)
        self._content_layout.addWidget(card, 1)

    # ────────────────────────────────────────────
    #  Result Preview Card (shown after correction)
    # ────────────────────────────────────────────
    def _build_result_preview(self):
        """Build result preview card — initially hidden, shown after correction."""
        self._preview_card = QFrame()
        self._preview_card.setObjectName("corrCard")
        self._preview_card.setStyleSheet(f"""
            QFrame#corrCard {{
                background: {Dark.NAVY};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.BASE}px;
            }}
        """)
        self._preview_card.setVisible(False)

        layout = QVBoxLayout(self._preview_card)
        layout.setContentsMargins(Space.BASE, Space.MD, Space.BASE, Space.MD)
        layout.setSpacing(Space.SM)

        # Header
        hdr = QHBoxLayout()
        bar = QFrame()
        bar.setFixedSize(4, 16)
        bar.setStyleSheet(f"background: {Dark.GREEN}; border: none; border-radius: 2px;")
        hdr.addWidget(bar)
        lbl = QLabel("결과 미리보기")
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

        # Interactive tide chart (PyQtGraph)
        self._tide_chart = None
        self._weight_chart = None
        if HAS_CHARTS:
            self._tide_chart = TideChart()
            self._tide_chart.setFixedHeight(250)
            layout.addWidget(self._tide_chart)

            self._weight_chart = WeightChart()
            self._weight_chart.setFixedHeight(200)
            layout.addWidget(self._weight_chart)

        # Static image fallback
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(200)
        self._preview_label.setStyleSheet(f"""
            background: {Dark.BG_ALT};
            border: 1px solid {Dark.BORDER};
            border-radius: {Radius.SM}px;
        """)
        self._preview_label.setVisible(False)
        layout.addWidget(self._preview_label)

        self._content_layout.addWidget(self._preview_card)

    # ════════════════════════════════════════════
    #  Widget Factories
    # ════════════════════════════════════════════

    def _option_group(self, label: str, widget: QWidget) -> QHBoxLayout:
        grp = QHBoxLayout()
        grp.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.XS}px;
            background: transparent;
        """)
        grp.addWidget(lbl)
        grp.addWidget(widget)
        return grp

    def _make_tide_type_combo(self) -> QComboBox:
        self._tide_type_combo = QComboBox()
        self._tide_type_combo.addItems(["실측", "예측"])
        self._tide_type_combo.setFixedWidth(80)
        self._style_combo(self._tide_type_combo)
        return self._tide_type_combo

    def _make_rank_spin(self) -> QSpinBox:
        self._rank_spin = QSpinBox()
        self._rank_spin.setRange(1, 10)
        self._rank_spin.setValue(10)
        self._rank_spin.setFixedWidth(60)
        self._style_spin(self._rank_spin)
        return self._rank_spin

    def _make_tz_combo(self) -> QComboBox:
        self._tz_combo = QComboBox()
        for label, _ in TIMEZONE_OPTIONS:
            self._tz_combo.addItem(label)
        self._tz_combo.setFixedWidth(130)
        self._style_combo(self._tz_combo)
        return self._tz_combo

    def _make_interval_spin(self) -> QSpinBox:
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(0, 9999)
        self._interval_spin.setValue(0)
        self._interval_spin.setSuffix(" 초")
        self._interval_spin.setFixedWidth(80)
        self._style_spin(self._interval_spin)
        return self._interval_spin

    def _make_tolerance_spin(self) -> QDoubleSpinBox:
        self._tolerance_spin = QDoubleSpinBox()
        self._tolerance_spin.setRange(0.1, 100.0)
        self._tolerance_spin.setValue(1.0)
        self._tolerance_spin.setSuffix(" cm")
        self._tolerance_spin.setDecimals(1)
        self._tolerance_spin.setFixedWidth(80)
        self._style_spin(self._tolerance_spin)
        return self._tolerance_spin

    def _make_tide_model_combo(self) -> QComboBox:
        self._tide_model_combo = QComboBox()
        self._tide_model_combo.addItems([
            "KHOA (국내)",
            "FES2014 (글로벌)",
            "TPXO9 (글로벌)",
        ])
        self._tide_model_combo.setFixedWidth(140)
        self._style_combo(self._tide_model_combo)
        self._tide_model_combo.currentIndexChanged.connect(self._on_tide_model_changed)
        return self._tide_model_combo

    def _make_output_format_combo(self) -> QComboBox:
        self._output_format_combo = QComboBox()
        self._output_format_combo.addItems([
            "TID (기본)",
            "TID + CSV",
            "TID + Kingdom",
            "TID + SonarWiz",
        ])
        self._output_format_combo.setFixedWidth(140)
        self._style_combo(self._output_format_combo)
        return self._output_format_combo

    def _on_tide_model_changed(self, index: int):
        """Toggle DB/station rows vs model directory row based on selected model."""
        is_global = index > 0  # FES2014 or TPXO9
        # Hide/show DB-related rows
        self._db_row.setVisible(not is_global)
        self._station_row.setVisible(not is_global)
        self._tide_row.set_enabled(not is_global and not self._api_check.isChecked())
        # Show model directory for global models
        self._model_dir_row.setVisible(is_global)
        # Disable API checkbox and hide API key for global models
        self._api_check.setEnabled(not is_global)
        if is_global:
            self._api_widget.setVisible(False)
        else:
            self._api_widget.setVisible(self._api_check.isChecked())

    def _styled_check(self, text: str, checked: bool) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                background: transparent;
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {Dark.BORDER_H};
                border-radius: 3px;
                background: {Dark.BG_ALT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
            }}
        """)
        return cb

    def _style_combo(self, combo: QComboBox):
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 4px 8px;
            }}
            QComboBox:focus {{ border-color: {Dark.ORANGE}; }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {Dark.NAVY};
                color: {Dark.TEXT};
                border: 1px solid {Dark.BORDER};
                selection-background-color: {Dark.SLATE};
            }}
        """)

    def _style_spin(self, spin):
        spin.setStyleSheet(f"""
            QSpinBox, QDoubleSpinBox {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 4px 8px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {Dark.ORANGE}; }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 16px;
                border: none;
                background: {Dark.SLATE};
            }}
        """)

    # ════════════════════════════════════════════
    #  Auto-Discovery
    # ════════════════════════════════════════════

    def _auto_discover_paths(self):
        """Auto-discover DB and station info on startup."""
        try:
            from tidebedpy.config import TideBedConfig, _find_project_root
            project_root = _find_project_root()
            temp = TideBedConfig()
            temp.auto_discover(project_root)

            db_found = bool(temp.db_root and os.path.isdir(temp.db_root))
            station_found = bool(temp.ref_st_info_path and os.path.isfile(temp.ref_st_info_path))

            if db_found:
                self._db_row.set_text(temp.db_root)
                self._db_row.set_auto_discovered(True)
            if station_found:
                self._station_row.set_text(temp.ref_st_info_path)
                self._station_row.set_auto_discovered(True)

            self._db_section.set_auto_discovered(db_found and station_found)
        except Exception:
            pass

    def _on_nav_changed(self, nav_path: str):
        """When Nav path changes, try to re-discover DB/station and suggest output."""
        if not nav_path or not os.path.isdir(nav_path):
            return

        # Suggest output path
        if not self._output_row.text():
            parent = os.path.dirname(nav_path.rstrip("/\\"))
            self._output_row.set_text(os.path.join(parent, "result.tid"))

        # Re-discover DB from nav parent tree
        try:
            from tidebedpy.config import TideBedConfig, _find_project_root
            nav_parent = os.path.dirname(nav_path.rstrip("/\\"))
            temp = TideBedConfig()
            temp.auto_discover(nav_parent)

            if temp.db_root and not self._db_row.text():
                self._db_row.set_text(temp.db_root)
                self._db_row.set_auto_discovered(True)
            if temp.ref_st_info_path and not self._station_row.text():
                self._station_row.set_text(temp.ref_st_info_path)
                self._station_row.set_auto_discovered(True)

            if self._db_row.text() and self._station_row.text():
                self._db_section.set_auto_discovered(True)
        except Exception:
            pass

        # Auto-detect rank limit
        self._auto_detect_rank_limit()

    def _on_tide_changed(self, tide_path: str):
        """When tide path changes, auto-detect matching stations and update rank."""
        self._auto_detect_rank_limit()

    def _on_station_changed(self, station_path: str):
        """When station info path changes, re-detect rank limit."""
        self._auto_detect_rank_limit()

    def _auto_detect_rank_limit(self):
        """Detect matching station count and update rank spin."""
        tide_dir = self._tide_row.text()
        station_file = self._station_row.text()
        if not tide_dir or not station_file:
            return
        if not os.path.isdir(tide_dir) or not os.path.isfile(station_file):
            return
        try:
            from tidebedpy.data_io.station import load_stations, get_station_by_name
            from tidebedpy.data_io.tide_series import _extract_station_name
            stations = load_stations(station_file)
            if not stations:
                return
            matched_names = set()
            for fname in os.listdir(tide_dir):
                if not fname.lower().endswith(('.txt', '.tts', '.csv', '.tsv', '.dat')):
                    continue
                fpath = os.path.join(tide_dir, fname)
                lines = None
                for enc in ['utf-8-sig', 'euc-kr', 'cp949']:
                    try:
                        with open(fpath, 'r', encoding=enc) as f:
                            lines = f.readlines()[:20]
                        break
                    except Exception:
                        continue
                if not lines:
                    continue
                sname = _extract_station_name(lines)
                if not sname and fname.lower().endswith('.csv'):
                    header_line = lines[0] if lines else ''
                    if '관측소명' in header_line and '관측시간' in header_line:
                        for line in lines[1:]:
                            parts = line.strip().split(',')
                            if len(parts) >= 3 and parts[1].strip():
                                sname = parts[1].strip()
                                break
                if sname and sname not in matched_names and get_station_by_name(stations, sname):
                    matched_names.add(sname)
            if matched_names:
                self._rank_spin.setValue(len(matched_names))
        except Exception:
            pass

    # ════════════════════════════════════════════
    #  Toggle / Browse helpers
    # ════════════════════════════════════════════

    def _toggle_batch_mode(self, checked: bool):
        """Toggle between single nav row and batch list."""
        self._nav_row.setVisible(not checked)
        self._batch_widget.setVisible(checked)
        self._update_drop_zone_status()

    def _batch_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Nav 폴더 선택")
        if folder:
            self._batch_list.addItem(folder)
            self._update_drop_zone_status()

    def _batch_remove_selected(self):
        for item in self._batch_list.selectedItems():
            self._batch_list.takeItem(self._batch_list.row(item))
        self._update_drop_zone_status()

    def _toggle_api(self, checked: bool):
        self._api_widget.setVisible(checked)
        self._tide_row.set_enabled(not checked)
        # API mode disables manual rank limit (auto-determined by API)
        self._rank_spin.setEnabled(not checked)
        self._save_api_key()

    def _toggle_validate(self, checked: bool):
        self._validate_edit.setEnabled(checked)
        self._validate_btn.setEnabled(checked)

    def _browse_validate(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "참조 TID 파일", self._validate_edit.text(),
            "TID (*.tid);;All (*.*)",
        )
        if path:
            self._validate_edit.setText(path)

    # ════════════════════════════════════════════
    #  API Key persistence
    # ════════════════════════════════════════════

    def _save_api_key(self):
        key = self._api_key_edit.text().strip()
        try:
            key_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".api_key",
            )
            if key:
                with open(key_path, "w") as f:
                    f.write(key)
        except Exception:
            pass

    def _load_saved_api_key(self):
        try:
            key_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".api_key",
            )
            if os.path.exists(key_path):
                with open(key_path, "r") as f:
                    key = f.read().strip()
                if key:
                    self._api_key_edit.setText(key)
        except Exception:
            pass

    # ════════════════════════════════════════════
    #  Preset / INI
    # ════════════════════════════════════════════

    def _get_current_settings(self) -> dict:
        tz_idx = self._tz_combo.currentIndex()
        utc_offset = TIMEZONE_OPTIONS[tz_idx][1] if tz_idx >= 0 else 0.0

        # C2: Tide model mapping
        model_map = {0: 'KHOA', 1: 'FES2014', 2: 'TPXO9'}
        tide_model = model_map.get(self._tide_model_combo.currentIndex(), 'KHOA')

        # C3: Output format mapping
        fmt_map = {0: 'TID', 1: 'TID + CSV', 2: 'TID + Kingdom', 3: 'TID + SonarWiz'}
        output_format = fmt_map.get(self._output_format_combo.currentIndex(), 'TID')

        return {
            "nav_path": self._nav_row.text(),
            "tide_path": self._tide_row.text(),
            "output_path": self._output_row.text(),
            "db_path": self._db_row.text(),
            "station_path": self._station_row.text(),
            "tide_type": self._tide_type_combo.currentText(),
            "rank_limit": self._rank_spin.value(),
            "time_interval": self._interval_spin.value(),
            "timezone": self._tz_combo.currentText(),
            "utc_offset": utc_offset,
            "write_detail": self._detail_check.isChecked(),
            "generate_graph": self._graph_check.isChecked(),
            "tolerance_cm": self._tolerance_spin.value(),
            "use_api": self._api_check.isChecked(),
            "api_key": self._api_key_edit.text(),
            "do_validate": self._validate_check.isChecked(),
            "validate_path": self._validate_edit.text(),
            "tide_model": tide_model,
            "model_dir": self._model_dir_row.text(),
            "output_format": output_format,
        }

    def _apply_settings(self, settings: dict):
        if "nav_path" in settings:
            self._nav_row.set_text(settings["nav_path"])
        if "tide_path" in settings:
            self._tide_row.set_text(settings["tide_path"])
        if "output_path" in settings:
            self._output_row.set_text(settings["output_path"])
        if "db_path" in settings:
            self._db_row.set_text(settings["db_path"])
        if "station_path" in settings:
            self._station_row.set_text(settings["station_path"])
        if "tide_type" in settings:
            idx = self._tide_type_combo.findText(settings["tide_type"])
            if idx >= 0:
                self._tide_type_combo.setCurrentIndex(idx)
        if "rank_limit" in settings:
            self._rank_spin.setValue(settings["rank_limit"])
        if "time_interval" in settings:
            self._interval_spin.setValue(settings["time_interval"])
        if "timezone" in settings:
            idx = self._tz_combo.findText(settings["timezone"])
            if idx >= 0:
                self._tz_combo.setCurrentIndex(idx)
        if "write_detail" in settings:
            self._detail_check.setChecked(settings["write_detail"])
        if "generate_graph" in settings:
            self._graph_check.setChecked(settings["generate_graph"])
        if "tolerance_cm" in settings:
            self._tolerance_spin.setValue(settings["tolerance_cm"])
        if "use_api" in settings:
            self._api_check.setChecked(settings["use_api"])
        if "api_key" in settings:
            self._api_key_edit.setText(settings["api_key"])

    def _save_preset(self):
        from tidebedpy.settings_manager import save_preset
        from PySide6.QtWidgets import QInputDialog
        from datetime import datetime

        name, ok = QInputDialog.getText(
            self, "세팅 저장",
            "프리셋 이름:",
            text=f"세팅_{datetime.now().strftime('%Y%m%d')}",
        )
        if ok and name.strip():
            filepath = save_preset(name.strip(), self._get_current_settings())
            self._controller.toast_requested.emit(
                f"세팅 저장: {os.path.basename(filepath)}", "success"
            )

    def _load_preset(self):
        from tidebedpy.settings_manager import list_presets, load_preset

        presets = list_presets()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        names = [f"{p['name']}  ({p['created']})" for p in presets]
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(
            self, "세팅 불러오기", "프리셋 선택:", names, 0, False,
        )
        if ok:
            idx = names.index(name)
            settings = load_preset(presets[idx]["path"])
            if settings:
                self._apply_settings(settings)
                self._controller.toast_requested.emit(
                    f"세팅 불러오기: {presets[idx]['name']}", "info"
                )

    def _load_ini(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "TideBedLite.ini", "",
            "INI (*.ini);;All (*.*)",
        )
        if not path:
            return
        try:
            from tidebedpy.config import TideBedConfig
            config = TideBedConfig.from_ini(path)
            if config.nav_directory:
                self._nav_row.set_text(config.nav_directory)
            if config.tts_folder:
                self._tide_row.set_text(config.tts_folder)
            if config.db_root:
                self._db_row.set_text(config.db_root)
            if config.ref_st_info_path:
                self._station_row.set_text(config.ref_st_info_path)
            self._tide_type_combo.setCurrentText(config.tide_series_type)
            self._rank_spin.setValue(config.rank_limit)
            self._interval_spin.setValue(config.time_interval_sec)
            self._detail_check.setChecked(config.write_detail)
            if config.is_kst:
                self._tz_combo.setCurrentText("KST (UTC+9)")
            else:
                self._tz_combo.setCurrentText("GMT (UTC+0)")

            config.auto_discover()
            if config.db_root and not self._db_row.text():
                self._db_row.set_text(config.db_root)
            if config.ref_st_info_path and not self._station_row.text():
                self._station_row.set_text(config.ref_st_info_path)

            self._auto_detect_rank_limit()
            self._controller.toast_requested.emit("INI 설정 불러오기 완료", "info")
        except Exception as e:
            self._controller.toast_requested.emit(f"INI 오류: {e}", "error")

    def _reset(self):
        self._nav_row.set_text("")
        self._tide_row.set_text("")
        self._output_row.set_text("")
        self._validate_edit.setText("")
        self._tide_type_combo.setCurrentIndex(0)
        self._rank_spin.setValue(10)
        self._interval_spin.setValue(0)
        self._tz_combo.setCurrentIndex(0)
        self._detail_check.setChecked(True)
        self._graph_check.setChecked(True)
        self._tolerance_spin.setValue(1.0)
        self._validate_check.setChecked(False)
        self._api_check.setChecked(False)
        self._tide_model_combo.setCurrentIndex(0)
        self._output_format_combo.setCurrentIndex(0)
        self._model_dir_row.set_text("")
        self._progress.reset()
        self._open_folder_btn.setVisible(False)
        self._toggle_validate(False)
        self._toggle_api(False)
        self._on_tide_model_changed(0)
        self._auto_discover_paths()
        self._controller.toast_requested.emit("설정이 초기화되었습니다", "info")

    # ════════════════════════════════════════════
    #  Run / Stop
    # ════════════════════════════════════════════

    def _validate_inputs(self) -> bool:
        errors = []

        if self._batch_mode.isChecked():
            if self._batch_list.count() == 0:
                errors.append("Batch 모드: 처리할 Nav 폴더가 없습니다.")
            else:
                for i in range(self._batch_list.count()):
                    p = self._batch_list.item(i).text()
                    if not os.path.isdir(p):
                        errors.append(f"Batch 폴더를 찾을 수 없습니다: {p}")
        else:
            nav = self._nav_row.text()
            if not nav:
                errors.append("항적 파일 폴더가 지정되지 않았습니다.")
            elif not os.path.isdir(nav):
                errors.append(f"항적 폴더를 찾을 수 없습니다: {nav}")

        is_global_model = self._tide_model_combo.currentIndex() > 0

        if is_global_model:
            # C2: Global model only needs model directory
            model_dir = self._model_dir_row.text()
            if not model_dir:
                errors.append("글로벌 모델 경로가 지정되지 않았습니다.")
            elif not os.path.isdir(model_dir):
                errors.append(f"모델 폴더를 찾을 수 없습니다: {model_dir}")
        else:
            if self._api_check.isChecked():
                if not self._api_key_edit.text().strip():
                    errors.append("API 자동 수집 모드에서는 API 키가 필요합니다.")
            else:
                tide = self._tide_row.text()
                if not tide:
                    errors.append("조위 시계열 폴더가 지정되지 않았습니다.")
                elif not os.path.isdir(tide):
                    errors.append(f"조위 폴더를 찾을 수 없습니다: {tide}")

            db = self._db_row.text()
            if not db:
                errors.append("개정수 DB 경로가 지정되지 않았습니다.")
            elif not os.path.isdir(db):
                errors.append(f"DB 폴더를 찾을 수 없습니다: {db}")

            station = self._station_row.text()
            if not station:
                errors.append("기준항정보 파일이 지정되지 않았습니다.")
            elif not os.path.isfile(station):
                errors.append(f"기준항정보 파일을 찾을 수 없습니다: {station}")

        output = self._output_row.text()
        if not output:
            errors.append("출력 파일 경로가 지정되지 않았습니다.")

        if errors:
            for err in errors:
                self._log_viewer.append_log(err, "error")
            QMessageBox.critical(self, "입력 오류", "\n".join(errors))
            return False
        return True

    def _run(self):
        if self._is_running:
            return
        if not self._validate_inputs():
            return

        if self._batch_mode.isChecked() and self._batch_list.count() > 0:
            self._run_batch()
            return

        self._run_start_time = time.time()
        self._is_running = True
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._open_folder_btn.setVisible(False)
        self._log_viewer.clear_log()
        self._progress.start()
        self._set_inputs_locked(True)

        config_dict = self._get_current_settings()

        # Save API key
        self._save_api_key()

        self._worker = CorrectionWorker(config_dict)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log_viewer.append_log)
        self._worker.status.connect(lambda s: self._progress.set_status(s))
        self._worker.finished.connect(self._on_finished)
        self._worker.result_data.connect(self._on_result_data)

        # C1: Connect station selection signal for API one-click pipeline
        self._worker.station_select_needed.connect(self._on_station_select_needed)

        self._thread.start()

    def _run_batch(self):
        """Run correction for each folder in the batch list sequentially."""
        total = self._batch_list.count()
        if total == 0:
            return

        self._is_running = True
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._open_folder_btn.setVisible(False)
        self._log_viewer.clear_log()
        self._progress.start()
        self._set_inputs_locked(True)
        self._save_api_key()

        self._batch_folders = [
            self._batch_list.item(i).text() for i in range(total)
        ]
        self._batch_index = 0
        self._batch_total = total
        self._batch_results = []
        self._run_start_time = time.time()
        self._run_next_batch()

    def _run_next_batch(self):
        """Start the next batch item."""
        idx = self._batch_index
        total = self._batch_total

        if idx >= total:
            # All done
            self._is_running = False
            self._set_inputs_locked(False)
            self._run_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            elapsed = time.time() - self._run_start_time
            success_count = sum(1 for r in self._batch_results if r)
            msg = f"Batch 완료: {success_count}/{total} 성공 ({elapsed:.1f}초)"
            self._progress.set_finished(success_count == total, msg)
            self._controller.toast_requested.emit(msg, "success" if success_count == total else "warning")
            self._open_folder_btn.setVisible(True)
            self._save_recent_paths()
            return

        folder = self._batch_folders[idx]
        folder_name = os.path.basename(folder.rstrip("/\\"))
        self._log_viewer.append_log(
            f"{'=' * 40}", "info"
        )
        self._log_viewer.append_log(
            f"[Batch {idx + 1}/{total}] {folder_name}", "info"
        )
        self._log_viewer.append_log(
            f"{'=' * 40}", "info"
        )

        # Build config for this batch item
        config_dict = self._get_current_settings()
        config_dict["nav_path"] = folder
        # Auto-generate output path per folder
        parent = os.path.dirname(folder.rstrip("/\\"))
        config_dict["output_path"] = os.path.join(parent, f"{folder_name}.tid")

        self._worker = CorrectionWorker(config_dict)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log_viewer.append_log)
        self._worker.status.connect(lambda s: self._progress.set_status(
            f"[Batch {idx + 1}/{total}] {s}"
        ))
        self._worker.finished.connect(self._on_batch_item_finished)

        self._thread.start()

    @Slot(bool, str)
    def _on_batch_item_finished(self, success: bool, msg: str):
        """Handle completion of one batch item."""
        self._batch_results.append(success)
        idx = self._batch_index
        folder_name = os.path.basename(self._batch_folders[idx].rstrip("/\\"))
        status = "OK" if success else "FAIL"
        self._log_viewer.append_log(
            f"[Batch {idx + 1}/{self._batch_total}] {folder_name}: {status} - {msg}",
            "info" if success else "error"
        )

        if success:
            # Record history for each successful batch item
            config_dict = self._get_current_settings()
            config_dict["nav_path"] = self._batch_folders[idx]
            parent = os.path.dirname(self._batch_folders[idx].rstrip("/\\"))
            output_path = os.path.join(parent, f"{folder_name}.tid")
            self._append_history(config_dict["nav_path"], config_dict.get("tide_path", ""), output_path)

        # Wait for thread to fully stop before releasing references
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self._worker = None
        self._thread = None
        self._batch_index += 1
        self._run_next_batch()

    def _stop(self):
        if self._worker:
            self._worker.request_stop()
            self._progress.set_status("중지 중...", Dark.WARNING)

    @Slot(int, int)
    def _on_progress(self, current: int, total: int):
        self._progress.set_progress(current, total)

    @Slot(list, list)
    def _on_station_select_needed(self, nearby_stations: list, nav_points: list):
        """C1: Worker requests station selection — show dialog on main thread."""
        from tidebedpy.desktop.widgets.station_select_dialog import StationSelectDialog
        selected = StationSelectDialog.get_selection(
            nearby_stations, nav_points=nav_points, parent=self
        )
        if self._worker:
            self._worker.set_selected_stations(selected or [])

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str):
        try:
            self._is_running = False
            self._set_inputs_locked(False)
            self._run_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            self._progress.set_finished(success, msg)

            if success:
                self._controller.toast_requested.emit(msg, "success")
                self._open_folder_btn.setVisible(True)
                self._save_recent_paths()
                self._show_result_preview()
                # A4: Append to history
                elapsed = time.time() - getattr(self, "_run_start_time", time.time())
                self._append_history(
                    self._nav_row.text(),
                    self._tide_row.text(),
                    self._output_row.text(),
                    elapsed=elapsed,
                )
            else:
                self._controller.toast_requested.emit(msg, "error")
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Ensure UI is always unlocked even on error
            self._run_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        finally:
            # Wait for thread to fully stop before releasing references
            # to avoid "QThread: Destroyed while thread is still running"
            thread = self._thread
            if thread is not None:
                thread.quit()
                thread.wait(5000)  # wait up to 5s for clean exit
            self._worker = None
            self._thread = None

    @Slot(dict)
    def _on_result_data(self, viz_data: dict):
        """Forward result data to viewer panel and switch to it."""
        try:
            app = self.window()
            viewer = app._panels.get("viewer")
            if viewer and hasattr(viewer, "load_result_data"):
                viewer.load_result_data(viz_data)
                # Auto-switch to viewer panel
                app.sidebar.set_active_panel("viewer")
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _set_inputs_locked(self, locked: bool):
        """Lock/unlock all input widgets during processing."""
        # Block signals to avoid cascading triggers during batch enable/disable
        signal_widgets = (self._api_check, self._validate_check,
                          self._tide_model_combo, self._batch_mode)
        for w in signal_widgets:
            w.blockSignals(True)

        # Path rows
        for row in (self._nav_row, self._tide_row, self._output_row,
                     self._db_row, self._station_row):
            row.set_enabled(not locked)
        # Option widgets
        for w in (self._tide_type_combo, self._rank_spin, self._tz_combo,
                  self._interval_spin, self._tolerance_spin,
                  self._detail_check, self._graph_check,
                  self._validate_check, self._validate_edit, self._validate_btn,
                  self._api_check, self._api_key_edit,
                  self._batch_mode, self._batch_add_btn, self._batch_remove_btn,
                  self._tide_model_combo, self._output_format_combo):
            w.setEnabled(not locked)
        self._model_dir_row.set_enabled(not locked)

        # Unblock signals
        for w in signal_widgets:
            w.blockSignals(False)

        # Re-apply toggle states after unlock (with signals restored)
        if not locked:
            self._toggle_api(self._api_check.isChecked())
            self._toggle_validate(self._validate_check.isChecked())
            self._on_tide_model_changed(self._tide_model_combo.currentIndex())

    def _show_result_preview(self):
        """Display interactive charts and/or static graph images after correction."""
        from PySide6.QtGui import QPixmap
        output = self._output_row.text()
        if not output:
            return

        chart_loaded = False

        # Load TID result into interactive charts
        if HAS_CHARTS and self._tide_chart and os.path.isfile(output):
            try:
                from tidebedpy.output.report import parse_tid_data
                from datetime import datetime
                tid_data = parse_tid_data(output)
                if tid_data and len(tid_data) > 0:
                    times = []
                    values = []
                    for item in tid_data:
                        # parse_tid_data returns (time_str, tc_value) tuples
                        t_str, tc_val = item[0], item[1]
                        try:
                            t = datetime.strptime(t_str, "%Y/%m/%d %H:%M:%S")
                            times.append(t)
                            values.append(float(tc_val))
                        except (ValueError, TypeError):
                            continue
                    if times:
                        self._tide_chart.set_data(times, values)
                        chart_loaded = True
            except Exception:
                import traceback
                traceback.print_exc()

        self._preview_card.setVisible(True)
        if self._tide_chart:
            self._tide_chart.setVisible(chart_loaded)
        if self._weight_chart:
            self._weight_chart.setVisible(False)  # needs station weight data

        # Static image fallback/supplement
        candidates = [
            output + ".png",
            output + ".compare.png",
            output + ".map.png",
            output + ".corrmap.png",
        ]
        found = None
        for path in candidates:
            if os.path.isfile(path):
                found = path
                break

        if found:
            pixmap = QPixmap(found)
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(
                    min(self._preview_label.width() or 800, 900),
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._preview_label.setPixmap(scaled)
                self._preview_label.setVisible(True)
        else:
            self._preview_card.setVisible(False)

    def _open_output_folder(self):
        output = self._output_row.text()
        if output:
            folder = os.path.dirname(output)
            if os.path.isdir(folder):
                if sys.platform == "win32":
                    os.startfile(folder)
                else:
                    subprocess.Popen(["xdg-open", folder])

    # ════════════════════════════════════════════
    #  Recent Paths Persistence
    # ════════════════════════════════════════════

    def _load_recent_paths(self):
        """Restore last-used paths from JSON config."""
        try:
            if os.path.isfile(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Only restore if fields are currently empty
                if not self._nav_row.text() and data.get("nav_path"):
                    self._nav_row.set_text(data["nav_path"])
                if not self._tide_row.text() and data.get("tide_path"):
                    self._tide_row.set_text(data["tide_path"])
                if not self._output_row.text() and data.get("output_path"):
                    self._output_row.set_text(data["output_path"])
                if not self._db_row.text() and data.get("db_path"):
                    self._db_row.set_text(data["db_path"])
                if not self._station_row.text() and data.get("station_path"):
                    self._station_row.set_text(data["station_path"])
                # Restore options
                if "tide_type" in data:
                    idx = self._tide_type_combo.findText(data["tide_type"])
                    if idx >= 0:
                        self._tide_type_combo.setCurrentIndex(idx)
                if "timezone" in data:
                    idx = self._tz_combo.findText(data["timezone"])
                    if idx >= 0:
                        self._tz_combo.setCurrentIndex(idx)
                if "rank_limit" in data:
                    self._rank_spin.setValue(data["rank_limit"])
                if "time_interval" in data:
                    self._interval_spin.setValue(data["time_interval"])
        except Exception:
            pass

    def _save_recent_paths(self):
        """Save current paths to JSON config for next session."""
        try:
            os.makedirs(self._CONFIG_DIR, exist_ok=True)
            # Preserve existing history
            data = {}
            if os.path.isfile(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data.update({
                "nav_path": self._nav_row.text(),
                "tide_path": self._tide_row.text(),
                "output_path": self._output_row.text(),
                "db_path": self._db_row.text(),
                "station_path": self._station_row.text(),
                "tide_type": self._tide_type_combo.currentText(),
                "timezone": self._tz_combo.currentText(),
                "rank_limit": self._rank_spin.value(),
                "time_interval": self._interval_spin.value(),
            })
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ════════════════════════════════════════════
    #  Project History (A4)
    # ════════════════════════════════════════════

    def _append_history(self, nav_path: str, tide_path: str, output_path: str,
                        elapsed: float = 0.0, points_count: int = 0):
        """Append a correction run to the history in recent.json."""
        from datetime import datetime
        try:
            os.makedirs(self._CONFIG_DIR, exist_ok=True)
            data = {}
            if os.path.isfile(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

            history = data.get("history", [])
            entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "nav_path": nav_path,
                "tide_path": tide_path,
                "output_path": output_path,
                "points_count": points_count,
                "elapsed_seconds": round(elapsed, 1),
            }
            history.append(entry)
            # Keep only last 10
            data["history"] = history[-10:]
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._refresh_history_combo()
        except Exception:
            pass

    def _load_history(self):
        """Load history from recent.json and populate combo."""
        try:
            if os.path.isfile(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history_entries = data.get("history", [])
            else:
                self._history_entries = []
        except Exception:
            self._history_entries = []
        self._refresh_history_combo()

    def _refresh_history_combo(self):
        """Update the history combo box items."""
        self._history_combo.clear()
        try:
            if os.path.isfile(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history_entries = data.get("history", [])
            else:
                self._history_entries = []
        except Exception:
            self._history_entries = []

        for entry in reversed(self._history_entries):
            nav_name = os.path.basename(entry.get("nav_path", "").rstrip("/\\"))
            date_str = entry.get("date", "")
            self._history_combo.addItem(f"{date_str}  {nav_name}")

    def _on_history_selected(self, index: int):
        """Restore paths from a history entry and open output location."""
        if index < 0:
            return
        # Index is reversed (newest first)
        actual_idx = len(self._history_entries) - 1 - index
        if actual_idx < 0 or actual_idx >= len(self._history_entries):
            return
        entry = self._history_entries[actual_idx]

        # Restore paths
        nav_path = entry.get("nav_path", "")
        tide_path = entry.get("tide_path", "")
        output_path = entry.get("output_path", "")

        if nav_path:
            self._nav_row.set_text(nav_path)
        if tide_path:
            self._tide_row.set_text(tide_path)
        if output_path:
            self._output_row.set_text(output_path)

        # Open output folder if it exists
        if output_path:
            folder = os.path.dirname(output_path)
            if os.path.isdir(folder):
                if sys.platform == "win32":
                    os.startfile(folder)
                else:
                    subprocess.Popen(["xdg-open", folder])

        self._controller.toast_requested.emit(
            f"히스토리 복원: {os.path.basename(nav_path)}", "info"
        )
