"""Put this package's ``src/`` on ``sys.path``.

The monorepo deliberately avoids a packaging tool (see CONVENTIONS.md: the
demo is about CI, not packaging). Imports are wired with a per-package
``conftest.py`` instead, which keeps every imported module a real file inside
the repository — a hard requirement for test impact analysis, because coverage
edges are recorded against repository paths.
"""

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent

for _path in (_PACKAGE_ROOT / "src",):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
