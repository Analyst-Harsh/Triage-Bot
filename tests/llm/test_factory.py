from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from config.settings import Settings
from llm.config import LLMEndpointConfig
from llm.factory import create_chat_model


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "anthropic_api_key": SecretStr("sk-ant-test"),
        "openai_api_key": SecretStr("sk-oai-test"),
        "llm_request_timeout_seconds": 45.0,
        "llm_max_retries": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # pyright: ignore[reportArgumentType]


def test_create_chat_model_anthropic() -> None:
    config = LLMEndpointConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    model = create_chat_model(config, _settings())

    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-haiku-4-5-20251001"
    assert model.default_request_timeout == 45.0
    assert model.max_retries == 3


def test_create_chat_model_openai() -> None:
    config = LLMEndpointConfig(provider="openai", model="gpt-4o-mini")
    model = create_chat_model(config, _settings())

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o-mini"
    assert model.request_timeout == 45.0
    assert model.max_retries == 3


def test_create_chat_model_uses_configured_temperature() -> None:
    config = LLMEndpointConfig(provider="openai", model="gpt-4o-mini", temperature=0.7)
    model = create_chat_model(config, _settings())

    assert isinstance(model, ChatOpenAI)
    assert model.temperature == 0.7
