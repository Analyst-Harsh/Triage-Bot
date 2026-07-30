import type { RiskLevel } from '../lib/riskColors'

export interface PipelineStage {
  id: string
  label: string
  title: string
  description: string
  accent: RiskLevel | 'primary'
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    id: 'planner',
    label: '01 · PLANNER',
    title: 'Classify, and build a plan',
    description:
      'Classifies the issue and builds an investigation plan. Short-circuits spam straight to human-approved close, and checks episodic memory for similar past issues.',
    accent: 'primary',
  },
  {
    id: 'researcher',
    label: '02 · RESEARCHER',
    title: 'Actually investigate',
    description:
      'A tool-calling subgraph that searches the codebase, queries indexed docs, and searches the web — producing typed, grounded findings, not guesses.',
    accent: 'primary',
  },
  {
    id: 'drafter',
    label: '03 · DRAFTER',
    title: 'Write, and verify in a sandbox',
    description:
      'Writes the response. For code fixes, reproduces the bug and verifies a real fix in an isolated, network-locked sandbox before proposing it.',
    accent: 'low',
  },
  {
    id: 'risk-check',
    label: '04 · RISK CHECK',
    title: 'Score the action, not guess',
    description:
      'Every action gets a LOW / MEDIUM / HIGH risk score. Code fixes are hardcoded HIGH by fixed policy — never an LLM judgment call.',
    accent: 'medium',
  },
  {
    id: 'auto-post',
    label: '05 · AUTO-POST / APPROVAL',
    title: 'Act, or ask — checkpointed',
    description:
      'LOW-risk actions post immediately. Anything riskier pauses the run via a checkpointed interrupt() — surviving a restart — until a human approves each action.',
    accent: 'high',
  },
]
