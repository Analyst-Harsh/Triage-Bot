from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.guardrail_settings import GuardrailSettings


class Settings(BaseSettings):
    """Secrets and ops-tunable infra values only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_nested_delimiter="__")

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    github_token: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    e2b_api_key: SecretStr | None = None

    # Every tool-call/attempt/budget cap, plus the timeout/retry/E2B-budget
    # fields formerly listed directly here, lives under this one namespace --
    # see `GuardrailSettings`' own docstring for why. Env override example:
    # `GUARDRAILS__RESEARCHER_MAX_TOOL_CALLS=8` (env_nested_delimiter="__" above).
    guardrails: GuardrailSettings = GuardrailSettings()

    e2b_cost_per_second_usd: float = 0.000028
    e2b_restrict_network: bool = True

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
    drafter_file_read_max_chars: int = 16_000
    drafter_test_log_success_max_chars: int = 500
    drafter_test_log_failure_max_chars: int = 3_000

    # Postgres+pgvector connection string, shared by the episodic memory
    # store, the production (Postgres) checkpointer, and the triage_runs
    # tracking table -- one Postgres instance, one connection string.
    # Unset by default; every consumer degrades gracefully (episodic memory
    # to NullEpisodicMemoryStore) except the API (api/app.py), which
    # requires it -- there is no meaningful "off" state for checkpointing.
    database_url: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    episodic_memory_top_k: int = 3
    # `EpisodicMemoryStore.find_similar` searches this prefix across every
    # repo's sub-namespace, so retrieval stays cross-repo (a similar issue in
    # another repo is still a useful signal); `save_episode` writes one level
    # deeper, namespaced per repo underneath it.
    episodic_memory_namespace_prefix: tuple[str, ...] = ("episodes",)

    # Langfuse tracing (observability/tracing.py). Unset by default -- same
    # optional-feature pattern as episodic memory: every trace-emitting call
    # degrades to a no-op without both keys present, rather than requiring
    # this to run at all.
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # HMAC secret verifying X-Hub-Signature-256 on inbound GitHub webhook
    # deliveries (api/routers/webhooks.py). Unset means the webhook route
    # refuses every request with 503 rather than silently accepting
    # unverifiable ones.
    github_webhook_secret: SecretStr | None = None

    # Static bearer token protecting the operator-facing API routes
    # (api/routers/runs.py) -- not the webhook route, which is
    # authenticated by github_webhook_secret's HMAC instead.
    api_bearer_token: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
