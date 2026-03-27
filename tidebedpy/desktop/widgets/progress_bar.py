"""ProgressBar — Status label + thin bar + elapsed time."""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space


class TideProgressBar(QWidget):
    """Progress display: status label + bar + elapsed time."""

    def __init__(self, accent: str = "#F59E0B", parent=None):
        super().__init__(parent)
        self._accent = accent
        self._start_time = 0.0
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Status row: left = status text, right = elapsed time
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("대기 중")
        self._status_label.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.SM}px;
            background: transparent;
        """)
        status_row.addWidget(self._status_label)

        status_row.addStretch()

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet(f"""
            color: {Dark.DIM};
            font-size: {Font.XS}px;
            font-family: {Font.MONO};
            background: transparent;
        """)
        status_row.addWidget(self._elapsed_label)

        layout.addLayout(status_row)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setFixedHeight(8)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {Dark.DARK};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {accent};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self._bar)

        # Elapsed timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)

    def start(self):
        """Begin progress tracking."""
        self._start_time = time.time()
        self._running = True
        self._bar.setValue(0)
        self._status_label.setStyleSheet(f"""
            color: {Dark.TEXT};
            font-size: {Font.SM}px;
            background: transparent;
        """)
        self._timer.start()

    def stop(self):
        """Stop the timer."""
        self._running = False
        self._timer.stop()

    def reset(self):
        """Reset to initial state."""
        self._running = False
        self._timer.stop()
        self._bar.setValue(0)
        self._status_label.setText("대기 중")
        self._status_label.setStyleSheet(f"""
            color: {Dark.MUTED};
            font-size: {Font.SM}px;
            background: transparent;
        """)
        self._elapsed_label.setText("")

    def set_progress(self, current: int, total: int):
        """Update progress bar and status text."""
        if total <= 0:
            return
        pct = int(current / total * 100)
        self._bar.setValue(pct)
        self._status_label.setText(
            f"처리 중  {current:,} / {total:,}  ({pct}%)"
        )

    def set_status(self, text: str, color: str = ""):
        """Set custom status text."""
        self._status_label.setText(text)
        if color:
            self._status_label.setStyleSheet(f"""
                color: {color};
                font-size: {Font.SM}px;
                background: transparent;
            """)

    def set_finished(self, success: bool, msg: str = ""):
        """Show completion status."""
        self.stop()
        if success:
            self._bar.setValue(100)
            self._bar.setStyleSheet(f"""
                QProgressBar {{ background: {Dark.DARK}; border: none; border-radius: 4px; }}
                QProgressBar::chunk {{ background: {Dark.GREEN}; border-radius: 4px; }}
            """)
            self.set_status(msg or "보정 완료", Dark.GREEN)
        else:
            self._bar.setStyleSheet(f"""
                QProgressBar {{ background: {Dark.DARK}; border: none; border-radius: 4px; }}
                QProgressBar::chunk {{ background: {Dark.RED}; border-radius: 4px; }}
            """)
            self.set_status(msg or "처리 실패", Dark.RED)

    def _update_elapsed(self):
        if not self._running:
            return
        elapsed = time.time() - self._start_time
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        self._elapsed_label.setText(f"{mins:02d}:{secs:02d}")
