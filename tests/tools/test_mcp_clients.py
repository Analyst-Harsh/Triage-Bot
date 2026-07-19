from langchain_core.tools import tool
from pydantic import SecretStr

from config.settings import Settings
from tools.mcp_clients import (
    build_mcp_connections,
    clamp_tool_output,
    researcher_toolset,
)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "github_token": None,
        "tavily_api_key": None,
        "docmind_mcp_command": None,
        "docmind_mcp_args": [],
        "docmind_mcp_cwd": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # pyright: ignore[reportArgumentType]


def test_build_mcp_connections_omits_github_when_token_unset() -> None:
    connections = build_mcp_connections(make_settings())
    assert "github" not in connections


def test_build_mcp_connections_includes_github_when_token_set() -> None:
    settings = make_settings(github_token=SecretStr("ghp_test"))
    connections = build_mcp_connections(settings)
    github = connections["github"]

    assert github["transport"] == "streamable_http"
    assert github.get("url") == settings.github_mcp_url
    assert github.get("headers") == {"Authorization": "Bearer ghp_test"}


def test_build_mcp_connections_uses_configured_github_mcp_url() -> None:
    settings = make_settings(
        github_token=SecretStr("ghp_test"), github_mcp_url="https://example.test/mcp/"
    )
    connections = build_mcp_connections(settings)

    assert connections["github"].get("url") == "https://example.test/mcp/"


def test_build_mcp_connections_omits_docmind_when_command_unset() -> None:
    connections = build_mcp_connections(make_settings())
    assert "docmind" not in connections


def test_build_mcp_connections_includes_docmind_when_command_set() -> None:
    connections = build_mcp_connections(
        make_settings(docmind_mcp_command="docmind-mcp", docmind_mcp_args=["stdio"])
    )

    docmind = connections["docmind"]
    assert docmind["transport"] == "stdio"
    assert docmind.get("command") == "docmind-mcp"
    assert docmind.get("args") == ["stdio"]


@tool
def _echo(text: str) -> str:
    """Echo the input."""
    return text


@tool
def _search_code(query: str) -> str:
    """Search the codebase."""
    return query


async def test_clamp_tool_output_passes_through_short_output() -> None:
    clamped = clamp_tool_output(_echo, max_chars=100)

    result = await clamped.ainvoke({"text": "short"})
    assert result == "short"


async def test_clamp_tool_output_truncates_long_output() -> None:
    clamped = clamp_tool_output(_echo, max_chars=10)

    result = await clamped.ainvoke({"text": "x" * 100})
    assert result.startswith("x" * 10)
    assert "truncated" in result


async def test_clamp_tool_output_preserves_name_and_description() -> None:
    clamped = clamp_tool_output(_search_code)

    assert clamped.name == "_search_code"
    assert clamped.description == "Search the codebase."


async def test_researcher_toolset_yields_empty_list_with_no_credentials() -> None:
    async with researcher_toolset(make_settings()) as tools:
        assert tools == []


async def test_researcher_toolset_includes_tavily_when_configured() -> None:
    async with researcher_toolset(make_settings(tavily_api_key=SecretStr("tvly-test"))) as tools:
        assert len(tools) == 1
        assert tools[0].name == "tavily_search"
