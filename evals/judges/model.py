from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import Settings
from llm.config import LLMEndpointConfig
from llm.factory import create_chat_model

JUDGE_LLM_CONFIG = LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0)


def judge_chat_model(settings: Settings) -> BaseChatModel:
    """The one LLM every eval judge in this package grades with -- reuses
    `llm.factory.create_chat_model`, the exact same primitive every graph
    node's LLM call goes through, so the judge gets the same timeout/retry/
    API-key-via-`Settings` guarantees for free."""
    return create_chat_model(JUDGE_LLM_CONFIG, settings)
