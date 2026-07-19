from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import structlog
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_tavily import TavilySearch

from config.settings import Settings

log = structlog.get_logger(__name__)


def build_mcp_connections(settings: Settings) -> dict[str, Connection]:
    """Servers configured this run — `github` when a token is set, `docmind`
    only when its (still-unfinalized) launch command is configured. Neither
    is required: an unconfigured server is logged and simply absent from the
    returned mapping, not an error — the Researcher degrades gracefully."""
    connections: dict[str, Connection] = {}

    if settings.github_token is not None:
        connections["github"] = {
            "transport": "streamable_http",
            "url": settings.github_mcp_url,
            "headers": {"Authorization": f"Bearer {settings.github_token.get_secret_value()}"},
        }
    else:
        log.warning("researcher_tool_unavailable", tool="github", reason="GITHUB_TOKEN not set")

    if settings.docmind_mcp_command is not None:
        connections["docmind"] = {
            "transport": "stdio",
            "command": settings.docmind_mcp_command,
            "args": settings.docmind_mcp_args,
            "cwd": settings.docmind_mcp_cwd,
        }
    else:
        log.warning(
            "researcher_tool_unavailable",
            tool="docmind",
            reason="DOCMIND_MCP_COMMAND not set",
        )

    return connections


def clamp_tool_output(tool: BaseTool, max_chars: int = 8_000) -> BaseTool:
    """Wraps `tool` so its output is clamped to `max_chars`, with the
    truncation noted inline so the model knows the excerpt is partial.

    Tool outputs are untrusted input — issue text, GitHub comments, and web
    pages are all attacker- or at least author-controlled — so this bounds
    context/cost blowup from a single huge file or webpage. Delegates to the
    original tool's own `ainvoke()` rather than touching its internals, so
    it works uniformly across MCP-provided and directly-constructed tools.

    `max_chars` defaults to a literal here (not `Settings`) so this stays a
    pure, standalone-testable helper; `researcher_toolset` is the one
    production call site and always passes `settings.researcher_tool_output_max_chars`
    explicitly.
    """

    async def _clamped(**kwargs: object) -> str:
        result = await tool.ainvoke(kwargs)
        text = result if isinstance(result, str) else str(result)
        if len(text) <= max_chars:
            return text
        omitted = len(text) - max_chars
        return f"{text[:max_chars]}\n...[truncated, {omitted} more characters]"

    coroutine: Callable[..., Awaitable[str]] = _clamped
    return StructuredTool.from_function(
        coroutine=coroutine,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


@asynccontextmanager
async def researcher_toolset(settings: Settings) -> AsyncGenerator[list[BaseTool]]:
    """Loads the Researcher's tools for the graph's lifetime.

    Opens **persistent** MCP sessions (`client.session()` held open via an
    `AsyncExitStack`, not the ephemeral per-call default) — for the stdio
    DocMind server, the default mode would respawn its process on every
    single tool call. Sessions close on exit, mirroring
    `graph/checkpointer.py`'s `sqlite_checkpointer()` context-manager idiom.

    Each unavailable/failed tool is logged and omitted, never fatal — an
    empty toolset still runs the Researcher (low-confidence, issue-text-only
    findings), which keeps replay/dev usable without any secrets configured.
    """
    connections = build_mcp_connections(settings)
    tools: list[BaseTool] = []

    async with AsyncExitStack() as stack:
        if connections:
            client = MultiServerMCPClient(connections)
            for server_name in connections:
                try:
                    session = await stack.enter_async_context(client.session(server_name))
                    server_tools = await load_mcp_tools(session)
                except Exception:
                    log.warning("researcher_tool_load_failed", server=server_name, exc_info=True)
                    continue
                tools.extend(
                    clamp_tool_output(tool, max_chars=settings.researcher_tool_output_max_chars)
                    for tool in server_tools
                )

        if settings.tavily_api_key is not None:
            web_tool: Any = TavilySearch(tavily_api_key=settings.tavily_api_key)
            tools.append(
                clamp_tool_output(web_tool, max_chars=settings.researcher_tool_output_max_chars)
            )
        else:
            log.warning("researcher_tool_unavailable", tool="web", reason="TAVILY_API_KEY not set")

        yield tools
