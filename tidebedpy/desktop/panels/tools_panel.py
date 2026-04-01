"""ToolsPanel — API download + CSV-to-TOPS conversion tools."""

import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Slot, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QScrollArea, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QProgressBar, QAbstractItemView, QCheckBox,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius

ACCENT = "#F59E0B"


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("toolCard")
    card.setStyleSheet(f"""
        QFrame#toolCard {{
            background: {Dark.NAVY};
            border: 1px solid {Dark.BORDER};
            border-radius: {Radius.BASE}px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(Space.BASE, Space.MD, Space.BASE, Space.MD)
    layout.setSpacing(Space.SM)

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


class ApiWorker(QWidget):
    """Worker that runs API download in a thread and emits signals."""

    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, api_key, codes, start, end, out_dir, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._codes = codes
        self._start = start
        self._end = end
        self._out_dir = out_dir

    def run_in_thread(self):
        def _worker():
            try:
                from tidebedpy.data_io.khoa_api import download_and_export
                results = download_and_export(
                    self._api_key, self._codes, self._start, self._end,
                    self._out_dir,
                    progress_callback=lambda msg: self.log.emit(msg),
                )
                ok = [r for r in results if not r.error]
                err = [r for r in results if r.error]

                lines = [f"완료: {len(ok)}개 관측소"]
                for r in ok:
                    lines.append(f"  {r.station_name}: 실측 {r.obs_count}행, 예측 {r.pred_count}행")
                for r in err:
                    lines.append(f"  오류 {r.station_name}: {r.error}")
                self.finished.emit(True, "\n".join(lines))
            except Exception as e:
                self.finished.emit(False, str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()


class ToolsPanel(QWidget):
    """Tools: API download, CSV→TOPS conversion."""

    panel_title = "도구"

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)

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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.BASE)

        self._build_api_card(layout)
        self._build_cache_card(layout)
        self._build_csv_card(layout)
        self._build_manual_card(layout)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── API Download Card ──
    def _build_api_card(self, parent_layout):
        card, layout = _card("조위 API 다운로드 (공공데이터포털)")

        input_style = f"""
            QLineEdit {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 5px 8px;
            }}
            QLineEdit:focus {{ border-color: {Dark.ORANGE}; }}
        """

        # API key
        row1 = QHBoxLayout()
        lbl = QLabel("API 서비스키")
        lbl.setFixedWidth(100)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(f"color: {Dark.TEXT}; font-size: {Font.SM}px; font-weight: {Font.MEDIUM}; background: transparent;")
        row1.addWidget(lbl)
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("공공데이터포털 인증키")
        self._api_key_input.setStyleSheet(input_style)
        row1.addWidget(self._api_key_input, 1)
        layout.addLayout(row1)

        # Date range
        row2 = QHBoxLayout()
        lbl2 = QLabel("기간")
        lbl2.setFixedWidth(100)
        lbl2.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl2.setStyleSheet(f"color: {Dark.TEXT}; font-size: {Font.SM}px; font-weight: {Font.MEDIUM}; background: transparent;")
        row2.addWidget(lbl2)

        today = datetime.now()
        self._start_date = QLineEdit(today.replace(day=1).strftime("%Y%m%d"))
        self._start_date.setFixedWidth(90)
        self._start_date.setStyleSheet(input_style)
        row2.addWidget(self._start_date)

        sep = QLabel("~")
        sep.setStyleSheet(f"color: {Dark.MUTED}; background: transparent;")
        row2.addWidget(sep)

        self._end_date = QLineEdit(today.strftime("%Y%m%d"))
        self._end_date.setFixedWidth(90)
        self._end_date.setStyleSheet(input_style)
        row2.addWidget(self._end_date)

        hint = QLabel("(YYYYMMDD)")
        hint.setStyleSheet(f"color: {Dark.DIM}; font-size: {Font.XS}px; background: transparent;")
        row2.addWidget(hint)
        row2.addStretch()
        layout.addLayout(row2)

        # Station list
        lbl3 = QLabel("관측소 (Ctrl+클릭 다중선택)")
        lbl3.setStyleSheet(f"color: {Dark.TEXT}; font-size: {Font.SM}px; font-weight: {Font.MEDIUM}; background: transparent;")
        layout.addWidget(lbl3)

        self._station_list = QListWidget()
        self._station_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._station_list.setMaximumHeight(200)
        self._station_list.setAlternatingRowColors(True)
        self._station_list.setStyleSheet(f"""
            QListWidget {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 2px 4px;
            }}
            QListWidget::item:alternate {{
                background: {Dark.DARK};
            }}
            QListWidget::item:selected {{
                background: {Dark.SLATE};
                color: {Dark.TEXT_BRIGHT};
            }}
        """)
        try:
            from tidebedpy.data_io.khoa_api import STATION_LIST
            for code, name in STATION_LIST:
                self._station_list.addItem(f"{name} ({code})")
        except ImportError:
            self._station_list.addItem("(khoa_api 모듈 로드 실패)")
        layout.addWidget(self._station_list)

        # Select all/none
        sel_row = QHBoxLayout()
        for text, callback in [
            ("전체 선택", lambda: self._station_list.selectAll()),
            ("선택 해제", lambda: self._station_list.clearSelection()),
        ]:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Dark.MUTED};
                    font-size: {Font.XS}px;
                    border: 1px solid {Dark.BORDER};
                    border-radius: 4px;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{ color: {Dark.TEXT}; background: {Dark.SLATE}; }}
            """)
            btn.clicked.connect(callback)
            sel_row.addWidget(btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Status + progress
        self._api_status = QLabel("대기 중")
        self._api_status.setStyleSheet(f"color: {Dark.MUTED}; font-size: {Font.XS}px; background: transparent;")
        layout.addWidget(self._api_status)

        self._api_progress = QProgressBar()
        self._api_progress.setFixedHeight(6)
        self._api_progress.setRange(0, 0)
        self._api_progress.setVisible(False)
        self._api_progress.setStyleSheet(f"""
            QProgressBar {{
                background: {Dark.DARK};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {ACCENT};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self._api_progress)

        # Download button
        btn_row = QHBoxLayout()
        self._download_btn = QPushButton("  다운로드 시작  ")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: {Dark.BG};
                font-size: {Font.SM}px;
                font-weight: {Font.BOLD};
                border: none;
                border-radius: {Radius.SM}px;
                padding: 8px 24px;
            }}
            QPushButton:hover {{ background: #D97706; }}
            QPushButton:disabled {{ background: {Dark.SLATE}; color: {Dark.DIM}; }}
        """)
        self._download_btn.clicked.connect(self._do_download)
        btn_row.addWidget(self._download_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── CSV→TOPS Card ──
    def _build_csv_card(self, parent_layout):
        card, layout = _card("CSV \u2192 TOPS 변환")

        desc = QLabel("KHOA 바다누리 CSV 파일을 TOPS 형식으로 변환합니다.")
        desc.setStyleSheet(f"color: {Dark.MUTED}; font-size: {Font.XS}px; background: transparent;")
        layout.addWidget(desc)

        btn_row = QHBoxLayout()

        btn_folder = QPushButton("폴더 변환")
        btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_folder.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT};
                font-size: {Font.SM}px;
                font-weight: {Font.MEDIUM};
                border: 1px solid {ACCENT}66;
                border-radius: {Radius.SM}px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ background: {ACCENT}1A; border-color: {ACCENT}; }}
        """)
        btn_folder.clicked.connect(lambda: self._convert_csv(folder_mode=True))
        btn_row.addWidget(btn_folder)

        btn_files = QPushButton("파일 선택 변환")
        btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_files.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Dark.MUTED};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ color: {Dark.TEXT}; background: {Dark.SLATE}; }}
        """)
        btn_files.clicked.connect(lambda: self._convert_csv(folder_mode=False))
        btn_row.addWidget(btn_files)

        btn_row.addStretch()
        layout.addLayout(btn_row)
        parent_layout.addWidget(card)

    # ── Manual Card ──
    def _build_manual_card(self, parent_layout):
        card, layout = _card("매뉴얼")

        btn_row = QHBoxLayout()
        btn = QPushButton("매뉴얼 열기")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ color: {Dark.TEXT_BRIGHT}; background: {Dark.SURFACE}; }}
        """)
        btn.clicked.connect(self._open_manual)
        btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Shortcut hints
        hint = QLabel("Ctrl+R  보정 수행   |   Ctrl+S  세팅 저장   |   Esc  중지")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            color: {Dark.DIM};
            font-size: {Font.XS}px;
            background: transparent;
            border: none;
            padding: {Space.SM}px 0;
        """)
        layout.addWidget(hint)

        parent_layout.addWidget(card)

    # ── Cache Card ──
    def _build_cache_card(self, parent_layout):
        card, layout = _card("API 캐시")

        desc = QLabel("KHOA API 조위 데이터를 로컬에 캐시하여 재다운로드를 줄입니다.")
        desc.setStyleSheet(f"color: {Dark.MUTED}; font-size: {Font.XS}px; background: transparent;")
        layout.addWidget(desc)

        # Cache enabled checkbox
        self._cache_check = QCheckBox("API 캐시 사용")
        self._cache_check.setChecked(True)
        self._cache_check.setStyleSheet(f"""
            QCheckBox {{
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {Dark.BORDER};
                border-radius: 3px;
                background: {Dark.BG_ALT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
            }}
        """)
        layout.addWidget(self._cache_check)

        # Stats label
        self._cache_stats_label = QLabel("")
        self._cache_stats_label.setStyleSheet(
            f"color: {Dark.MUTED}; font-size: {Font.XS}px; background: transparent;"
        )
        layout.addWidget(self._cache_stats_label)
        self._refresh_cache_stats()

        # Clear button
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("캐시 비우기")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Dark.MUTED};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ color: {Dark.TEXT}; background: {Dark.SLATE}; }}
        """)
        clear_btn.clicked.connect(self._clear_cache)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    def _refresh_cache_stats(self):
        """Update cache stats label."""
        try:
            from tidebedpy.data_io.tide_cache import TideCache
            cache = TideCache()
            stats = cache.stats()
            cache.close()
            total = stats.get("total_records", 0)
            stations = stats.get("stations", 0)
            self._cache_stats_label.setText(
                f"{total}일치 데이터, {stations}개 관측소"
            )
        except Exception:
            self._cache_stats_label.setText("캐시 정보 없음")

    def _clear_cache(self):
        """Clear all cached tide data."""
        reply = QMessageBox.question(
            self, "캐시 비우기",
            "모든 캐시된 조위 데이터를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from tidebedpy.data_io.tide_cache import TideCache
            cache = TideCache()
            cache.clear()
            cache.close()
            self._refresh_cache_stats()
            self._controller.toast_requested.emit("캐시 비우기 완료", "success")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"캐시 비우기 실패:\n{e}")

    def is_cache_enabled(self) -> bool:
        """Return whether API cache is enabled."""
        return self._cache_check.isChecked()

    # ════════════════════════════════════════════
    #  API Download
    # ════════════════════════════════════════════

    def _do_download(self):
        api_key = self._api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "입력 필요", "API 서비스키를 입력하세요.")
            return

        selected = self._station_list.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "선택 필요", "관측소를 선택하세요.")
            return

        start = self._start_date.text().strip()
        end = self._end_date.text().strip()
        if len(start) != 8 or len(end) != 8:
            QMessageBox.warning(self, "입력 오류", "날짜를 YYYYMMDD 형식으로 입력하세요.")
            return

        try:
            from tidebedpy.data_io.khoa_api import STATION_LIST
            codes = [STATION_LIST[idx.row()][0] for idx in selected]
        except Exception:
            return

        out_dir = QFileDialog.getExistingDirectory(self, "CSV 출력 폴더")
        if not out_dir:
            return

        self._download_btn.setEnabled(False)
        self._api_progress.setVisible(True)

        worker = ApiWorker(api_key, codes, start, end, out_dir, self)
        worker.log.connect(lambda msg: self._api_status.setText(msg))
        worker.finished.connect(self._on_download_done)
        worker.run_in_thread()
        self._api_worker = worker  # prevent GC

    @Slot(bool, str)
    def _on_download_done(self, success, msg):
        self._download_btn.setEnabled(True)
        self._api_progress.setVisible(False)
        if success:
            self._api_status.setText("다운로드 완료")
            self._controller.toast_requested.emit("API 다운로드 완료", "success")
            QMessageBox.information(self, "완료", msg)
        else:
            self._api_status.setText(f"오류: {msg}")
            self._controller.toast_requested.emit(f"API 오류: {msg}", "error")

    # ════════════════════════════════════════════
    #  CSV→TOPS
    # ════════════════════════════════════════════

    def _convert_csv(self, folder_mode: bool):
        if folder_mode:
            csv_dir = QFileDialog.getExistingDirectory(self, "CSV 폴더 선택")
            if not csv_dir:
                return
            csv_files = [
                os.path.join(csv_dir, f) for f in os.listdir(csv_dir)
                if f.lower().endswith(".csv")
            ]
            if not csv_files:
                QMessageBox.warning(self, "변환", "CSV 파일이 없습니다.")
                return
        else:
            files, _ = QFileDialog.getOpenFileNames(
                self, "CSV 파일 선택", "", "CSV (*.csv);;All (*.*)"
            )
            if not files:
                return
            csv_files = list(files)

        out_dir = QFileDialog.getExistingDirectory(self, "TOPS 출력 폴더")
        if not out_dir:
            return

        try:
            from tidebedpy.data_io.csv_to_tops import batch_convert
            results = batch_convert(csv_files, out_dir, export_observed=True, export_predicted=True)
            if results:
                self._controller.toast_requested.emit(
                    f"CSV→TOPS: {len(results)}개 관측소 변환 완료", "success"
                )
                QMessageBox.information(
                    self, "완료",
                    f"{len(results)}개 관측소 변환 완료\n출력: {out_dir}",
                )
            else:
                QMessageBox.warning(self, "결과", "변환된 파일이 없습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"변환 실패:\n{e}")

    # ════════════════════════════════════════════
    #  Manual
    # ════════════════════════════════════════════

    def _open_manual(self):
        from tidebedpy.config import _find_project_root
        search_dirs = [
            os.path.join(_find_project_root(), "manual"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manual"),
        ]
        for d in search_dirs:
            for fname in ["TideBedPy_Manual.docx", "TideBedPy_Manual.txt"]:
                path = os.path.join(d, fname)
                if os.path.isfile(path):
                    try:
                        os.startfile(path)
                        return
                    except Exception:
                        import subprocess
                        subprocess.Popen(["start", "", path], shell=True)
                        return
        QMessageBox.information(self, "매뉴얼", "매뉴얼 파일을 찾을 수 없습니다.")
