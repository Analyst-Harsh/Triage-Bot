"""Tests for `observability.tracing`: Langfuse client setup, deterministic
trace IDs, and the no-op degrade path when Langfuse isn't configured (same
contract as `utils/episodic_memory_store.py`'s `NullEpisodicMemoryStore`).

The actual span-enrichment call sites (`TriageNode.__call__`,
`AgentSubgraph.assemble_node`) are proven in
tests/graph/nodes/test_base.py and test_agent_subgraph.py, alongside the
code they cover, per this repo's 1:1 test-mirrors-source convention, rather
than duplicated here.
"""

from collections.abc import Generator
from typing import Any, ClassVar

import pytest
from pydantic import SecretStr

from config.settings import Settings
from observability import tracing


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "langfuse_host": "https://cloud.langfuse.com",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture(autouse=True)
def reset_tracing_state() -> Generator[None]:
    """`ensure_langfuse_client` is deliberately idempotent for production use
    -- that guard would make every test after the first a no-op, so force a
    fresh unconfigured state per test, same pattern as
    tests/observability/test_logging_config.py's `reset_logging_state`."""
    tracing._configured = False  # pyright: ignore[reportPrivateUsage]
    yield
    tracing._configured = False  # pyright: ignore[reportPrivateUsage]


class _FakeLangfuse:
    """Captures constructor kwargs so a test can assert on exactly what
    `ensure_langfuse_client` passed through -- never a real client, no
    network calls."""

    instances: ClassVar[list[_FakeLangfuse]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _FakeLangfuse.instances.append(self)


@pytest.fixture(autouse=True)
def reset_fake_langfuse_instances() -> None:
    _FakeLangfuse.instances = []


def test_ensure_langfuse_client_noops_without_both_keys() -> None:
    tracing.ensure_langfuse_client(_settings())

    assert tracing._configured is False  # pyright: ignore[reportPrivateUsage]


def test_ensure_langfuse_client_noops_with_only_one_key() -> None:
    tracing.ensure_langfuse_client(_settings(langfuse_public_key=SecretStr("pk-test")))

    assert tracing._configured is False  # pyright: ignore[reportPrivateUsage]


def test_ensure_langfuse_client_constructs_client_with_unwrapped_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)
    settings = _settings(
        langfuse_public_key=SecretStr("pk-test"),
        langfuse_secret_key=SecretStr("sk-test"),
        langfuse_host="http://localhost:3000",
    )

    tracing.ensure_langfuse_client(settings)

    assert tracing._configured is True  # pyright: ignore[reportPrivateUsage]
    assert len(_FakeLangfuse.instances) == 1
    kwargs = _FakeLangfuse.instances[0].kwargs
    assert kwargs["public_key"] == "pk-test"
    assert kwargs["secret_key"] == "sk-test"  # pragma: allowlist secret -- fake test fixture
    assert kwargs["base_url"] == "http://localhost:3000"
    # Never the SecretStr object itself -- only its resolved value, at the
    # one boundary that needs it (docs/agent/security.md).
    assert not isinstance(kwargs["public_key"], SecretStr)
    assert not isinstance(kwargs["secret_key"], SecretStr)


def test_ensure_langfuse_client_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)
    settings = _settings(
        langfuse_public_key=SecretStr("pk-test"), langfuse_secret_key=SecretStr("sk-test")
    )

    tracing.ensure_langfuse_client(settings)
    tracing.ensure_langfuse_client(settings)

    assert len(_FakeLangfuse.instances) == 1


def test_create_trace_id_is_deterministic_for_the_same_seed() -> None:
    assert tracing.create_trace_id("octo/repo#42") == tracing.create_trace_id("octo/repo#42")


def test_create_trace_id_differs_across_seeds() -> None:
    assert tracing.create_trace_id("octo/repo#42") != tracing.create_trace_id("octo/repo#43")


class _FakeCallbackHandler:
    """Captures constructor kwargs so a test can assert on exactly what
    `build_callback_handler` passed through -- never a real handler."""

    instances: ClassVar[list[_FakeCallbackHandler]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs: dict[str, Any] = kwargs
        _FakeCallbackHandler.instances.append(self)


@pytest.fixture(autouse=True)
def reset_fake_callback_handler_instances() -> None:
    _FakeCallbackHandler.instances = []


def test_build_callback_handler_returns_none_when_unconfigured() -> None:
    assert tracing.build_callback_handler() is None
    assert tracing.build_callback_handler(trace_id="deadbeef" * 4) is None


def test_build_callback_handler_omits_trace_context_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The no-`trace_id` default lets the handler's own root chain span fall
    through to ambient OTel nesting (under `root_span`) instead of becoming a
    second, sibling root-level span in the same trace -- see
    `build_callback_handler`'s docstring for the regression this guards."""
    monkeypatch.setattr(tracing, "CallbackHandler", _FakeCallbackHandler)
    tracing._configured = True  # pyright: ignore[reportPrivateUsage]

    tracing.build_callback_handler()

    assert len(_FakeCallbackHandler.instances) == 1
    assert _FakeCallbackHandler.instances[0].kwargs == {"trace_context": None}


def test_build_callback_handler_binds_trace_context_when_trace_id_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """For the future no-ambient-`root_span` case (see the docstring) --
    an explicit `trace_id` does get threaded into `trace_context`."""
    monkeypatch.setattr(tracing, "CallbackHandler", _FakeCallbackHandler)
    tracing._configured = True  # pyright: ignore[reportPrivateUsage]

    tracing.build_callback_handler(trace_id="deadbeef" * 4)

    assert len(_FakeCallbackHandler.instances) == 1
    kwargs = _FakeCallbackHandler.instances[0].kwargs
    assert kwargs == {"trace_context": {"trace_id": "deadbeef" * 4}}


async def test_node_span_yields_none_when_unconfigured() -> None:
    async with tracing.node_span("planner") as span:
        assert span is None


async def test_root_span_is_a_noop_when_unconfigured() -> None:
    async with tracing.root_span(
        name="triage_run", trace_id="deadbeef" * 4, session_id="octo/repo#42", metadata={}
    ):
        pass
