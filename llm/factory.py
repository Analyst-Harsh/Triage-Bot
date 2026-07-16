from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from config.settings import Settings
from llm.config import LLMEndpointConfig


def create_chat_model(config: LLMEndpointConfig, settings: Settings) -> BaseChatModel:
    """Explicit provider switch rather than `init_chat_model`'s string-inferred
    provider — matches this codebase's existing preference for discriminated
    unions over magic inference (see `graph/schemas/actions.py`)."""
    # Both classes' real __init__ is `Serializable.__init__(*args, **kwargs)`
    # (fully dynamic); pyright instead type-checks calls against a
    # pydantic-field-synthesized overload that doesn't line up with the
    # documented kwargs used here (verified working at runtime against the
    # installed langchain-anthropic/langchain-openai). Same category as the
    # `reportMissingTypeStubs` exclusion already noted in pyproject.toml —
    # third-party stub incompleteness, not a bug in this call.
    match config.provider:
        case "anthropic":
            return ChatAnthropic(
                model=config.model,  # pyright: ignore[reportCallIssue]
                temperature=config.temperature,
                api_key=settings.anthropic_api_key,
                timeout=settings.llm_request_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        case "openai":
            return ChatOpenAI(
                model=config.model,  # pyright: ignore[reportCallIssue]
                temperature=config.temperature,
                api_key=settings.openai_api_key,
                timeout=settings.llm_request_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
