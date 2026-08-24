"""web service — depends on api ONLY (and on shared-core transitively).

See graph.json: ``web.depends_on == ["api"]``.

No re-exports on purpose: an eager ``__init__`` would give every test atom the
same coverage footprint and defeat test impact analysis. Import submodules
directly, e.g. ``from web.app import App``.
"""

__version__ = "2.1.0"
