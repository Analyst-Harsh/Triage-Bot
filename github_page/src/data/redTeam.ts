export interface RedTeamCase {
  issue: string
  technique: string
  owasp: string
}

export const RED_TEAM_CASES: RedTeamCase[] = [
  { issue: '#12', technique: 'Instruction override', owasp: 'LLM01' },
  { issue: '#13', technique: 'Fake authority / impersonation', owasp: 'LLM01' },
  { issue: '#14', technique: 'Schema manipulation', owasp: 'LLM01' },
  { issue: '#15', technique: 'Delimiter confusion', owasp: 'LLM01' },
  { issue: '#16', technique: 'System-prompt extraction', owasp: 'LLM07' },
  { issue: '#17', technique: 'Tool-misuse bait', owasp: 'LLM06' },
]
