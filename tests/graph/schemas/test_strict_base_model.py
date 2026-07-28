import pytest
from pydantic import ValidationError

from graph.schemas.base import StrictBaseModel


class _Sample(StrictBaseModel):
    value: str


def test_accepts_declared_fields() -> None:
    sample = _Sample(value="ok")
    assert sample.value == "ok"


def test_rejects_unexpected_field() -> None:
    with pytest.raises(ValidationError):
        _Sample.model_validate({"value": "ok", "unexpected_field": "surprise"})
