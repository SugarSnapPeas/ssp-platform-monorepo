"""A tiny path router with typed segment captures.

Pure web code: imports neither ``api`` nor ``shared_core``. Control module for
the web lane.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

__all__ = ["Route", "RouteMatch", "Router", "NoRoute", "DuplicateRoute"]

_SEGMENT = re.compile(r"^:(?P<name>[a-z_][a-z0-9_]*)(?::(?P<kind>int|str))?$")


class NoRoute(LookupError):
    """No registered route matched the requested path."""


class DuplicateRoute(ValueError):
    """Two routes were registered with the same method and pattern."""


@dataclass(frozen=True)
class RouteMatch:
    name: str
    params: Dict[str, object]


class Route:
    def __init__(self, method: str, pattern: str, name: str) -> None:
        if not pattern.startswith("/"):
            raise ValueError("pattern must start with '/', got {0!r}".format(pattern))
        self.method = method.strip().upper()
        self.pattern = pattern.rstrip("/") or "/"
        self.name = name
        self.segments = [s for s in self.pattern.split("/") if s]

    def match(self, method: str, path: str) -> Optional[Dict[str, object]]:
        if method.strip().upper() != self.method:
            return None
        parts = [s for s in (path.rstrip("/") or "/").split("/") if s]
        if len(parts) != len(self.segments):
            return None
        params: Dict[str, object] = {}
        for expected, actual in zip(self.segments, parts):
            capture = _SEGMENT.match(expected)
            if capture is None:
                if expected != actual:
                    return None
                continue
            kind = capture.group("kind") or "str"
            if kind == "int":
                if not actual.isdigit():
                    return None
                params[capture.group("name")] = int(actual)
            else:
                params[capture.group("name")] = actual
        return params


class Router:
    """First-registered-wins routing over a small list of routes."""

    def __init__(self) -> None:
        self._routes: List[Route] = []

    def __len__(self) -> int:
        return len(self._routes)

    def add(self, method: str, pattern: str, name: str) -> "Router":
        route = Route(method, pattern, name)
        for existing in self._routes:
            if existing.method == route.method and existing.pattern == route.pattern:
                raise DuplicateRoute("{0} {1} is already registered".format(method, pattern))
        self._routes.append(route)
        return self

    def resolve(self, method: str, path: str) -> RouteMatch:
        for route in self._routes:
            params = route.match(method, path)
            if params is not None:
                return RouteMatch(route.name, params)
        raise NoRoute("no route for {0} {1}".format(method.upper(), path))

    def allowed_methods(self, path: str) -> List[str]:
        """Which methods would match ``path``. Useful for a 405 response."""
        found = {r.method for r in self._routes if r.match(r.method, path) is not None}
        return sorted(found)
