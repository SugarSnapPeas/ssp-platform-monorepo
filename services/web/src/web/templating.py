"""A deliberately small ``{{ name }}`` template renderer.

Pure web code: no ``api``, no ``shared_core``.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Mapping, Sequence

__all__ = ["MissingVariable", "render", "render_rows", "escape_html", "variables_in"]

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

_ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#39;"),
)


class MissingVariable(KeyError):
    """A placeholder had no matching key in the context."""


def escape_html(value: object) -> str:
    """HTML-escape ``value`` after stringifying it."""
    text = str(value)
    for raw, replacement in _ESCAPES:
        text = text.replace(raw, replacement)
    return text


def variables_in(template: str) -> List[str]:
    """Placeholder names in first-appearance order, de-duplicated."""
    seen: List[str] = []
    for name in _PLACEHOLDER.findall(template):
        if name not in seen:
            seen.append(name)
    return seen


def render(template: str, context: Mapping[str, object], autoescape: bool = True) -> str:
    """Substitute ``{{ name }}`` placeholders from ``context``."""
    if not isinstance(template, str):
        raise TypeError("template must be a string")
    missing = [name for name in variables_in(template) if name not in context]
    if missing:
        raise MissingVariable("missing template variables: {0}".format(", ".join(missing)))

    def substitute(match: "re.Match") -> str:
        value = context[match.group(1)]
        return escape_html(value) if autoescape else str(value)

    return _PLACEHOLDER.sub(substitute, template)


def render_rows(template: str, rows: Sequence[Mapping[str, object]], separator: str = "\n") -> str:
    """Render ``template`` once per row and join the results."""
    return separator.join(render(template, row) for row in rows)

# narrow selection demo: only atoms covering templating should run

# fresh run
