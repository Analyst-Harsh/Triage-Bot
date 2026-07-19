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
