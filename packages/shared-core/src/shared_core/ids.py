"""Deterministic identifier and slug helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional

__all__ = ["OrderId", "slugify", "short_hash", "new_order_id", "parse_order_id"]

_ORDER_ID = re.compile(r"^(?P<prefix>[A-Z]{2,5})-(?P<day>\d{8})-(?P<seq>\d{6})$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class OrderId:
    prefix: str
    day: date
    sequence: int

    def render(self) -> str:
        return "{0}-{1}-{2:06d}".format(
            self.prefix, self.day.strftime("%Y%m%d"), self.sequence
        )

    def __str__(self) -> str:
        return self.render()


def slugify(text: str, max_length: int = 60) -> str:
    """Lower-case, ASCII-fold and hyphenate ``text``.

    >>> slugify("  Crème Brûlée  Tart! ")
    'creme-brulee-tart'
    """
    if not isinstance(text, str):
        raise TypeError("slugify() expects a string")
    if max_length < 1:
        raise ValueError("max_length must be >= 1")
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    hyphenated = _NON_ALNUM.sub("-", ascii_only.lower()).strip("-")
    if len(hyphenated) <= max_length:
        return hyphenated
    clipped = hyphenated[:max_length].rstrip("-")
    return clipped


def short_hash(text: str, length: int = 8) -> str:
    """A stable, short, lower-case hex digest of ``text``."""
    if not isinstance(text, str):
        raise TypeError("short_hash() expects a string")
    if not 1 <= length <= 64:
        raise ValueError("length must be between 1 and 64")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:length]


def new_order_id(sequence: int, prefix: str = "ORD", day: Optional[date] = None) -> str:
    """Render a zero-padded, date-stamped order identifier."""
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise TypeError("sequence must be an int")
    if not 0 <= sequence <= 999999:
        raise ValueError("sequence must be between 0 and 999999")
    code = prefix.strip().upper()
    if not re.match(r"^[A-Z]{2,5}$", code):
        raise ValueError("prefix must be 2-5 letters, got {0!r}".format(prefix))
    return OrderId(code, day or date.today(), sequence).render()


def parse_order_id(order_id: str) -> OrderId:
    """Inverse of :func:`new_order_id`."""
    if not isinstance(order_id, str):
        raise TypeError("parse_order_id() expects a string")
    match = _ORDER_ID.match(order_id.strip())
    if match is None:
        raise ValueError("not an order id: {0!r}".format(order_id))
    day_text = match.group("day")
    day = date(int(day_text[0:4]), int(day_text[4:6]), int(day_text[6:8]))
    return OrderId(match.group("prefix"), day, int(match.group("seq")))

# fan-out demo: every service imports shared-core
