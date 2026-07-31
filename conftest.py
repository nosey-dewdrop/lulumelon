"""Make the repo importable as the `lulumelon` package when pytest runs here.

Pytest puts the directory containing a test file on `sys.path`, not the project
root, so `import lulumelon` fails on a checkout that has not been installed.
The alternative is requiring `pip install -e .` before the suite can run at
all, which turns a fresh clone into a setup problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
