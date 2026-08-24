"""Aggregate reporting over money values.

Imports ``shared_core`` but NOT ``api`` — the worker lane's example of a
direct shared-core edge that does not pass through the api service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from shared_core.ids import slugify
from shared_core.money import Money, total

__all__ = ["Bucket", "bucket_by", "top_n", "running_total"]


@dataclass(frozen=True)
class Bucket:
    key: str
    count: int
    amount: Money

    @property
    def slug(self) -> str:
        return slugify(self.key)


def bucket_by(rows: Iterable[Tuple[str, Money]], currency: str) -> List[Bucket]:
    """Group ``(key, amount)`` rows, returned in descending amount order.

    Ties are broken alphabetically by key so the output is deterministic.
    """
    counts: Dict[str, int] = {}
    sums: Dict[str, Money] = {}
    for key, amount in rows:
        if amount.currency != currency:
            raise ValueError(
                "row {0!r} is {1}, expected {2}".format(key, amount.currency, currency)
            )
        counts[key] = counts.get(key, 0) + 1
        sums[key] = sums.get(key, Money.zero(currency)) + amount
    buckets = [Bucket(k, counts[k], sums[k]) for k in sums]
    buckets.sort(key=lambda b: (-b.amount.as_minor_units(), b.key))
    return buckets


def top_n(buckets: Sequence[Bucket], n: int, currency: str) -> Tuple[List[Bucket], Money]:
    """Return the first ``n`` buckets plus the summed remainder."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an int")
    if n < 0:
        raise ValueError("n must not be negative")
    head = list(buckets[:n])
    rest = total([b.amount for b in buckets[n:]], currency)
    return head, rest


def running_total(amounts: Sequence[Money], currency: str) -> List[Money]:
    """Cumulative sums; the last element equals the grand total."""
    out: List[Money] = []
    acc = Money.zero(currency)
    for amount in amounts:
        acc = acc + amount
        out.append(acc)
    return out
