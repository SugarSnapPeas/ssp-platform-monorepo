"""Import wiring for the worker service.

worker depends on BOTH api and shared-core, directly. See graph.json.
"""

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _SERVICE_ROOT.parents[1]

_IMPORT_PATHS = (
    _SERVICE_ROOT / "src",                                # worker
    _REPO_ROOT / "services" / "api" / "src",              # api        (direct dep)
    _REPO_ROOT / "packages" / "shared-core" / "src",      # shared_core (direct dep)
)

for _path in _IMPORT_PATHS:
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
