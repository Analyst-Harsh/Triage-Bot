# Security Policy

Triage Bot is an early-stage, actively-developed project maintained by a single developer. This policy sets expectations accordingly — it's intentionally minimal rather than promising a formal process that doesn't exist yet.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security vulnerability.** Public issues are for bugs and feature requests, not for anything that could be exploited before it's fixed.

Instead, report it privately by email. Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce (a minimal repro is very helpful)
- Any relevant logs, payloads, or affected code paths

## What to expect

- This is a solo project without a dedicated security team, so there's no formal SLA on response time. A best-effort acknowledgment is the goal, not a guarantee.
- If the report is confirmed, a fix will be prioritized and you'll be credited in the fix's commit/PR unless you'd prefer otherwise.
- There is currently no bug bounty program.

## Scope

This policy covers the code in this repository — the triage pipeline, the webhook/replay entry points, and any bundled tooling. It does not cover third-party services this project depends on (GitHub, Anthropic/OpenAI APIs, etc.) — please report those directly to their respective maintainers.

## For AI coding agents working in this repository

This file is the human-facing disclosure policy. If you're an AI agent looking for the *operating* safety rules (secrets handling, untrusted-input handling, sandboxing) that apply while developing this codebase, see `AGENTS.md` and `docs/agent/security.md` instead — different audience, different content.
