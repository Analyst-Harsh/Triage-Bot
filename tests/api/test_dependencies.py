from __future__ import annotations

import hashlib
import hmac
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from api.dependencies import require_bearer_token, verify_github_webhook_signature
from config.settings import Settings


def make_settings(**overrides: Any) -> Settings:
    # `_env_file=None` bypasses a developer's local `.env` -- tests that rely
    # on a field being genuinely unset (the two "unconfigured" tests below)
    # must not be affected by ambient environment/`.env` state either way.
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


async def test_require_bearer_token_raises_503_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    with pytest.raises(HTTPException) as excinfo:
        await require_bearer_token(make_settings(), authorization=None)
    assert excinfo.value.status_code == 503


async def test_require_bearer_token_raises_401_when_missing() -> None:
    settings = make_settings(api_bearer_token=SecretStr("secret"))
    with pytest.raises(HTTPException) as excinfo:
        await require_bearer_token(settings, authorization=None)
    assert excinfo.value.status_code == 401


async def test_require_bearer_token_raises_401_when_wrong() -> None:
    settings = make_settings(api_bearer_token=SecretStr("secret"))
    with pytest.raises(HTTPException) as excinfo:
        await require_bearer_token(settings, authorization="Bearer wrong")
    assert excinfo.value.status_code == 401


async def test_require_bearer_token_passes_when_correct() -> None:
    settings = make_settings(api_bearer_token=SecretStr("secret"))
    await require_bearer_token(settings, authorization="Bearer secret")  # must not raise


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self._body = body
        self.headers = headers

    async def body(self) -> bytes:
        return self._body


async def test_verify_github_webhook_signature_raises_503_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    request = _FakeRequest(b"{}", headers={})
    with pytest.raises(HTTPException) as excinfo:
        await verify_github_webhook_signature(request, make_settings())  # type: ignore[arg-type]
    assert excinfo.value.status_code == 503


async def test_verify_github_webhook_signature_rejects_oversized_body() -> None:
    settings = make_settings(github_webhook_secret=SecretStr("wh-secret"))
    request = _FakeRequest(b"{}", headers={"content-length": str(2 * 1024 * 1024)})
    with pytest.raises(HTTPException) as excinfo:
        await verify_github_webhook_signature(request, settings)  # type: ignore[arg-type]
    assert excinfo.value.status_code == 413


async def test_verify_github_webhook_signature_allows_body_under_cap() -> None:
    settings = make_settings(github_webhook_secret=SecretStr("wh-secret"))
    body = b'{"action": "opened"}'
    signature = "sha256=" + hmac.new(b"wh-secret", body, hashlib.sha256).hexdigest()
    request = _FakeRequest(
        body,
        headers={"content-length": str(len(body)), "X-Hub-Signature-256": signature},
    )

    result = await verify_github_webhook_signature(request, settings)  # type: ignore[arg-type]

    assert result == body


async def test_verify_github_webhook_signature_raises_401_when_header_missing() -> None:
    settings = make_settings(github_webhook_secret=SecretStr("wh-secret"))
    request = _FakeRequest(b"{}", headers={})
    with pytest.raises(HTTPException) as excinfo:
        await verify_github_webhook_signature(request, settings)  # type: ignore[arg-type]
    assert excinfo.value.status_code == 401


async def test_verify_github_webhook_signature_raises_401_on_mismatch() -> None:
    settings = make_settings(github_webhook_secret=SecretStr("wh-secret"))
    request = _FakeRequest(b"{}", headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    with pytest.raises(HTTPException) as excinfo:
        await verify_github_webhook_signature(request, settings)  # type: ignore[arg-type]
    assert excinfo.value.status_code == 401


async def test_verify_github_webhook_signature_returns_body_on_match() -> None:
    settings = make_settings(github_webhook_secret=SecretStr("wh-secret"))
    body = b'{"action": "opened"}'
    signature = "sha256=" + hmac.new(b"wh-secret", body, hashlib.sha256).hexdigest()
    request = _FakeRequest(body, headers={"X-Hub-Signature-256": signature})

    result = await verify_github_webhook_signature(request, settings)  # type: ignore[arg-type]

    assert result == body
