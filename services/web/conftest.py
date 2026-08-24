"""Import wiring for the web service.

web depends on api directly, and on shared-core only transitively (api pulls
it in at import time). shared-core is therefore on sys.path here even though
no module under ``services/web/src`` imports it — see graph.json, where
``web.depends_on == ["api"]``.
"""

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _SERVICE_ROOT.parents[1]

_IMPORT_PATHS = (
    _SERVICE_ROOT / "src",                                # web
    _REPO_ROOT / "services" / "api" / "src",              # api         (direct dep)
    _REPO_ROOT / "packages" / "shared-core" / "src",      # shared_core (transitive)
)

for _path in _IMPORT_PATHS:
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
