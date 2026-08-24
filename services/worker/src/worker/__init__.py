"""worker service — depends on BOTH shared-core and api. See graph.json.

No re-exports on purpose: an eager ``__init__`` would give every test atom the
same coverage footprint and defeat test impact analysis. Import submodules
directly, e.g. ``from worker.queue import TaskQueue``.
"""

__version__ = "0.9.2"
