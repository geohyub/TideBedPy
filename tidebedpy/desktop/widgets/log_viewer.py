"""LogViewer — Dark-themed scrollable log display with colored tags."""

from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QTextEdit, QMenu
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QAction

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))
from geoview_pyside6.constants import Dark, Font


# Tag → (foreground color, bold)
_TAG_STYLES = {
    "info":    ("#82E0AA", False),
    "step":    ("#85C1E9", True),
    "detail":  ("#AAB7B8", False),
    "warning": ("#F9E79F", False),
    "error":   ("#F1948A", False),
    "success": ("#58D68D", True),
    "header":  ("#AED6F1", True),
    "dim":     ("#5D6D7E", False),
}


class LogViewer(QTextEdit):
    """Read-only dark log viewer with colored tags and context menu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setObjectName("logViewer")

        self.setStyleSheet(f"""
            QTextEdit#logViewer {{
                background: {Dark.BG};
                color: #D5D8DC;
                font-size: {Font.SM}px;
                font-family: {Font.MONO};
                border: 1px solid {Dark.BORDER};
                border-radius: 6px;
                padding: 10px;
                selection-background-color: #34495E;
            }}
        """)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    @Slot(str, str)
    def append_log(self, message: str, tag: str = "info"):
        """Append a timestamped log line with colored tag."""
        ts = datetime.now().strftime("%H:%M:%S")
        color_hex, bold = _TAG_STYLES.get(tag, _TAG_STYLES["info"])

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        else:
            fmt.setFontWeight(QFont.Weight.Normal)

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(f"{ts}  {message}\n", fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_log(self):
        self.clear()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Dark.NAVY};
                color: {Dark.TEXT};
                border: 1px solid {Dark.BORDER};
                padding: 4px;
                font-size: {Font.SM}px;
            }}
            QMenu::item:selected {{
                background: {Dark.SLATE};
            }}
        """)

        copy_action = QAction("선택 복사", self)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)

        copy_all = QAction("전체 복사", self)
        copy_all.triggered.connect(self._copy_all)
        menu.addAction(copy_all)

        menu.addSeparator()

        clear_action = QAction("로그 지우기", self)
        clear_action.triggered.connect(self.clear_log)
        menu.addAction(clear_action)

        menu.exec(self.mapToGlobal(pos))

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.toPlainText())
