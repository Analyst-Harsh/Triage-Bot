import pytest
from pydantic import SecretStr

from config.settings import Settings


def test_database_url_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # A developer's local .env commonly sets DATABASE_URL for manual testing
    # -- this test asserts the field's actual default, so it must not be
    # affected by ambient environment/`.env` state either way.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # `_env_file` is a real, runtime-supported pydantic-settings BaseSettings
    # kwarg (confirmed via `inspect.signature`) that isn't reflected in the
    # subclass's synthesized `__init__` stub pyright sees.
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.database_url is None


def test_database_url_settable() -> None:
    fake_url = "postgresql://user:pass@localhost:5432/db"  # pragma: allowlist secret
    settings = Settings(database_url=SecretStr(fake_url))
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == fake_url


def test_github_webhook_secret_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.github_webhook_secret is None


def test_api_bearer_token_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_bearer_token is None
