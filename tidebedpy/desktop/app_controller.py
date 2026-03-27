"""TideBedPy Desktop — Signal Hub for inter-panel communication."""

from PySide6.QtCore import QObject, Signal


class AppController(QObject):
    """Central signal hub — all communication between panels and services."""

    # ── Navigation ──
    navigate_correction = Signal()
    navigate_tools = Signal()

    # ── Correction workflow ──
    correction_started = Signal()
    correction_progress = Signal(int, int)      # current, total
    correction_log = Signal(str, str)            # message, tag
    correction_status = Signal(str)              # status text
    correction_finished = Signal(bool, str)      # success, message

    # ── API workflow ──
    api_progress = Signal(str)
    api_finished = Signal(list)                  # list of results
    api_error = Signal(str)

    # ── Station select ──
    station_select_requested = Signal(list, list)  # nearby_stations, nav_points
    station_select_done = Signal(list)             # selected stations

    # ── Toast ──
    toast_requested = Signal(str, str)             # message, level

    # ── Settings changed ──
    settings_loaded = Signal(dict)                 # settings dict from preset
