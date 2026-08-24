"""shared-core — the single shared node in the ssp-platform-monorepo DAG.

Every service in this monorepo depends on this package, directly or
transitively. See ``graph.json`` at the repo root.

This module deliberately re-exports NOTHING. Importing submodules here would
make ``import shared_core.money`` also load ``ids``, ``retry`` and
``validation``, so every test atom would record a coverage edge to every file
in the package and test impact analysis would select the whole suite for any
change. ``circleci testsuite doctor`` fails this with "Every test atom
impacted the same files." Import the submodule you need:

    from shared_core.money import Money
"""

__version__ = "0.3.0"
