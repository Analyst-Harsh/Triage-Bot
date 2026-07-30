import { ClipboardList, Search, TerminalSquare, Gauge, ShieldCheck } from 'lucide-react'

export const STAGE_ICONS = {
  planner: ClipboardList,
  researcher: Search,
  drafter: TerminalSquare,
  'risk-check': Gauge,
  'auto-post': ShieldCheck,
} as const
