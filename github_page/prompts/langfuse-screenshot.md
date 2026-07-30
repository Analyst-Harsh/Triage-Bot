This asset is a REAL screenshot — never fabricate or mock this one. A fake
observability screenshot on a portfolio site built for precision would
misrepresent the project.

Steps:
1. Open the real Langfuse project for Triage Bot.
2. Pick one representative real trace — ideally showing the full nested span
   tree (Planner -> Researcher -> Drafter -> Risk check) for a single run, since
   that's the clearest "proof of observability" shot.
3. Before capturing, check the trace for anything sensitive: real repo names,
   tokens/API keys, or user data in span inputs, and real cost/billing figures
   you don't want public. Pick a clean trace or redact before use.
4. Capture at a wide viewport (1600px+) so span names/durations stay legible
   once scaled down into a card.
5. Save as github_page/public/assets/langfuse-trace.png (convert to .webp for
   the final build).
6. If no clean, presentable real trace exists yet, fall back to treating this
   section the same way as the dashboard mock (clearly labeled concept/diagram)
   rather than shipping a low-quality or sensitive screenshot.
