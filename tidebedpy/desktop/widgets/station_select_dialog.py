"""StationSelectDialog — Map-based station selector for API collection."""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QWidget, QFrame, QMessageBox,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius

ACCENT = "#F59E0B"


class StationSelectDialog(QDialog):
    """Modal dialog for selecting nearby tide stations before API fetch."""

    def __init__(self, nearby_stations, nav_points=None, parent=None):
        """
        Args:
            nearby_stations: list of (code, name, distance_km)
            nav_points: list of NavPoint objects (for map display)
        """
        super().__init__(parent)
        self._nearby = nearby_stations
        self._nav = nav_points or []
        self._check_vars: list[QCheckBox] = []
        self.result = None  # None = cancelled, list = selected stations

        self.setWindowTitle("API 관측소 선택")
        self.setMinimumSize(500, 500)
        self.resize(600, 550)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Dark.BG};
            }}
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        layout.setSpacing(Space.MD)

        # Title
        title = QLabel("관측소 선택")
        title.setStyleSheet(f"""
            color: {Dark.TEXT_BRIGHT};
            font-size: {Font.LG}px;
            font-weight: {Font.SEMIBOLD};
            background: transparent;
        """)
        layout.addWidget(title)

        desc = QLabel("체크된 관측소에서 조위를 수집합니다. 100km 이내는 자동 선택됩니다.")
        desc.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.XS}px;
            background: transparent;
        """)
        layout.addWidget(desc)

        # Select all / none
        btn_row = QHBoxLayout()
        for text, callback in [
            ("전체 선택", lambda: self._set_all(True)),
            ("전체 해제", lambda: self._set_all(False)),
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
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Station list (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {Dark.NAVY}; border: 1px solid {Dark.BORDER}; border-radius: {Radius.SM}px; }}
            QScrollBar:vertical {{
                background: {Dark.BG_ALT}; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {Dark.SLATE}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        list_widget = QWidget()
        list_widget.setStyleSheet(f"background: {Dark.NAVY};")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(Space.SM, Space.SM, Space.SM, Space.SM)
        list_layout.setSpacing(2)

        for code, name, dist in self._nearby:
            cb = QCheckBox(f"{name}  ({dist:.0f} km)")
            cb.setChecked(dist <= 100)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {Dark.TEXT};
                    font-size: {Font.SM}px;
                    background: transparent;
                    padding: 4px 6px;
                    spacing: 6px;
                }}
                QCheckBox:hover {{
                    background: {Dark.SLATE};
                    border-radius: 4px;
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
            self._check_vars.append(cb)
            list_layout.addWidget(cb)

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        layout.addWidget(scroll, 1)

        # Summary label
        self._summary = QLabel(self._get_summary())
        self._summary.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.XS}px;
            background: transparent;
        """)
        layout.addWidget(self._summary)

        # Update summary on checkbox change
        for cb in self._check_vars:
            cb.toggled.connect(self._update_summary)

        # Bottom buttons
        btn_frame = QHBoxLayout()
        btn_frame.setSpacing(Space.SM)

        ok_btn = QPushButton("  수집 시작  ")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
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
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_frame.addWidget(ok_btn)

        cancel_btn = QPushButton("  취소  ")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{ background: {Dark.SURFACE}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_frame.addWidget(cancel_btn)

        btn_frame.addStretch()
        layout.addLayout(btn_frame)

    def _set_all(self, val: bool):
        for cb in self._check_vars:
            cb.setChecked(val)

    def _get_summary(self) -> str:
        count = sum(1 for cb in self._check_vars if cb.isChecked())
        return f"{count}개 관측소 선택됨"

    def _update_summary(self):
        self._summary.setText(self._get_summary())

    def _on_ok(self):
        selected = [
            (code, name, dist)
            for (code, name, dist), cb in zip(self._nearby, self._check_vars)
            if cb.isChecked()
        ]
        if not selected:
            QMessageBox.warning(self, "선택 없음", "최소 1개 관측소를 선택하세요.")
            return
        self.result = selected
        self.accept()

    @staticmethod
    def get_selection(nearby_stations, nav_points=None, parent=None):
        """Show dialog and return selected stations or None if cancelled."""
        dlg = StationSelectDialog(nearby_stations, nav_points, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result
        return None
