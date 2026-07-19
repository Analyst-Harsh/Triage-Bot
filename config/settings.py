from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets and ops-tunable infra values only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    github_token: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    # GitHub's officially-hosted remote MCP server (streamable-HTTP transport).
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"

    # DocMind-MCP: a sibling project whose exact launch command isn't
    # finalized yet. All optional/unset by default — the Researcher must
    # degrade gracefully (tool omitted, gap recorded) rather than require it.
    docmind_mcp_command: str | None = None
    docmind_mcp_args: list[str] = []
    docmind_mcp_cwd: str | None = None

    # Bounds context/cost blowup from a single huge file or webpage returned
    # by an untrusted research tool call.
    researcher_tool_output_max_chars: int = 8_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
