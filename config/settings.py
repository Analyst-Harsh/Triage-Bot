from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets and ops-tunable infra values only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
