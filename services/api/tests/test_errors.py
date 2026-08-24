"""Pure api tests.

IMPORTANT for the demo: this file imports ``api.errors`` and NOTHING from
shared-core. It is the control case — a change confined to
``packages/shared-core/**`` must not select this test atom.
"""

import pytest

from api.errors import (
    ApiError,
    BadRequest,
    Conflict,
    NotFound,
    UnprocessableEntity,
    error_payload,
    status_text,
)


@pytest.mark.parametrize(
    "cls,status,code",
    [
        (BadRequest, 400, "bad_request"),
        (NotFound, 404, "not_found"),
        (Conflict, 409, "conflict"),
        (UnprocessableEntity, 422, "unprocessable_entity"),
        (ApiError, 500, "internal_error"),
    ],
)
def test_error_classes_carry_status_and_code(cls, status, code):
    err = cls("boom")
    assert err.status == status
    assert err.code == code
    assert str(err) == "boom"
    assert isinstance(err, ApiError)


def test_status_text():
    assert status_text(404) == "Not Found"
    assert status_text(418) == "Unknown"


def test_error_payload_shape():
    payload = error_payload(NotFound("gone"))
    assert payload == {
        "error": {
            "status": 404,
            "reason": "Not Found",
            "code": "not_found",
            "message": "gone",
        }
    }


def test_error_payload_includes_detail_when_present():
    payload = error_payload(Conflict("dupe", {"sku": "SSP-1001"}))
    assert payload["error"]["detail"] == {"sku": "SSP-1001"}


def test_error_payload_rejects_non_api_errors():
    with pytest.raises(TypeError):
        error_payload(ValueError("nope"))


def test_detail_is_copied_not_aliased():
    detail = {"a": 1}
    err = BadRequest("x", detail)
    detail["a"] = 2
    assert err.detail == {"a": 1}


def test_repr_is_useful():
    assert repr(NotFound("gone")) == (
        "NotFound(status=404, code='not_found', message='gone')"
    )
