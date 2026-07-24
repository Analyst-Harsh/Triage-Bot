## Summary

<!-- What does this PR do, and why? -->

## Type of change

- [ ] Feature
- [ ] Fix
- [ ] Refactor
- [ ] Docs
- [ ] Test
- [ ] Chore / tooling

## Testing

- [ ] Unit tests added/updated for this change
- [ ] `uv run pytest` passes locally
- [ ] Manually verified (describe below, if applicable)

<!-- How was this tested? Include commands run and their output if relevant. -->

## Quality gate

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run pyright` (strict mode, whole project)
- [ ] No TODOs, swallowed exceptions, or disabled lint/type rules without an inline reason
- [ ] No secrets in the diff or commit messages (`detect-secrets` should already have caught this locally)
- [ ] Docs updated if behavior changed (`AGENTS.md`, `docs/agent/*.md`, or `docs/summary.md`)

## Related issues

Closes #
