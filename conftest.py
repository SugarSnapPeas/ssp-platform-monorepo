"""Repo-root pytest wiring: makes ``tools/`` importable by ``tests/``.

This conftest applies ONLY to the repo-root ``tests/`` directory. Each
subpackage (``packages/shared-core``, ``services/*``) pins its own rootdir
with a ``pytest.ini`` and has its own conftest, so running
``circleci testsuite`` from a subpackage never picks this file up.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_TOOLS = str(_REPO_ROOT / "tools")

if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
