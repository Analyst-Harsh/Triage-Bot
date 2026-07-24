#!/bin/bash
# PostToolUse hook: ruff-only feedback after every Edit/Write to a .py file.
# Type diagnostics are intentionally not run here -- with the pyright-lsp
# plugin installed, real-time type feedback already comes natively from the
# language server, so a redundant subprocess `pyright` run per edit is
# avoided. See AGENTS.md's recommended-plugin section.
set -euo pipefail

FILE_PATH=$(jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0

cd "$CLAUDE_PROJECT_DIR" || exit 0

RUFF_OUT=$(uv run ruff check "$FILE_PATH" 2>&1) && RUFF_STATUS=0 || RUFF_STATUS=$?

if [ "$RUFF_STATUS" -ne 0 ]; then
  jq -n --arg reason "$RUFF_OUT" '{decision: "block", reason: $reason}'
fi

exit 0
