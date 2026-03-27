"""PathRow — Label + LineEdit + Browse button with drag-and-drop support."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font, Space, Radius


class _DropLineEdit(QLineEdit):
    """QLineEdit that accepts file/folder drops."""

    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.styleSheet() + f"border-color: {Dark.CYAN};")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        # Reset border — rely on parent to re-apply normal style
        self.setStyleSheet(self.styleSheet().replace(f"border-color: {Dark.CYAN};", ""))

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.setText(path)
            self.path_dropped.emit(path)
            event.acceptProposedAction()
        self.setStyleSheet(self.styleSheet().replace(f"border-color: {Dark.CYAN};", ""))


class PathRow(QWidget):
    """
    Path input row: [Label] [LineEdit] [Browse]
    Supports folder/file browse and drag-and-drop.
    """

    path_changed = Signal(str)

    def __init__(
        self,
        label: str,
        hint: str = "",
        mode: str = "folder",        # "folder", "file", "save"
        file_filter: str = "",       # e.g. "TID (*.tid);;All (*.*)"
        parent=None,
    ):
        super().__init__(parent)
        self._mode = mode
        self._file_filter = file_filter
        self._auto_discovered = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(2)

        # Main row
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Space.SM)

        # Label
        lbl = QLabel(label)
        lbl.setFixedWidth(110)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(f"""
            color: {Dark.TEXT};
            font-size: {Font.SM}px;
            font-weight: {Font.MEDIUM};
            background: transparent;
        """)
        row.addWidget(lbl)

        # Auto-discover badge (hidden by default)
        self._badge = QLabel("AUTO")
        self._badge.setFixedSize(40, 18)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(f"""
            background: {Dark.GREEN}1A;
            color: {Dark.GREEN};
            font-size: 9px;
            font-weight: {Font.SEMIBOLD};
            border-radius: 4px;
            border: none;
        """)
        self._badge.setVisible(False)
        row.addWidget(self._badge)

        # Line edit
        self._edit = _DropLineEdit()
        self._edit.setPlaceholderText(hint or f"{label} 경로를 입력하거나 탐색하세요")
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Dark.BG_ALT};
                color: {Dark.TEXT};
                font-size: {Font.SM}px;
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border-color: {Dark.ORANGE};
            }}
        """)
        self._edit.textChanged.connect(self.path_changed.emit)
        self._edit.path_dropped.connect(self._on_drop)
        row.addWidget(self._edit, 1)

        # Browse button
        browse_btn = QPushButton("탐색")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setFixedWidth(54)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Dark.SLATE};
                color: {Dark.TEXT};
                font-size: {Font.XS}px;
                font-weight: {Font.MEDIUM};
                border: 1px solid {Dark.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 0;
            }}
            QPushButton:hover {{
                background: {Dark.SURFACE};
                border-color: {Dark.BORDER_H};
            }}
        """)
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)

        root_layout.addLayout(row)

        # Hint row (optional)
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet(f"""
                color: {Dark.DIM};
                font-size: {Font.XS}px;
                background: transparent;
                padding-left: {110 + Space.SM}px;
            """)
            root_layout.addWidget(hint_lbl)

    # ── Public API ──

    def text(self) -> str:
        return self._edit.text().strip()

    def set_text(self, path: str):
        self._edit.setText(path)

    def set_auto_discovered(self, discovered: bool):
        """Show/hide the AUTO badge."""
        self._auto_discovered = discovered
        self._badge.setVisible(discovered)

    def set_enabled(self, enabled: bool):
        self._edit.setEnabled(enabled)
        for child in self.findChildren(QPushButton):
            child.setEnabled(enabled)

    # ── Private ──

    def _browse(self):
        if self._mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "폴더 선택", self.text())
        elif self._mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, "저장 경로", self.text(), self._file_filter
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "파일 선택", self.text(), self._file_filter
            )
        if path:
            self._edit.setText(path)

    def _on_drop(self, path: str):
        # If mode is folder but a file was dropped, use its parent directory
        if self._mode == "folder" and os.path.isfile(path):
            path = os.path.dirname(path)
            self._edit.setText(path)
