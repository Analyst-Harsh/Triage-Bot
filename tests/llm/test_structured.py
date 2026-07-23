from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from llm.structured import call_structured
from tests.graph.nodes.conftest import make_fake_chat_model


class _Answer(BaseModel):
    value: str


async def test_call_structured_returns_parsed_result_from_primary() -> None:
    primary = make_fake_chat_model(model_name="primary-model", parsed_result=_Answer(value="ok"))
    fallback = make_fake_chat_model(model_name="fallback-model")

    result = await call_structured(primary, fallback, [], _Answer)

    assert result.parsed == _Answer(value="ok")
    assert result.models_invoked == ["primary-model"]


async def test_call_structured_falls_back_on_primary_failure() -> None:
    primary = make_fake_chat_model(model_name="primary-model", raise_on_generate=True)
    fallback = make_fake_chat_model(
        model_name="fallback-model", parsed_result=_Answer(value="from fallback")
    )

    result = await call_structured(primary, fallback, [], _Answer)

    assert result.parsed == _Answer(value="from fallback")
    assert result.models_invoked == ["fallback-model"]


async def test_call_structured_retries_primary_on_transient_parse_failure() -> None:
    """A validation/parsing failure (e.g. a required field missing from the
    model's tool-call args) is often just sampling variance -- the same
    prompt resent to the same model can succeed on the next attempt. This
    should recover in place, never touching the fallback model at all."""
    primary = make_fake_chat_model(
        model_name="primary-model", parsed_result=_Answer(value="ok"), fail_parse_times=1
    )
    fallback = make_fake_chat_model(model_name="fallback-model")

    result = await call_structured(primary, fallback, [], _Answer)

    assert result.parsed == _Answer(value="ok")
    assert result.models_invoked == ["primary-model"]
    assert primary.parse_attempts == 2


async def test_call_structured_falls_back_after_primary_exhausts_retries() -> None:
    """Once primary fails on every one of its own attempts, only then does
    the fallback model get tried. `primary-model` still appears in
    `models_invoked`: `_generate` succeeded every time (only parsing failed),
    so its usage/cost was genuinely incurred and must still be counted."""
    primary = make_fake_chat_model(model_name="primary-model", fail_parse=True)
    fallback = make_fake_chat_model(
        model_name="fallback-model", parsed_result=_Answer(value="from fallback")
    )

    result = await call_structured(primary, fallback, [], _Answer)

    assert result.parsed == _Answer(value="from fallback")
    assert result.models_invoked == ["primary-model", "fallback-model"]
    # 2 attempts against primary before call_structured moves on to fallback
    # -- matches llm/structured.py's _STRUCTURED_OUTPUT_MAX_ATTEMPTS.
    assert len(primary.received_messages) == 2


async def test_call_structured_repairs_after_a_validation_error() -> None:
    """A genuine pydantic.ValidationError (not just any exception) should get
    the validation error fed back to the model as a corrective follow-up
    message before the next attempt."""
    primary = make_fake_chat_model(
        model_name="primary-model",
        parsed_result=_Answer(value="ok"),
        raise_validation_error_times=1,
    )
    fallback = make_fake_chat_model(model_name="fallback-model")

    result = await call_structured(primary, fallback, [], _Answer)

    assert result.parsed == _Answer(value="ok")
    assert len(primary.received_messages) == 2
    second_call_messages = primary.received_messages[1]
    corrective_message = second_call_messages[-1]
    assert isinstance(corrective_message, HumanMessage)
    assert "did not match the required schema" in corrective_message.content
