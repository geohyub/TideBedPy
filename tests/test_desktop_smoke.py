"""Desktop smoke tests -- verify panels load without crash."""
import os
import sys
import pytest

# Setup paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "_shared"))

# Skip if no display
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.environ.get("DISPLAY") is None and sys.platform != "win32",
    reason="No display available"
)


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication once for all tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_main_window_loads(qapp):
    from tidebedpy.desktop.main import TideBedApp
    w = TideBedApp()
    w.show()
    qapp.processEvents()
    assert w.isVisible()


def test_all_panels_switch(qapp):
    from tidebedpy.desktop.main import TideBedApp
    w = TideBedApp()
    w.show()
    for panel_name in ['correction', 'tools', 'compare', 'viewer']:
        w.sidebar.set_active_panel(panel_name)
        qapp.processEvents()
    # No crash = pass


def test_viewer_tabs(qapp):
    from tidebedpy.desktop.main import TideBedApp
    w = TideBedApp()
    w.show()
    w.sidebar.set_active_panel('viewer')
    viewer = w._panels.get('viewer')
    assert viewer is not None
    for i in range(6):
        viewer._switch_tab(i)
        qapp.processEvents()
    # No crash = pass


def test_settings_manager_defaults():
    """Test that preset defaults are complete."""
    from tidebedpy.settings_manager import PRESET_DEFAULTS
    required_keys = ['nav_path', 'tide_path', 'output_path', 'tide_type',
                     'rank_limit', 'time_interval', 'timezone']
    for key in required_keys:
        assert key in PRESET_DEFAULTS, f"Missing default: {key}"


def test_coastline_path_finder():
    """Test that coastline path finder doesn't crash."""
    from tidebedpy.desktop.panels.viewer_panel import COASTLINE_PATH
    # May be empty string if no coastline file found, but should not crash
    assert isinstance(COASTLINE_PATH, str)
