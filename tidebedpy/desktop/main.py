"""TideBedPy Desktop — PySide6 Application Entry Point."""

import sys
import os

# Ensure tidebedpy package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "_shared"))

from PySide6.QtGui import QShortcut, QKeySequence

from geoview_pyside6 import GeoViewApp, Category

from tidebedpy.desktop.app_controller import AppController
from tidebedpy.desktop.widgets.toast import ToastManager
from tidebedpy.desktop.panels.correction_panel import CorrectionPanel


class TideBedApp(GeoViewApp):
    """TideBedPy — Tidal Correction Desktop Application."""

    APP_NAME = "TideBedPy"
    APP_VERSION = "v3.0"
    CATEGORY = Category.PREPROCESSING

    def __init__(self):
        self.controller = AppController()
        super().__init__()

        # Toast manager
        self.toast_mgr = ToastManager(self.content_stack)
        self.controller.toast_requested.connect(self.toast_mgr.show_toast)

        # Keyboard shortcuts
        self._setup_shortcuts()

    def setup_panels(self):
        # Main correction panel
        self._correction = CorrectionPanel(self.controller)
        self.add_panel("correction", "\u25A0", "조석보정", self._correction)

        # Tools panel (lazy import to avoid circular)
        try:
            from tidebedpy.desktop.panels.tools_panel import ToolsPanel
            self._tools = ToolsPanel(self.controller)
            self.add_panel("tools", "\u25C6", "도구", self._tools)
        except ImportError:
            pass

        # Compare panel
        try:
            from tidebedpy.desktop.panels.compare_panel import ComparePanel
            self._compare = ComparePanel(self.controller)
            self.add_panel("compare", "\u25C7", "비교", self._compare)
        except ImportError:
            pass

        # Viewer panel
        try:
            from tidebedpy.desktop.panels.viewer_panel import ViewerPanel
            self._viewer = ViewerPanel(self.controller)
            self.add_panel("viewer", "\u25B3", "시각화", self._viewer)
        except ImportError:
            pass

    def _setup_shortcuts(self):
        # Ctrl+R: Run correction
        sc_run = QShortcut(QKeySequence("Ctrl+R"), self)
        sc_run.activated.connect(self._correction._run)

        # Ctrl+S: Save preset
        sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        sc_save.activated.connect(self._correction._save_preset)

        # Ctrl+L: Load preset
        sc_load = QShortcut(QKeySequence("Ctrl+L"), self)
        sc_load.activated.connect(self._correction._load_preset)

        # Escape: Stop correction
        sc_stop = QShortcut(QKeySequence("Escape"), self)
        sc_stop.activated.connect(self._correction._stop)

    # ── Project Context Integration ──

    def on_project_context_changed(self, ctx, old_ctx=None):
        """공유 프로젝트 컨텍스트 변경 시 timezone_offset 힌트."""
        if ctx is None:
            return
        parts = []
        if ctx.timezone_offset != 0:
            sign = "+" if ctx.timezone_offset >= 0 else ""
            parts.append(f"TZ: UTC{sign}{ctx.timezone_offset}")
        if ctx.survey_area:
            parts.append(f"Area: {ctx.survey_area}")
        if parts:
            self.status_bar.showMessage(" | ".join(parts), 5000)


def main():
    TideBedApp.run()


if __name__ == "__main__":
    main()
