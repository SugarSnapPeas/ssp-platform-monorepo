"""Import wiring for the api service.

api depends on shared-core only. See graph.json.
"""

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _SERVICE_ROOT.parents[1]

# Order matters only for readability; each entry is a distinct namespace.
_IMPORT_PATHS = (
    _SERVICE_ROOT / "src",                                # api
    _REPO_ROOT / "packages" / "shared-core" / "src",      # shared_core
)

for _path in _IMPORT_PATHS:
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
