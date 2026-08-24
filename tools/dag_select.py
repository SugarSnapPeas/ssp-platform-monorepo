#!/usr/bin/env python3
"""Reference implementation of the ``graph.json`` selection algorithm.

This is the executable specification of the schema documented in README.md.
The real selector lives in the ``sugarsnappeas/selector`` orb
(``ssp-ci-platform``); this module exists so that the monorepo can prove, in
its own test suite, that the declared DAG produces the fan-out the demo
depends on. Keep the two in agreement.

CLI::

    python tools/dag_select.py services/api/src/pricing.py
    git diff --name-only origin/main... | python tools/dag_select.py -
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

SCHEMA = "ssp.dag/v1"
DEFAULT_GRAPH = Path(__file__).resolve().parents[1] / "graph.json"


class GraphError(ValueError):
    """The graph file is malformed."""


def _match(path: str, pattern: str) -> bool:
    """``fnmatch``-style glob match where ``*`` does not cross a ``/``.

    ``**`` matches across separators. This mirrors the semantics documented
    in ``graph.json`` under ``selection.direct_match``.
    """
    return _match_parts(path.split("/"), pattern.split("/"))


def _match_parts(path_parts: Sequence[str], pattern_parts: Sequence[str]) -> bool:
    from fnmatch import fnmatchcase

    if not pattern_parts:
        return not path_parts
    head = pattern_parts[0]
    if head == "**":
        rest = pattern_parts[1:]
        if not rest:
            return True  # `**` at the end matches everything below, inclusive
        for i in range(len(path_parts) + 1):
            if _match_parts(path_parts[i:], rest):
                return True
        return False
    if not path_parts:
        return False
    if not fnmatchcase(path_parts[0], head):
        return False
    return _match_parts(path_parts[1:], pattern_parts[1:])


class Graph:
    def __init__(self, data: dict) -> None:
        if data.get("schema") != SCHEMA:
            raise GraphError(
                "expected schema {0!r}, got {1!r}".format(SCHEMA, data.get("schema"))
            )
        self.data = data
        self.full_run_paths: List[str] = list(data.get("full_run_paths", []))
        self.nodes: Dict[str, dict] = {}
        for node in data.get("nodes", []):
            node_id = node["id"]
            if node_id in self.nodes:
                raise GraphError("duplicate node id {0!r}".format(node_id))
            self.nodes[node_id] = node
        if not self.nodes:
            raise GraphError("graph has no nodes")

        for node_id, node in self.nodes.items():
            for dependency in node.get("depends_on", []):
                if dependency not in self.nodes:
                    raise GraphError(
                        "node {0!r} depends on unknown node {1!r}".format(node_id, dependency)
                    )
        self._check_acyclic()

        # reverse edges: dependency -> the nodes that depend on it
        self.dependents: Dict[str, Set[str]] = {n: set() for n in self.nodes}
        for node_id, node in self.nodes.items():
            for dependency in node.get("depends_on", []):
                self.dependents[dependency].add(node_id)

    @classmethod
    def load(cls, path: Path = DEFAULT_GRAPH) -> "Graph":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def _check_acyclic(self) -> None:
        state: Dict[str, int] = {}

        def visit(node_id: str, stack: List[str]) -> None:
            if state.get(node_id) == 2:
                return
            if state.get(node_id) == 1:
                raise GraphError("cycle: {0}".format(" -> ".join(stack + [node_id])))
            state[node_id] = 1
            for dependency in self.nodes[node_id].get("depends_on", []):
                visit(dependency, stack + [node_id])
            state[node_id] = 2

        for node_id in self.nodes:
            visit(node_id, [])

    # -- selection ------------------------------------------------------

    def node_for(self, path: str) -> List[str]:
        """Every node whose ``paths`` globs match ``path``."""
        return sorted(
            node_id
            for node_id, node in self.nodes.items()
            if any(_match(path, glob) for glob in node.get("paths", []))
        )

    def is_full_run(self, path: str) -> bool:
        return any(_match(path, glob) for glob in self.full_run_paths)

    def transitive_dependencies(self, node_id: str) -> Set[str]:
        out: Set[str] = set()
        pending = list(self.nodes[node_id].get("depends_on", []))
        while pending:
            current = pending.pop()
            if current in out:
                continue
            out.add(current)
            pending.extend(self.nodes[current].get("depends_on", []))
        return out

    def select(self, changed_paths: Iterable[str]) -> dict:
        """Return the selection decision for ``changed_paths``.

        The returned dict is the shape the selector job stores as evidence.
        """
        changed = sorted(set(changed_paths))
        full_run_triggers = [p for p in changed if self.is_full_run(p)]
        directly_changed: Dict[str, List[str]] = {}
        unattributed: List[str] = []

        for path in changed:
            if self.is_full_run(path):
                continue
            matched = self.node_for(path)
            if not matched:
                unattributed.append(path)
            for node_id in matched:
                directly_changed.setdefault(node_id, []).append(path)

        if full_run_triggers:
            selected = set(self.nodes)
        else:
            selected = set(directly_changed)
            pending = list(selected)
            while pending:
                current = pending.pop()
                for dependent in self.dependents[current]:
                    if dependent not in selected:
                        selected.add(dependent)
                        pending.append(dependent)

        reasons: Dict[str, str] = {}
        for node_id in sorted(selected):
            if full_run_triggers:
                reasons[node_id] = "full-run: {0}".format(", ".join(full_run_triggers))
            elif node_id in directly_changed:
                reasons[node_id] = "changed: {0}".format(", ".join(directly_changed[node_id]))
            else:
                upstream = sorted(self.transitive_dependencies(node_id) & set(directly_changed))
                reasons[node_id] = "depends on {0}".format(", ".join(upstream))

        return {
            "changed_paths": changed,
            "full_run": bool(full_run_triggers),
            "full_run_triggers": full_run_triggers,
            "directly_changed": sorted(directly_changed),
            "unattributed_paths": unattributed,
            "selected": sorted(selected),
            "reasons": reasons,
        }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths", nargs="*", help="changed file paths, or '-' to read them from stdin"
    )
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH), help="path to graph.json")
    parser.add_argument("--json", action="store_true", help="emit the full decision as JSON")
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if not paths or paths == ["-"]:
        paths = [line.strip() for line in sys.stdin if line.strip()]

    decision = Graph.load(Path(args.graph)).select(paths)
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        for node_id in decision["selected"]:
            print("{0}\t{1}".format(node_id, decision["reasons"][node_id]))
        for path in decision["unattributed_paths"]:
            print("(unattributed)\t{0}".format(path), file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
