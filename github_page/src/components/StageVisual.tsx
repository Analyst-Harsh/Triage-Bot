import { Check, LockKeyhole, Search, X } from 'lucide-react'
import { PIPELINE_STAGES } from '../data/pipeline'

const PLAN_STEPS = ['Classify issue type', 'Check episodic memory', 'Scope investigation']

function PlannerVisual() {
  return (
    <div className="w-full max-w-lg rounded-xl border border-[var(--color-surface-border)] bg-black/30 p-8 text-left lg:max-w-xl">
      <p className="mb-5 font-mono text-base tracking-wide text-[var(--color-text-muted)]">
        INVESTIGATION PLAN
      </p>
      <ul className="space-y-4">
        {PLAN_STEPS.map((step, i) => (
          <li
            key={step}
            className="stage-visual-motion flex items-center gap-3 text-lg text-[var(--color-text)]"
            style={{ animation: `plan-check 0.5s ease ${i * 0.3 + 0.15}s both` }}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--color-risk-low)]">
              <Check size={16} className="text-[var(--color-risk-low)]" />
            </span>
            {step}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ResearcherVisual() {
  const widths = ['70%', '45%', '85%', '55%', '65%']
  return (
    <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-[var(--color-surface-border)] bg-black/30 p-8 text-left lg:max-w-xl">
      <div className="mb-5 flex items-center gap-3">
        <Search size={20} className="text-[var(--color-secondary-to)]" />
        <span className="font-mono text-base text-[var(--color-text-muted)]">
          codebase search
        </span>
      </div>
      <div className="space-y-3">
        {widths.map((w, i) => (
          <div
            key={i}
            className="h-3.5 rounded-full bg-white/10"
            style={{ width: w }}
          />
        ))}
      </div>
      <div
        className="stage-visual-motion pointer-events-none absolute inset-x-8 top-8 h-14 bg-gradient-to-b from-[var(--color-secondary-to)]/0 via-[var(--color-secondary-to)]/25 to-[var(--color-secondary-to)]/0"
        style={{ animation: 'scan-sweep 2.6s ease-in-out infinite' }}
      />
    </div>
  )
}

function DrafterVisual() {
  return (
    <div className="w-full max-w-lg rounded-xl border border-[var(--color-surface-border)] bg-black/30 p-8 text-left font-mono text-lg lg:max-w-xl">
      <div className="mb-4 flex items-center gap-2.5">
        <span className="stage-visual-motion h-3.5 w-3.5 animate-ping rounded-full bg-[var(--color-risk-low)]" />
        <span className="text-base text-[var(--color-text-muted)]">sandbox: running</span>
      </div>
      <p className="text-[var(--color-text-muted)]">$ reproduce_bug()</p>
      <p className="text-[var(--color-text-muted)]">$ apply_fix()</p>
      <p className="text-[var(--color-risk-low)]">
        PASSED 4/4
        <span
          className="stage-visual-motion ml-1 inline-block h-5 w-2.5 translate-y-0.5 bg-[var(--color-risk-low)]"
          style={{ animation: 'blink-caret 1s step-end infinite' }}
        />
      </p>
    </div>
  )
}

function RiskCheckVisual() {
  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-5 rounded-xl border border-[var(--color-surface-border)] bg-black/30 p-8 lg:max-w-xl">
      <p className="self-start font-mono text-base text-[var(--color-text-muted)]">
        RISK SCORE
      </p>
      <svg width="260" height="148" viewBox="0 0 140 80">
        <path
          d="M 10 75 A 60 60 0 0 1 55 17"
          fill="none"
          stroke="var(--color-risk-low)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M 58 15 A 60 60 0 0 1 82 15"
          fill="none"
          stroke="var(--color-risk-medium)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M 85 17 A 60 60 0 0 1 130 75"
          fill="none"
          stroke="var(--color-risk-high)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <g style={{ transformOrigin: '70px 75px', animation: 'gauge-sweep 3.2s ease-in-out infinite' }} className="stage-visual-motion">
          <line x1="70" y1="75" x2="70" y2="25" stroke="var(--color-text)" strokeWidth="3" strokeLinecap="round" />
        </g>
        <circle cx="70" cy="75" r="5" fill="var(--color-text)" />
      </svg>
    </div>
  )
}

function ApprovalVisual() {
  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-6 rounded-xl border border-[var(--color-surface-border)] bg-black/30 p-9 text-center lg:max-w-xl">
      <div className="relative flex h-20 w-20 items-center justify-center">
        <span className="stage-visual-motion absolute inset-0 animate-ping rounded-full bg-[var(--color-primary)]/30" />
        <span className="relative flex h-20 w-20 items-center justify-center rounded-full border border-[var(--color-primary)] bg-black/40">
          <LockKeyhole size={32} className="text-[var(--color-secondary-to)]" />
        </span>
      </div>
      <p className="font-mono text-base text-[var(--color-text-muted)]">
        paused — awaiting approval
      </p>
      <div className="flex gap-3">
        <span className="flex items-center gap-1.5 rounded-full border border-[var(--color-risk-low)]/40 px-4 py-2.5 text-base text-[var(--color-risk-low)]">
          <Check size={18} /> approve
        </span>
        <span className="flex items-center gap-1.5 rounded-full border border-[var(--color-risk-high)]/40 px-4 py-2.5 text-base text-[var(--color-risk-high)]">
          <X size={18} /> reject
        </span>
      </div>
    </div>
  )
}

const VISUALS: Record<string, React.ReactNode> = {
  planner: <PlannerVisual />,
  researcher: <ResearcherVisual />,
  drafter: <DrafterVisual />,
  'risk-check': <RiskCheckVisual />,
  'auto-post': <ApprovalVisual />,
}

export function StageVisual({ activeId }: { activeId: string }) {
  return (
    <div className="relative h-96 w-full overflow-hidden sm:h-[28rem] lg:h-[34rem] xl:h-[38rem]">
      {PIPELINE_STAGES.map((stage) => (
        <div
          key={stage.id}
          className={`absolute inset-0 flex items-center justify-center p-6 transition-opacity duration-500 ${
            stage.id === activeId ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        >
          {VISUALS[stage.id]}
        </div>
      ))}
    </div>
  )
}
