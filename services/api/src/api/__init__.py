"""api service — depends on shared-core. Imported in-process by worker and web.

No re-exports on purpose: an eager ``__init__`` would give every test atom the
same coverage footprint and defeat test impact analysis. Import submodules
directly, e.g. ``from api.pricing import quote``.
"""

__version__ = "1.4.0"
