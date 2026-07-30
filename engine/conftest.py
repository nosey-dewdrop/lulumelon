"""Make the `mirror` package importable when pytest runs from the repo root.

The rabadon gate invokes pytest from ~/damla_projects_2026, where `mirror` is a
plain directory rather than something on sys.path. Without this shim the suite
collects and then fails on import, which looks like a broken test rather than a
path problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
