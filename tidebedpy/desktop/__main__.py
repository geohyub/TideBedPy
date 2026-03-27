"""python -m tidebedpy.desktop"""

import sys
import os

# Ensure geoview_pyside6 is importable
_shared = os.path.join(os.path.dirname(__file__), "..", "..", "..", "_shared")
if os.path.isdir(_shared) and _shared not in sys.path:
    sys.path.insert(0, os.path.abspath(_shared))

# Ensure tidebedpy package root is on path
_pkg_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _pkg_root not in sys.path:
    sys.path.insert(0, os.path.abspath(_pkg_root))

from tidebedpy.desktop.main import TideBedApp

if __name__ == "__main__":
    TideBedApp.run()
