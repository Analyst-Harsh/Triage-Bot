"""Thin, explicitly-typed wrappers around `TestClient.get`/`.post`.

Starlette's `TestClient` (which every router test in this package uses)
has known gaps in its own type stubs under strict pyright -- its
`get`/`post` signatures resolve to `Unknown` parameter/return types
(confirmed against a minimal reproduction, not assumed), which would
otherwise cascade `reportUnknownVariableType`/`reportUnknownMemberType`
into every call site. Confining the acknowledgment of that gap to these
two functions keeps the actual test bodies fully typed against a real
`httpx.Response`.
"""

from typing import Any

import httpx
from fastapi.testclient import TestClient


def get(client: TestClient, url: str, **kwargs: Any) -> httpx.Response:
    return client.get(url, **kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]


def post(client: TestClient, url: str, **kwargs: Any) -> httpx.Response:
    return client.post(url, **kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
