export interface Differentiator {
  id: string
  icon: 'gauge' | 'shieldCheck' | 'activity' | 'flaskConical' | 'history' | 'box'
  title: string
  description: string
}

export const DIFFERENTIATORS: Differentiator[] = [
  {
    id: 'guardrails',
    icon: 'gauge',
    title: 'Guardrails, not vibes',
    description:
      'Hard cost ceilings checked before every LLM/tool call, iteration and tool-call caps, cache-aware cost accounting — a real safety mechanism, not a demo toy.',
  },
  {
    id: 'injection-defense',
    icon: 'shieldCheck',
    title: 'Structural injection defense',
    description:
      'Draft actions are a Pydantic discriminated union — even a fully compromised LLM call cannot execute anything outside that schema. A deterministic scanner runs on every action as a second layer.',
  },
  {
    id: 'observability',
    icon: 'activity',
    title: 'Full observability',
    description:
      'Every run traced end-to-end via OpenTelemetry + Langfuse, nested per-node spans, deterministic trace IDs so a paused, resumed run rejoins the same trace.',
  },
  {
    id: 'eval-driven',
    icon: 'flaskConical',
    title: 'Eval-driven, cross-provider',
    description:
      'Golden cases and LLM-judge rubrics — judged by Anthropic while the agent itself runs on OpenAI, to avoid correlated blind spots.',
  },
  {
    id: 'resume-safe',
    icon: 'history',
    title: 'Resume-safe by construction',
    description:
      'Postgres checkpointing means a paused run awaiting human approval survives a process restart — resuming the exact same graph state.',
  },
  {
    id: 'sandboxed',
    icon: 'box',
    title: 'Sandboxed code execution',
    description:
      'Any code the Drafter runs — bug repro, fix verification — executes in an ephemeral, network-locked sandbox. Never on the host shell.',
  },
]
