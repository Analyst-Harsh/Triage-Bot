"""Manual verification that OpenAI prompt caching actually engages for the
Drafter's real static prefix (system prompt + sandbox tool schemas) --
addressing community reports of flaky/zero cache hits on `gpt-5.4-nano`
specifically. This is an empirical spot-check, not automated CI: real API
cache behavior can vary run to run in ways the test suite must never depend
on, and this repo does not make live network calls from `uv run pytest`.

Usage:
    uv run python scripts/verify_prompt_caching.py
    uv run python scripts/verify_prompt_caching.py --models gpt-5.4-nano,gpt-5-nano

Requires a real OPENAI_API_KEY, resolved via `config.settings.get_settings()`
(never `os.environ` directly, per this repo's non-negotiable secrets rule).

What it does, per model:
1. Builds the real production static prefix: `prompts.drafter.
   build_drafter_system_prompt` given the real 7 sandbox tool names (from
   `tools.sandbox.build_sandbox_tools` against an in-memory `SandboxHandle`
   -- no live E2B session needed just to read each tool's `.name`), bound
   onto the chat model via `.bind_tools(...)` exactly as
   `AgentSubgraph.build_agent()` binds them.
2. Sends the identical (system prompt + one short fixed human turn) request
   twice via `.ainvoke()` -- OpenAI's cache is keyed by exact-prefix hash, so
   an unchanged prefix on the second call is the one condition expected to
   trigger a hit.
3. Reads `usage_metadata["input_token_details"]` off each returned
   `AIMessage` (langchain-core's provider-neutral projection of OpenAI's own
   `prompt_tokens_details.cached_tokens`) and prints input tokens /
   cache_read / cache_creation for both calls.
4. Prints a verdict: `cache_read > 0` on the second call means caching
   engaged; `0` means either the prefix is under the 1024-token threshold
   (check the printed total first) or this is the documented flakiness --
   rerun before concluding the model doesn't support it.

Interpretation is manual: read the printed numbers, there is no assertion.
"""

import argparse
import asyncio

from github import Github
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from config.settings import get_settings
from llm.config import LLMEndpointConfig
from llm.factory import create_chat_model
from prompts.drafter import build_drafter_system_prompt
from tools.sandbox import SandboxHandle, build_sandbox_tools

_FIXED_USER_TURN = (
    "Draft a comment for a bug report about a NoneType crash on startup, citing src/config.py."
)


async def _probe_model(model_name: str) -> None:
    settings = get_settings()
    if settings.openai_api_key is None:
        raise RuntimeError(
            "OPENAI_API_KEY is not set (via Settings/.env) -- required for this live check."
        )
    # Dummy settings/github_client: build_sandbox_tools only needs each
    # tool's schema/name here, never a live E2B session or GitHub call.
    handle = SandboxHandle(
        settings=settings, github_client=Github(), repo_full_name="octo/repo", ref="main"
    )
    tools = build_sandbox_tools(handle, file_read_max_chars=settings.drafter_file_read_max_chars)
    system_prompt = build_drafter_system_prompt([tool.name for tool in tools])
    model = create_chat_model(
        LLMEndpointConfig(provider="openai", model=model_name, temperature=0.0), settings
    )
    bound = model.bind_tools(tools)
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=_FIXED_USER_TURN),
    ]

    print(f"\n=== {model_name} ===")
    for call_number in (1, 2):
        response = await bound.ainvoke(messages)
        usage = response.usage_metadata or {}
        details = usage.get("input_token_details", {})
        cache_read = details.get("cache_read", 0)
        cache_creation = details.get("cache_creation", 0)
        print(
            f"call {call_number}: input_tokens={usage.get('input_tokens')} "
            f"cache_read={cache_read} cache_creation={cache_creation}"
        )
        if call_number == 2:
            verdict = "CACHE HIT" if cache_read > 0 else "NO CACHE HIT (see module docstring)"
            print(f"verdict: {verdict}")


async def main(models: list[str]) -> None:
    for model_name in models:
        await _probe_model(model_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="gpt-5.4-nano,gpt-5-nano")
    args = parser.parse_args()
    asyncio.run(main(args.models.split(",")))
