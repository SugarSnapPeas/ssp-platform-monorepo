"""Small, dependency-free validation helpers shared by every service."""

from __future__ import annotations

import re
from typing import Callable, Iterable, List, Optional, Sequence

__all__ = [
    "ValidationError",
    "require",
    "ensure_range",
    "validate_sku",
    "validate_email",
    "validate_quantity",
    "collect_errors",
]

#: ``ABC-1234`` with an optional ``-A1`` variant suffix.
SKU_PATTERN = re.compile(r"^[A-Z]{3}-\d{4}(-[A-Z0-9]{2})?$")

_EMAIL_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")
_EMAIL_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")

MAX_QUANTITY = 999


class ValidationError(ValueError):
    """A single field-level validation failure."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__("{0}: {1} ({2})".format(field, message, code))
        self.field = field
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"field": self.field, "code": self.code, "message": self.message}


def require(value, field: str):
    """Return ``value`` unless it is ``None`` or an empty/whitespace string."""
    if value is None:
        raise ValidationError(field, "missing", "value is required")
    if isinstance(value, str) and not value.strip():
        raise ValidationError(field, "blank", "value must not be blank")
    return value


def ensure_range(
    value,
    field: str,
    minimum=None,
    maximum=None,
):
    """Return ``value`` if it falls within the inclusive bounds given."""
    if minimum is not None and value < minimum:
        raise ValidationError(
            field, "below_minimum", "must be >= {0}, got {1}".format(minimum, value)
        )
    if maximum is not None and value > maximum:
        raise ValidationError(
            field, "above_maximum", "must be <= {0}, got {1}".format(maximum, value)
        )
    return value


def validate_sku(sku: str, field: str = "sku") -> str:
    """Normalise and validate a stock-keeping unit.

    Accepts lower case and surrounding whitespace, returns the canonical
    upper-case form.
    """
    require(sku, field)
    if not isinstance(sku, str):
        raise ValidationError(field, "type", "sku must be a string")
    candidate = sku.strip().upper()
    if not SKU_PATTERN.match(candidate):
        raise ValidationError(
            field, "format", "expected AAA-0000 or AAA-0000-XX, got {0!r}".format(sku)
        )
    return candidate


def validate_email(address: str, field: str = "email") -> str:
    """Validate an email address strictly enough to be interesting to test."""
    require(address, field)
    if not isinstance(address, str):
        raise ValidationError(field, "type", "email must be a string")
    candidate = address.strip()
    if any(ch.isspace() for ch in candidate):
        raise ValidationError(field, "format", "email must not contain whitespace")
    if candidate.count("@") != 1:
        raise ValidationError(field, "format", "email must contain exactly one '@'")
    local, _, domain = candidate.partition("@")
    if not local or len(local) > 64:
        raise ValidationError(field, "format", "local part must be 1-64 characters")
    if not _EMAIL_LOCAL.match(local):
        raise ValidationError(field, "format", "local part has illegal characters")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValidationError(field, "format", "local part has a misplaced dot")
    labels = domain.split(".")
    if len(labels) < 2:
        raise ValidationError(field, "format", "domain must have at least one dot")
    for label in labels:
        if not _EMAIL_LABEL.match(label):
            raise ValidationError(field, "format", "bad domain label {0!r}".format(label))
    tld = labels[-1]
    if len(tld) < 2 or not tld.isalpha():
        raise ValidationError(field, "format", "bad top-level domain {0!r}".format(tld))
    return local + "@" + domain.lower()


def validate_quantity(quantity, field: str = "quantity") -> int:
    """Validate an order line quantity: an int in ``1..999``."""
    require(quantity, field)
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError(field, "type", "quantity must be an int")
    ensure_range(quantity, field, minimum=1, maximum=MAX_QUANTITY)
    return quantity


def collect_errors(checks: Sequence[Callable[[], object]]) -> List[ValidationError]:
    """Run every check, collecting rather than short-circuiting on failure."""
    errors: List[ValidationError] = []
    for check in checks:
        try:
            check()
        except ValidationError as exc:
            errors.append(exc)
    return errors
