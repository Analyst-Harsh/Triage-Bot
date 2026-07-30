"""FastAPI dependencies shared across routers: bearer-token auth for the
operator-facing routes (api/routers/runs.py), HMAC signature verification
for the webhook route (api/routers/webhooks.py -- authenticated by the
signature instead, never bearer-protected), and the `TriageRunService`
lookup every route handler needs."""

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from config.settings import Settings, get_settings
from services.triage_run_service import TriageRunService

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_bearer_token(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if settings.api_bearer_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "API bearer token is not configured"
        )
    expected = f"Bearer {settings.api_bearer_token.get_secret_value()}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing bearer token")


async def verify_github_webhook_signature(request: Request, settings: SettingsDep) -> bytes:
    """Reads and returns the raw body -- HMAC must be computed over exactly
    the bytes GitHub sent, before any JSON parsing."""
    if settings.github_webhook_secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook secret is not configured")
    content_length = request.headers.get("content-length")

    if (
        content_length is not None
        and content_length.isdigit()
        and int(content_length) > settings.guardrails.max_webhook_body_bytes
    ):
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "payload too large")
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if signature is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-Hub-Signature-256 header")
    expected = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.get_secret_value().encode(), body, hashlib.sha256
        ).hexdigest()
    )
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "signature mismatch")
    return body


def get_run_service(request: Request) -> TriageRunService:
    return request.app.state.run_service


RunServiceDep = Annotated[TriageRunService, Depends(get_run_service)]
